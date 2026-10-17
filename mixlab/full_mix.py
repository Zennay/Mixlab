"""Offline full-song MixLab export: track A -> M1 transition -> track B.

Uses the existing validated DSP transition, while keeping the actual
preceding/outgoing and following/incoming song material. A user-provided
manual A/B cue is mandatory. No model, automatic beatmatch, upload, public
HTTP server, musical preference claim, or long in-memory audio buffers.
"""
from __future__ import annotations

import argparse
from array import array
import html
import json
import math
import os
from pathlib import Path
import shutil
import sys
import wave

from .cueprep import ID, _digest, _extract, _identity, _inspect_source, _number, _read_spec, _source_path
from .dsp import render
from .engine import FAMILY_NAMES
from .ingest import MAX_BYTES, MAX_FRAMES, RIGHTS
from .models import Recipe


MAX_MIX_BYTES = 512 * 1024 * 1024
CHUNK_FRAMES = 4096
MIX_NAME = "full-song-mix.wav"
MAX_SONG_MINUTES = 15


def _manual_pair(spec, root, pair_id):
    records, pairs = spec.get("tracks"), spec.get("pairs")
    if not isinstance(records, list) or not 2 <= len(records) <= 20:
        raise ValueError("2..20 permitted full-length tracks required")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 10:
        raise ValueError("1..10 hand-declared pair choices required")
    bank = {}
    partitioned = any(isinstance(item, dict) and "partition" in item for item in records)
    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError("Invalid full-track record")
        tid = rec.get("id")
        if not isinstance(tid, str) or not ID.fullmatch(tid) or tid in bank:
            raise ValueError("Invalid or duplicate track ID")
        if rec.get("rights") not in RIGHTS or not isinstance(rec.get("provenance"), str) or not rec["provenance"].strip():
            raise ValueError("Every track requires permission and source provenance")
        _number(rec.get("bpm"), "manual track BPM", 30, 300)
        if partitioned and rec.get("partition") not in ("development", "evaluation"):
            raise ValueError("All tracks need a partition when any is marked")
        bank[tid] = rec
    matching = [p for p in pairs if isinstance(p, dict) and p.get("id") == pair_id]
    if len(matching) != 1 or not isinstance(pair_id, str) or not ID.fullmatch(pair_id):
        raise ValueError("Select exactly one registered pair ID")
    pair = matching[0]
    a, b = pair.get("a"), pair.get("b")
    if not isinstance(a, str) or not isinstance(b, str) or a == b or a not in bank or b not in bank:
        raise ValueError("Pair needs two distinct registered source tracks")
    left, right = bank[a], bank[b]
    if left["bpm"] != right["bpm"]:
        raise ValueError("Full mix requires equal manual BPM; no tempo stretch yet")
    if partitioned and left["partition"] != right["partition"]:
        raise ValueError("Source tracks cross dataset partitions")
    beats = pair.get("beats", 8)
    if type(beats) is not int or not 1 <= beats <= 64:
        raise ValueError("Manual transition beats must be 1..64")
    audio = []
    for rec in (left, right):
        wav = _source_path(root, rec.get("path"))
        info = _inspect_source(wav, rec.get("sha256"))
        audio.append((wav, info, rec))
    a_wav, a_info, _ = audio[0]
    b_wav, b_info, _ = audio[1]
    if (a_info["rate"], a_info["channels"]) != (b_info["rate"], b_info["channels"]):
        raise ValueError("Songs must use identical PCM16 format; normalize via media_import")
    rate, channels = a_info["rate"], a_info["channels"]
    frames = round(beats * 60 / left["bpm"] * rate)
    if not 2 <= frames <= MAX_FRAMES or 44 + frames * channels * 2 > MAX_BYTES:
        raise ValueError("Transition exceeds established excerpt audio limits")
    cue_a = _number(pair.get("a_start_seconds"), "outgoing manual cue seconds", 0, 900)
    cue_b = _number(pair.get("b_start_seconds"), "incoming manual cue seconds", 0, 900)
    start_a, start_b = round(cue_a * rate), round(cue_b * rate)
    if start_a + frames > a_info["frames"] or start_b + frames > b_info["frames"]:
        raise ValueError("Manual cue extends beyond a declared source song")
    total = start_a + frames + (b_info["frames"] - start_b - frames)
    if not 2 <= total or 44 + total * channels * 2 > MAX_MIX_BYTES:
        raise ValueError("Full-song output would exceed private 512 MiB WAV budget")
    return {"id": pair_id, "a": a, "b": b, "bpm": left["bpm"],
            "beats": beats, "frames": frames, "cue_a": start_a, "cue_b": start_b,
            "rate": rate, "channels": channels, "total": total, "sources": audio}


