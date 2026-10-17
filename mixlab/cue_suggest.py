"""Bounded local cue suggestions aligned to *declared* downbeats and tempo.

Heuristic RMS energy proposals only. No automatic beat/phrase, harmonic,
lyric or musical-quality assertion is made. A DJ must approve every cue.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import wave

from .cueprep import (_inspect_source, _number, _read_spec, _source_path,
                      _identity, MAX_TRACK_SECONDS)
from .ingest import digest

HOP_SECONDS = .25
MAX_OUTPUT_BYTES = 1024 * 1024


def _db(power):
    return max(-120.0, 10.0 * math.log10(max(power, 1e-12)))


def _rms_envelope(path, info):
    """Streaming sampled-frame RMS, independent of stereo polarity.

    About 4,000 decoded sample frames/s are inspected at 0.25s resolution.
    This cheap energy proxy is not integrated loudness (LUFS) or a phrase
    classifier. Data and metadata stay in local memory only.
    """
    rate, channels = info["rate"], info["channels"]
    chunk_frames = max(1, round(rate * HOP_SECONDS))
    sample_stride = max(1, rate // 4000)
    powers = []
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        if _identity(os.fstat(handle.fileno())) != info["identity"]:
            raise ValueError("Full-track source changed after checksum admission")
        with wave.open(handle, "rb") as audio:
            if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth(),
                audio.getnframes()) != (channels, rate, 2, info["frames"]):
                raise ValueError("Full-track format changed before analysis")
            remaining = info["frames"]
            while remaining:
                n = min(remaining, chunk_frames)
                raw = audio.readframes(n)
                if len(raw) != n * channels * 2:
                    raise ValueError("Truncated PCM while estimating local energy")
                samples = array("h")
                samples.frombytes(raw)
                if sys.byteorder != "little":
                    samples.byteswap()
                energy = 0
                count = 0
                for pos in range(0, len(samples), sample_stride * channels):
                    for channel in range(channels):
                        value = samples[pos + channel]
                        energy += value * value
                        count += 1
                powers.append((energy / count) / (32768.0 * 32768.0))
                remaining -= n
        if (_identity(os.fstat(handle.fileno())) != info["identity"]
                or _identity(path.lstat()) != info["identity"]):
            raise ValueError("Full-track source changed during energy analysis")
    return powers, chunk_frames / rate


def _excerpt_features(powers, step, start, duration):
    begin = round(start / step)
    end = min(len(powers), round((start + duration) / step))
    local = powers[begin:end]
    if len(local) < 4:
        return None
    quarter = max(1, len(local) // 4)
    initial = statistics.mean(local[:quarter])
    final = statistics.mean(local[-quarter:])
    mean = statistics.mean(local)
    silence = sum(p < 10 ** (-45 / 10) for p in local) / len(local)
    change = _db(final) - _db(initial)
    return {"start_rms_dbfs": round(_db(initial), 2),
            "end_rms_dbfs": round(_db(final), 2),
            "mean_rms_dbfs": round(_db(mean), 2),
            "rms_ramp_db": round(change, 2),
            "silence_fraction": round(silence, 4),
            "start_db_unrounded": _db(initial),
            "end_db_unrounded": _db(final),
            "change_db_unrounded": change}


def _rank_windows(powers, step, *, rate, frames, bpm, anchor, beats, phrase_bars, max_cues):
    duration = frames / rate
    excerpt = beats * 60 / bpm
    period = phrase_bars * 4 * 60 / bpm
    proposals = {"entry": [], "exit": []}
    position = 0
    # Every proposed anchor is on the MANUALLY declared phrase grid.
    # "8 bars" is a convention from the user, not an automatically inferred
    # phrase boundary. Never label these as detected musical sections.
    while anchor + position * period + excerpt <= duration:
        start = anchor + position * period
        metrics = _excerpt_features(powers, step, start, excerpt)
        if metrics and metrics["silence_fraction"] < .8:
            change = metrics.pop("change_db_unrounded")
            first = metrics.pop("start_db_unrounded")
            final = metrics.pop("end_db_unrounded")
            for role, score in (
                ("entry", .8 * change + .25 * max(0.0, -12.0 - first)),
                ("exit", -.8 * change + .10 * max(0.0, first + 25.0))
            ):
                score -= metrics["silence_fraction"] * 25
                proposals[role].append({
                    "start_seconds": round(start, 6),
                    "start_frame": round(start * rate),
                    "duration_seconds": round(excerpt, 6),
                    "role": role,
                    "score_heuristic": round(score, 3),
                    "basis": "sampled-RMS + user-declared phrase grid",
                    **metrics
                })
        position += 1
    for role, entries in proposals.items():
        entries.sort(key=lambda r: (-r["score_heuristic"], r["start_frame"]))
        proposals[role] = entries[:max_cues]
    return proposals


def suggest(spec_path, output_path, *, track_id=None, beats=16, phrase_bars=8, max_cues=5):
    """Produce private path-free manually aligned entry/exit suggestions."""
    if type(beats) is not int or not 1 <= beats <= 64:
        raise ValueError("beats must be an integer 1..64")
    if phrase_bars not in (4, 8, 16) or type(phrase_bars) is not int:
        raise ValueError("phrase-bars must be 4, 8 or 16")
    if type(max_cues) is not int or not 1 <= max_cues <= 8:
        raise ValueError("max-cues must be 1..8")
    spec_path = Path(spec_path).absolute()
    spec = _read_spec(spec_path)
    root = spec_path.parent.resolve(strict=True)
    records = spec.get("tracks")
    if not isinstance(records, list) or not 2 <= len(records) <= 20:
        raise ValueError("Source spec needs 2..20 tracks")
    if track_id is not None and (not isinstance(track_id, str) or not track_id):
        raise ValueError("Invalid track filter")
    seen, proposals = set(), []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Source track must be an object")
        tid = record.get("id")
        if not isinstance(tid, str) or not tid or tid in seen:
            raise ValueError("Duplicate or invalid source track identifier")
        seen.add(tid)
        if track_id is not None and tid != track_id:
            continue
        if record.get("rights") not in ("synthetic", "licensed", "user-permitted", "public-domain"):
            raise ValueError("Missing declared source permission")
        if not isinstance(record.get("provenance"), str) or not record["provenance"].strip():
            raise ValueError("Source provenance required")
        bpm = _number(record.get("bpm"), "manual BPM", 30, 300)
        path = _source_path(root, record.get("path"))
        info = _inspect_source(path, record.get("sha256"))
        anchor = _number(record.get("first_downbeat_seconds"), "manually verified first downbeat", 0, MAX_TRACK_SECONDS)
        if anchor >= info["frames"] / info["rate"]:
            raise ValueError("Manual first downbeat is outside WAV duration")
        powers, step = _rms_envelope(path, info)
        ranked = _rank_windows(powers, step, rate=info["rate"], frames=info["frames"],
                               bpm=bpm, anchor=anchor, beats=beats,
                               phrase_bars=phrase_bars, max_cues=max_cues)
        proposals.append({"track_id": tid, "full_track_sha256": info["sha256"],
                          "declared_bpm": bpm,
                          "declared_first_downbeat_seconds": anchor,
                          "entry": ranked["entry"], "exit": ranked["exit"]})
    if track_id is not None and len(proposals) != 1:
        raise ValueError("Requested source track is missing")
    if not proposals:
        raise ValueError("No eligible source tracks")
    payload = {"schema_version": 1, "kind": "heuristic-manual-grid-cue-suggestions",
               "source_manifest_sha256": digest(spec_path),
               "analysis": "channel-energy sampled at ~4k frames/s, hop 250ms",
               "phrase_grid_source": "manual first downbeat + declared BPM + fixed bar count",
               "beats_per_cue": beats, "bars_per_assumed_phrase": phrase_bars,
               "warnings": ["suggestions are not musical phrase detections",
                            "manual DJ approval required before setting pair start_seconds",
                            "not integrated loudness or harmonic analysis"],
               "tracks": proposals}
    raw = (json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("Suggestion file exceeds 1 MiB")
    destination = Path(output_path).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir() or destination.suffix != ".json":
        raise ValueError("Provide a new local .json output path")
    for ancestor in (destination, *destination.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Keep private cue suggestions outside Git checkouts")
    try:
        with destination.open("xb") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(raw)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return len(proposals)


def main():
    parser = argparse.ArgumentParser(description="Suggest manual-grid entry/exit cues on local full-length PCM16")
    parser.add_argument("source_manifest", help="Existing private cueprep source JSON")
    parser.add_argument("output_json", help="New private output .json")
    parser.add_argument("--track", help="Only this source track ID")
    parser.add_argument("--beats", type=int, default=16)
    parser.add_argument("--phrase-bars", type=int, default=8)
    parser.add_argument("--max-cues", type=int, default=5)
    args = parser.parse_args()
    try:
        total = suggest(args.source_manifest, args.output_json, track_id=args.track,
                        beats=args.beats, phrase_bars=args.phrase_bars, max_cues=args.max_cues)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab cues: {exc}\n")
    print(json.dumps({"tracks_analyzed": total,
                      "status": "manual-review-required",
                      "output": str(Path(args.output_json).absolute())}))


if __name__ == "__main__":
    main()
