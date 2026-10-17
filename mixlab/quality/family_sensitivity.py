"""Anonymous transition-family sensitivity QA for small blind MixLab pilots.

This is a post-rating diagnostic, not a winner selector or proof of DJ quality.
Runs only after canonical checksum-bound pack and aggregate admission.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from math import comb

from ..evaluation import aggregate
from ..evaluation.json_admission import load_bounded_json
from ..models import FAMILY_NAMES
from .study_binding import verify_study_pack_binding

_ERROR = "invalid, inconsistent or changed private family evidence"
_FAMILIES = tuple(name for name in FAMILY_NAMES if name != "baseline")
_FIELDS = ("candidate", "baseline", "ties", "both_unusable")


class FamilySensitivityError(ValueError):
    """Never carry private paths, source identifiers or reviewer details."""


def _reject():
    raise FamilySensitivityError(_ERROR)


def _sign_tail(wins: int, decisive: int) -> float | None:
    if not decisive:
        return None
    return sum(comb(decisive, i) for i in range(wins, decisive + 1)) / (1 << decisive)


def inspect_family_sensitivity(summary: object) -> dict:
    """Conservatively detect concentration of blind preferences in one family.

    A single exploratory family can look strong while all others fail. Treat
    pairs as units, not individual correlated rating clicks, and adjust the
    descriptive one-sided sign reference over ALL configured candidate
    families (including families not sampled). No individual pair, family
    name, answer, reviewer or private study identifier is returned.
    """
    if not isinstance(summary, dict):
        _reject()
    reviewers, trials = summary.get("reviewers"), summary.get("trials")
    rows, counts = summary.get("per_pair_family"), summary.get("counts")
    confounds = summary.get("audio_confounds")
    if (type(reviewers) is not int or not 1 <= reviewers <= 16
            or type(trials) is not int or not 5 <= trials <= 10
            or not isinstance(rows, list) or len(rows) != trials
            or not isinstance(counts, dict)
            or not isinstance(confounds, list)
            or summary.get("milestone_pass") is not False):
        _reject()

    grouped = {family: [] for family in _FAMILIES}
    summed = Counter()
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            _reject()
        pair = row.get("pair")
        family = row.get("candidate_family")
        if (type(pair) is not str or not pair or pair in seen
                or type(family) is not str or family not in grouped):
            _reject()
        seen.add(pair)
        values = []
        for field in _FIELDS:
            value = row.get(field)
            if type(value) is not int or not 0 <= value <= reviewers:
                _reject()
            summed[field] += value
            values.append(value)
        if sum(values) != reviewers:
            _reject()
        candidate, baseline = values[:2]
        grouped[family].append(1 if candidate > baseline else -1 if baseline > candidate else 0)
    if any(type(counts.get(field)) is not int or counts[field] != summed[field]
           for field in _FIELDS):
        _reject()
    if sum(summed.values()) != reviewers * trials:
        _reject()

    anonymous = []
    positive_groups = negative_groups = 0
    for index, family in enumerate(_FAMILIES, 1):
        signs = grouped[family]
        wins, losses = signs.count(1), signs.count(-1)
        decisive = wins + losses
        original = _sign_tail(wins, decisive)
        adjusted = min(1.0, len(_FAMILIES) * original) if original is not None else None
        leave_one = [
            _sign_tail(wins - (sign == 1), decisive - (sign != 0))
            for sign in signs
        ] if decisive else []
        valid_omissions = [value for value in leave_one if value is not None]
        worst = max(valid_omissions) if len(valid_omissions) == len(signs) and signs else None
        adjusted_worst = min(1.0, len(_FAMILIES) * worst) if worst is not None else None
        positive_groups += wins > losses
        negative_groups += losses > wins
        anonymous.append({
            "anonymous_stratum": f"group-{index:02d}",
            "pair_count": len(signs),
            "decisive_pair_count": decisive,
            "candidate_favored_pairs": wins,
            "baseline_favored_pairs": losses,
            "tie_or_unusable_pairs": signs.count(0),
            "one_sided_sign_reference": original,
            "familywise_adjusted_reference": adjusted,
            "worst_leave_one_pair_out_adjusted_reference": adjusted_worst,
            "sufficient_for_family_reference": reviewers >= 3 and decisive >= 5,
            "robust_nominal_family_reference": bool(
                reviewers >= 3 and decisive >= 5
                and adjusted is not None and adjusted <= 0.05
                and adjusted_worst is not None and adjusted_worst <= 0.05
                and not confounds
            ),
        })

    sampled = [row for row in anonymous if row["pair_count"]]
    imbalance = bool(sampled) and (
        max(row["pair_count"] for row in sampled) - min(row["pair_count"] for row in sampled) > 1
    )
    concentration = positive_groups > 0 and negative_groups > 0
    any_strong = any(row["robust_nominal_family_reference"] for row in sampled)
    return {
        "schema_version": 1,
        "frozen_pair_count": trials,
        "reviewer_file_count": reviewers,
        "candidate_family_space_count": len(_FAMILIES),
        "represented_family_count": len(sampled),
        "anonymous_family_strata": anonymous,
        "unequal_family_coverage_review": imbalance or len(sampled) != len(_FAMILIES)
                                          or any(row["pair_count"] < 2 for row in sampled),
        "opposing_family_directions_review": concentration,
        "official_audio_confounds_reported": bool(confounds),
        "any_robust_nominal_family_reference": any_strong,
        "family_sensitivity_review_required": not any_strong or concentration
            or bool(confounds) or imbalance or len(sampled) != len(_FAMILIES),
        "source_rights_independently_authenticated": False,
        "listener_independence_authenticated": False,
        "musical_preference_proven": False,
        "milestone_pass": False,
    }


def inspect_real_families(study_path, pack_path, expected_study_id, rating_paths) -> dict:
    """Read genuine frozen study, original PCM-bound pack and official ballots."""
    if (not isinstance(rating_paths, (list, tuple))
            or not 1 <= len(rating_paths) <= 16):
        _reject()
    try:
        first = verify_study_pack_binding(study_path, pack_path, expected_study_id)
        if (first.get("study_pack_metadata_consistent_with_pinned_id") is not True
                or first.get("milestone_pass") is not False):
            _reject()
        study = load_bounded_json(study_path)
        pairs = study.get("pairs") if isinstance(study, dict) else None
        if not isinstance(pairs, list) or len(pairs) != first.get("trial_count"):
            _reject()
        declared = Counter()
        for pair in pairs:
            if not isinstance(pair, dict) or pair.get("candidate_family") not in _FAMILIES:
                _reject()
            declared[pair["candidate_family"]] += 1
        official = aggregate(pack_path, rating_paths)
        observed = Counter()
        for row in official.get("per_pair_family", []):
            if not isinstance(row, dict):
                _reject()
            family = row.get("candidate_family")
            if type(family) is not str:
                _reject()
            observed[family] += 1
        if observed != declared:
            _reject()
        report = inspect_family_sensitivity(official)
        if (verify_study_pack_binding(study_path, pack_path, expected_study_id) != first
                or load_bounded_json(study_path) != study):
            _reject()
        return report
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            OverflowError, RecursionError):
        raise FamilySensitivityError(_ERROR) from None


def main(argv=None) -> int:
    class PrivateParser(argparse.ArgumentParser):
        def error(self, _message):
            self.exit(2, "MixLab family sensitivity: invalid arguments\n")

    parser = PrivateParser(description="Private exploratory family QA; not release approval")
    parser.add_argument("study")
    parser.add_argument("pack")
    parser.add_argument("ratings", nargs="+")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_real_families(
            args.study, args.pack, args.expected_study_id, args.ratings)
    except (OSError, ValueError, TypeError, RecursionError):
        parser.exit(2, "MixLab family sensitivity: private inputs invalid or changed\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 3 if report["family_sensitivity_review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
