"""Bounded private USB bundle for one already rendered Event Marathon.

The original mixed WAV remains unchanged. The ZIP manifest is unsigned and
therefore proves internal file consistency, never external authenticity.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import stat
import tempfile
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


def export_marathon_bundle(original_marathon_wav, new_zip, *, cues=None, master_choice=None):
    """Package the real WAV, its exact receipt and its official offline player."""
    wav = Path(original_marathon_wav).absolute()
    if wav.name != "marathon.wav":
        raise ValueError("Only original Marathon WAVs can enter this private bundle")
    folder = wav.parent
    target = _new_zip_path(wav, new_zip)
    duration, sections, evidence = _marathon_duration(folder, wav)
    if evidence not in ("marathon", "marathon_blend") or not 2 <= sections <= 8:
        raise ValueError("Private Marathon is not a completed original export")
    receipt = _read_small_json(folder / "marathon.receipt.private.json")
    if not isinstance(receipt, dict):
        raise ValueError("Original joined master has no private receipt")
    files = [
        _source(folder, "marathon.wav", MAX_MARATHON),
        _source(folder, "marathon.receipt.private.json", RECEIPT_LIMIT),
        _source(folder, "index.html", PAGE_LIMIT),
    ]
    if (folder / "marathon.join-studio.private.html").exists():
        files.append(_source(folder, "marathon.join-studio.private.html", PAGE_LIMIT))
    if (folder / "marathon.runbook.private.html").exists():
        files.append(_source(folder, "marathon.runbook.private.html", PAGE_LIMIT))
    portable = [name for name in ("marathon.mp3", "marathon.flac")
                if (folder / name).exists() or (folder / name).is_symlink()]
    if len(portable) > 1:
        raise ValueError("Only one official portable audio codec can enter one private Marathon ZIP")
    if portable:
        name = portable[0]
        receipt_name = name + ".receipt.private.json"
        player_name = name + ".player.html"
        audio, audio_meta = _source(folder, name, 512 * 1024 * 1024)
        portable_receipt, receipt_meta = _source(folder, receipt_name, RECEIPT_LIMIT)
        page, page_meta = _source(folder, player_name, PAGE_LIMIT)
        details = _read_small_json(portable_receipt)
        if (not isinstance(details, dict) or
                details.get("kind") != "mixlab-private-marathon-mobile-v1" or
                details.get("source_wav_sha256") != receipt["wav_sha256"] or
                details.get("format") != audio.suffix.lower()[1:] or
                details.get("private_local_use_only") is not True or
                details.get("automatic_licensing") is not False or
                not isinstance(details.get("output_sha256"), str)):
            raise ValueError("Portable audio does not match the original private Marathon receipt")
        files.extend([(audio, audio_meta), (portable_receipt, receipt_meta), (page, page_meta)])
    with ExitStack() as stack:
        if master_choice is not None:
            # Explicit opt-in only: handwritten human notes can contain
            # sensitive private event detail and must never leak by default.
            from .marathon_master_review import bound_choice_for_master
            selected = bound_choice_for_master(wav, master_choice)
            if selected["sha256"] != receipt["wav_sha256"]:
                raise ValueError("Chosen master differs from actual private WAV")
            private_plan = Path(master_choice).absolute()
            files.append(_source(private_plan.parent, private_plan.name, RECEIPT_LIMIT))
            # Generate human-readable notes only on explicit operator
            # inclusion and only from the SHA-verified selected master.
            from .marathon_master_review import create_master_brief
            brief_dir = Path(stack.enter_context(
                tempfile.TemporaryDirectory(prefix=".mixlab-marathon-review-", dir=folder)))
            brief_path = brief_dir / "marathon.master-choice.private.html"
            create_master_brief(wav, private_plan, brief_path)
            files.append(_source(brief_dir, brief_path.name, PAGE_LIMIT))
        if cues is not None:
            # Only an explicit opt-in can package human notes. The printed
            # sheet is rebuilt from receipt-bound JSON (not arbitrary HTML).
            from .marathon_cue_sheet import create_cue_sheet
            cues_path = Path(cues).absolute()
            if cues_path.name != "mixlab-marathon-cues.private.json":
                raise ValueError("Use the original Stage-exported private cue filename")
            scratch = Path(stack.enter_context(
                tempfile.TemporaryDirectory(prefix=".mixlab-marathon-cues-", dir=folder)))
            sheet_path = scratch / "marathon.cues.private.html"
            create_cue_sheet(wav, cues_path, sheet_path)
            files.append(_source(cues_path.parent, cues_path.name, RECEIPT_LIMIT))
            files.append(_source(scratch, sheet_path.name, PAGE_LIMIT))
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
                                    expected_hash=(receipt["wav_sha256"] if item == wav else
                                                   details["output_sha256"] if portable and item == audio else None))
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
                        "operator_cues_included": cues is not None,
                        "master_choice_included": master_choice is not None,
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
                "archive_authenticated": False, "source_media_included": False,
                "operator_cues_included": cues is not None,
                "master_choice_included": master_choice is not None}


def main():
    parser = argparse.ArgumentParser(
        description="Package one original private MixLab Marathon WAV into a SHA-manifest USB ZIP")
    parser.add_argument("marathon_wav", help="Existing receipt-bound marathon.wav")
    parser.add_argument("new_private_zip", help="NEW private .zip beside marathon.wav")
    parser.add_argument("--cues", help="Include the SHA-bound private Stage cue log and newly generated printable show sheet")
    parser.add_argument("--master-choice", help="EXPLICIT opt-in to include private SHA-bound human Master Review selection/notes")
    args = parser.parse_args()
    try:
        result = export_marathon_bundle(args.marathon_wav, args.new_private_zip, cues=args.cues,
                                        master_choice=args.master_choice)
    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile):
        parser.exit(2, "MixLab Marathon ZIP: no complete package was published; "
                       "inspect your original local WAV and receipt.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
