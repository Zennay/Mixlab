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
import wave

from .cueprep import _number
from .media_import import (
    SOURCE_FORMATS, MAX_INPUT_BYTES, OUTPUT_RATE, _fingerprint,
    _regular_source, _file_identity,
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


def _wav_frame_bounds(source, expected_identity):
    """Inspect a SHA-pinned WAV header without following changed source links.

    Only uncompressed PCM16 has a verified sample window at wizard time.
    Other formats are explicitly deferred to the canonical local decoder.
    """
    if source.suffix.lower() != ".wav":
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise ValueError("Selected media changed during WAV cue inspection") from exc
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or _file_identity(before) != expected_identity:
            raise ValueError("Selected media changed during WAV cue inspection")
        try:
            with wave.open(handle, "rb") as audio:
                channels, width, rate, frames, compression, _ = audio.getparams()
        except (wave.Error, EOFError):
            return None
        after = os.fstat(handle.fileno())
    try:
        current = source.lstat()
    except OSError as exc:
        raise ValueError("Selected media changed during WAV cue inspection") from exc
    if (_file_identity(before) != _file_identity(after) or
            _file_identity(before) != _file_identity(current) or
            not stat.S_ISREG(current.st_mode)):
        raise ValueError("Selected media changed during WAV cue inspection")
    if channels not in (1, 2) or width != 2 or compression != "NONE" or not 8000 <= rate <= 96000:
        return None
    return (rate, frames)


def create_manifest(source_directory, output_manifest, *,
                    read=input, write=print, partition="development",
                    adjacent_playlist=False):
    """Interactively create a private media-import manifest without guessing.

    output_manifest MUST be in the same folder as the selected source files,
    because the imported library uses local relative filenames.
    """
    if partition not in ("development", "evaluation"):
        raise ValueError("Partition must be development or evaluation")
    if type(adjacent_playlist) is not bool:
        raise ValueError("Adjacent playlist must be a boolean")
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
    if adjacent_playlist and len(indexes) > 11:
        raise ValueError("Adjacent playlist accepts at most 11 songs (10 pairs)")
    choices = [files[i - 1] for i in indexes]
    tracks = []
    verified_wav_bounds = []
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
        sha, identity = _fingerprint(source)
        verified_wav_bounds.append(_wav_frame_bounds(source, identity))
        track = {"id": f"track-{index:03d}", "path": name,
                 "sha256": sha, "bpm": bpm, "rights": rights,
                 "provenance": provenance, "partition": partition,
                 "recording_id": f"recording-{index:03d}"}
        if first_downbeat is not None:
            track["first_downbeat_seconds"] = first_downbeat
        tracks.append(track)
    if adjacent_playlist:
        pair_count = len(tracks) - 1
        write("Preserving the selected playlist order; adjacent songs become pairs.")
        write("BPM compatibility and cue points remain manually verified.")
    else:
        write("Select A and B from this verified local track set:")
        for index, track in enumerate(tracks, 1):
            write(f"{index}. {choices[index - 1]} | {track['bpm']} BPM | {track['id']}")
        pair_count = _ask(read, write, "Number of transition pairs (1..10): ",
                          _integer_between(1, 10))
    pairs = []
    for k in range(pair_count):
        write(f"Pair {k + 1}/{pair_count}")
        if adjacent_playlist:
            a_index, b_index = k + 1, k + 2
            if tracks[a_index - 1]["bpm"] != tracks[b_index - 1]["bpm"]:
                raise ValueError(
                    f"Adjacent songs {a_index} and {b_index} have different verified BPM; "
                    "no transition or source manifest was guessed"
                )
        else:
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
        # Catch impossible WAV cue windows before publishing a manifest which
        # the local excerpt renderer would reject. Never guess compressed-media
        # duration, source BPM, musical cues or license authority.
        for song_index, cue in ((a_index, a_start), (b_index, b_start)):
            bounds = verified_wav_bounds[song_index - 1]
            if bounds is not None:
                rate, frame_count = bounds
                start_frame = round(cue * rate)
                transition_frames = round(beats * 60 / bpm * rate)
                if start_frame + transition_frames > frame_count:
                    raise ValueError(
                        f"Cue window for song {song_index} is outside verified WAV duration; "
                        "no source manifest was published"
                    )
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


class _PrivateManifestParser(argparse.ArgumentParser):
    """Do not copy private music paths or invalid CLI values to logs."""
    def error(self, message):
        self.exit(2, "MixLab wizard: invalid arguments (private details withheld); see --help\n")


def main():
    parser = _PrivateManifestParser(
        description="Guide local rights/BPM/cue entry and build a SHA-pinned MixLab source manifest")
    parser.add_argument("music_directory", help="Private local folder of permitted audio files")
    parser.add_argument("manifest", help="New .json file in the same directory; not already existing")
    parser.add_argument("--partition", choices=("development", "evaluation"),
                        default="development")
    parser.add_argument("--adjacent-playlist", action="store_true",
                        help="Connect neighboring selected songs in order, with manual cue entry (2..11 songs)")
    args = parser.parse_args()
    try:
        result = create_manifest(args.music_directory, args.manifest,
                                 partition=args.partition, adjacent_playlist=args.adjacent_playlist)
    except (ValueError, TypeError, OSError, EOFError, KeyboardInterrupt) as exc:
        parser.exit(2, "MixLab wizard: cancelled or invalid input; no existing files overwritten\n")
    print(json.dumps({"ready": True, "private_manifest": str(result),
                      "next": "python3 -m mixlab.session <manifest> <new-private-project-directory>"}))


if __name__ == "__main__":
    main()
