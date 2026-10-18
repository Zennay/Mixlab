"""One-command private event production from an approved human DJ journey.

Publish real canonical WAV + player + optional compressed delivery + operator
runbook. This only orchestrates existing source admission, MixLab renderer and
receipts; it does not decode in browsers, infer licenses, or close M1 gates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from .journey import _source_root, _private_json_path, _read_json
from .playlist_approval import KIND as APPROVAL_KIND, load_approval
from .playlist_studio import build_playlist_studio
from .show_runbook import create_runbook
from .studio import FAMILY_NAMES

ROOT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,59}\Z")
CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")


def _check_output_root(private_music, new_root):
    """Reject Git, symlink, hidden/root traversal and existing destinations."""
    destination = Path(new_root).absolute()
    if (not ROOT_NAME.fullmatch(destination.name)
            or destination.name in (".", "..") or
            destination.exists() or destination.is_symlink()):
        raise ValueError("Choose a NEW simple-named output folder outside music and Git")
    if destination.is_relative_to(private_music):
        raise ValueError("Final event audio and session must stay outside the music library")
    if not destination.parent.is_dir():
        raise ValueError("Create the private output parent before this command")
    for path in (destination, *destination.parents):
        if path.is_symlink() or (path / ".git").exists():
            raise ValueError("No symlink destination or private rendered audio inside Git")
    return destination


def publish_event(music_folder, private_plan, private_approval, new_output_root,
                  *, family="bass_swap", delivery=None, bitrate_kbps=192,
                  start=None, timeout_seconds=600, read=input, write=print):
    """Compile one human-approved DJ event into a single NEW private folder.

    The source manifest must remain in the music folder because the canonical
    media importer resolves only SHA-bound relative filenames from that root.
    The new session and complete WAV are siblings, because the official
    continuous-set exporter forbids WAV publication inside a Studio session.
    """
    source = _source_root(music_folder)
    plan = _private_json_path(source, private_plan, existing=True)
    approval = _private_json_path(source, private_approval, existing=True)
    if plan == approval:
        raise ValueError("Private journey and approval must be different files")
    target = _check_output_root(source, new_output_root)
    if family not in FAMILY_NAMES:
        raise ValueError("Choose an existing canonical DSP transition family")
    if delivery not in (None, "mp3", "flac"):
        raise ValueError("Choose optional MP3 or FLAC delivery, not arbitrary codecs")
    if type(bitrate_kbps) is not int or bitrate_kbps not in (128, 192, 256, 320):
        raise ValueError("MP3 output must use an allowed bitrate")
    if start is not None and (not isinstance(start, str) or not CLOCK.fullmatch(start)):
        raise ValueError("Planned start time must be HH:MM in your local timezone")
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 900:
        raise ValueError("Local audio decoder timeout must be 30–900 seconds")

    data, _ = _read_json(approval)
    beats = data.get("beats")
    if data.get("kind") != APPROVAL_KIND or type(beats) is not int:
        raise ValueError("Use the original explicit private human cue approval file")
    # Validate the exact bound plan/approval and rehash local music BEFORE
    # creating any output folder or source manifest.
    load_approval(source, plan, approval, beats=beats)

    manifest = source / ("mixlab-" + target.name + ".sources.private.json")
    if manifest.exists() or manifest.is_symlink():
        raise ValueError("This event's source manifest already exists; use a fresh output folder name")

    # Private 0700 event container. Never remove it on optional failures:
    # surviving manifest, Studio and real master may support explicit recovery.
    target.mkdir(mode=0o700)
    session = target / "studio-session"
    wav = target / "final-set.wav"
    encoded = target / ("final-set." + delivery) if delivery else None
    write("MixLab private event production: all sources remain local.")
    write("Only actual, human-approved source rights, track order and cues are admissible.")
    studio = build_playlist_studio(
        source, manifest, session,
        read=read, write=write, beats=beats, timeout_seconds=timeout_seconds,
        partition="development", resume=False, manifest_only=False,
        full_set_wav=wav, family=family, styles=(),
        delivery=encoded, bitrate_kbps=bitrate_kbps,
        journey_plan=plan, approval_file=approval,
    )

    # The underlying Studio is deliberately permitted to retain its expensive
    # successfully rendered work if optional continuous-set compilation fails.
    # This higher-level user command must NOT misreport a missing WAV as ready.
    set_data = studio.get("instant_complete_set")
    if not isinstance(set_data, dict) or set_data.get("continuous_set") != str(wav):
        warning = "; ".join(studio.get("warnings", []))
        raise ValueError(
            "The private Studio exists but no complete event WAV was published. "
            "Keep the source manifest/session for an explicit recovery. " +
            (warning[:500] if warning else "Check the original Studio output.")
        )

    runbook = None
    warnings = list(studio.get("warnings", []))
    if set_data.get("delivery_warning"):
        warnings.append(set_data["delivery_warning"])
    if set_data.get("player_warning"):
        warnings.append(set_data["player_warning"])
    try:
        runbook = create_runbook(
            session, wav, target / "final-set.runbook.private.html", start=start
        )
    except (ValueError, TypeError, OSError, KeyError) as exc:
        # A successfully produced WAV must NEVER be deleted or masquerade as
        # incomplete because the optional operator companion cannot publish.
        warnings.append("Full WAV exists; optional event runbook unavailable: " + str(exc))

    return {
        "ready": True,
        "kind": "mixlab-private-approved-full-event",
        "private_event_folder": str(target),
        "private_source_manifest": str(manifest),
        "session": str(session),
        "full_set_wav": str(wav),
        "offline_full_set_player": set_data.get("offline_player"),
        "offline_show_runbook": str(runbook) if runbook else None,
        "compressed_delivery": set_data.get("compressed_delivery"),
        "selected_transitions": set_data.get("transitions"),
        "warnings": warnings,
        "offline": True,
        "source_uploads": False,
        "automatic_tempo_matching": False,
        "human_preference_proven": False,
        "automatic_licensing": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Publish a rights-declared, manually cued DJ event as real WAV, player, showbook and optional MP3/FLAC")
    parser.add_argument("private_music_directory", help="Permitted music folder, outside Git")
    parser.add_argument("private_journey_plan", help="Exact private SHA-bound DJ plan")
    parser.add_argument("private_cue_approval", help="Exact bound local rights + cue approval file")
    parser.add_argument("new_output_folder", help="NEW private event folder outside music and Git")
    parser.add_argument("--family", choices=tuple(FAMILY_NAMES), default="bass_swap",
                        help="DSP fallback for pairs not assigned an explicit style in the approval form")
    parser.add_argument("--delivery", choices=("mp3", "flac"),
                        help="Optional additional portable output from the completed WAV; needs installed FFmpeg")
    parser.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320), default=192)
    parser.add_argument("--start", help="Optional HH:MM local show start for the offline runbook")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        result = publish_event(
            args.private_music_directory, args.private_journey_plan,
            args.private_cue_approval, args.new_output_folder,
            family=args.family, delivery=args.delivery,
            bitrate_kbps=args.bitrate_kbps, start=args.start,
            timeout_seconds=args.timeout_seconds,
        )
    except (ValueError, TypeError, KeyError, OSError, EOFError, KeyboardInterrupt) as exc:
        parser.exit(2, "MixLab event production: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
