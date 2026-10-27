"""One command from locally permitted songs to a complete continuous WAV set.

This opt-in wrapper uses the already shipped private import -> cue -> Studio
renderer and the immutable manual continuous-set exporter. There are no
network calls, uploads, auto-selected cues or automatic tempo matching.
"""
from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

from .cueprep import _read_spec
from .session import _manual_cues_present, _private_project_dir, make_session
from .set_export import _unique_pairs, _valid_destination, export_set
from .studio import FAMILY_NAMES
from .set_player import publish_player


def render_party_mix(manifest, session_directory, output_wav, transitions=(),
                     *, family=None, timeout_seconds=600, suggestions=False,
                     preview=False, verify_wavs=False, preview_html=False,
                     preview_workflow='party_mix', preview_next_family=None):
    """Render the source Studio and chosen continuous set in one safe run.

    The expensive private Studio is deliberately retained if the final WAV
    fails: the caller can correct their selection and retry the export without
    re-importing private media. No preexisting files are modified.
    """
    if verify_wavs and not preview:
        raise ValueError("--verify-wavs requires --preview")
    if preview_html and not preview:
        raise ValueError("--preview-html requires --preview")
    source = Path(manifest).absolute()
    session_dir = _private_project_dir(session_directory, source)
    output = Path(output_wav).absolute()
    # Validate all cheap user-controlled destinations/selections BEFORE doing
    # CPU-heavy conversion; no partial output or session is created here.
    _valid_destination(output, session_dir)
    if output.is_relative_to(session_dir) or session_dir.is_relative_to(output):
        raise ValueError("The output WAV must be outside the private session directory")
    # Catch an impossible playlist before decoding any potentially expensive
    # local files. Final frame/hash admission still belongs to set_export.
    declared = _read_spec(source)
    _manual_cues_present(declared)
    pairs = declared.get("pairs")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 10:
        raise ValueError("A complete set needs 1..10 registered transitions")
    if family is not None:
        if transitions or family not in FAMILY_NAMES:
            raise ValueError("Choose either --family or explicit --transition values")
        selected = _unique_pairs([f"{pair['id']}:{family}" for pair in pairs])
    else:
        selected = _unique_pairs(transitions)
    # One-command *complete* sets must not silently omit registered songs,
    # start in the middle, reorder transitions or export only a subset.
    if [pid for pid, _ in selected] != [pair['id'] for pair in pairs]:
        raise ValueError("Select every registered transition in playlist order; no partial set")
    by_id = {}
    for pair in pairs:
        pid = pair.get("id")
        if not isinstance(pid, str) or pid in by_id:
            raise ValueError("Manifest has duplicate or invalid transition IDs")
        by_id[pid] = pair
    previous = None
    for pid, _family in selected:
        pair = by_id.get(pid)
        if pair is None:
            raise ValueError("Selected pair is not in the source manifest")
        if previous is not None and pair.get("a") != previous:
            raise ValueError("Selected pairs do not form an outgoing-to-incoming song route")
        previous = pair.get("b")
    # The human-selected style lives with its exact source pair. A generic
    # --family only fills unapproved pairs; explicit different pair choices
    # must be reapproved rather than silently replacing that decision.
    requested = []
    for pid, choice in selected:
        pinned = by_id[pid].get('approved_family')
        if pinned is not None and pinned not in FAMILY_NAMES:
            raise ValueError('Invalid source-bound approved transition family')
        if pinned is not None and family is None and choice != pinned:
            raise ValueError('Cannot silently override an approved transition style')
        requested.append((pid, pinned if pinned is not None else choice))
    selected = requested
    # All source tracks must appear exactly once, not just all pair IDs.
    catalog = declared.get('tracks')
    if not isinstance(catalog, list) or not 2 <= len(catalog) <= 11:
        raise ValueError('A complete mix needs 2..11 registered source tracks')
    ids = [t.get('id') for t in catalog if isinstance(t, dict)]
    route_ids = [by_id[selected[0][0]]['a']] + [by_id[pid]['b'] for pid, _ in selected]
    if (len(ids) != len(catalog) or
            any(not isinstance(i, str) or not i for i in ids) or
            len(ids) != len(set(ids)) or len(route_ids) != len(ids) or
            len(set(route_ids)) != len(route_ids) or set(route_ids) != set(ids)):
        raise ValueError('Complete playlist must use every declared track exactly once')
    # Cue overlap is a full-set failure, not merely a Studio validation.
    # Catch it now, before media import/real transition rendering starts.
    total_transition_seconds = 0.0
    next_available = 0.0
    manual_bpm = {t['id']: t['bpm'] for t in declared['tracks']}
    transitions_plan = []
    for index, (pid, style) in enumerate(selected, 1):
        pair = by_id[pid]
        bpm = manual_bpm[pair['a']]
        duration = pair.get('beats', 8) * 60.0 / bpm
        start = pair['a_start_seconds']
        if index > 1 and start + 1e-8 < next_available:
            raise ValueError('Outgoing cue overlaps the previous incoming transition; correct the manual cues')
        next_available = pair['b_start_seconds'] + duration
        total_transition_seconds += duration
        transitions_plan.append(dict(pair=pid, from_track=pair['a'], to_track=pair['b'],
                                     family=style, beats=pair.get('beats', 8),
                                     bpm=bpm, duration_seconds=round(duration, 4),
                                     outgoing_cue_seconds=start,
                                     incoming_cue_seconds=pair['b_start_seconds']))
    if suggestions:
        tracks = declared.get('tracks', [])
        if not all(isinstance(t, dict) and 'first_downbeat_seconds' in t for t in tracks):
            raise ValueError('Suggestions require a confirmed first downbeat per track')
    if preview:
        result = dict(status='manual-plan-preview-only-no-files-created',
                      source_tracks=len(route_ids), transition_count=len(selected),
                      track_order=route_ids, transitions=transitions_plan,
                      total_transition_seconds=round(total_transition_seconds, 4),
                      complete_mix_duration='not-known-until-source-PCM-validation',
                      audio_rendered=False, source_audio_validated=False,
                      source_rights_verified=False, automatic_beatmatching=False,
                      musical_quality_claim=False)
        if verify_wavs:
            from .playlist_wav_preview import inspect_playlist
            result.update(inspect_playlist(source, catalog, route_ids, transitions_plan))
        if preview_html:
            from .playlist_preview_page import publish, local_song_title
            # Browser-only labels: never expose a source directory or change
            # source IDs, the saved manifest, or the machine preview JSON.
            names = {entry['id']: local_song_title(entry['path']) for entry in catalog}
            result['preview_html'] = str(publish(result, output, display_names=names,
                                                 workflow=preview_workflow, next_family=preview_next_family))
            result['status'] = 'private-offline-plan-page-created-no-audio'
        return result
    # Full Studio must render every pair in order to satisfy user selections.
    studio_page = make_session(source, session_dir, suggestions=suggestions,
                               timeout_seconds=timeout_seconds)
    result = export_set(session_dir, output, [f"{p}:{family}" for p, family in selected])
    response = {"status": "continuous-private-set-created", "studio": str(studio_page),
                "continuous_wav": str(result),
                "private_receipt": str(result) + ".receipt.private.json",
                "transition_count": len(selected), "offline_player": None,
                "automatic_beatmatching": False, "musical_quality_claim": False}
    # Once the canonical mix and receipt have been published, the browser
    # player is optional. Preserve the complete WAV even if HTML fails.
    try:
        from .playlist_preview_page import local_song_title
        names = {entry['id']: local_song_title(entry['path']) for entry in catalog}
        response["offline_player"] = str(publish_player(
            session_dir, result, display_names=names))
    except (OSError, ValueError, TypeError, KeyError, wave.Error):
        # A player error may contain a private path; return a bounded message.
        response["player_warning"] = "Complete WAV is ready; optional local player unavailable"
    return response


