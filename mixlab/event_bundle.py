"""Private, bounded streaming ZIP for a real SHA-verified MixLab event set.

No source media upload or inclusion, no unverified compressed audio, no
renderer changes, no public distribution rights inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

from .event_dashboard import _local_optional
from .ingest import digest
from .set_composer import _parse_json, _secure_file
from .set_player import build_chapters

MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 896 * 1024 * 1024
BLOCK = 65536
MAX_ITEMS = 9


def _new_zip_path(wav, destination):
    out = Path(destination).absolute()
    if (out.parent != wav.parent or out.suffix.lower() != ".zip" or
            out.is_symlink() or out.exists()):
        raise ValueError("Choose a NEW private ZIP in the completed WAV folder")
    for item in (out, *out.parents):
        if item.is_symlink() or (item / ".git").exists():
            raise ValueError("Private portable DJ ZIP must stay outside Git and symlinked paths")
    return out


def _regular_companion(folder, value):
    path = Path(value).absolute()
    if (path.parent != folder or path.is_symlink() or not path.is_file() or
            "/" in path.name or "\\" in path.name):
        raise ValueError("Cannot pack a file outside the completed private event folder")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE:
        raise ValueError("Event file is not regular, is empty or exceeds the maximum bundle file size")
    return path, info


def _copy_entry(archive, item, meta, *, expected_hash=None):
    """Never dereference a source symlink; stream once into ZIP_STORED."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    handle = os.open(item, flags)
    with os.fdopen(handle, "rb") as src:
        before = os.fstat(src.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_size != meta.st_size or
                before.st_ino != meta.st_ino or before.st_dev != meta.st_dev or
                before.st_mtime_ns != meta.st_mtime_ns):
            raise ValueError("An event file changed before ZIP publication")
        h = hashlib.sha256()
        info = zipfile.ZipInfo(item.name)
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o600 << 16
        info.flag_bits |= 0x800  # UTF-8 zip entry filename
        with archive.open(info, "w", force_zip64=True) as output:
            remaining = before.st_size
            while remaining:
                chunk = src.read(min(BLOCK, remaining))
                if not chunk:
                    raise ValueError("Truncated source while assembling private event ZIP")
                output.write(chunk)
                h.update(chunk)
                remaining -= len(chunk)
        after = os.fstat(src.fileno())
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
            raise ValueError("Event file changed while creating private ZIP")
        observed = h.hexdigest()
        if expected_hash is not None and observed != expected_hash:
            raise ValueError("Event audio SHA mismatch during ZIP packaging")
        return {"file": item.name, "sha256": observed, "size_bytes": before.st_size}


