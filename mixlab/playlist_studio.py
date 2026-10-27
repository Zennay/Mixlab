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
from .idea_board import prepare_board
from .cue_suggest import suggest as suggest_cues

MAX_PLAYLIST_TRACKS = 11
MAX_SPEC_BYTES = 1024 * 1024


def _check_paths(music_dir, manifest_path, destination, *, resume=False):
    source = Path(music_dir).absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Select an existing non-symlink music folder")
    source = source.resolve(strict=True)
    manifest = Path(manifest_path).absolute()
    if manifest.parent != source or manifest.suffix.lower() != ".json":
        raise ValueError("New private .json playlist manifest must be saved next to the music files")
    if manifest.is_symlink():
        raise ValueError("Manifest symlinks are forbidden")
    if resume:
        if not manifest.is_file() or not 0 < manifest.stat().st_size <= MAX_SPEC_BYTES:
            raise ValueError("Resume requires an existing bounded regular private source manifest")
    elif manifest.exists():
        raise ValueError("Never overwrite an existing music manifest")
    for item in (source, *source.parents):
        if (item / ".git").exists():
            raise ValueError("Local music must remain outside Git")
    project = _private_project_dir(destination, manifest)
    return source, manifest, project


def _positive_cue(value):
    return _float_between(0, 900)(value)


