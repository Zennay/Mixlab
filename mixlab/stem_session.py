"""Turn private full-length WAV stems into an actual offline stem-transition Studio.

No model inference or source separation: the user supplies independent vocal
and instrumental files. Mono sources are upmixed to stereo with sample-exact
duplication, not silently reinterpreted as different musical material.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import wave

from .cueprep import (
    ID, _digest, _extract, _identity, _inspect_source, _number, _source_path,
)
from .ingest import MAX_BYTES, MAX_FRAMES, RIGHTS
from .stem_render import STEMS, render_stem_studio

MAX_SOURCE_STEMS = 4
BLOCK_FRAMES = 4096


def _upmix_excerpt(source, target, start, frames, info):
    """Read bounded mono PCM16 from its admitted fd and duplicate to L/R."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(source, flags)
    with os.fdopen(fd, "rb") as stream:
        if _identity(os.fstat(stream.fileno())) != info["identity"]:
            raise ValueError("Source stem changed after admission")
        with wave.open(stream, "rb") as reader:
            if (reader.getnchannels(), reader.getframerate(), reader.getsampwidth(),
                    reader.getnframes()) != (1, info["rate"], 2, info["frames"]):
                raise ValueError("Source stem format changed")
            reader.setpos(start)
            with target.open("xb") as out:
                os.fchmod(out.fileno(), 0o600)
                with wave.open(out, "wb") as writer:
                    writer.setparams((2, 2, info["rate"], frames, "NONE", "not compressed"))
                    remaining = frames
                    while remaining:
                        request = min(remaining, BLOCK_FRAMES)
                        raw = reader.readframes(request)
                        if len(raw) != request * 2:
                            raise ValueError("Full-length mono stem truncated during extraction")
                        original = array("h")
                        original.frombytes(raw)
                        if sys.byteorder != "little":
                            original.byteswap()
                        doubled = array("h")
                        for sample in original:
                            doubled.extend((sample, sample))
                        if sys.byteorder != "little":
                            doubled.byteswap()
                        writer.writeframesraw(doubled.tobytes())
                        remaining -= request
        if (_identity(os.fstat(stream.fileno())) != info["identity"]
                or _identity(source.lstat()) != info["identity"]):
            raise ValueError("Source stem changed during mono/stereo conversion")


def _new_workspace(output, library):
    output = Path(output).absolute()
    library = Path(library).resolve(strict=True)
    if (output.exists() or output.is_symlink() or output == library
            or output.is_relative_to(library) or library.is_relative_to(output)
            or not output.parent.is_dir()):
        raise ValueError("Choose a new private workspace outside the input stem directory")
    for parent in (output, *output.parents):
        if (parent / ".git").exists():
            raise ValueError("Keep generated stem music outside any source repository")
    output.mkdir(mode=0o700)
    return output


def _source_spec(library, sources, rights, provenance, pair_id, bpm, beats, start_a, start_b):
    if rights not in RIGHTS:
        raise ValueError("Explicit legal audio-processing permission declaration required")
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 600:
        raise ValueError("Nonempty source-stem provenance required")
    if not isinstance(pair_id, str) or not ID.fullmatch(pair_id):
        raise ValueError("Invalid stem pair ID")
    bpm = _number(bpm, "manual BPM", 30, 300)
    start_a = _number(start_a, "outgoing cue seconds", 0, 900)
    start_b = _number(start_b, "incoming cue seconds", 0, 900)
    if type(beats) is not int or not 1 <= beats <= 64:
        raise ValueError("Transition must have 1..64 beats")
    if not isinstance(sources, dict) or set(sources) != set(STEMS):
        raise ValueError("Exactly four vocal/instrumental stem paths are required")

    seen = set()
    prepared = {}
    rate = None
    for role in STEMS:
        source = _source_path(library, sources[role])
        if source in seen:
            raise ValueError("Each stem role needs an independent WAV recording")
        seen.add(source)
        # The existing full-length validator also authenticates file format,
        # size, duration and changes against an open descriptor.
        checksum = _digest(source)
        info = _inspect_source(source, checksum)
        if rate is None:
            rate = info["rate"]
        elif rate != info["rate"]:
            raise ValueError("Stem sources need the same sample rate; no hidden time stretching")
        prepared[role] = {"source": source, "sha256": checksum, "info": info}
    count = round(beats * 60 / bpm * rate)
    if not 2 <= count <= MAX_FRAMES or 44 + 4 * count > MAX_BYTES:
        raise ValueError("Selected stem transition is outside the canonical PCM16 budget")
    for role, entry in prepared.items():
        info = entry["info"]
        start = round((start_a if role.startswith("a_") else start_b) * rate)
        if start + count > info["frames"]:
            raise ValueError("Stem cue extends beyond one of the full-length recordings")
        entry["start_frame"] = start
    return prepared, rate, count, dict(pair_id=pair_id, rights=rights,
        provenance=provenance, bpm=bpm, beats=beats, start_a=start_a,
        start_b=start_b)


