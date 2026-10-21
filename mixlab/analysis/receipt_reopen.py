"""Reopen a private manually entered MixLab cue receipt against its exact PCM source.

The receipt is an unsigned self-declaration; reopening it is an integrity check,
not independent proof of human listening, audio rights, mixability or research
quality. It never mutates a rendering recipe, cache, user track or local file.
"""
from __future__ import annotations

import argparse
import json

from . import ManualProvider
from .manual_review import _admit_markers
from .source_receipt import source_identity, verify_source
from ..evaluation.json_admission import load_bounded_json
from ..ingest import HASH, number

FIELDS = frozenset({
    "schema_version", "kind", "source_sha256", "provider",
    "provider_version", "duration_seconds", "bpm", "first_beat_seconds",
    "downbeats_seconds", "phrase_starts_seconds", "key", "timing_source",
    "key_source", "operator_declared_manual_review",
    "human_confirmation_independently_verified", "human_identity_exported",
    "rights_verified", "render_authorized", "research_quality_verified",
    "note",
})


def reopen(wav, receipt):
    """Accept only the exact private operator-receipt contract and original WAV."""
    item = load_bounded_json(receipt)
    if not isinstance(item, dict) or set(item) != FIELDS:
        raise ValueError("Invalid private cue receipt schema")
    if (type(item["schema_version"]) is not int or item["schema_version"] != 1
            or item["kind"] != "private_operator_declared_cue_receipt"
            or item["provider"] != "manual"
            or item["provider_version"] != "manual-v1"
            or item["timing_source"] != "manual"
            or item["operator_declared_manual_review"] is not True
            or item["human_confirmation_independently_verified"] is not False
            or item["human_identity_exported"] is not False
            or item["rights_verified"] is not False
            or item["render_authorized"] is not False
            or item["research_quality_verified"] is not False):
        raise ValueError("Private cue receipt origin or safety boundary invalid")
    sha = item["source_sha256"]
    if not isinstance(sha, str) or not HASH.fullmatch(sha):
        raise ValueError("Invalid source identity receipt")
    if not isinstance(item["note"], str) or len(item["note"]) > 600:
        raise ValueError("Invalid private receipt note")
    bpm = number(item["bpm"], "manual BPM", 30, 300)
    first = number(item["first_beat_seconds"], "first beat", 0, 250)
    duration = number(item["duration_seconds"], "duration", 0, 250)
    downbeats = _admit_markers(item["downbeats_seconds"], "manual downbeat")
    phrases = _admit_markers(item["phrase_starts_seconds"], "manual phrase")
    key = item["key"]
    if not downbeats and not phrases and key is None:
        raise ValueError("No manually entered key or downbeat")
    if item["key_source"] != ("manual" if key is not None else "unavailable"):
        raise ValueError("Inconsistent key provenance")

    original_identity = source_identity(wav)
    # Reconstruct using the original ManualProvider: rechecks on-grid markers,
    # strict key constraints and audio duration, without copying any source data.
    # The private annotator label was deliberately omitted from the receipt.
    provider = ManualProvider(bpm, first, downbeats=downbeats, phrases=phrases,
                              key=key, annotator="local-receipt-reopen")
    analysis = provider.analyze(wav)
    if (analysis.source_sha256 != sha
            or abs(analysis.duration_seconds - duration) > 0.000001
            or analysis.key != key
            or analysis.downbeats_seconds != downbeats
            or analysis.phrase_starts_seconds != phrases):
        raise ValueError("Private cue receipt no longer matches this PCM source")
    verify_source(wav, original_identity, sha)
    # Never promote a self-declaration to an independently verified receipt.
    return {
        "schema_version": 1,
        "kind": "private_operator_declared_cue_reopen",
        "source_sha256": sha,
        "bpm": analysis.bpm,
        "first_beat_seconds": first,
        "key": key,
        "downbeats_seconds": list(downbeats),
        "phrase_starts_seconds": list(phrases),
        "operator_declared_manual_review": True,
        "human_confirmation_independently_verified": False,
        "rights_verified": False,
        "render_authorized": False,
        "file_identity_rechecked": True,
        "receipt_authenticity_cryptographically_verified": False,
        "note": "Local source match only. The original review and music rights remain unverified.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read a saved private manual cue receipt without opening mixing gates")
    parser.add_argument("wav", help="original permitted local PCM16 excerpt")
    parser.add_argument("receipt", help="private JSON produced by analysis.manual_review")
    args = parser.parse_args(argv)
    try:
        result = reopen(args.wav, args.receipt)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        parser.exit(2, "MixLab private receipt: invalid, changed or unavailable (details withheld)\n")
    print(json.dumps(result, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
