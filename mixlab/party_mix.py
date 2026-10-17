"""One command from locally permitted songs to a complete continuous WAV set.

This opt-in wrapper uses the already shipped private import -> cue -> Studio
renderer and the immutable manual continuous-set exporter. There are no
network calls, uploads, auto-selected cues or automatic tempo matching.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .session import _private_project_dir, make_session
from .set_export import _unique_pairs, _valid_destination, export_set


def render_party_mix(manifest, session_directory, output_wav, transitions,
                     *, timeout_seconds=600, suggestions=False):
    """Render the source Studio and chosen continuous set in one safe run.

    The expensive private Studio is deliberately retained if the final WAV
    fails: the caller can correct their selection and retry the export without
    re-importing private media. No preexisting files are modified.
    """
    source = Path(manifest).absolute()
    session_dir = _private_project_dir(session_directory, source)
    output = Path(output_wav).absolute()
    # Validate all cheap user-controlled destinations/selections BEFORE doing
    # CPU-heavy conversion; no partial output or session is created here.
    selected = _unique_pairs(transitions)
    _valid_destination(output, session_dir)
    if output.is_relative_to(session_dir) or session_dir.is_relative_to(output):
        raise ValueError("The output WAV must be outside the private session directory")
    # Full Studio must render every pair in order to satisfy user selections.
    studio_page = make_session(source, session_dir, suggestions=suggestions,
                               timeout_seconds=timeout_seconds)
    result = export_set(session_dir, output, [f"{p}:{family}" for p, family in selected])
    return {"status": "continuous-private-set-created", "studio": str(studio_page),
            "continuous_wav": str(result),
            "private_receipt": str(result) + ".receipt.private.json",
            "transition_count": len(selected), "automatic_beatmatching": False,
            "musical_quality_claim": False}


def main():
    parser = argparse.ArgumentParser(
        description="One-command local permitted music -> transition Studio -> continuous WAV")
    parser.add_argument("source_manifest", help="Private SHA-pinned permitted local music manifest")
    parser.add_argument("new_session_directory", help="New private session directory outside source music and Git")
    parser.add_argument("new_output_wav", help="New destination .wav outside the session and Git")
    parser.add_argument("--transition", action="append", required=True, metavar="PAIR:FAMILY",
                        help="One explicitly chosen transition, repeat in playlist order (up to 10)")
    parser.add_argument("--timeout-seconds", type=int, default=600,
                        help="Allowed FFmpeg processing time per input track, 30..900 seconds")
    parser.add_argument("--suggestions", action="store_true",
                        help="Make independent manual-grid energy proposals without applying them")
    args = parser.parse_args()
    try:
        result = render_party_mix(args.source_manifest, args.new_session_directory,
                                  args.new_output_wav, args.transition,
                                  timeout_seconds=args.timeout_seconds,
                                  suggestions=args.suggestions)
    except (ValueError, TypeError, OSError, KeyError) as exc:
        parser.exit(2, f"MixLab party mix: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
