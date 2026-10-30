"""One-command private MixLab transition session: import -> cues -> audition.

Uses the *existing* engine rather than claiming a new DJ algorithm.
No model, network, source upload, automatic cue acceptance or QA execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat

from .cueprep import MAX_SOURCE_MANIFEST_BYTES, _read_spec, compile_cues
from .cue_suggest import suggest
from .media_import import OUTPUT_RATE, import_library
from .studio import build_studio
from .ingest import MAX_FRAMES


def _bound_source_manifest_sha256(path):
    """Bind a single regular 1 MiB source inode without following aliases."""
    if path.is_symlink():
        raise ValueError("source manifest changed during session")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("source manifest changed during session") from exc
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE_MANIFEST_BYTES:
            raise ValueError("source manifest changed during session")
        raw = source.read(MAX_SOURCE_MANIFEST_BYTES + 1)
        after = os.fstat(source.fileno())
    try:
        current = path.lstat()
    except OSError as exc:
        raise ValueError("source manifest changed during session") from exc
    def identity(item):
        return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if (len(raw) != before.st_size or not stat.S_ISREG(current.st_mode)
            or identity(before) != identity(after) or identity(before) != identity(current)):
        raise ValueError("source manifest changed during session")
    return hashlib.sha256(raw).hexdigest()


def _private_project_dir(destination, source_manifest):
    destination = Path(destination).absolute()
    source_manifest = Path(source_manifest).absolute()
    source_root = source_manifest.parent.resolve(strict=True)
    if (destination.exists() or destination.is_symlink() or
            destination == source_root or
            destination.is_relative_to(source_root) or
            source_root.is_relative_to(destination)):
        raise ValueError("Use a new private project directory outside source music")
    if not destination.parent.is_dir():
        raise ValueError("Project parent directory must already exist")
    for ancestor in (destination, *destination.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Never generate music in a Git checkout")
    return destination


def _manual_cues_present(manifest):
    """Do not accidentally render a random zero-time slice from each song."""
    pairs, tracks = manifest.get("pairs"), manifest.get("tracks")
    if not isinstance(pairs, list) or not isinstance(tracks, list):
        raise ValueError("Invalid source manifest: tracks and pairs required")
    bpm = {entry.get("id"): entry.get("bpm") for entry in tracks
           if isinstance(entry, dict)}
    for pair in pairs:
        if not isinstance(pair, dict):
            raise ValueError("Invalid transition pair")
        for side in ("a", "b"):
            key = side + "_start_seconds"
            cue = pair.get(key)
            if type(cue) not in (int, float) or not math.isfinite(cue) or cue < 0:
                raise ValueError("Every pair needs manually approved a_start_seconds and b_start_seconds")
        a, b = pair.get("a"), pair.get("b")
        tempo = bpm.get(a)
        if (type(tempo) not in (int, float) or not math.isfinite(tempo)
                or not 30 <= tempo <= 300 or type(bpm.get(b)) not in (int, float)
                or not math.isfinite(bpm[b]) or tempo != bpm[b]):
            raise ValueError("Current Transition Studio requires matching manual BPM")
        beats = pair.get("beats", 8)
        if type(beats) is not int or not 1 <= beats <= 64:
            raise ValueError("Transition beats must be 1..64")
        length = beats * 60 / tempo
        if not math.isfinite(length) or not 2 <= round(length * OUTPUT_RATE) <= MAX_FRAMES:
            raise ValueError("Manual transition duration exceeds canonical frame limits")


def _receipt_json(data):
    return (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def make_session(source_manifest, destination, *, suggestions=False, pair=None,
                 timeout_seconds=600):
    source_manifest = Path(source_manifest).absolute()
    source_sha = _bound_source_manifest_sha256(source_manifest)
    manifest = _read_spec(source_manifest)
    if _bound_source_manifest_sha256(source_manifest) != source_sha:
        raise ValueError("source manifest changed during session")
    _manual_cues_present(manifest)
    if suggestions:
        tracks = manifest.get("tracks", [])
        if not all(isinstance(t, dict) and "first_downbeat_seconds" in t for t in tracks):
            raise ValueError("--suggestions needs manually verified first_downbeat_seconds on every track")
    if pair is not None:
        if not isinstance(pair, str) or pair not in [
                p.get("id") for p in manifest.get("pairs", []) if isinstance(p, dict)]:
            raise ValueError("Requested pair ID does not exist")
    destination = _private_project_dir(destination, source_manifest)
    destination.mkdir(mode=0o700)
    try:
        imported = destination / "sources"
        converted_manifest = import_library(source_manifest, imported,
                                           timeout_seconds=timeout_seconds)
        if _bound_source_manifest_sha256(source_manifest) != source_sha:
            raise ValueError("source manifest changed during session")
        if suggestions:
            suggest(converted_manifest, destination / "cue-suggestions.private.json")
        # All original pairs are generated into a bounded shared excerpt
        # manifest; --pair only narrows CPU-heavy audition/render output.
        excerpts = destination / "excerpts"
        excerpt_manifest = compile_cues(converted_manifest, excerpts)
        studio_index = build_studio(excerpt_manifest, destination / "studio", pair_id=pair)
        manifest_data = excerpt_manifest.read_bytes()
        if _bound_source_manifest_sha256(source_manifest) != source_sha:
            raise ValueError("source manifest changed during session")
        studio_receipt = destination / "studio" / "studio-receipt.private.json"
        result = {
            "schema_version": 1,
            "kind": "offline-manual-transition-session",
            "stage": "studio-ready",
            "source_manifest_sha256": source_sha,
            "normalized_manifest": "sources/source_manifest.json",
            "prepared_manifest": "excerpts/library.json",
            "prepared_manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
            "studio_index": "studio/index.html",
            "studio_receipt_sha256": hashlib.sha256(studio_receipt.read_bytes()).hexdigest(),
            "suggestions": "cue-suggestions.private.json" if suggestions else None,
            "selected_pair": pair,
            "warnings": ["private local music only; do not upload project directory",
                         "manual tempo and cues; no automatic beat/key/phrase analysis",
                         "creative audition is not blind listener preference evidence"]
        }
        raw = _receipt_json(result)
        if len(raw) > 65536:
            raise ValueError("Project manifest unexpectedly exceeds 64 KiB")
        manifest_out = destination / "session-receipt.private.json"
        with manifest_out.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
        return studio_index
    except BaseException:
        # Only the initially non-existent private project is removed.
        # Original music and existing user files are never overwritten.
        shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Import permitted songs and make a complete private DJ audition in one command")
    parser.add_argument("source_manifest", help="Private source JSON with SHA, rights, BPM and A/B cue seconds")
    parser.add_argument("destination", help="New private project folder outside input and Git")
    parser.add_argument("--suggestions", action="store_true",
                        help="Also prepare manual-grid energy proposals (not automatically accepted)")
    parser.add_argument("--pair", help="Audition only this pair; others are still prepared")
    parser.add_argument("--timeout-seconds", type=int, default=600,
                        help="Maximum seconds of FFmpeg processing per track (30..900)")
    args = parser.parse_args()
    try:
        page = make_session(args.source_manifest, args.destination,
                            suggestions=args.suggestions, pair=args.pair,
                            timeout_seconds=args.timeout_seconds)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"MixLab session: {exc}\n")
    print(json.dumps({"ready": True, "private_studio": str(page),
                      "workflow": "local-import -> manual-cues -> real-render -> creative-audition",
                      "musical_quality_claim": False}))


if __name__ == "__main__":
    main()