def main():
    parser = argparse.ArgumentParser(
        description="One-command local permitted music -> transition Studio -> continuous WAV")
    parser.add_argument("source_manifest", help="Private SHA-pinned permitted local music manifest")
    parser.add_argument("new_session_directory", help="New private session directory outside source music and Git")
    parser.add_argument("new_output_wav", help="New destination .wav outside the session and Git")
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--family", choices=tuple(FAMILY_NAMES),
                         help="One manually chosen transition style for every registered pair")
    choices.add_argument("--transition", action="append", metavar="PAIR:FAMILY",
                         help="Choose all registered pairs in order, repeat for each transition")
    parser.add_argument("--timeout-seconds", type=int, default=600,
                        help="Allowed FFmpeg processing time per input track, 30..900 seconds")
    parser.add_argument("--suggestions", action="store_true",
                        help="Make independent manual-grid energy proposals without applying them")
    parser.add_argument("--preview", action="store_true",
                        help="Show the manual track route, cue times and styles without creating audio or files")
    parser.add_argument("--verify-wavs", action="store_true",
                        help="With --preview: check canonical PCM16 WAV hashes and calculate the exact full-set duration")
    parser.add_argument("--preview-html", action="store_true",
                        help="With --preview: write a private standalone tracklist page beside the planned output WAV")
    args = parser.parse_args()
    try:
        result = render_party_mix(args.source_manifest, args.new_session_directory,
                                  args.new_output_wav, args.transition or (), family=args.family,
                                  timeout_seconds=args.timeout_seconds,
                                  suggestions=args.suggestions, preview=args.preview,
                                  verify_wavs=args.verify_wavs,
                                  preview_html=args.preview_html)
    except (ValueError, TypeError, OSError, KeyError) as exc:
        parser.exit(2, f"MixLab party mix: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
