"""Independent, read-only sensitivity QA for tiny frozen blind listening pilots.

The official MixLab aggregate() validates PCM/ratings. This additional gate
treats *pairs*, not correlated individual rating clicks, as analysis units.
One-sided exact sign probabilities are descriptive references under assumed
independent, exchangeable source pairs; they are NOT validated p-values for
real music, independent listeners or an M1 milestone decision.
"""
from __future__ import annotations

import argparse
from collections import Counter
from math import comb
import json

from ..evaluation import aggregate
from ..evaluation.json_admission import load_bounded_json
from .study_binding import verify_study_pack_binding

_ERROR = "invalid, changed or incompatible private pilot evidence"


class PilotSensitivityError(ValueError):
    """Non-private generic failure of the opt-in sensitivity check."""


def _reject() -> None:
    raise PilotSensitivityError(_ERROR)


def _sign_reference(winners: int, decisive_pairs: int) -> float | None:
    """Exact one-sided fair-sign tail, *conditional on independent pairs*."""
    if not decisive_pairs:
        return None
    return sum(comb(decisive_pairs, i)
               for i in range(winners, decisive_pairs + 1)) / (1 << decisive_pairs)


def inspect_pair_sensitivity(aggregation: object, *, source_reuse: bool = False) -> dict:
    """Conservatively assess one-family-per-frozen-pair pilot sensitivity.

    Never accept a fabricated tally with extra candidate families as a
    preregistered single-candidate pilot. No pair IDs, source fingerprints,
    winner labels or individual reviewer votes leave the function.
    """
    if type(source_reuse) is not bool or not isinstance(aggregation, dict):
        _reject()
    reviewers = aggregation.get("reviewers")
    trials = aggregation.get("trials")
    rows = aggregation.get("per_pair_family")
    counts = aggregation.get("counts")
    if (type(reviewers) is not int or not 1 <= reviewers <= 16
            or type(trials) is not int or not 5 <= trials <= 10
            or not isinstance(rows, list) or len(rows) != trials
            or not isinstance(counts, dict)
            or not isinstance(aggregation.get("audio_confounds"), list)
            or aggregation.get("milestone_pass") is not False):
        _reject()

    tally = Counter()
    seen_pairs = set()
    sums = Counter()
    fields = ("candidate", "baseline", "ties", "both_unusable")
    for row in rows:
        if not isinstance(row, dict):
            _reject()
        pair, family = row.get("pair"), row.get("candidate_family")
        if (not isinstance(pair, str) or not pair
                or pair in seen_pairs
                or not isinstance(family, str) or not family
                or family == "baseline"):
            _reject()
        seen_pairs.add(pair)
        values = []
        for field in fields:
            number = row.get(field)
            if type(number) is not int or not 0 <= number <= reviewers:
                _reject()
            values.append(number)
            sums[field] += number
        if sum(values) != reviewers:
            _reject()
        candidate, baseline = values[:2]
        tally["candidate" if candidate > baseline
              else "baseline" if candidate < baseline else "tie"] += 1
    if any(type(counts.get(name)) is not int or counts[name] != sums[name]
           for name in fields):
        _reject()

    wins = tally["candidate"]
    losses = tally["baseline"]
    tied = tally["tie"]
    n = wins + losses
    enough = reviewers >= 3 and n >= 5 and not source_reuse
    confounds = bool(aggregation["audio_confounds"])
    reference = _sign_reference(wins, n) if enough else None

    # Include all omissions, not just favorable ones. A tie pair removal may
    # leave the sign tail unchanged but still reduces the sample size.
    tails = []
    if enough:
        for winner in ([True] * wins + [False] * losses + [None] * tied):
            left_wins = wins - (winner is True)
            left_n = n - (winner is not None)
            tail = _sign_reference(left_wins, left_n)
            if tail is None:
                _reject()
            tails.append(tail)
    worst = max(tails) if tails else None
    nominal = reference is not None and reference <= .05
    robust = bool(nominal and worst is not None and worst <= .05 and not confounds)

    return {
        "schema_version": 1,
        "reviewer_file_count": reviewers,
        "frozen_pair_count": trials,
        "decisive_pair_count": n,
        "candidate_favored_pair_count": wins,
        "baseline_favored_pair_count": losses,
        "tied_or_unusable_pair_count": tied,
        "audio_confounds_reported": confounds,
        "shared_source_across_pairs_detected": source_reuse,
        "minimum_data_for_pair_reference": enough,
        "one_sided_pair_sign_reference_probability": reference,
        "worst_leave_one_pair_out_reference_probability": worst,
        "nominal_pair_reference_threshold_met": nominal if enough else None,
        "one_pair_omission_removes_nominal_signal":
            (bool(nominal and worst is not None and worst > .05) if enough else None),
        "pair_sensitivity_review_required": not robust,
        "source_rights_independently_authenticated": False,
        "listener_independence_authenticated": False,
        "human_musical_preference_proven": False,
        "milestone_pass": False,
    }


def inspect_real_pilot(study_path, pack_path, expected_study_id, rating_paths) -> dict:
    """Run genuine pinned PCM preflight and the actual rating aggregator."""
    try:
        if not isinstance(rating_paths, (tuple, list)) or not 1 <= len(rating_paths) <= 16:
            _reject()
        pinned = verify_study_pack_binding(study_path, pack_path, expected_study_id)
        if (pinned.get("study_pack_metadata_consistent_with_pinned_id") is not True
                or pinned.get("milestone_pass") is not False):
            _reject()
        study = load_bounded_json(study_path)
        pairs = study.get("pairs") if isinstance(study, dict) else None
        if (not isinstance(pairs, list)
                or len(pairs) != pinned.get("trial_count")):
            _reject()
        hashes = []
        for pair in pairs:
            if not isinstance(pair, dict):
                _reject()
            for key in ("a_sha256", "b_sha256"):
                source = pair.get(key)
                if not isinstance(source, str) or len(source) != 64:
                    _reject()
                hashes.append(source)
        reuse = len(set(hashes)) != len(hashes)
        result = aggregate(pack_path, rating_paths)
        # Neither study nor pack metadata may drift while rating audio
        # is re-opened for the full official quality/confound scan.
        again = verify_study_pack_binding(study_path, pack_path, expected_study_id)
        if again != pinned or load_bounded_json(study_path) != study:
            _reject()
        return inspect_pair_sensitivity(result, source_reuse=reuse)
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            OverflowError, RecursionError):
        raise PilotSensitivityError(_ERROR) from None


def main(argv=None) -> int:
    class PrivateParser(argparse.ArgumentParser):
        def error(self, _msg):
            self.exit(2, "MixLab pilot sensitivity: invalid arguments\n")

    parser = PrivateParser(description="Frozen pair-level sensitivity QA; never music approval")
    parser.add_argument("study")
    parser.add_argument("pack")
    parser.add_argument("ratings", nargs="+")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_real_pilot(
            args.study, args.pack, args.expected_study_id, args.ratings)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        parser.exit(2, "MixLab pilot sensitivity: private inputs invalid or changed\n")
    print(json.dumps(report, allow_nan=False, sort_keys=True))
    return 3 if report["pair_sensitivity_review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
