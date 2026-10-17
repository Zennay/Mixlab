"""Independent crest-factor comparison for offline, rights-safe blind A/B QA.

Crest factor is sample peak / whole-clip RMS. It is not LUFS, true peak,
dynamic-range quality or a predictor of human musical preference.
This module reuses the existing bounded, non-mutating PCM16 comparator.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from . import compare_wavs

DEFAULT_CREST_TOLERANCE_DB = 6.0


def _crest_factor_db(metrics: dict) -> float | None:
    """Return sample-peak-minus-RMS in dB; silence has no crest factor."""
    peak = metrics["peak"]
    rms = metrics["rms"]
    if peak <= 0 or rms <= 0:
        return None
    return round(20.0 * math.log10(peak / rms), 3)


def compare_crest_factors(
    baseline: str | Path,
    candidates: list[str | Path],
    *,
    crest_tolerance_db: float = DEFAULT_CREST_TOLERANCE_DB,
) -> dict:
    """Flag large crest-factor differences in equal-format listening variants.

    The existing comparator enforces bounded input, matching format/duration,
    streaming reads and opaque candidate IDs. No audio, paths, peak locations,
    envelopes, hashes or blind answer keys are placed in the public report.
    The threshold is only an exploratory review cue: percussive arrangements
    can legitimately have a different crest factor.
    """
    if (isinstance(crest_tolerance_db, bool)
            or not isinstance(crest_tolerance_db, (int, float))
            or not math.isfinite(crest_tolerance_db)
            or not 0.5 <= crest_tolerance_db <= 24.0):
        raise ValueError("crest_tolerance_db must be finite within 0.5..24")
    report = compare_wavs(baseline, candidates)
    base_crest = _crest_factor_db(report["baseline"])
    results = []
    for entry in report["candidates"]:
        candidate_crest = _crest_factor_db(entry["metrics"])
        delta = (
            round(candidate_crest - base_crest, 3)
            if base_crest is not None and candidate_crest is not None else None
        )
        risk = delta is not None and abs(delta) >= crest_tolerance_db
        results.append({
            "candidate_id": entry["candidate_id"],
            "crest_factor_db": candidate_crest,
            "crest_delta_db_vs_baseline": delta,
            "crest_factor_confound_risk": risk,
            "warnings": (["crest_factor_difference_inspect_not_preference"] if risk else []),
            "requires_human_review": True,
        })
    return {
        "schema_version": 1,
        "purpose": "technical_crest_factor_screen_not_musical_preference",
        "analysis_method": "sample_peak_over_whole_clip_rms_not_lufs_or_true_peak",
        "crest_tolerance_db": float(crest_tolerance_db),
        "baseline_crest_factor_db": base_crest,
        "candidates": results,
        "human_preference_test_required": True,
        "contains_source_paths_or_audio": False,
    }


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally echoes unknown options and bad numeric values.
        # Avoid accidentally publishing private audio labels in CI stderr.
        self.exit(2, "Invalid crest-screen arguments (details withheld)\n")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateArgumentParser(
        description="Offline crest-factor diagnostic; not an audible quality score."
    )
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--crest-tolerance-db", type=float, default=DEFAULT_CREST_TOLERANCE_DB)
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = compare_crest_factors(
            args.baseline, args.candidates, crest_tolerance_db=args.crest_tolerance_db,
        )
    except (OSError, ValueError, EOFError, OverflowError):
        print("Cannot inspect PCM16 audio (details withheld)", file=sys.stderr)
        return 3
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    if args.fail_on_warnings and any(c["crest_factor_confound_risk"] for c in report["candidates"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
