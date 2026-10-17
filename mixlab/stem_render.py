"""Offline transitions from *user-supplied* instrumental and vocal WAV stems.

Stems are not generated or inferred. Audio must be legally processed and
manually aligned by the user. No GPU, remote model, service or upload.
"""
from __future__ import annotations

from array import array
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import wave

from .cueprep import ID, SHA, _number, _read_spec, _source_path
from .dsp import Meter
from .ingest import MAX_FRAMES, RIGHTS, digest, inspect_wav_and_digest, pcm_blocks


STEMS = ("a_instrumental", "a_vocals", "b_instrumental", "b_vocals")
FAMILIES = ("vocal_handoff", "instrumental_bridge", "drop_swap")
CHUNK_FRAMES = 4096


def _smooth(value):
    x = min(1., max(0., value))
    return x*x*(3.-2.*x)


def _weights(family, progress):
    """Four gains: outgoing instrumental/vocals, incoming instrumental/vocals."""
    t = progress
    if family == "vocal_handoff":
        return (math.cos(t * math.pi / 2),
                1 - _smooth((t - .38) / .42),
                math.sin(t * math.pi / 2),
                _smooth((t - .67) / .33))
    if family == "instrumental_bridge":
        return (math.cos(t * math.pi / 2),
                1 - _smooth(t / .26),
                math.sin(t * math.pi / 2),
                _smooth((t - .74) / .26))
    if family == "drop_swap":
        switch = _smooth((t - .48) / .04)
        return (1 - switch, 1 - _smooth((t - .45) / .07),
                switch, _smooth((t - .52) / .07))
    raise ValueError("Unsupported stem transition family")


def _admit_stems(spec_path):
    spec = _read_spec(spec_path)
    pair_id = spec.get("pair_id")
    if not isinstance(pair_id, str) or not ID.fullmatch(pair_id):
        raise ValueError("A safe pair_id is required")
    rights = spec.get("rights")
    if rights not in RIGHTS or not isinstance(spec.get("provenance"), str) or not spec["provenance"].strip():
        raise ValueError("Explicit source-stem rights and provenance required")
    bpm = _number(spec.get("bpm"), "manual pair BPM", 30, 300)
    beats = spec.get("beats", 16)
    if type(beats) is not int or not 1 <= beats <= 64:
        raise ValueError("Stem transition beats must be 1..64")
    start_a = _number(spec.get("a_start_seconds"), "manual outgoing cue seconds", 0, 250)
    start_b = _number(spec.get("b_start_seconds"), "manual incoming cue seconds", 0, 250)
    stems = spec.get("stems")
    if not isinstance(stems, dict) or set(stems) != set(STEMS):
        raise ValueError("Exactly four declared instrumental/vocal WAV stems are required")
    sources = {}
    info_first = None
    used_paths = set()
    count = None
    for role in STEMS:
        record = stems[role]
        if not isinstance(record, dict):
            raise ValueError("Each declared stem must be an object")
        expected = record.get("sha256")
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise ValueError("Every source stem needs a pinned SHA-256")
        path = _source_path(spec_path.parent, record.get("path"))
        if path in used_paths:
            raise ValueError("Each stem role needs an independently declared WAV file")
        used_paths.add(path)
        info, sha = inspect_wav_and_digest(path)
        if sha != expected:
            raise ValueError("Source stem checksum does not match declaration")
        if info_first is None:
            info_first = (info["sample_rate"], info["channels"])
            count = round(beats * 60 / bpm * info["sample_rate"])
            if not 2 <= count <= MAX_FRAMES:
                raise ValueError("Stem render exceeds canonical frame limit")
        elif (info["sample_rate"], info["channels"]) != info_first:
            raise ValueError("All four stems must share sample rate and channel count")
        start = round((start_a if role.startswith("a_") else start_b) * info["sample_rate"])
        if start + count > info["frame_count"]:
            raise ValueError("Source stem too short for requested manual cue and beats")
        sources[role] = {"path": path, "sha256": expected, "start": start}
    return spec, sources, count, info_first


def _render_one(sources, out, frames, rate, channels, family, gain_db):
    """Bounded sample-by-sample mix; publish WAV only after all sources finish."""
    gain = 10 ** (gain_db / 20)
    meter = Meter(channels)
    fd, tmp = tempfile.mkstemp(prefix=".stem-part-", suffix=".wav", dir=out.parent)
    os.close(fd)
    try:
        with wave.open(tmp, "wb") as destination:
            destination.setparams((channels, 2, rate, frames, "NONE", "not compressed"))
            generators = [pcm_blocks(sources[role]["path"], sources[role]["start"],
                                     frames, CHUNK_FRAMES) for role in STEMS]
            position = 0
            for pieces in zip(*generators):
                if any(len(block) != len(pieces[0]) for block in pieces):
                    raise ValueError("Source stems changed during rendering")
                result = array("h")
                for index in range(0, len(pieces[0]), channels):
                    progress = position / (frames - 1)
                    weights = _weights(family, progress)
                    for channel in range(channels):
                        value = gain * sum(
                            weights[role] * pieces[role][index + channel] / 32768
                            for role in range(len(STEMS)))
                        # No hidden clipping or auto limiter: reject instead.
                        if not -1. <= value <= 32767 / 32768:
                            raise ValueError("Stem transition would clip; lower --gain-db")
                        meter.add((value,)) if channels == 1 else None
                        result.append(round(value * 32768))
                    if channels == 2:
                        meter.add(tuple(result[-channels + c] / 32768 for c in range(channels)))
                    position += 1
                if sys.byteorder != "little":
                    result.byteswap()
                destination.writeframesraw(result.tobytes())
            if position != frames:
                raise ValueError("Input stems changed during render")
        for record in sources.values():
            if digest(record["path"]) != record["sha256"]:
                raise ValueError("Stem input changed while rendering")
        os.link(tmp, out)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"frames": frames, "sample_rate": rate, "channels": channels,
            "family": family, "gain_db": gain_db,
            "output_sha256": digest(out), "metrics": meter.result()}