def _render_chunks(input_path, info, beginning, frames, output, gain):
    """Copy a bounded span from an admitted *full-length* PCM16 WAV.

    The main renderer only admits <=32 MiB excerpts. Full song segments use
    the same PCM format and strict single-descriptor source identity checks,
    but may be as long as 15 minutes.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(input_path, flags)
    with os.fdopen(fd, "rb") as stream:
        if _identity(os.fstat(stream.fileno())) != info["identity"]:
            raise ValueError("Source changed after checksum admission")
        with wave.open(stream, "rb") as reader:
            if (reader.getnchannels(), reader.getsampwidth(),
                    reader.getframerate(), reader.getnframes()) != (
                info["channels"], 2, info["rate"], info["frames"]
            ):
                raise ValueError("Source WAV metadata changed during render")
            reader.setpos(beginning)
            remaining = frames
            channels = info["channels"]
            while remaining:
                count = min(remaining, CHUNK_FRAMES)
                block = reader.readframes(count)
                if len(block) != count * channels * 2:
                    raise ValueError("Full-length PCM source truncated during streaming")
                if gain != 1.0:
                    samples = array("h")
                    samples.frombytes(block)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    for i, sample in enumerate(samples):
                        sample = round(sample * gain)
                        if not -32768 <= sample <= 32767:
                            raise ValueError("Source mix would clip at selected gain")
                        samples[i] = sample
                    if sys.byteorder != "little":
                        samples.byteswap()
                    block = samples.tobytes()
                output.writeframesraw(block)
                remaining -= count
        if (_identity(os.fstat(stream.fileno())) != info["identity"]
                or _identity(input_path.lstat()) != info["identity"]):
            raise ValueError("Source was changed or replaced while streaming")


def _render_transition(stream, source, expected_sha, rate, channels, frames):
    """Insert the exact already-rendered DSP transition without reprocessing."""
    if _digest(source) != expected_sha:
        raise ValueError("Transition audio changed after DSP rendering")
    with wave.open(str(source), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) != (
            channels, 2, rate, frames
        ):
            raise ValueError("Transition WAV mismatches source timing/channel format")
        left = frames
        while left:
            count = min(CHUNK_FRAMES, left)
            block = wav.readframes(count)
            if len(block) != count * channels * 2:
                raise ValueError("Intermediate transition truncated during assembly")
            stream.writeframesraw(block)
            left -= count
    if _digest(source) != expected_sha:
        raise ValueError("Transition changed during final assembly")


def _private_page(output, *, pair, family, gain_db):
    safe_id, safe_family = html.escape(pair["id"]), html.escape(family)
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; base-uri 'none'">
<title>MixLab / Full Song Studio</title><style>
:root{font-family:system-ui;background:#101118;color:#f5f4ff;color-scheme:dark}
main{max-width:860px;margin:8vh auto;padding:0 24px}h1{font-size:clamp(42px,8vw,76px);letter-spacing:-.07em}
p{line-height:1.6;color:#bbc0d6}.box{background:#212435;border:1px solid #444861;border-radius:20px;padding:26px}
audio{width:100%}a{color:#cebaff}.tag{color:#bfaaef;text-transform:uppercase;letter-spacing:.15em}
</style></head><body><main><p class="tag">MIXLAB / PRIVATE FULL SONG</p>
<h1>One complete<br>transition.</h1><div class="box"><p>Pair """+safe_id+""" · """+safe_family+""" · consistent gain """+str(gain_db)+""" dB</p>
<audio controls preload="metadata" src="full-song-mix.wav"></audio><p><a href="full-song-mix.wav" download="mixlab-full-song-mix.wav">
Download complete WAV</a></p></div>
<p>Song A plays to the manually approved cue, an actual M1-rendered
transition follows, then song B plays to its end. Nothing was uploaded.
This is a local creative mix, not licensed distribution or blind listening proof.</p></main></body></html>"""
    page_path = output / "index.html"
    page_path.write_text(page, encoding="utf-8")
    page_path.chmod(0o600)


