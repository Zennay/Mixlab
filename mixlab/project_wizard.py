"""Guided local source manifest creator for the one-command MixLab session.

No BPM, rights, musical source timing, or licensing facts are inferred.
All sensitive source paths and hashes stay in a local private JSON file.
"""
from __future__ import annotations

from .private_output import write_private_new

import argparse
import json
import os
from pathlib import Path
import re
import stat

from .cueprep import _number
from .media_import import (
    SOURCE_FORMATS, MAX_INPUT_BYTES, OUTPUT_RATE, _fingerprint,
    _regular_source,
)
from .ingest import MAX_FRAMES, RIGHTS


MAX_DIRECTORY_FILES = 200
MAX_PROMPT_ATTEMPTS = 12


def _ask(reader, writer, label, validate):
    for _ in range(MAX_PROMPT_ATTEMPTS):
        answer = reader(label).strip()
        try:
            return validate(answer)
        except (ValueError, TypeError):
            writer("Invalid answer; check the requested format and try again.")
    raise ValueError("Too many invalid answers; no manifest has been written")


def _integer_between(minimum, maximum):
    def check(value):
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("Expected a whole number")
        n = int(value)
        if not minimum <= n <= maximum:
            raise ValueError("Integer out of range")
        return n
    return check


def _float_between(minimum, maximum):
    def check(value):
        try:
            n = float(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError("Expected a number") from exc
        return _number(n, "manual value", minimum, maximum)
    return check


def _selection(maximum):
    def check(value):
        pieces = [s.strip() for s in value.split(",")]
        indexes = [_integer_between(1, maximum)(s) for s in pieces]
        # Numeric aliases (01 and 1) are the same local song. Compare
        # canonical indices rather than raw prompt spellings.
        if len(indexes) != len(set(indexes)):
            raise ValueError("Each song can be selected once")
        if not 2 <= len(indexes) <= 20:
            raise ValueError("Select 2..20 songs")
        return indexes
    return check


def _nonblank(value):
    if not value or len(value) > 300 or any(ord(c) < 32 for c in value):
        raise ValueError("Required short text")
    return value


def _rights(value):
    if value not in RIGHTS:
        raise ValueError("Unsupported rights declaration")
    return value


def _media_listing(source_root):
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("Choose a non-symlink private music directory")
    files = []
    with os.scandir(source_root) as listing:
        for number, record in enumerate(listing):
            if number >= MAX_DIRECTORY_FILES:
                raise ValueError("Directory has too many files; choose a smaller private folder (<=200 entries)")
            try:
                info = record.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError("Music directory changed while listing") from exc
            if (stat.S_ISREG(info.st_mode) and
                    Path(record.name).suffix.lower() in SOURCE_FORMATS and
                    not any(ord(c) < 32 for c in record.name) and
                    0 < info.st_size <= MAX_INPUT_BYTES):
                files.append(record.name)
    files.sort(key=str.casefold)
    if len(files) < 2:
        raise ValueError("Need at least two supported local audio files")
    return files


def create_manifest(source_directory, output_manifest, *,
                    read=input, write=print, partition="development"):
    """Interactively create a private media-import manifest without guessing.

    output_manifest MUST be in the same folder as the selected source files,
    because the imported library uses local relative filenames.
    """
    if partition not in ("development", "evaluation"):
        raise ValueError("Partition must be development or evaluation")
    # Resolve only after rejecting a user-selected symlink: resolving first
    # erased the very alias that _media_listing intended to refuse.
    requested_root = Path(source_directory).absolute()
    if requested_root.is_symlink():
        raise ValueError("Choose a non-symlink private music directory")
    source_root = requested_root.resolve(strict=True)
    output = Path(output_manifest).absolute()
    if output.parent != source_root or output.suffix.lower() != ".json":
        raise ValueError("Save the new .json manifest in the music directory")
    if output.exists() or output.is_symlink():
        raise ValueError("Never overwrite a source manifest")
    for ancestor in (source_root, *source_root.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Keep music and generated manifests outside Git")
    files = _media_listing(source_root)
    write("MixLab private project wizard — local music only")
    write("Only process media you have permission to use. BPM and cue points must be checked manually.")
    for index, name in enumerate(files, 1):
        write(f"{index:>3}. {name}")
    indexes = _ask(read, write, "Select 2..20 song numbers separated by commas: ",
                   _selection(len(files)))
    choices = [files[i - 1] for i in indexes]
    tracks = []
    write("For each chosen song, provide actual BPM, source rights and provenance.")
    for index, name in enumerate(choices, 1):
        write(f"Song {index}/{len(choices)}: {name}")
        bpm = _ask(read, write, "Verified BPM (30..300): ", _float_between(30, 300))
        first_downbeat = _ask(read, write,
                              "Verified first downbeat in seconds (blank to skip): ",
                              lambda value: None if not value else _float_between(0, 900)(value))
        rights = _ask(read, write,
                      "Rights (synthetic / licensed / user-permitted / public-domain): ",
                      _rights)
        provenance = _ask(read, write, "Source provenance (required): ", _nonblank)
        source = _regular_source(source_root, name)
        sha, _ = _fingerprint(source)
        track = {"id": f"track-{index:03d}", "path": name,
                 "sha256": sha, "bpm": bpm, "rights": rights,
                 "provenance": provenance, "partition": partition,
                 "recording_id": f"recording-{index:03d}"}
        if first_downbeat is not None:
            track["first_downbeat_seconds"] = first_downbeat
        tracks.append(track)
    write("Select A and B from this verified local track set:")
    for index, track in enumerate(tracks, 1):
        write(f"{index}. {choices[index - 1]} | {track['bpm']} BPM | {track['id']}")
    pair_count = _ask(read, write, "Number of transition pairs (1..10): ",
                      _integer_between(1, 10))
    pairs = []
    for k in range(pair_count):
        write(f"Pair {k + 1}/{pair_count}")
        a_index = _ask(read, write, "Outgoing track number: ",
                       _integer_between(1, len(tracks)))
        def target_index(value):
            chosen = _integer_between(1, len(tracks))(value)
            if chosen == a_index or tracks[chosen - 1]["bpm"] != tracks[a_index - 1]["bpm"]:
                raise ValueError("Distinct track with matching manually verified BPM required")
            return chosen
        b_index = _ask(read, write, "Incoming track number (matching BPM): ", target_index)
        bpm = tracks[a_index - 1]["bpm"]
        beats = _ask(read, write, "Transition beat count (1..64, try 16): ",
                     _integer_between(1, 64))
        if not 2 <= round(beats * 60 / bpm * OUTPUT_RATE) <= MAX_FRAMES:
            raise ValueError("This combination exceeds the canonical renderer frame budget")
        a_start = _ask(read, write, "Outgoing cue start seconds (verified by listening): ",
                       _float_between(0, 900))
        b_start = _ask(read, write, "Incoming cue start seconds (verified by listening): ",
                       _float_between(0, 900))
        pairs.append({"id": f"pair-{k + 1:03d}",
                      "a": tracks[a_index - 1]["id"],
                      "b": tracks[b_index - 1]["id"],
                      "bpm": bpm, "beats": beats,
                      "a_start_seconds": a_start, "b_start_seconds": b_start})
    data = {"schema_version": 1, "purpose": "development-pilot"
            if partition == "development" else "frozen-evaluation-preparation",
            "tracks": tracks, "pairs": pairs}
    raw = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > 1024 * 1024:
        raise ValueError("Manifest exceeds private parser limit")
    write_private_new(output, raw)
    write("Private manifest created. You can now run mixlab.session using this JSON file.")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Guide local rights/BPM/cue entry and build a SHA-pinned MixLab source manifest")
    parser.add_argument("music_directory", help="Private local folder of permitted audio files")
    parser.add_argument("manifest", help="New .json file in the same directory; not already existing")
    parser.add_argument("--partition", choices=("development", "evaluation"),
                        default="development")
    args = parser.parse_args()
    try:
        result = create_manifest(args.music_directory, args.manifest,
                                 partition=args.partition)
    except (ValueError, TypeError, OSError, EOFError, KeyboardInterrupt) as exc:
        parser.exit(2, "MixLab wizard: cancelled or invalid input; no existing files overwritten\n")
    print(json.dumps({"ready": True, "private_manifest": str(result),
                      "next": "python3 -m mixlab.session <manifest> <new-private-project-directory>"}))


if __name__ == "__main__":
    main()
