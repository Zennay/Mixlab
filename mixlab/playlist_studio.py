"""One-command local DJ playlist wizard -> immutable Studio -> Set Composer.

The DJ explicitly chooses the playback order, confirms BPM, rights and cue
points; no automatic music discovery, source upload or implicit tempo matching.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .cue_editor import prepare as prepare_visual_editor
from .ingest import MAX_FRAMES
from .media_import import OUTPUT_RATE, _fingerprint, _regular_source
from .project_wizard import (
    _ask, _float_between, _integer_between, _media_listing, _nonblank,
    _rights, _selection,
)
from .session import _private_project_dir, make_session
from .set_composer import create_composer

MAX_PLAYLIST_TRACKS = 11
MAX_SPEC_BYTES = 1024 * 1024


def _check_paths(music_dir, manifest_path, destination):
    source = Path(music_dir).absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Select an existing non-symlink music folder")
    source = source.resolve(strict=True)
    manifest = Path(manifest_path).absolute()
    if manifest.parent != source or manifest.suffix.lower() != ".json":
        raise ValueError("New private .json playlist manifest must be saved next to the music files")
    if manifest.exists() or manifest.is_symlink():
        raise ValueError("Never overwrite an existing music manifest")
    for item in (source, *source.parents):
        if (item / ".git").exists():
            raise ValueError("Local music must remain outside Git")
    project = _private_project_dir(destination, manifest)
    return source, manifest, project


def _positive_cue(value):
    return _float_between(0, 900)(value)


def create_playlist_manifest(music_directory, output_manifest, new_session,
                             *, read=input, write=print, beats=16, partition="development"):
    """Capture an ordered rights-permitted private playlist and every manual cue.

    Cheap input checks run before touching the local song collection. Sources
    are read only to SHA-256 pin the exact bytes; they are never copied here.
    """
    if type(beats) is not int or not 1 <= beats <= 64:
        raise ValueError("Use a valid 1..64-beat transition duration")
    if partition not in ("development", "evaluation"):
        raise ValueError("Invalid dataset partition")
    source, manifest_path, project = _check_paths(music_directory, output_manifest, new_session)
    files = _media_listing(source)
    write("\nMIXLAB · PRIVATE PLAYLIST STUDIO")
    write("Select an ordered list of up to 11 rights-permitted local tracks.")
    write("All BPM, cue points and permissions must be supplied by you; no tempo is inferred.")
    for i, name in enumerate(files, 1):
        write(f"{i:>3}. {name}")
    numbers = _ask(read, write,
                   "Playback order (2..11 distinct song numbers, comma-separated): ",
                   _selection(len(files)))
    if len(numbers) > MAX_PLAYLIST_TRACKS:
        raise ValueError("Maximum 11 songs (10 transitions) per private playlist")
    ordered = [files[i - 1] for i in numbers]
    catalog = []
    for i, name in enumerate(ordered, 1):
        write(f"\nSong {i}/{len(ordered)}: {name}")
        bpm = _ask(read, write, "Manually verified BPM (30..300): ",
                   _float_between(30, 300))
        first_downbeat = _ask(read, write,
                              "Verified first downbeat seconds (blank if unknown): ",
                              lambda s: None if not s else _positive_cue(s))
        rights = _ask(read, write, "Declared rights (synthetic / licensed / user-permitted / public-domain): ",
                      _rights)
        provenance = _ask(read, write, "Source provenance / your permission basis: ",
                          _nonblank)
        song = _regular_source(source, name)
        sha, _identity = _fingerprint(song)
        item = {"id": f"track-{i:03d}", "path": name, "sha256": sha,
                "bpm": bpm, "rights": rights, "provenance": provenance,
                "partition": partition, "recording_id": f"recording-{i:03d}"}
        if first_downbeat is not None:
            item["first_downbeat_seconds"] = first_downbeat
        catalog.append(item)
    for i in range(len(catalog) - 1):
        if catalog[i]["bpm"] != catalog[i + 1]["bpm"]:
            raise ValueError(
                "Adjacent songs have different manually verified BPM. "
                "The current M1 renderer cannot stretch audio; change the ordered playlist.")
    length_seconds = beats * 60 / catalog[0]["bpm"]
    if not 2 <= round(length_seconds * OUTPUT_RATE) <= MAX_FRAMES:
        raise ValueError("Selected beat duration exceeds the existing PCM renderer limit")
    pairs = []
    write("\nConfirm the start time of each outgoing and incoming song.")
    write("A cue start is the FIRST sample used in that transition; never guessed.")
    previous_incoming_end = 0.
    for i in range(len(catalog) - 1):
        write(f"\nTransition {i + 1}/{len(catalog)-1}: {ordered[i]}  →  {ordered[i+1]}")
        def outgoing(raw):
            value = _positive_cue(raw)
            if value + 1e-8 < previous_incoming_end:
                raise ValueError("Outgoing cue backtracks before the previous incoming transition ends")
            return value
        a_start = _ask(read, write,
                       f"Outgoing A cue in seconds (>= {previous_incoming_end:g}): ", outgoing)
        b_start = _ask(read, write, "Incoming B cue in seconds: ", _positive_cue)
        pairs.append({"id": f"pair-{i+1:03d}",
                      "a": catalog[i]["id"], "b": catalog[i+1]["id"],
                      "bpm": catalog[i]["bpm"], "beats": beats,
                      "a_start_seconds": a_start, "b_start_seconds": b_start})
        previous_incoming_end = b_start + length_seconds
    spec = {"schema_version": 1, "purpose": "development-pilot"
            if partition == "development" else "frozen-evaluation-preparation",
            "tracks": catalog, "pairs": pairs}
    raw = (json.dumps(spec, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_SPEC_BYTES:
        raise ValueError("Private source manifest exceeds 1 MiB")
    # Constructing the manifest is a separate durable product operation: if
    # decoding later fails, the user can retry with this exact unchanged spec.
    with manifest_path.open("xb") as target:
        os.fchmod(target.fileno(), 0o600)
        target.write(raw)
    write(f"\nSaved {len(catalog)} SHA-bound songs and {len(pairs)} manual transitions: {manifest_path}")
    write("Only permitted local material will be imported; sources remain untouched.")
    return manifest_path


def build_playlist_studio(music_directory, output_manifest, new_session,
                          *, read=input, write=print, beats=16,
                          timeout_seconds=600, partition="development"):
    """Run the complete local product workflow after explicit human annotation."""
    source, manifest, destination = _check_paths(
        music_directory, output_manifest, new_session)
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 900:
        raise ValueError("Audio decoder timeout must be between 30 and 900 seconds")
    create_playlist_manifest(source, manifest, destination, read=read, write=write,
                             beats=beats, partition=partition)
    # Existing session admission and hash policies remain authoritative. It
    # also cleans up its own fresh output folder on decoding/render errors.
    studio = make_session(manifest, destination, timeout_seconds=timeout_seconds)
    normalized = destination / "sources" / "source_manifest.json"
    warnings = []
    editor = None
    composer = None
    # The already rendered private Studio is a complete usable result even
    # if optional HTML entry points cannot be written (e.g. too many samples
    # for the visual waveform page). Never delete that expensive session.
    try:
        editor = prepare_visual_editor(normalized, destination / "sources" / "cue-editor.html")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        warnings.append("Optional cue editor unavailable: " + str(exc))
    try:
        composer = create_composer(destination)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        warnings.append("Optional Set Composer unavailable: " + str(exc))
    with manifest.open("r", encoding="utf-8") as reader:
        summary = json.load(reader)
    payload = {"ready": True, "private_source_manifest": str(manifest),
               "session_directory": str(destination), "studio": str(studio),
               "visual_cue_editor": str(editor) if editor else None,
               "set_composer": str(composer) if composer else None,
               "tracks": len(summary["tracks"]), "transition_pairs": len(summary["pairs"]),
               "warnings": warnings, "offline": True,
               "automatic_tempo_matching": False, "music_preference_proven": False}
    write("Playlist Studio rendered. Open the Set Composer or the fallback Studio page.")
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Guided offline manual playlist -> real rendered Studio -> Set Composer")
    parser.add_argument("private_music_directory", help="Local folder of permitted WAV/MP3/FLAC/etc.")
    parser.add_argument("new_source_manifest", help="New private JSON inside the music directory")
    parser.add_argument("new_session_directory", help="New private session directory outside music/Git")
    parser.add_argument("--beats", type=int, default=16,
                        help="Manually chosen transition beat count, shared by all pairs (1..64)")
    parser.add_argument("--partition", choices=("development", "evaluation"),
                        default="development")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        result = build_playlist_studio(
            args.private_music_directory, args.new_source_manifest,
            args.new_session_directory, beats=args.beats, partition=args.partition,
            timeout_seconds=args.timeout_seconds)
    except (ValueError, TypeError, OSError, EOFError, KeyboardInterrupt) as exc:
        parser.exit(2, f"MixLab Playlist Studio: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
