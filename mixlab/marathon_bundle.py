"""Bounded private USB bundle for one already rendered Event Marathon.

The original mixed WAV remains unchanged. The ZIP manifest is unsigned and
therefore proves internal file consistency, never external authenticity.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import zipfile

from .event_bundle import BLOCK, MAX_TOTAL, _copy_entry, _new_zip_path
from .event_vault import MAX_MARATHON, _marathon_duration, _read_small_json

MANIFEST = "mixlab-bundle-manifest.private.json"
PAGE_LIMIT = 512 * 1024
RECEIPT_LIMIT = 65536


def _source(folder, name, maximum):
    path = folder / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing private Marathon output file")
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= maximum:
        raise ValueError("Marathon output is not an ordinary bounded file")
    return path, metadata


def export_marathon_bundle(original_marathon_wav, new_zip):
    """Package the real WAV, its exact receipt and its official offline player."""
    wav = Path(original_marathon_wav).absolute()
    if wav.name != "marathon.wav":
        raise ValueError("Only original Marathon WAVs can enter this private bundle")
    folder = wav.parent
    target = _new_zip_path(wav, new_zip)
    duration, sections, evidence = _marathon_duration(folder, wav)
    if evidence != "marathon" or not 2 <= sections <= 8:
        raise ValueError("Private Marathon is not a completed original export")
    receipt = _read_small_json(folder / "marathon.receipt.private.json")
    if not isinstance(receipt, dict):
        raise ValueError("Original joined master has no private receipt")
    files = [
        _source(folder, "marathon.wav", MAX_MARATHON),
        _source(folder, "marathon.receipt.private.json", RECEIPT_LIMIT),
        _source(folder, "index.html", PAGE_LIMIT),
    ]
    if sum(meta.st_size for _, meta in files) > MAX_TOTAL:
        raise ValueError("Private Marathon package exceeds the existing ZIP memory/disk budget")
    created = False
    complete = False
    try:
        with target.open("xb") as output:
            created = True
            os.fchmod(output.fileno(), 0o600)
            with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED,
                                 allowZip64=True) as archive:
                records = [
                    _copy_entry(archive, item, meta,
                                expected_hash=receipt["wav_sha256"] if item == wav else None)
                    for item, meta in files
                ]
                manifest = {
                    "schema_version": 1,
                    "kind": "mixlab-private-portable-marathon-v1",
                    "wav_sha256": receipt["wav_sha256"],
                    "chapters": sections,
                    "source_media_included": False,
                    "private_local_use_only": True,
                    "automatic_licensing": False,
                    "files": records,
                }
                descriptor = zipfile.ZipInfo(MANIFEST)
                descriptor.compress_type = zipfile.ZIP_STORED
                descriptor.external_attr = 0o600 << 16
                with archive.open(descriptor, "w") as stream:
                    stream.write((json.dumps(manifest, sort_keys=True, indent=2,
                                             allow_nan=False) + "\n").encode("utf-8"))
        complete = True
    finally:
        if created and not complete:
            target.unlink(missing_ok=True)
    return {"private_bundle_zip": str(target), "wav_sha256": receipt["wav_sha256"],
            "events_joined": sections, "private": True, "network_uploads": False,
            "archive_authenticated": False, "source_media_included": False}


def main():
    parser = argparse.ArgumentParser(
        description="Package one original private MixLab Marathon WAV into a SHA-manifest USB ZIP")
    parser.add_argument("marathon_wav", help="Existing receipt-bound marathon.wav")
    parser.add_argument("new_private_zip", help="NEW private .zip beside marathon.wav")
    args = parser.parse_args()
    try:
        result = export_marathon_bundle(args.marathon_wav, args.new_private_zip)
    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile):
        parser.exit(2, "MixLab Marathon ZIP: no complete package was published; "
                       "inspect your original local WAV and receipt.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