def full_mix(source_manifest, destination, *, pair_id, family="bass_swap", gain_db=-9):
    if family not in FAMILY_NAMES:
        raise ValueError("Choose an existing M1 DSP transition family")
    gain_db = _number(gain_db, "common gain", -24, 0)
    if not isinstance(pair_id, str) or not ID.fullmatch(pair_id):
        raise ValueError("Select a registered pair ID")
    source_manifest = Path(source_manifest).absolute()
    spec = _read_spec(source_manifest)
    source_root = source_manifest.parent.resolve(strict=True)
    selection = _manual_pair(spec, source_root, pair_id)
    destination = Path(destination).absolute()
    if (destination.exists() or destination.is_symlink()
            or destination == source_root or destination.is_relative_to(source_root)
            or source_root.is_relative_to(destination)
            or not destination.parent.is_dir()):
        raise ValueError("Use a new private output directory outside the source library")
    for ancestor in (destination, *destination.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Never render private full songs inside Git")
    destination.mkdir(mode=0o700)
    try:
        workspace = destination / ".render"
        workspace.mkdir(mode=0o700)
        frames, rate, channels = selection["frames"], selection["rate"], selection["channels"]
        (a_path, a_info, _), (b_path, b_info, _) = selection["sources"]
        first, second = workspace / "a.wav", workspace / "b.wav"
        _extract(a_path, first, selection["cue_a"], frames, a_info)
        _extract(b_path, second, selection["cue_b"], frames, b_info)
        gain = 10 ** (gain_db / 20)
        recipe = Recipe(family=family, bpm=selection["bpm"], beats=selection["beats"],
                        a_bpm=selection["bpm"], b_bpm=selection["bpm"],
                        a_start=0, b_start=0, gain_db=gain_db)
        tmp_transition = workspace / "transition.wav"
        dsp_receipt = render(first, second, tmp_transition, recipe)
        output = destination / MIX_NAME
        with output.open("xb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            with wave.open(handle, "wb") as writer:
                writer.setparams((channels, 2, rate, selection["total"], "NONE", "not compressed"))
                # 1. Song A from the beginning up to the outgoing cue.
                _render_chunks(a_path, a_info, 0, selection["cue_a"], writer, gain)
                # 2. Exact established M1 DSP transition (sample gain matched).
                _render_transition(writer, tmp_transition, dsp_receipt["output_sha256"],
                                   rate, channels, frames)
                # 3. Song B continues right after its mixed-in cue.
                suffix_start = selection["cue_b"] + frames
                _render_chunks(b_path, b_info, suffix_start,
                               b_info["frames"] - suffix_start, writer, gain)
        if output.stat().st_size > MAX_MIX_BYTES:
            raise ValueError("Completed full mix exceeds 512 MiB")
        if (_digest(a_path) != a_info["sha256"] or _digest(b_path) != b_info["sha256"]):
            raise ValueError("Original WAV content changed during export")
        receipt = {
            "schema_version": 1, "kind": "private-two-song-playthrough",
            "pair_id": pair_id, "transition_family": family,
            "gain_db": gain_db, "manual_bpm": selection["bpm"],
            "sample_rate": rate, "channels": channels,
            "total_frames": selection["total"], "duration_seconds": round(selection["total"] / rate, 6),
            "a_track_id": selection["a"], "b_track_id": selection["b"],
            "a_pretransition_frames": selection["cue_a"],
            "transition_frames": frames,
            "b_posttransition_frames": b_info["frames"]-selection["cue_b"]-frames,
            "source_manifest_sha256": _digest(source_manifest),
            "source_audio_sha256": [a_info["sha256"], b_info["sha256"]],
            "transition_audio_sha256": dsp_receipt["output_sha256"],
            "full_mix_sha256": _digest(output),
            "boundaries": ["user-provided manual equal BPM and cuepoints",
                           "local audio only; sharing/distribution requires permissions",
                           "not independently measured DJ quality or listener preference"]
        }
        receipt_path = destination / "full-mix-receipt.private.json"
        with receipt_path.open("xb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write((json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        _private_page(destination, pair=selection, family=family, gain_db=gain_db)
        shutil.rmtree(workspace)
        return output
    except BaseException:
        shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Render one complete private 2-track DJ mix with an actual M1 transition")
    parser.add_argument("source_manifest", help="Permitted full-length PCM16 source manifest")
    parser.add_argument("private_output", help="New private output directory, not in Git")
    parser.add_argument("--pair", required=True, help="One existing pair in source manifest")
    parser.add_argument("--family", choices=FAMILY_NAMES, default="bass_swap")
    parser.add_argument("--gain-db", type=float, default=-9.)
    args = parser.parse_args()
    try:
        output = full_mix(args.source_manifest, args.private_output,
                          pair_id=args.pair, family=args.family, gain_db=args.gain_db)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, "MixLab full song: " + str(exc) + "\n")
    print(json.dumps({"ready": True, "private_wav": str(output),
                      "local_preview": str(output.parent / "index.html"),
                      "song_count": 2, "audio_uploaded": False}))


if __name__ == "__main__":
    main()
