"""Blind A/B review-pack quality preflight; never read the private answer key.

Inspect only neutral trial-###-{A,B}.wav pairs. All audio remains local.
Metrics are technical diagnostics, not proof of musical preference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from . import compare_wavs

_TRIAL_WAV = re.compile(r"^(trial-([0-9]{3}))-([AB])\.wav$")
MAX_TRIALS = 60


def inspect_review_pack(
    review_directory: str | Path, *, window_ms: int = 100,
    loudness_tolerance_db: float = 1.5,
) -> dict:
    """Screen an immutable local review directory without looking up answers.

    Fail closed on malformed, incomplete, aliased or excessive WAV inventories.
    Do not return filenames, paths, source hashes or PCM window envelopes.
    """
    directory = Path(review_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Review input must be a real directory, not a symlink")
    groups: dict[str, dict[str, Path]] = {}
    for entry in directory.iterdir():
        # The review directory may be served to a listener. Reject leaked
        # answer keys, manifests, downloads or other unexpected assets, even
        # when they are not audio. Only the generated index is public.
        if entry.name == "index.html":
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("Review index must be a regular file")
            continue
        if entry.suffix.lower() != ".wav":
            raise ValueError("Review directory contains an unexpected public asset")
        match = _TRIAL_WAV.fullmatch(entry.name)
        if match is None or int(match.group(2)) == 0:
            raise ValueError("Review directory contains an unexpected WAV filename")
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("Review WAV must be a regular file, not a symlink")
        trial_id, _, label = match.groups()
        labels = groups.setdefault(trial_id, {})
        if label in labels:
            raise ValueError("Review directory contains a duplicate trial label")
        labels[label] = entry
        if len(groups) > MAX_TRIALS:
            raise ValueError("Review directory exceeds the trial limit")
    if not groups:
        raise ValueError("Review directory contains no trial WAV pairs")
    if any(set(labels) != {"A", "B"} for labels in groups.values()):
        raise ValueError("Review directory contains an incomplete trial WAV pair")

    trials = []
    warning_trial_count = 0
    for trial_id, labels in sorted(groups.items()):
        result = compare_wavs(
            labels["A"], [labels["B"]], window_ms=window_ms,
            loudness_tolerance_db=loudness_tolerance_db,
        )
        candidate = result["candidates"][0]
        warnings = {
            "A": result["baseline_warnings"],
            "B": candidate["warnings"],
        }
        # A/B designation has no relationship to baseline/candidate assignment:
        # packaging randomization stays blinded and no private key is opened.
        if candidate["duplicate_pcm_of"] == "baseline":
            warnings["B"] = [
                "identical_pcm_between_A_and_B" if w == "identical_pcm_to_baseline_inspect_for_noop" else w
                for w in warnings["B"]
            ]
        flagged = bool(warnings["A"] or warnings["B"])
        warning_trial_count += flagged
        trials.append({
            "trial_id": trial_id,
            "A": {"metrics": result["baseline"], "warnings": warnings["A"]},
            "B": {"metrics": candidate["metrics"], "warnings": warnings["B"]},
            "B_minus_A_rms_db": candidate["rms_delta_db_vs_baseline"],
            "short_window_level_mismatch_fraction": candidate["short_window_level_mismatch_fraction"],
            "short_window_level_mismatch_risk": candidate["short_window_level_mismatch_risk"],
            "identical_pcm": candidate["duplicate_pcm_of"] == "baseline",
            "technical_warnings_present": flagged,
        })
    return {
        "schema_version": 1,
        "purpose": "blind_review_technical_preflight_not_musical_quality",
        "analysis_method": "streaming_pcm16_rms_not_lufs",
        "trial_count": len(trials),
        "warning_trial_count": warning_trial_count,
        "human_preference_test_required": True,
        "answer_key_opened": False,
        "contains_source_paths_hashes_or_audio": False,
        "trials": trials,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect neutral A/B review WAVs without opening a private answer key"
    )
    parser.add_argument("review_directory", help="Directory containing trial-###-[AB].wav")
    parser.add_argument("--window-ms", type=int, default=100)
    parser.add_argument("--loudness-tolerance-db", type=float, default=1.5)
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_review_pack(
            args.review_directory, window_ms=args.window_ms,
            loudness_tolerance_db=args.loudness_tolerance_db,
        )
    except (OSError, ValueError):
        parser.exit(3, "review quality preflight: invalid or unreadable pack (details withheld)\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 2 if args.fail_on_warnings and result["warning_trial_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