def _write_browser(root, pair_id, records):
    sections = []
    for item in records:
        family = item["family"]
        name = html.escape(family.replace("_", " ").title())
        relative = html.escape(item["relative_path"], quote=True)
        sections.append('<article class="option"><h2>' + name + '</h2>' +
                        '<audio controls preload="none" src="' + relative +
                        '"></audio><p><a download="' + family +
                        '.wav" href="' + relative + '">Download this WAV</a></p></article>')
    safe_pair = html.escape(pair_id)
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>MixLab Stems — Creative Studio</title>
<style>
body{background:#0d1018;color:#f3f4fa;font:16px system-ui;max-width:1000px;margin:auto;
padding:46px 22px}h1{font-size:clamp(36px,7vw,68px);letter-spacing:-.06em}
small{color:#b9a3f7;letter-spacing:.15em}p{line-height:1.65;color:#b6c0d2}
.option{background:#222635;padding:26px;border:1px solid #464857;border-radius:18px;
margin:20px 0}audio{width:100%}a{color:#cbb9ff}
</style><main><small>MIXLAB / OFFLINE STEM STUDIO</small>
<h1>Vocal + instrumental<br>transitions.</h1>
<p>Manual stems for pair ''' + safe_pair + '''. Local private creative audition only:
not automatic source separation, musical key analysis, or a blind quality study.</p>
''' + "".join(sections) + '''
<p>Original stems, permissions and answer keys remain private. No analytics,
streaming services, external dependencies or uploads.</p></main></html>'''
    path = root / "index.html"
    path.write_text(page, encoding="utf-8")
    path.chmod(0o600)


def render_stem_studio(manifest, output, *, gain_db=-12.):
    gain_db = _number(gain_db, "stem mix gain in dB", -30, -6)
    manifest = Path(manifest).absolute()
    spec, sources, frames, (rate, channels) = _admit_stems(manifest)
    root = Path(output).absolute()
    if root.exists() or root.is_symlink() or root.is_relative_to(manifest.parent):
        raise ValueError("Use a new private output directory outside the source stems")
    if not root.parent.is_dir():
        raise ValueError("Output parent must already exist")
    for parent in (root, *root.parents):
        if (parent / ".git").exists():
            raise ValueError("Stem audio cannot be generated inside Git")
    root.mkdir(mode=0o700)
    try:
        records = []
        for family in FAMILIES:
            target = root / (family + ".wav")
            metrics = _render_one(sources, target, frames, rate, channels, family, gain_db)
            target.chmod(0o600)
            records.append({"family": family, "relative_path": target.name,
                            "sha256": metrics["output_sha256"],
                            "frames": frames, "sample_rate": rate,
                            "channels": channels, "metrics": metrics["metrics"]})
        private = {"schema_version": 1, "kind": "manual-stem-transition-studio",
                   "pair_id": spec["pair_id"], "source_manifest_sha256": digest(manifest),
                   "rights": spec["rights"], "output_count": len(records),
                   "source_declaration": "four externally provided vocal/instrumental WAV stems",
                   "gain_db": gain_db, "renders": records,
                   "limitations": ["no automatic stem separation or time stretching",
                                   "manual alignment required", "not listener preference proof"]}
        receipt = root / "studio-receipt.private.json"
        receipt.write_text(json.dumps(private, indent=2, sort_keys=True, allow_nan=False) + "\n")
        receipt.chmod(0o600)
        _write_browser(root, spec["pair_id"], records)
        return root / "index.html"
    except BaseException:
        shutil.rmtree(root)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Render vocal/instrumental transitions from four private, user-provided stems")
    parser.add_argument("source_manifest")
    parser.add_argument("private_studio_directory")
    parser.add_argument("--gain-db", type=float, default=-12.)
    args = parser.parse_args()
    try:
        result = render_stem_studio(args.source_manifest,
                                    args.private_studio_directory, gain_db=args.gain_db)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"MixLab stems: {exc}\n")
    print(json.dumps({"private_studio": str(result), "family_count": len(FAMILIES),
                      "source_separation_performed": False,
                      "ready_for_private_creative_audition": True}))


if __name__ == "__main__":
    main()
