"""Explicit private confirmation of human-selected musical cues for one PCM16 clip.

Does not turn model proposals into verified facts. A human must supply and
confirm each value and explicitly bind it to a SHA from a prior private preview.
The command emits JSON to stdout and never changes tracks or render recipes.
"""
from __future__ import annotations

import argparse
import json

from . import ManualProvider
from .source_receipt import source_identity, verify_source
from ..ingest import HASH, number

MAX_MARKERS = 10000


def _admit_markers(values, label):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_MARKERS:
        raise ValueError("Invalid manual marker sequence")
    previous = -1.
    output = []
    for value in values:
        t = number(value, label, 0, 250)
        if t <= previous:
            raise ValueError("Manual cue markers must be strictly increasing")
        output.append(t)
        previous = t
    return tuple(output)


def confirm(path, *, expected_sha256, bpm, first_beat=0.,
            downbeats=(), phrases=(), key=None, annotator="", approved=False):
    """Emit source-verified manual timing receipt, never render authorization."""
    if approved is not True:
        raise ValueError("Explicit human confirmation required")
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        raise ValueError("Expected source SHA-256 must come from a private preview")
    if not isinstance(annotator, str) or not annotator.strip():
        raise ValueError("A human annotator is required")
    number(bpm, "manual BPM", 30, 300)
    number(first_beat, "manual first beat", 0, 250)
    downbeats = _admit_markers(downbeats, "manual downbeat")
    phrases = _admit_markers(phrases, "manual phrase")
    # Require a real manually reviewed cue beyond the baseline BPM to avoid
    # labeling an empty/missing-cue proposal as fully verified structure.
    if not downbeats and not phrases and key is None:
        raise ValueError("At least one human-confirmed key or downbeat required")

    original_identity = source_identity(path)
    provider = ManualProvider(bpm, first_beat, downbeats=downbeats,
                              phrases=phrases, key=key, annotator=annotator)
    record = provider.analyze(path)
    if record.source_sha256 != expected_sha256:
        raise ValueError("Manual confirmation source does not match preview")
    verify_source(path, original_identity, expected_sha256)
    return {
        "schema_version": 1,
        "kind": "private_human_confirmed_cue_receipt",
        "source_sha256": expected_sha256,
        "provider": record.provider,
        "provider_version": record.provider_version,
        "duration_seconds": record.duration_seconds,
        "bpm": record.bpm,
        "first_beat_seconds": first_beat,
        "downbeats_seconds": list(record.downbeats_seconds),
        "phrase_starts_seconds": list(record.phrase_starts_seconds),
        "key": record.key,
        "timing_source": "manual",
        "key_source": record.key_source,
        "human_confirmation": True,
        "human_identity_exported": False,
        "rights_verified": False,
        "render_authorized": False,
        "research_quality_verified": False,
        "note": ("Only the explicitly entered cues are human-confirmed. "
                 "Missing key/downbeats/phrases remain unavailable; "
                 "this receipt does not modify any rendering metadata."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Confirm manually selected cue fields for a prior private MixLab preview")
    parser.add_argument("wav", help="locally permitted short PCM16 excerpt")
    parser.add_argument("--source-sha256", required=True,
                        help="exact SHA-256 from this same excerpt's private cue preview")
    parser.add_argument("--bpm", required=True, type=float, help="human-confirmed BPM")
    parser.add_argument("--first-beat", type=float, default=0.)
    parser.add_argument("--downbeat", action="append", type=float, default=[])
    parser.add_argument("--phrase", action="append", type=float, default=[])
    parser.add_argument("--key", help="manually confirmed major/minor key, e.g. 'C major'")
    parser.add_argument("--annotator", required=True,
                        help="private human label, used for version hash, never printed")
    parser.add_argument("--confirm-manual-cues", action="store_true",
                        help="explicitly confirm own BPM/key/downbeat/phrase review")
    args = parser.parse_args(argv)
    try:
        document = confirm(
            args.wav, expected_sha256=args.source_sha256, bpm=args.bpm,
            first_beat=args.first_beat, downbeats=args.downbeat, phrases=args.phrase,
            key=args.key, annotator=args.annotator, approved=args.confirm_manual_cues)
    except (ValueError, TypeError, OSError, OverflowError):
        parser.exit(2, "MixLab manual cue confirmation: invalid, unavailable, or changed private source (details withheld)\n")
    print(json.dumps(document, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