def create_playlist_manifest(music_directory, output_manifest, new_session,
                             *, read=input, write=print, beats=16, partition="development",
                             journey_plan=None, approval_file=None, approval_styles=None):
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
    approved = None
    if approval_file is not None:
        if journey_plan is None:
            raise ValueError("--approval-file requires --journey-plan")
        from .playlist_approval import load_approval
        approved = load_approval(source, journey_plan, approval_file, beats=beats)
    write("\nMIXLAB · PRIVATE PLAYLIST STUDIO")
    write("Select an ordered list of up to 11 rights-permitted local tracks.")
    write("All BPM, cue points and permissions must be supplied by you; no tempo is inferred.")
    for i, name in enumerate(files, 1):
        write(f"{i:>3}. {name}")
    pinned_bpm = {}
    if journey_plan is None:
        numbers = _ask(read, write,
                       "Playback order (2..11 distinct song numbers, comma-separated): ",
                       _selection(len(files)))
        if len(numbers) > MAX_PLAYLIST_TRACKS:
            raise ValueError("Maximum 11 songs (10 transitions) per private playlist")
        ordered = [files[i - 1] for i in numbers]
    else:
        from .journey import load_journey
        proposed = load_journey(source, journey_plan)
        ordered = [record["path"] for record in proposed]
        if len(ordered) > MAX_PLAYLIST_TRACKS or any(name not in files for name in ordered):
            raise ValueError("Journey includes unavailable local music")
        pinned_bpm = {record["path"]: record["bpm"] for record in proposed}
        write("\nSuggested energy journey (human notes, not automatic music analysis):")
        for index, record in enumerate(proposed, 1):
            write(f"  {index}. {record['path']} | {record['bpm']} BPM "
                  f"| annotated energy {record['energy']}/10")
        if read("Accept this exact suggested order? Type yes: ").strip().lower() != "yes":
            raise ValueError("Journey not approved; no playlist manifest created")
    catalog = []
    for i, name in enumerate(ordered, 1):
        write(f"\nSong {i}/{len(ordered)}: {name}")
        if journey_plan is None:
            bpm = _ask(read, write, "Manually verified BPM (30..300): ",
                       _float_between(30, 300))
        else:
            bpm = pinned_bpm[name]
            write(f"Using human-verified notes: {bpm} BPM; source hash checked.")
        if approved is None:
            first_downbeat = _ask(read, write,
                                  "Verified first downbeat seconds (blank if unknown): ",
                                  lambda s: None if not s else _positive_cue(s))
            rights = _ask(read, write, "Declared rights (synthetic / licensed / user-permitted / public-domain): ",
                          _rights)
            provenance = _ask(read, write, "Source provenance / your permission basis: ",
                              _nonblank)
        else:
            manual = approved["tracks"][i-1]
            if manual["path"] != name:
                raise ValueError("Approved track order differs from plan")
            first_downbeat = manual["first_downbeat_seconds"]
            rights = _rights(manual["rights"])
            provenance = _nonblank(manual["provenance"])
            write("Using explicitly supplied local human rights, provenance and downbeat fields.")
        song = _regular_source(source, name)
        sha, _identity = _fingerprint(song)
        if approved is not None and sha != manual["sha256"]:
            raise ValueError("Source changed since manual cue approval")
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
        if approved is None:
            a_start = _ask(read, write,
                           f"Outgoing A cue in seconds (>= {previous_incoming_end:g}): ", outgoing)
            b_start = _ask(read, write, "Incoming B cue in seconds: ", _positive_cue)
        else:
            approved_pair = approved["pairs"][i]
            a_start = outgoing(str(approved_pair["a_start_seconds"]))
            b_start = _positive_cue(str(approved_pair["b_start_seconds"]))
            write("Using manually checked source-bound A/B cues from approved private form.")
        if approved is not None and approved["pairs"][i]["family"] is not None:
            if approval_styles is not None:
                approval_styles.append(f"pair-{i+1:03d}:{approved['pairs'][i]['family']}")
        row = {"id": f"pair-{i+1:03d}",
               "a": catalog[i]["id"], "b": catalog[i+1]["id"],
               "bpm": catalog[i]["bpm"], "beats": beats,
               "a_start_seconds": a_start, "b_start_seconds": b_start}
        # Preserve a specifically approved render style WITH the immutable
        # manual cue pair, not in ephemeral CLI state lost on --resume.
        if approved is not None and approved["pairs"][i]["family"] is not None:
            row["approved_family"] = approved["pairs"][i]["family"]
        pairs.append(row)
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
                          timeout_seconds=600, partition="development",
                          resume=False, manifest_only=False, ideas=False,
                          full_set_wav=None, family="bass_swap", styles=(),
                          delivery=None, bitrate_kbps=192, journey_plan=None,
                          approval_file=None, plan_html=False, plan_verify_wavs=False):
    """Run the complete local product workflow after explicit human annotation."""
    if approval_file is not None and journey_plan is None:
        raise ValueError("--approval-file needs the original --journey-plan")
    if approval_file is not None and styles:
        raise ValueError("Choose render styles in the approval form OR via --style, not both")
    if resume and approval_file is not None:
        raise ValueError("--approval-file is only used on fresh manifest creation")
    if resume and journey_plan is not None:
        raise ValueError("--journey-plan is only for a fresh playlist, not --resume")
    if resume and manifest_only:
        raise ValueError("Choose either --resume or --manifest-only, never both")
    if plan_html and not manifest_only:
        raise ValueError("--plan-html requires --manifest-only")
    if plan_verify_wavs and not plan_html:
        raise ValueError("--plan-verify-wavs requires --plan-html")
    if manifest_only and ideas:
        raise ValueError("--ideas needs imported private audio; it cannot run with --manifest-only")
    if manifest_only and full_set_wav is not None:
        raise ValueError("--full-set-wav requires rendering and cannot use --manifest-only")
    if full_set_wav is None and styles:
        raise ValueError("--style requires --full-set-wav; no set is exported otherwise")
    if full_set_wav is None and delivery is not None:
        raise ValueError("--delivery requires --full-set-wav so the completed PCM master is preserved")
    source, manifest, destination = _check_paths(
        music_directory, output_manifest, new_session, resume=resume)
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 900:
        raise ValueError("Audio decoder timeout must be between 30 and 900 seconds")
    approved_styles = []
    if resume:
        write("Resuming the exact existing private playlist manifest without changing its cues.")
    else:
        create_playlist_manifest(source, manifest, destination, read=read, write=write,
                                 beats=beats, partition=partition, journey_plan=journey_plan,
                                 approval_file=approval_file, approval_styles=approved_styles)
    # Reject contradictory style overrides and invalid pinned decisions
    # before expensive import and Studio rendering, also during --resume.
    from .cueprep import _read_spec
    from .studio import FAMILY_NAMES
    pinned = {}
    for pair in _read_spec(manifest).get('pairs', []):
        locked = pair.get('approved_family')
        if locked is not None:
            if locked not in FAMILY_NAMES:
                raise ValueError('Invalid source-bound approved transition style')
            pinned[pair['id']] = locked
    for value in styles:
        if isinstance(value, str) and value.count(':') == 1:
            pid, requested = value.split(':', 1)
            if pid in pinned and pinned[pid] != requested:
                raise ValueError('Cannot silently override a previously approved transition style')
    idea_beats = None
    if ideas:
        with manifest.open("r", encoding="utf-8") as reader:
            manual_sources = json.load(reader)
        if not all(isinstance(x, dict) and "first_downbeat_seconds" in x
                   for x in manual_sources.get("tracks", [])):
            raise ValueError("--ideas requires a verified first downbeat on every chosen track")
        # A resumed playlist might use a different beat count from the CLI
        # default. Bind the RMS windows to the actual immutable pair specs,
        # never to an unrelated default.
        declared_pairs = manual_sources.get("pairs")
        if not isinstance(declared_pairs, list) or not declared_pairs:
            raise ValueError("No manually registered pairs for transition ideas")
        durations = {item.get("beats", 8) for item in declared_pairs
                     if isinstance(item, dict) and type(item.get("beats", 8)) is int}
        if len(durations) != 1 or len(declared_pairs) != sum(
                isinstance(item, dict) and type(item.get("beats", 8)) is int
                for item in declared_pairs):
            raise ValueError("--ideas needs one shared manually approved beat length per playlist")
        idea_beats = next(iter(durations))
        if not 1 <= idea_beats <= 64:
            raise ValueError("Idea duration must be in the canonical 1..64-beat range")
    if manifest_only:
        response = {"ready": True, "stage": "manual-playlist-manifest",
                    "private_source_manifest": str(manifest), "session_directory": None,
                    "private_plan_html": None, "planned_complete_wav": None,
                    "offline": True, "automatic_tempo_matching": False,
                    "music_preference_proven": False}
        if plan_html:
            # The proposed destination is not published. It can later be
            # passed to --full-set-wav, after the actual source is rechecked.
            suggested_wav = destination.parent / (destination.name + '.wav')
            try:
                from .party_mix import render_party_mix
                preview = render_party_mix(
                    manifest, destination, suggested_wav, family=family,
                    preview=True, verify_wavs=plan_verify_wavs,
                    preview_html=True)
            except (ValueError, TypeError, OSError, KeyError):
                # Preserve the irreplaceable manually entered cues/rights
                # even when this entirely optional companion cannot render.
                response['warnings'] = [
                    'Private manifest saved; optional plan page unavailable. '
                    'Correct the manifest or use standalone preview.']
            else:
                response['private_plan_html'] = preview['preview_html']
                response['planned_complete_wav'] = str(suggested_wav)
                response['planned_mix_seconds'] = (
                    preview['complete_mix_duration'] if plan_verify_wavs else None)
                write('Private playlist page ready. No session or audio rendered.')
        write("Manifest saved. Render later with the same command and --resume.")
        return response
    # Existing session admission and hash policies remain authoritative. It
    # also cleans up its own fresh output folder on decoding/render errors.
    studio = make_session(manifest, destination, timeout_seconds=timeout_seconds)
    normalized = destination / "sources" / "source_manifest.json"
    warnings = []
    editor = None
    composer = None
    idea_page = None
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
    if ideas:
        try:
            # Generate the same manually gridded number of beats as the actual
            # approved transition recipes, including --resume sessions.
            ideas_path = destination / "cue-suggestions.private.json"
            suggest_cues(normalized, ideas_path, beats=idea_beats)
            idea_page = prepare_board(
                normalized, ideas_path,
                destination / "sources" / "transition-ideas.html")
        except (ValueError, OSError, TypeError, KeyError) as exc:
            warnings.append("Optional cue idea board unavailable: " + str(exc))
    instant_set = None
    if full_set_wav is not None:
        try:
            # Explicit family selection, canonical WAV exporter, real PCM
            # chapter player; never masquerade a suggested style as AI ranking.
            from .instant_set import render_instant_set
            from .playlist_preview_page import local_song_title
            original = _read_spec(manifest)
            names = {entry['id']: local_song_title(entry['path'])
                     for entry in original['tracks']}
            instant_set = render_instant_set(destination, full_set_wav,
                                             family=family, styles=styles,
                                             delivery=delivery,
                                             bitrate_kbps=bitrate_kbps,
                                             display_names=names)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            warnings.append("Private Studio exists, but optional complete-set WAV failed: " + str(exc))
    with manifest.open("r", encoding="utf-8") as reader:
        summary = json.load(reader)
    payload = {"ready": True, "private_source_manifest": str(manifest),
               "session_directory": str(destination), "studio": str(studio),
               "visual_cue_editor": str(editor) if editor else None,
               "set_composer": str(composer) if composer else None,
               "transition_idea_board": str(idea_page) if idea_page else None,
               "instant_complete_set": instant_set,
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
    parser.add_argument("--journey-plan",
                        help="Private SHA-pinned energy journey suggestion; explicitly approve before cues")
    parser.add_argument("--approval-file",
                        help="Private SHA-bound human rights/cues exported from playlist_approval; requires --journey-plan")
    parser.add_argument("--beats", type=int, default=16,
                        help="Manually chosen transition beat count, shared by all pairs (1..64)")
    parser.add_argument("--partition", choices=("development", "evaluation"),
                        default="development")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--manifest-only", action="store_true",
                        help="Record the verified ordered playlist without decoding or rendering")
    parser.add_argument("--plan-html", action="store_true",
                        help="With --manifest-only: create a private visual playlist page without rendering audio")
    parser.add_argument("--plan-verify-wavs", action="store_true",
                        help="With --plan-html: verify original PCM16 WAVs and show the expected mix length")
    parser.add_argument("--resume", action="store_true",
                        help="Render a new private session from an existing unchanged source manifest")
    parser.add_argument("--ideas", action="store_true",
                        help="Suggest RMS-based manual-grid cue options and prepare an offline review board")
    parser.add_argument("--full-set-wav",
                        help="Optionally publish a complete private WAV and offline player in the same run")
    parser.add_argument("--family", default="bass_swap",
                        choices=("baseline", "bass_swap", "echo_exit", "hard_cut"),
                        help="Manually chosen style for all complete-set transitions")
    parser.add_argument("--style", action="append", default=[], metavar="PAIR:FAMILY",
                        help="Per-transition override for instant complete-set export; repeatable")
    parser.add_argument("--delivery",
                        help="Optional NEW .mp3 or .flac output, encoded locally from completed PCM master")
    parser.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320),
                        default=192, help="MP3 encoding bitrate; FLAC is lossless")
    args = parser.parse_args()
    try:
        result = build_playlist_studio(
            args.private_music_directory, args.new_source_manifest,
            args.new_session_directory, beats=args.beats, partition=args.partition,
            timeout_seconds=args.timeout_seconds,
            resume=args.resume, manifest_only=args.manifest_only,
            ideas=args.ideas, full_set_wav=args.full_set_wav,
            family=args.family, styles=args.style,
            delivery=args.delivery, bitrate_kbps=args.bitrate_kbps,
            journey_plan=args.journey_plan, approval_file=args.approval_file,
            plan_html=args.plan_html, plan_verify_wavs=args.plan_verify_wavs)
    except (ValueError, TypeError, OSError, EOFError, KeyboardInterrupt) as exc:
        parser.exit(2, f"MixLab Playlist Studio: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
