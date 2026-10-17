"""Two-step offline MixLab music workflow with a human visual cue checkpoint.

START: permitted local music -> normalized PCM16 -> interactive cue editor.
FINISH: exact manifest-bound user choices -> safe excerpts -> real WAV studio.

No public service, CDN, model downloads, unattended auto-cue decisions
or silent replacement of an existing private benchmark/session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

from .cue_editor import apply as apply_cue_changes, prepare as prepare_cue_editor
from .cue_suggest import suggest as suggest_cues
from .cueprep import _read_spec, compile_cues
from .media_import import import_library
from .studio import build_studio
from .full_mix import full_mix
from .engine import FAMILY_NAMES

WORKFLOW_KIND = "private-interactive-mixlab-session"
WORKFLOW_VERSION = 1
MAX_RECEIPT_BYTES = 65536


def _raw_json(data):
    return (json.dumps(data, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _private_write(destination, data):
    raw = _raw_json(data)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("Private session receipt exceeds 64 KiB")
    with destination.open("xb") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(raw)


def _checksum(path):
    from .ingest import digest
    return digest(path)


def _check_git_destination(target):
    for item in (target, *target.parents):
        if (item / ".git").exists():
            raise ValueError("Private audio/project files must stay outside Git repositories")


def _check_destination(source_manifest, destination):
    source_manifest = Path(source_manifest).absolute()
    root = source_manifest.parent.resolve(strict=True)
    dest = Path(destination).absolute()
    if (dest.exists() or dest.is_symlink() or dest == root or
            dest.is_relative_to(root) or root.is_relative_to(dest)):
        raise ValueError("A new project directory outside your source music is required")
    if not dest.parent.is_dir():
        raise ValueError("New session parent directory must already exist")
    _check_git_destination(dest)
    return dest


def start_session(source_manifest, destination, *, suggest=False, timeout_seconds=600):
    """Create a new private workspace and a real offline A/B cue editor."""
    original = Path(source_manifest).absolute()
    source_spec = _read_spec(original)
    if suggest:
        tracks = source_spec.get("tracks")
        if (not isinstance(tracks, list) or
                not all(isinstance(t, dict) and "first_downbeat_seconds" in t for t in tracks)):
            raise ValueError("Suggestions require verified first-downbeat seconds on every track")
    root = _check_destination(original, destination)
    root.mkdir(mode=0o700)
    try:
        converted_manifest = import_library(
            original, root / "sources", timeout_seconds=timeout_seconds)
        page = prepare_cue_editor(converted_manifest, root / "sources" / "cue-editor.html")
        if suggest:
            suggest_cues(converted_manifest, root / "cue-suggestions.private.json")
        receipt = {
            "schema_version": WORKFLOW_VERSION,
            "kind": WORKFLOW_KIND,
            "state": "awaiting-manual-cue-approval",
            "original_spec_sha256": _checksum(original),
            "converted_manifest_sha256": _checksum(converted_manifest),
            "cue_editor_sha256": _checksum(page),
            "converted_manifest": "sources/source_manifest.json",
            "editor": "sources/cue-editor.html",
            "suggestions": "cue-suggestions.private.json" if suggest else None,
            "manual_check": "review A/B cue positions with offline browser editor",
            "policy": ["no public media upload", "no silent source-to-cue change",
                       "no automatic beat or phrase accuracy claim"]
        }
        _private_write(root / "project-receipt.private.json", receipt)
        return page
    except BaseException:
        shutil.rmtree(root)
        raise


def _admit_receipt(project):
    receipt = project / "project-receipt.private.json"
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("Private interactive session receipt is unavailable")
    raw = receipt.read_bytes()
    if not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        raise ValueError("Private session receipt has unexpected size")
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Private session receipt is not valid JSON") from exc
    if (not isinstance(data, dict) or data.get("schema_version") != WORKFLOW_VERSION or
            data.get("kind") != WORKFLOW_KIND or
            data.get("state") != "awaiting-manual-cue-approval"):
        raise ValueError("Session is not a valid pending MixLab interactive project")
    sources = project / "sources" / "source_manifest.json"
    page = project / "sources" / "cue-editor.html"
    if sources.is_symlink() or page.is_symlink() or not sources.is_file() or not page.is_file():
        raise ValueError("Source manifest or cue editor was replaced")
    if (data.get("converted_manifest_sha256") != _checksum(sources) or
            data.get("cue_editor_sha256") != _checksum(page)):
        raise ValueError("Converted library or authored cue editor changed")
    return data, sources


def finish_session(session, selections, *, pair=None, export_full_song=False,
                   full_song_family="bass_swap", full_song_gain_db=-9.):
    """Finalize separately approved browser cues into immutable WAV renders."""
    lexical = Path(session).absolute()
    if lexical.is_symlink():
        raise ValueError("Private session directory cannot be a link")
    root = lexical.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Private MixLab session directory unavailable")
    _check_git_destination(root)
    data, converted_manifest = _admit_receipt(root)
    if export_full_song and pair is None:
        raise ValueError("--full-song requires --pair to select one entire two-track mix")
    if full_song_family not in FAMILY_NAMES:
        raise ValueError("Unknown full-song transition family")
    if pair is not None:
        spec = _read_spec(converted_manifest)
        if not any(isinstance(item, dict) and item.get("id") == pair for item in spec.get("pairs", [])):
            raise ValueError("Requested pair is not registered in this local library")

    # Never overwrite or remove files created by anyone else.
    output_manifest = root / "sources" / "approved-cues.json"
    excerpts = root / "excerpts"
    studio = root / "studio"
    complete = root / "completed-receipt.private.json"
    full_song_dir = root / "full-song"
    if any(path.exists() or path.is_symlink() for path in
           (output_manifest, excerpts, studio, complete, full_song_dir)):
        raise ValueError("Session already finalized or contains reserved product files; use a new session")
    created = []
    try:
        apply_cue_changes(converted_manifest, selections, output_manifest)
        created.append(output_manifest)
        excerpt_manifest = compile_cues(output_manifest, excerpts)
        created.append(excerpts)
        index = build_studio(excerpt_manifest, studio, pair_id=pair)
        created.append(studio)
        full_song_result = None
        if export_full_song:
            full_song_result = full_mix(output_manifest, full_song_dir, pair_id=pair,
                                        family=full_song_family, gain_db=full_song_gain_db)
            created.append(full_song_dir)
        finish = {
            "schema_version": WORKFLOW_VERSION,
            "kind": WORKFLOW_KIND, "state": "manual-cues-rendered",
            "pending_receipt_sha256": _checksum(root / "project-receipt.private.json"),
            "approved_manifest_sha256": _checksum(output_manifest),
            "excerpt_manifest_sha256": _checksum(excerpt_manifest),
            "studio_receipt_sha256": _checksum(studio / "studio-receipt.private.json"),
            "selected_pair": pair,
            "studio_page": "studio/index.html",
            "full_song_wav": "full-song/full-song-mix.wav" if export_full_song else None,
            "full_song_receipt_sha256": (_checksum(full_song_dir / "full-mix-receipt.private.json")
                                          if full_song_result is not None else None),
            "source_manifest": "sources/approved-cues.json",
            "limitations": ["not a frozen blind listening study",
                            "timing and BPM manually approved",
                            "real music usage permissions remain user's responsibility"]
        }
        _private_write(complete, finish)
        return index
    except BaseException:
        # Only these four previously-absent files/directories were owned by
        # this invocation. Do not remove the imported WAVs or user's choices.
        for item in reversed(created):
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="MixLab visual approval workflow: private import -> browser cues -> real transition WAVs")
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("start", help="Import source tracks and create offline cue editor")
    p.add_argument("source_manifest")
    p.add_argument("private_project")
    p.add_argument("--suggestions", action="store_true",
                   help="Also compute private manual-grid energy cue suggestions")
    p.add_argument("--timeout-seconds", type=int, default=600)
    p = sub.add_parser("finish", help="Render WAV transitions from exported, approved cue choices")
    p.add_argument("private_project")
    p.add_argument("selection_json")
    p.add_argument("--pair", help="Render studio for just one pre-registered pair")
    p.add_argument("--full-song", action="store_true",
                   help="Also render the complete two-song WAV; requires --pair")
    p.add_argument("--full-song-family", choices=FAMILY_NAMES, default="bass_swap")
    p.add_argument("--full-song-gain-db", type=float, default=-9.)
    args = parser.parse_args()
    try:
        result = (start_session(args.source_manifest, args.private_project,
                                suggest=args.suggestions,
                                timeout_seconds=args.timeout_seconds)
                  if args.action == "start" else
                  finish_session(args.private_project, args.selection_json,
                                 pair=args.pair, export_full_song=args.full_song,
                                 full_song_family=args.full_song_family,
                                 full_song_gain_db=args.full_song_gain_db))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, "MixLab interactive session: " + str(exc) + "\n")
    print(json.dumps({"ready": True, "private_page": str(result),
                      "action": args.action, "audio_uploaded": False,
                      "manual_cue_approval_required": args.action == "start"}))


if __name__ == "__main__":
    main()
