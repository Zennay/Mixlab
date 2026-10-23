"""Complete offline cue-idea production flow: propose -> approve -> new Studio.

Builds on admitted private session receipts, the existing manual-grid sampled-
RMS cue generator and the existing real M1 renderer. Never rewrites original
songs, receipts, selected cue files or a frozen evaluation/holdout session.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .cueprep import _read_spec
from .cue_editor import prepare as prepare_visual_editor
from .cue_suggest import suggest as suggest_cues
from .idea_board import _build_pairs, apply_board, prepare_board
from .session import _private_project_dir, make_session
from .set_composer import _session_catalog, create_composer

PREFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")


def _paths(session, prefix):
    if not isinstance(prefix, str) or not PREFIX.fullmatch(prefix):
        raise ValueError("Choose a short safe filename prefix (letters, digits, _ or -)")
    root, _catalog = _session_catalog(session)
    manifest = root / "sources" / "source_manifest.json"
    return (root, manifest, root / f"{prefix}-suggestions.private.json",
            root / "sources" / f"{prefix}-board.html",
            root / "sources" / f"{prefix}-approved.private.json")


def _admit_manual_grid(manifest):
    """Require human-verified downbeats and a common beats-per-transition."""
    data = _read_spec(manifest)
    if data.get("purpose") != "development-pilot":
        raise ValueError("Creative cue ideas require a development-only session; no frozen study")
    tracks, pairs = data.get("tracks"), data.get("pairs")
    if (not isinstance(tracks, list) or not isinstance(pairs, list)
            or not 2 <= len(tracks) <= 20 or not 1 <= len(pairs) <= 10):
        raise ValueError("Expected 2..20 private tracks and 1..10 registered pairs")
    if not all(isinstance(t, dict) and t.get("partition") == "development" and
               "first_downbeat_seconds" in t for t in tracks):
        raise ValueError(
            "Enter verified first_downbeat_seconds for EVERY source track before "
            "asking for manual-grid ideas. Never guess missing downbeats.")
    beats = set()
    for pair in pairs:
        if not isinstance(pair, dict) or type(pair.get("beats", 8)) is not int:
            raise ValueError("Every pair needs an explicit valid integer beat duration")
        beats.add(pair.get("beats", 8))
    if len(beats) != 1 or not 1 <= next(iter(beats)) <= 64:
        raise ValueError(
            "All registered transitions need the same 1..64 beats for the current energy-grid idea board")
    return next(iter(beats))


def start_ideas(session, *, prefix="idea", phrase_bars=8, max_cues=5):
    """Generate exact-source-bound suggested cues AND an offline review board."""
    root, manifest, suggestions, board, _approved = _paths(session, prefix)
    beats = _admit_manual_grid(manifest)
    if suggestions.exists() or suggestions.is_symlink() or board.exists() or board.is_symlink():
        raise ValueError("An Idea Board already exists; use a new prefix to preserve it")
    suggest_cues(manifest, suggestions, beats=beats, phrase_bars=phrase_bars,
                 max_cues=max_cues)
    # Leave the newly-created immutable suggestions available for recovery if
    # the optional HTML publication fails; never delete original session data.
    prepare_board(manifest, suggestions, board)
    return {"stage": "manual-cue-review", "private_session": str(root),
            "idea_board": str(board), "suggestions": str(suggestions),
            "beats_per_transition": beats, "original_audio_unchanged": True,
            "manual_approval_required": True}


def finish_ideas(session, downloaded_approval, new_session, *,
                 prefix="idea", timeout_seconds=600, full_set_wav=None,
                 family="bass_swap", delivery=None, bitrate_kbps=192):
    """Apply every human choice and build real Studio/Composer in new workspace."""
    if delivery is not None and full_set_wav is None:
        raise ValueError("--delivery needs a complete PCM master: add --full-set-wav")
    root, manifest, suggestions, _board, approved = _paths(session, prefix)
    _admit_manual_grid(manifest)
    if not suggestions.is_file() or suggestions.is_symlink():
        raise ValueError("First generate energy suggestions using 'start'")
    if approved.exists() or approved.is_symlink():
        raise ValueError("Approved source manifest exists; choose a fresh prefix")
    destination = _private_project_dir(new_session, manifest)
    # Do not nest another project inside the already-completed original
    # private session or create it as the original session's ancestor.
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Render the approved playlist in a NEW separate project folder")
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 900:
        raise ValueError("Audio decoder timeout must be between 30 and 900 seconds")
    # The existing Idea Board is the only authority for candidate IDs,
    # source+suggestion hashes, manually approved picks and no-backtracking.
    # Its apply method requires exact source binding and refuses held-out data.
    apply_board(manifest, suggestions, downloaded_approval, approved)
    # If the real renderer rejects media/cues or external FFmpeg is absent,
    # it cleans up only its fresh destination; the human-approved manifest
    # survives untouched for diagnosis and an explicit retry.
    studio_index = make_session(approved, destination, timeout_seconds=timeout_seconds)
    normalized = destination / "sources" / "source_manifest.json"
    warnings = []
    cue_editor = None
    composer = None
    try:
        cue_editor = prepare_visual_editor(
            normalized, destination / "sources" / "cue-editor.html")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        warnings.append("Optional waveform cue editor unavailable: " + str(exc))
    try:
        composer = create_composer(destination)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        warnings.append("Optional Set Composer unavailable: " + str(exc))
    result = {"stage": "rendered-studio-ready", "private_studio": str(studio_index),
              "private_composer": str(composer) if composer else None,
              "visual_cue_editor": str(cue_editor) if cue_editor else None,
              "approved_source_manifest": str(approved),
              "new_session": str(destination), "warnings": warnings,
              "original_session_unchanged": True, "automatic_musical_quality_claim": False}
    if full_set_wav is not None:
        # Optional instant full-set export is a separate publication stage.
        # Preserve the valid newly rendered Studio on any output failure.
        try:
            from .instant_set import render_instant_set
            result["full_set"] = render_instant_set(
                destination, full_set_wav, family=family,
                delivery=delivery, bitrate_kbps=bitrate_kbps)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            warnings.append("Private Studio completed, but optional full-set export failed: " + str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Build local energy-based DJ idea board then render approved transitions")
    modes = parser.add_subparsers(dest="command", required=True)
    begin = modes.add_parser("start", help="Generate offline cue ideas and review board")
    begin.add_argument("session", help="Completed private development session")
    begin.add_argument("--prefix", default="idea",
                       help="New private filename prefix to keep independent draft versions")
    begin.add_argument("--phrase-bars", type=int, choices=(4, 8, 16), default=8)
    begin.add_argument("--max-cues", type=int, default=5)
    finish = modes.add_parser("finish", help="Render human-approved cues in a NEW private Studio")
    finish.add_argument("session", help="Original completed private session")
    finish.add_argument("approved_choices", help="Downloaded offline approval JSON")
    finish.add_argument("new_session", help="NEW project folder outside original music/session/Git")
    finish.add_argument("--prefix", default="idea")
    finish.add_argument("--timeout-seconds", type=int, default=600)
    finish.add_argument("--full-set-wav",
                        help="Optional NEW private WAV to render full approved route immediately")
    finish.add_argument("--family", choices=("bass_swap", "echo_exit", "hard_cut", "baseline"),
                        default="bass_swap",
                        help="Explicit family for every transition when --full-set-wav is used")
    finish.add_argument("--delivery", help="Optional NEW private MP3 or lossless FLAC after full WAV export")
    finish.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320),
                        default=192, help="MP3 bitrate; FLAC is lossless")
    args = parser.parse_args()
    try:
        if args.command == "start":
            result = start_ideas(args.session, prefix=args.prefix,
                                 phrase_bars=args.phrase_bars, max_cues=args.max_cues)
        else:
            result = finish_ideas(args.session, args.approved_choices,
                                  args.new_session, prefix=args.prefix,
                                  timeout_seconds=args.timeout_seconds,
                                  full_set_wav=args.full_set_wav,
                                  family=args.family, delivery=args.delivery,
                                  bitrate_kbps=args.bitrate_kbps)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, "MixLab Idea Pipeline: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