def create_stem_session(library, output, *, a_instrumental, a_vocals,
                        b_instrumental, b_vocals, pair_id, bpm, beats,
                        a_start, b_start, rights, provenance, gain_db=-12):
    """Generate cropped stereo stems and render three true stem-aware WAV styles."""
    lexical_library = Path(library).absolute()
    if lexical_library.is_symlink():
        raise ValueError("Private stem library must not be a symlink")
    library = lexical_library.resolve(strict=True)
    if not library.is_dir():
        raise ValueError("Private stem library must be a directory")
    fields = dict(a_instrumental=a_instrumental, a_vocals=a_vocals,
                  b_instrumental=b_instrumental, b_vocals=b_vocals)
    prepared, rate, frames, meta = _source_spec(
        library, fields, rights, provenance, pair_id, bpm, beats, a_start, b_start)
    # Existing stem renderer bounds manual common gain (-30..-6 dB).
    gain_db = _number(gain_db, "gain dB", -30, -6)
    root = _new_workspace(output, library)
    try:
        sources = root / "sources"
        sources.mkdir(mode=0o700)
        stems = {}
        originals = []
        for role, entry in prepared.items():
            filename = role + ".wav"
            dest = sources / filename
            info = entry["info"]
            if info["channels"] == 1:
                _upmix_excerpt(entry["source"], dest, entry["start_frame"], frames, info)
            else:
                _extract(entry["source"], dest, entry["start_frame"], frames, info)
                dest.chmod(0o600)
            if _digest(entry["source"]) != entry["sha256"]:
                raise ValueError("Original source stem mutated during session preparation")
            sha = _digest(dest)
            stems[role] = {"path": filename, "sha256": sha}
            originals.append({"role": role, "source_sha256": entry["sha256"],
                              "excerpt_sha256": sha,
                              "manual_start_frame": entry["start_frame"],
                              "source_channels": info["channels"],
                              "normalized_channels": 2})
        source_manifest = {
            "schema_version": 1, "pair_id": meta["pair_id"],
            "rights": meta["rights"], "provenance": meta["provenance"],
            "bpm": meta["bpm"], "beats": meta["beats"],
            "a_start_seconds": 0, "b_start_seconds": 0,
            "stems": stems
        }
        manifest = sources / "stem-manifest.json"
        with manifest.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write((json.dumps(source_manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        # Reuse the merged, canonical stem renderer for audio and local studio.
        result = render_stem_studio(manifest, root / "studio", gain_db=gain_db)
        summary = {
            "schema_version": 1, "kind": "manual-full-track-stem-session",
            "pair_id": meta["pair_id"], "bpm": meta["bpm"], "beats": meta["beats"],
            "manual_cue_seconds": {"a": meta["start_a"], "b": meta["start_b"]},
            "sample_rate": rate, "channels": 2, "frames_per_stem": frames,
            "original_sources": originals, "gain_db": gain_db,
            "render_receipt_sha256": _digest(root / "studio" / "studio-receipt.private.json"),
            "manifest_sha256": _digest(manifest),
            "limitations": ["source stems must already be separately available",
                            "no automatic separation/beat/key analysis",
                            "no general human preference claim"]
        }
        receipt = root / "session-receipt.private.json"
        with receipt.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write((json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        return result
    except BaseException:
        # The session directory was guaranteed not to exist beforehand.
        # Source stems, existing sessions and user recordings are untouched.
        shutil.rmtree(root)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Render true stereo vocal/instrumental transitions from full-length user-supplied stems")
    parser.add_argument("source_directory", help="Private folder containing the original four WAV stems")
    parser.add_argument("destination", help="New private session directory outside source folder")
    for role in STEMS:
        parser.add_argument("--" + role.replace("_", "-"), required=True,
                            help="Relative PCM16 WAV file inside source_directory")
    parser.add_argument("--pair-id", default="pair-001")
    parser.add_argument("--bpm", type=float, required=True,
                        help="Human-verified equal BPM for both source tracks")
    parser.add_argument("--beats", type=int, default=16)
    parser.add_argument("--a-start", type=float, required=True)
    parser.add_argument("--b-start", type=float, required=True)
    parser.add_argument("--gain-db", type=float, default=-12.0)
    parser.add_argument("--rights", required=True,
                        choices=sorted(RIGHTS))
    parser.add_argument("--provenance", required=True,
                        help="Actual source/permission declaration, not inferred")
    args = parser.parse_args()
    try:
        index = create_stem_session(
            args.source_directory, args.destination,
            a_instrumental=args.a_instrumental, a_vocals=args.a_vocals,
            b_instrumental=args.b_instrumental, b_vocals=args.b_vocals,
            pair_id=args.pair_id, bpm=args.bpm, beats=args.beats,
            a_start=args.a_start, b_start=args.b_start,
            rights=args.rights, provenance=args.provenance, gain_db=args.gain_db)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, "MixLab stem session: " + str(exc) + "\n")
    print(json.dumps({"ready": True, "private_studio": str(index),
                      "stem_separation_performed": False,
                      "audio_uploaded": False}))


if __name__ == "__main__":
    main()
