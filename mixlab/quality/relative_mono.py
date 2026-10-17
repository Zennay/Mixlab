"""Opt-in relative stereo-to-mono A/B confound screen (not a DJ-quality score).

The canonical MixLab quality scan already measures *absolute* fold-down
cancellation. This read-only companion asks a different question: is the
candidate substantially worse than the equal-duration baseline? No audio,
paths, hashes, or listener identifiers appear in the result.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import compare_wavs

MIN_DURATION_SECONDS = 1.0
MAX_SILENT_WINDOW_FRACTION = 0.2
MIN_CANDIDATE_RISK_FRACTION = 0.25
MIN_ADDED_RISK_FRACTION = 0.25
MAX_CANDIDATES = 4


def assess(report: dict) -> dict:
    """Interpret existing bounded 100ms stereo metrics; abstain on weak evidence."""
    baseline = report["baseline"]
    output = []
    for row in report["candidates"]:
        candidate = row["metrics"]
        base_risk = baseline.get("mono_fold_down_risky_window_fraction")
        candidate_risk = candidate.get("mono_fold_down_risky_window_fraction")
        adequate = (
            baseline["channels"] == candidate["channels"] == 2
            and baseline["duration_seconds"] >= MIN_DURATION_SECONDS
            and candidate["duration_seconds"] >= MIN_DURATION_SECONDS
            and baseline["silent_window_fraction"] <= MAX_SILENT_WINDOW_FRACTION
            and candidate["silent_window_fraction"] <= MAX_SILENT_WINDOW_FRACTION
            and baseline["rms_dbfs"] is not None
            and candidate["rms_dbfs"] is not None
            and base_risk is not None and candidate_risk is not None
        )
        if not adequate:
            status = "insufficient_stereo_evidence"
            delta = None
        else:
            delta = round(candidate_risk - base_risk, 6)
            if (candidate_risk >= MIN_CANDIDATE_RISK_FRACTION
                    and delta >= MIN_ADDED_RISK_FRACTION):
                status = "candidate_introduces_mono_cancellation"
            elif base_risk >= MIN_CANDIDATE_RISK_FRACTION:
                status = "baseline_already_has_mono_cancellation"
            else:
                status = "no_new_sustained_mono_cancellation_detected"
        output.append({
            "candidate_id": row["candidate_id"],
            "status": status,
            "added_risky_window_fraction": delta,
            "requires_human_review": True,
        })
    return {
        "schema_version": 1,
        "purpose": "technical_relative_mono_preflight_not_musical_quality",
        "candidate_count": len(output),
        "candidates": output,
        "human_preference_test_required": True,
        "milestone_pass": False,
        "contains_source_paths_or_audio": False,
    }


def inspect(baseline: str, candidates: list[str]) -> dict:
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("expected 1..4 candidates")
    return assess(compare_wavs(baseline, candidates, window_ms=100))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline relative stereo/mono QA; never certifies music quality"
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", action="append", required=True)
    options = parser.parse_args(argv)
    try:
        result = inspect(options.baseline, options.candidate)
    except Exception:
        # Fail closed on decoder errors too (e.g. wave.Error/struct.error).
        # Untrusted local filenames can appear in underlying OS errors.
        print(json.dumps({"status": "invalid_private_pcm", "milestone_pass": False}))
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    statuses = {entry["status"] for entry in result["candidates"]}
    return 3 if any(s != "no_new_sustained_mono_cancellation_detected" for s in statuses) else 0


if __name__ == "__main__":
    sys.exit(main())
