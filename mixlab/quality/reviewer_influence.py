"""Private, opt-in leave-one-reviewer-out stability QA for frozen audio pilots.

This independently re-runs the official PCM/ratings aggregate, preserving
a whole reviewer as the analysis unit. The flags are descriptive, not a
human independence, statistical significance or music-quality decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ..evaluation import aggregate
from ..evaluation.json_admission import load_bounded_json
from .study_binding import verify_study_pack_binding

_ERROR = "invalid, inconsistent or changed private listening evidence"
_MIN_REVIEWERS = 3
_MAX_REVIEWERS = 5
_SHIFT_REVIEW = 0.20
_FIELDS = ("candidate", "baseline", "ties", "both_unusable")


class ReviewerInfluenceError(ValueError):
    """Privacy-safe rejection: never includes reviewer, track or path."""


def _reject():
    raise ReviewerInfluenceError(_ERROR)


def _path(value):
    # Restrict to inert, built-in lexical path types. A hostile PathLike
    # could run code or raise an exception that contains a private filename.
    if type(value) not in (str, type(Path("."))):
        _reject()
    candidate = Path(value)
    return candidate if candidate.is_absolute() else Path.cwd() / candidate


def _snapshot(path):
    # The merged loader limits size, depth, JSON ambiguity and final-leaf
    # symlinks. Ancestor symlink hardening belongs to concurrent PR #87.
    payload = load_bounded_json(path)
    if not isinstance(payload, (list, dict)):
        _reject()
    canonical = json.dumps(payload, sort_keys=True,
                           ensure_ascii=True, allow_nan=False,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def _summary(result, expected_reviewers, expected_trials=None):
    """Check invariant structure rather than trusting arbitrary JSON labels."""
    if not isinstance(result, dict):
        _reject()
    reviewers, trials = result.get("reviewers"), result.get("trials")
    if (type(reviewers) is not int or reviewers != expected_reviewers
            or type(trials) is not int or not 5 <= trials <= 10
            or expected_trials is not None and trials != expected_trials
            or result.get("milestone_pass") is not False
            or not isinstance(result.get("audio_confounds"), list)):
        _reject()
    counts = result.get("counts")
    rows = result.get("per_pair_family")
    if not isinstance(counts, dict) or not isinstance(rows, list) or len(rows) != trials:
        _reject()
    values = {}
    for name in _FIELDS:
        number = counts.get(name)
        if type(number) is not int or not 0 <= number <= reviewers * trials:
            _reject()
        values[name] = number
    if sum(values.values()) != reviewers * trials:
        _reject()
    decisive = values["candidate"] + values["baseline"]
    if type(result.get("non_tied_preferences")) is not int or result["non_tied_preferences"] != decisive:
        _reject()
    if decisive:
        fraction = result.get("candidate_preference_fraction")
        if type(fraction) is not float or abs(fraction - values["candidate"] / decisive) > 1e-12:
            _reject()
    elif result.get("candidate_preference_fraction") is not None:
        _reject()
    group = {}
    for row in rows:
        if not isinstance(row, dict):
            _reject()
        pair, family = row.get("pair"), row.get("candidate_family")
        if not isinstance(pair, str) or not pair or not isinstance(family, str) or not family:
            _reject()
        key = (pair, family)
        if key in group:
            _reject()
        subgroup = []
        for name in _FIELDS:
            number = row.get(name)
            if type(number) is not int or number < 0 or number > reviewers:
                _reject()
            subgroup.append(number)
        if sum(subgroup) != reviewers:
            _reject()
        group[key] = tuple(subgroup)
    if len(group) != trials or tuple(sum(v[i] for v in group.values()) for i in range(4)) != tuple(values[name] for name in _FIELDS):
        _reject()
    return values, group, bool(result["audio_confounds"])


def inspect_real_reviewer_influence(study_path, pack_path, expected_study_id, rating_paths):
    """Genuine pinned PCM + reviewer jackknife, never participant scoring.

    Maximum five rating files / four extra real aggregate scans. Changing
    files during those scans invalidates the result; this is not a defence
    against adversarial rapid byte swapping and restoration.
    """
    if not isinstance(rating_paths, (tuple, list)) or not _MIN_REVIEWERS <= len(rating_paths) <= _MAX_REVIEWERS:
        _reject()
    try:
        study = _path(study_path)
        pack = _path(pack_path)
        raters = [_path(path) for path in rating_paths]
        if len(set(map(str, raters))) != len(raters):
            _reject()
        pinned = verify_study_pack_binding(study, pack, expected_study_id)
        if (pinned.get("study_pack_metadata_consistent_with_pinned_id") is not True
                or pinned.get("milestone_pass") is not False
                or not 5 <= pinned.get("trial_count", 0) <= 10):
            _reject()
        study_digest = _snapshot(study)
        vote_digests = [_snapshot(path) for path in raters]
        full = aggregate(pack, raters)
        total, groups, audio_confounds = _summary(full, len(raters), pinned["trial_count"])
        omit_counts, fractions, omitted_groups = [], [], []
        for index in range(len(raters)):
            others = raters[:index] + raters[index + 1:]
            report = aggregate(pack, others)
            counts, by_group, warnings = _summary(report, len(others), pinned["trial_count"])
            if set(by_group) != set(groups) or warnings != audio_confounds:
                _reject()
            omit_counts.append(counts)
            omitted_groups.append(by_group)
            decisive = counts["candidate"] + counts["baseline"]
            fractions.append(counts["candidate"] / decisive if decisive else None)
        # Cross-check the independent official runs: each reviewer ballot
        # occurs in exactly N-1 of the N omitted-reviewer aggregates.
        for name in _FIELDS:
            if sum(item[name] for item in omit_counts) != (len(raters) - 1) * total[name]:
                _reject()
        for key, values in groups.items():
            for column in range(4):
                if sum(item[key][column] for item in omitted_groups) != (len(raters) - 1) * values[column]:
                    _reject()
        if _snapshot(study) != study_digest or any(
                _snapshot(path) != digest for path, digest in zip(raters, vote_digests)):
            _reject()
        again = verify_study_pack_binding(study, pack, expected_study_id)
        if again != pinned:
            _reject()

        decisive_full = total["candidate"] + total["baseline"]
        base = total["candidate"] / decisive_full if decisive_full else None
        enough = (decisive_full >= 5 and
                  all(value is not None for value in fractions))
        finite_fractions = [item for item in fractions if item is not None]
        minimum = min(finite_fractions) if finite_fractions else None
        maximum = max(finite_fractions) if finite_fractions else None
        max_shift = max((abs(v - base) for v in finite_fractions),
                        default=None) if base is not None else None
        plurality_flip = (
            any((base > .5) != (fraction > .5) for fraction in fractions)
            if enough and base != .5 else None
        )
        # 20 percentage points is only a conservative reviewer-influence
        # heuristic, *not* a statistical threshold or proof of fake reviews.
        review = (not enough or audio_confounds or
                  plurality_flip is True or
                  (max_shift is not None and max_shift >= _SHIFT_REVIEW))
        return {
            "schema_version": 1,
            "reviewer_file_count": len(raters),
            "frozen_pair_count": pinned["trial_count"],
            "full_decisive_vote_count": decisive_full,
            "full_candidate_preference_fraction": base,
            "min_leave_one_reviewer_out_candidate_fraction": minimum,
            "max_leave_one_reviewer_out_candidate_fraction": maximum,
            "max_absolute_reviewer_omission_fraction_shift": max_shift,
            "omission_flips_candidate_plurality": plurality_flip,
            "sufficient_for_reviewer_influence_screen": enough,
            "official_audio_confounds_reported": audio_confounds,
            "reviewer_influence_review_required": bool(review),
            "real_human_identity_verified": False,
            "source_rights_independently_authenticated": False,
            "human_musical_preference_proven": False,
            "milestone_pass": False,
        }
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            OverflowError, RecursionError):
        raise ReviewerInfluenceError(_ERROR) from None


def main(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, "MixLab reviewer influence: invalid arguments\n")

    parser = SafeParser(description="Opt-in blinded review sensitivity, no release approval")
    parser.add_argument("study")
    parser.add_argument("pack")
    parser.add_argument("ratings", nargs="+")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        output = inspect_real_reviewer_influence(
            args.study, args.pack, args.expected_study_id, args.ratings)
    except (OSError, ValueError, TypeError, RecursionError):
        parser.exit(2, "MixLab reviewer influence: invalid or changed private evidence\n")
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return 3 if output["reviewer_influence_review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