def export_bundle(private_session, complete_wav, new_zip, *,
                  player=None, dashboard=None, runbook=None,
                  rehearsal=None, compressed=None):
    """Build private portable event ZIP from canonical WAV and validated links."""
    wav = Path(complete_wav).absolute()
    target = _new_zip_path(wav, new_zip)
    chapters = build_chapters(private_session, wav)
    if not chapters["chapters"]:
        raise ValueError("Only a completed, chaptered private set can be packaged")
    root = wav.parent
    inputs = []
    wav, _ = _regular_companion(root, wav)
    inputs.append((wav, chapters["wav_sha256"]))

    wav_receipt = wav.with_name(wav.name + ".receipt.private.json")
    wav_receipt, _ = _regular_companion(root, wav_receipt)
    inputs.append((wav_receipt, None))

    for optional in (player, dashboard, runbook, rehearsal):
        if optional is not None:
            path = _local_optional(root, optional, (".html",), required=True)
            inputs.append((path, None))

    if compressed is not None:
        if not isinstance(compressed, dict):
            raise ValueError("Portable delivery must be the official compressed output result")
        portable = _local_optional(root, compressed.get("private_delivery"), (".mp3", ".flac"), required=True)
        receipt = _local_optional(root, compressed.get("receipt"), (".json",), required=True)
        metadata = _parse_json(_secure_file(receipt, 65536))
        if (metadata.get("kind") != "private-compressed-continuous-set-delivery" or
                metadata.get("source_set_sha256") != chapters["wav_sha256"] or
                metadata.get("format") != portable.suffix.lower()[1:] or
                metadata.get("output_sha256") != digest(portable)):
            raise ValueError("Portable audio receipt must match the original WAV and actual MP3/FLAC")
        inputs.append((portable, metadata["output_sha256"]))
        inputs.append((receipt, None))
        if compressed.get("offline_player") is not None:
            html = _local_optional(root, compressed["offline_player"], (".html",), required=True)
            inputs.append((html, None))

    if len(inputs) > MAX_ITEMS:
        raise ValueError("Too many output files for one private DJ event bundle")
    if len({item.name for item, _ in inputs}) != len(inputs):
        raise ValueError("Cannot repeat an event item in a private ZIP")
    source_info = [(item, item.lstat(), expected) for item, expected in inputs]
    if sum(meta.st_size for _, meta, _ in source_info) > MAX_TOTAL:
        raise ValueError("The approved local set is too large for this portable ZIP budget")
    for item, meta, _ in source_info:
        if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= MAX_FILE:
            raise ValueError("Changed or oversized companion encountered before packaging")

    # A private zip contains ONLY already published package outputs, never
    # rights declarations, source files, original source manifest or secrets.
    packed = False
    created = False
    try:
        with target.open("xb") as stream:
            created = True
            os.fchmod(stream.fileno(), 0o600)
            with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_STORED,
                                 allowZip64=True) as archive:
                files = [_copy_entry(archive, item, meta, expected_hash=expected)
                         for item, meta, expected in source_info]
                manifest = {"schema_version": 1,
                            "kind": "mixlab-private-portable-full-set-v1",
                            "wav_sha256": chapters["wav_sha256"],
                            "chapters": len(chapters["chapters"]),
                            "human_preference_proven": False,
                            "source_media_included": False,
                            "private_local_use_only": True,
                            "files": files}
                entry = zipfile.ZipInfo("mixlab-bundle-manifest.private.json")
                entry.compress_type = zipfile.ZIP_STORED
                entry.external_attr = 0o600 << 16
                with archive.open(entry, "w") as output:
                    output.write((json.dumps(manifest, sort_keys=True, indent=2,
                                             allow_nan=False) + "\n").encode("utf-8"))
        packed = True
    finally:
        if created and not packed:
            # Only this newly created, incomplete archive is removed. Original
            # verified WAV, compressed delivery and operator pages are retained.
            target.unlink(missing_ok=True)
    return {"private_bundle_zip": str(target),
            "original_wav_sha256": chapters["wav_sha256"],
            "files": [item.name for item, _ in inputs],
            "source_media_included": False, "private": True,
            "automatic_licensing": False}


def main():
    parser = argparse.ArgumentParser(
        description="Bundle an existing receipt-verified private MixLab DJ set into a bounded local portable ZIP")
    parser.add_argument("private_session")
    parser.add_argument("complete_wav")
    parser.add_argument("new_private_zip")
    parser.add_argument("--player")
    parser.add_argument("--dashboard")
    parser.add_argument("--runbook")
    parser.add_argument("--rehearsal")
    parser.add_argument("--compressed")
    parser.add_argument("--compressed-receipt")
    parser.add_argument("--compressed-player")
    args = parser.parse_args()
    portable = None
    if args.compressed or args.compressed_receipt or args.compressed_player:
        if not args.compressed or not args.compressed_receipt:
            parser.exit(2, "Compressed audio needs the exact official delivery receipt\n")
        portable = {"private_delivery": args.compressed,
                    "receipt": args.compressed_receipt,
                    "offline_player": args.compressed_player}
    try:
        result = export_bundle(args.private_session, args.complete_wav,
                               args.new_private_zip, player=args.player,
                               dashboard=args.dashboard, runbook=args.runbook,
                               rehearsal=args.rehearsal,
                               compressed=portable)
    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, "MixLab portable bundle: " + str(exc) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
