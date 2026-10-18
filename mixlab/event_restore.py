"""Restore a private MixLab event USB ZIP into a NEW offline event directory.

Restores already-published MixLab outputs. An unsigned ZIP manifest proves
internal file consistency only, NOT authenticity, music rights or music quality.
Never extract an archive from an untrusted person.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile

from .event_bundle import BLOCK, MAX_FILE, MAX_ITEMS, MAX_TOTAL
from .event_vault import MAX_MARATHON, _marathon_duration

MANIFEST = "mixlab-bundle-manifest.private.json"
MAX_MANIFEST = 65536
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_ARCHIVE = MAX_TOTAL + 1024 * 1024


def _safe_name(name):
    """Flat outputs only: no rooted names, traversal, separators or control chars."""
    return (isinstance(name, str) and 0 < len(name) <= 180 and
            name not in (".", "..") and
            not name.startswith(("/", "\\")) and
            "/" not in name and "\\" not in name and ":" not in name and
            not any(ord(ch) < 32 or ord(ch) == 127 for ch in name) and
            name == Path(name).name and
            Path(name).suffix.lower() in (".wav", ".html", ".json", ".flac", ".mp3"))


def _destination(new_folder):
    folder = Path(new_folder).absolute()
    if (folder.name in ("", ".", "..") or not folder.name or
            folder.exists() or folder.is_symlink() or
            not folder.parent.is_dir()):
        raise ValueError("Restore into a NEW private folder with an existing parent")
    for candidate in (folder, *folder.parents):
        if candidate.is_symlink() or (candidate / ".git").exists():
            raise ValueError("Private event restoration cannot target Git or symlinked folders")
    return folder


def _open_archive(source):
    path = Path(source).absolute()
    if path.suffix.lower() != ".zip" or path.is_symlink():
        raise ValueError("Choose the original regular private .zip file")
    for ancestor in path.parents:
        if ancestor.is_symlink():
            raise ValueError("ZIP source must have no symlinked ancestors")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    stream = os.fdopen(fd, "rb")
    record = os.fstat(fd)
    if not stat.S_ISREG(record.st_mode) or not (64 <= record.st_size <= MAX_ARCHIVE):
        stream.close()
        raise ValueError("ZIP source is not a bounded regular file")
    return stream, record


def _inspect(archive):
    infos = archive.infolist()
    if not 3 <= len(infos) <= MAX_ITEMS + 4:
        raise ValueError("Private bundle has an invalid number of outputs")
    names = [info.filename for info in infos]
    if len(set(names)) != len(names) or names.count(MANIFEST) != 1:
        raise ValueError("Bundle has duplicate, missing or unexpected manifest names")
    for info in infos:
        if info.is_dir() or info.compress_type != zipfile.ZIP_STORED:
            raise ValueError("Only flat uncompressed private event ZIP entries are supported")
        if info.filename != MANIFEST and not _safe_name(info.filename):
            raise ValueError("ZIP contains an unsafe or unsupported output filename")
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind not in (0, stat.S_IFREG):
            raise ValueError("Archive must not contain symlinks or special files")
        limit = MAX_MANIFEST if info.filename == MANIFEST else (MAX_MARATHON if info.filename == "marathon.wav" else MAX_FILE)
        if not (0 < info.file_size <= limit):
            raise ValueError("Archive member is empty or larger than the private event budget")
        if info.compress_size != info.file_size:
            raise ValueError("The portable event archive must contain only uncompressed entries")
    manifest = json.loads(archive.read(MANIFEST).decode("utf-8"))
    mode = manifest.get("kind") if isinstance(manifest, dict) else None
    is_marathon = mode == "mixlab-private-portable-marathon-v1"
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or (
        mode not in ("mixlab-private-portable-full-set-v1",
                     "mixlab-private-portable-marathon-v1") or
        manifest.get("source_media_included") is not False or
        manifest.get("private_local_use_only") is not True or
        type(manifest.get("chapters")) is not int or
        not (2 if is_marathon else 1) <= manifest["chapters"] <= (8 if is_marathon else 200) or
        not isinstance(manifest.get("wav_sha256"), str) or
        not SHA.fullmatch(manifest["wav_sha256"])
    ):
        raise ValueError("Not a supported private MixLab event manifest")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not 2 <= len(entries) <= MAX_ITEMS + (3 if is_marathon else 0):
        raise ValueError("Bundle file inventory is missing or oversized")
    file_map = {}
    size_total = 0
    for row in entries:
        if (not isinstance(row, dict) or not _safe_name(row.get("file")) or
                type(row.get("size_bytes")) is not int or
                not 0 < row["size_bytes"] <= (MAX_MARATHON if is_marathon and row.get("file") == "marathon.wav" else MAX_FILE) or
                not isinstance(row.get("sha256"), str) or
                not SHA.fullmatch(row["sha256"]) or row["file"] in file_map or
                row["file"] == MANIFEST):
            raise ValueError("Malformed or repeated portable event file claim")
        file_map[row["file"]] = row
        size_total += row["size_bytes"]
        if archive.getinfo(row["file"]).file_size != row["size_bytes"]:
            raise ValueError("A portable event output size differs from its manifest")
    if (size_total > MAX_TOTAL or len(infos) != len(entries) + 1 or
            set(names) != set(file_map).union({MANIFEST})):
        raise ValueError("Event archive contains inventory mismatch or unlisted files")
    masters = [row for row in entries if row["file"].lower().endswith(".wav")]
    if is_marathon:
        required = {"marathon.wav", "marathon.receipt.private.json", "index.html"}
        optional = {"marathon.runbook.private.html", "marathon.join-studio.private.html",
                    "marathon.mp3", "marathon.mp3.receipt.private.json", "marathon.mp3.player.html",
                    "marathon.flac", "marathon.flac.receipt.private.json", "marathon.flac.player.html",
                    "mixlab-marathon-cues.private.json", "marathon.cues.private.html",
                    "mixlab-marathon-master-choice.private.json"}
        cue_pair = {"mixlab-marathon-cues.private.json", "marathon.cues.private.html"}
        contains_cues = set(file_map) & cue_pair
        if (bool(contains_cues) != (manifest.get("operator_cues_included") is True) or
                (contains_cues and not cue_pair.issubset(file_map))):
            raise ValueError("Portable operator cues must be explicitly declared and complete")
        has_choice = "mixlab-marathon-master-choice.private.json" in file_map
        if has_choice != (manifest.get("master_choice_included") is True):
            raise ValueError("Private human master choice must be an explicitly declared ZIP member")
        packed_codecs = [codec for codec in ("mp3", "flac")
                         if ("marathon." + codec) in file_map]
        if len(packed_codecs) > 1:
            raise ValueError("Portable Marathon cannot include two codecs")
        for codec in ("mp3", "flac"):
            companions = {"marathon." + codec,
                          "marathon." + codec + ".receipt.private.json",
                          "marathon." + codec + ".player.html"}
            if (set(file_map) & companions) and not companions.issubset(file_map):
                raise ValueError("Portable Marathon codec must include audio, receipt and player")
        if (not required.issubset(file_map) or not set(file_map).issubset(required | optional) or
                len(masters) != 1 or masters[0]["file"] != "marathon.wav" or
                masters[0]["sha256"] != manifest["wav_sha256"]):
            raise ValueError("Portable Marathon ZIP must include its one actual WAV, receipt and player")
    elif (len(masters) != 1 or masters[0]["sha256"] != manifest["wav_sha256"] or
            masters[0]["file"] + ".receipt.private.json" not in file_map):
        raise ValueError("Portable event is missing its exact original WAV and receipt")
    return file_map, masters[0]["file"]


def restore_bundle(private_zip, new_private_folder):
    """Safely restore a trusted, hash-consistent official portable set.

    Extraction is all-or-nothing: any failure removes only our own newly
    created destination. No existing event, original ZIP or input is changed.
    """
    output = _destination(new_private_folder)
    stream, before = _open_archive(private_zip)
    created = False
    published = False
    written = []
    try:
        with stream:
            with zipfile.ZipFile(stream, "r") as archive:
                files, master = _inspect(archive)
                output.mkdir(mode=0o700)
                created = True
                dfd = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                              getattr(os, "O_NOFOLLOW", 0))
                try:
                    # All names and sizes were validated before creating output.
                    for name, claim in files.items():
                        with archive.open(name, "r") as member:
                            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                            fd = os.open(name, flags, 0o600, dir_fd=dfd)
                            written.append(name)
                            with os.fdopen(fd, "wb") as dst:
                                h = hashlib.sha256()
                                remaining = claim["size_bytes"]
                                while remaining:
                                    chunk = member.read(min(BLOCK, remaining))
                                    if not chunk:
                                        raise ValueError("Event ZIP entry ended before its claimed size")
                                    dst.write(chunk)
                                    h.update(chunk)
                                    remaining -= len(chunk)
                                if member.read(1) or h.hexdigest() != claim["sha256"]:
                                    raise ValueError("Event ZIP file hash or size did not match manifest")
                        # CRC-32 is checked by ZipFile while streaming; SHA-256
                        # above enforces the bundle's declared per-file checksum.
                    with archive.open(MANIFEST, "r") as member:
                        fd = os.open(MANIFEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                     getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dfd)
                        written.append(MANIFEST)
                        with os.fdopen(fd, "wb") as dst:
                            while True:
                                chunk = member.read(BLOCK)
                                if not chunk:
                                    break
                                dst.write(chunk)
                finally:
                    os.close(dfd)
                if master == "marathon.wav":
                    # Check the actual joined WAV against its ORIGINAL continuous
                    # output receipt after extraction, not just the ZIP inventory.
                    _marathon_duration(output, output / master)
                    if "mixlab-marathon-cues.private.json" in files:
                        # The HTML is regenerated from the *restored*, SHA-
                        # verified WAV/receipt + locally validated JSON, and
                        # must match the claimed printout byte-for-byte.
                        from .marathon_cue_sheet import create_cue_sheet
                        check_sheet = output / "marathon.cues.check.private.html"
                        try:
                            create_cue_sheet(
                                output / master,
                                output / "mixlab-marathon-cues.private.json",
                                check_sheet)
                            expected = hashlib.sha256(check_sheet.read_bytes()).digest()
                            observed = hashlib.sha256(
                                (output / "marathon.cues.private.html").read_bytes()).digest()
                            if expected != observed:
                                raise ValueError("Marathon printed cues differ from validated Stage notes")
                        finally:
                            check_sheet.unlink(missing_ok=True)
                    if "mixlab-marathon-master-choice.private.json" in files:
                        # The same portable member is checked against the
                        # *actually restored* selected master, not just the
                        # ZIP's unsigned file inventory.
                        from .marathon_master_review import bound_choice_for_master
                        bound_choice_for_master(
                            output / master,
                            output / "mixlab-marathon-master-choice.private.json")
                    for codec in ("mp3", "flac"):
                        name = "marathon." + codec
                        if name not in files:
                            continue
                        from .event_vault import _read_small_json
                        compressed = _read_small_json(
                            output / (name + ".receipt.private.json"))
                        if (not isinstance(compressed, dict) or
                                compressed.get("kind") != "mixlab-private-marathon-mobile-v1" or
                                compressed.get("source_wav_sha256") != files[master]["sha256"] or
                                compressed.get("output_sha256") != files[name]["sha256"] or
                                compressed.get("format") != codec or
                                compressed.get("private_local_use_only") is not True or
                                compressed.get("automatic_licensing") is not False):
                            raise ValueError("Portable compressed audio does not belong to the joined WAV")
                after = os.fstat(stream.fileno())
                if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                        after.st_ctime_ns) != (
                        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                        before.st_ctime_ns):
                    raise ValueError("Portable event archive changed while restoring")
                published = True
                return {
                    "restored_private_folder": str(output),
                    "full_set_wav": str(output / master),
                    "offline_event_dashboard": str(output / "index.html") if "index.html" in files else None,
                    "offline_event_rehearsal": str(output / "final-set.rehearsal.private.html")
                        if "final-set.rehearsal.private.html" in files else None,
                    "file_count": len(files),
                    "wav_sha256": files[master]["sha256"],
                    "continuous_marathon": master == "marathon.wav",
                    "offline_join_studio": str(output / "marathon.join-studio.private.html")
                        if master == "marathon.wav" and "marathon.join-studio.private.html" in files else None,
                    "offline_marathon_master_choice": str(output / "mixlab-marathon-master-choice.private.json")
                        if master == "marathon.wav" and "mixlab-marathon-master-choice.private.json" in files else None,
                    "offline_marathon_cues": str(output / "mixlab-marathon-cues.private.json")
                        if master == "marathon.wav" and "mixlab-marathon-cues.private.json" in files else None,
                    "offline_marathon_cue_sheet": str(output / "marathon.cues.private.html")
                        if master == "marathon.wav" and "marathon.cues.private.html" in files else None,
                    "private_mobile_audio": next((str(output / name)
                        for name in ("marathon.mp3", "marathon.flac") if name in files), None),
                    "offline_marathon_runbook": str(output / "marathon.runbook.private.html")
                        if master == "marathon.wav" and "marathon.runbook.private.html" in files else None,
                    "private": True, "network_uploads": False,
                    "archive_authenticity_proven": False,
                    "automatic_licensing": False
                }
    finally:
        if created and not published:
            # Remove only files created inside our brand-new private directory.
            for name in reversed(written):
                try:
                    (output / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                output.rmdir()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Unpack a trusted private MixLab event ZIP into a NEW offline folder, streaming and checking its internal SHA manifest")
    parser.add_argument("private_event_zip", help="Existing trusted private event ZIP")
    parser.add_argument("new_private_folder", help="NEW output folder, outside Git")
    args = parser.parse_args()
    try:
        result = restore_bundle(args.private_event_zip, args.new_private_folder)
    except (ValueError, TypeError, KeyError, OSError, EOFError,
            zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        # Local source names and sensitive paths are not echoed in error output.
        parser.exit(2, "MixLab private restore: invalid or unavailable event bundle; "
                       "no complete restored set was published.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
