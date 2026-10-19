"""Bind a private DJ's gallery preference to one unmodified PCM16 WAV.

Offline product handoff: no automatic publication, no copyright approval,
no global playlist or blinded-listener-study claims.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .models import FAMILY_NAMES

MAX_JSON_BYTES = 65536
MAX_WAV_BYTES = 32 * 1024 * 1024
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON field")


def _read_json_and_digest(path):
    fd = os.open(path, READ_FLAGS)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_JSON_BYTES:
            raise ValueError("Private JSON must be a regular, bounded file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_JSON_BYTES + 1)
        after = os.fstat(fd)
        if len(data) != before.st_size or (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("Private JSON source changed while reading")
    finally:
        os.close(fd)
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid private JSON") from exc
    if type(parsed) is not dict:
        raise ValueError("Private JSON must contain an object")
    return parsed, hashlib.sha256(data).hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and HEX_SHA.fullmatch(value) is not None


def _verified_choice(receipt, receipt_sha, choice):
    if receipt.get("schema_version") != 1 or receipt.get("kind") != "mixlab-private-manual-transition-gallery":
        raise ValueError("Unsupported gallery receipt")
    if receipt.get("status") != "rendered-not-listener-validated" or receipt.get("rights_status") != "unverified":
        raise ValueError("Gallery status changed or unsupported")
    entries = receipt.get("renders")
    if type(entries) is not list or len(entries) != len(FAMILY_NAMES):
        raise ValueError("Gallery must contain the four original families")
    present = {}
    for entry in entries:
        if type(entry) is not dict:
            raise ValueError("Invalid gallery render entry")
        family = entry.get("family")
        if family not in FAMILY_NAMES or family in present:
            raise ValueError("Unexpected or duplicate gallery family")
        if entry.get("audio") != f"{family}.wav" or not _valid_sha(entry.get("audio_sha256")):
            raise ValueError("Invalid gallery output identity")
        present[family] = entry
    if set(present) != set(FAMILY_NAMES):
        raise ValueError("Gallery family coverage incomplete")
    if (choice.get("schema_version") != 1 or choice.get("kind") != "mixlab-private-dj-choice"
            or choice.get("human_choice_not_blind_study") is not True):
        raise ValueError("Unsupported private DJ choice")
    if not _valid_sha(choice.get("receipt_sha256")) or choice["receipt_sha256"] != receipt_sha:
        raise ValueError("DJ choice does not belong to this original gallery receipt")
    family = choice.get("selected_family")
    if not isinstance(family, str) or family not in present:
        raise ValueError("Unknown selected transition")
    note = choice.get("note")
    if type(note) is not str or len(note) > 240 or len(note.encode("utf-8")) > 1024:
        raise ValueError("Private DJ note is not bounded text")
    return family, present[family], note


def _copy_and_verify_wav(source_path, target_temp, expected_sha):
    source_fd = os.open(source_path, READ_FLAGS)
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or not 44 <= before.st_size <= MAX_WAV_BYTES:
            raise ValueError("Selected PCM16 WAV must be a bounded regular file")
        checksum = hashlib.sha256()
        total = 0
        with open(target_temp, "wb") as dest:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_WAV_BYTES:
                    raise ValueError("Selected WAV changed or exceeded size cap")
                checksum.update(chunk)
                dest.write(chunk)
        after = os.fstat(source_fd)
        if (total != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("Selected WAV changed during copy")
        if checksum.hexdigest() != expected_sha:
            raise ValueError("Selected WAV differs from the original render receipt")
    finally:
        os.close(source_fd)
    return total


def export_choice(gallery_dir, choice_file, output_wav):
    """Publish an exact chosen WAV and its private, review-only evidence sidecar."""
    gallery, output = Path(gallery_dir), Path(output_wav)
    if not gallery.is_dir() or not output.parent.is_dir():
        raise ValueError("Gallery and export parent directory must already exist")
    if output.suffix.lower() != ".wav":
        raise ValueError("Choose a new .wav destination")
    sidecar = output.with_suffix(".choice.json")
    if any(path.exists() or path.is_symlink() for path in (output, sidecar)):
        raise ValueError("Chosen WAV or sidecar already exists; no overwrite permitted")
    receipt, original_receipt_sha = _read_json_and_digest(gallery / "receipt.json")
    choice, choice_sha = _read_json_and_digest(choice_file)
    family, render_entry, note = _verified_choice(receipt, original_receipt_sha, choice)

    with tempfile.TemporaryDirectory(prefix=".mixlab-dj-selection-", dir=output.parent) as stage:
        staged_wav = Path(stage) / "chosen.wav"
        byte_count = _copy_and_verify_wav(gallery / f"{family}.wav", staged_wav,
                                          render_entry["audio_sha256"])
        evidence = {
            "schema_version": 1,
            "kind": "mixlab-private-dj-selection",
            "status": "human-chosen-not-blind-study",
            "rights_status": "unverified",
            "selected_family": family,
            "private_note": note,
            "gallery_receipt_sha256": original_receipt_sha,
            "dj_choice_sha256": choice_sha,
            "selected_wav_sha256": render_entry["audio_sha256"],
            "selected_wav_bytes": byte_count,
            "gain_policy": receipt.get("gain_policy"),
            "shared_gain_db": receipt.get("shared_gain_db"),
            "source_permission_verified": False,
            "human_blind_preference_verified": False,
        }
        staged_evidence = Path(stage) / "chosen.choice.json"
        staged_evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
                                   encoding="utf-8")
        # File hardlinks on one filesystem only, exclusively (EEXIST refuses
        # colliding paths/symlinks). Roll back our own WAV if sidecar linking fails.
        os.link(staged_wav, output)
        try:
            os.link(staged_evidence, sidecar)
        except BaseException:
            output.unlink()
            raise
    return output, sidecar


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export one receipt-verified private DJ transition without modifying gallery originals"
    )
    parser.add_argument("gallery_dir", help="Original private transition gallery directory")
    parser.add_argument("dj_choice", help="Human-downloaded mixlab-dj-choice.json")
    parser.add_argument("output_wav", help="New .wav path for the chosen export")
    args = parser.parse_args(argv)
    try:
        audio, sidecar = export_choice(args.gallery_dir, args.dj_choice, args.output_wav)
        print(f"Private WAV: {audio}\nPrivate choice receipt: {sidecar}")
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"MixLab DJ selection: {exc}\n")


if __name__ == "__main__":
    main()
