"""Single-command, fail-closed composition of the four *existing* M1 QA gates.

This runs real private, checksum-bound PCM checks. It is an optional technical
screen, NEVER a music-quality, source-rights, listener-identity or release gate.
No identifying answer map, source path or preference tally is emitted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .assignment_balance import audit_study_assignment
from .listener_position import inspect_listener_sides, _read_snapshot
from .pilot_sensitivity import inspect_real_pilot
from .reviewer_influence import inspect_real_reviewer_influence
from .study_binding import verify_study_pack_binding

_ERROR = "Invalid or changed private M1 gate inputs"
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class M1GateBundleError(ValueError):
    """Never include input names or private metadata in errors."""


def _fail():
    raise M1GateBundleError(_ERROR)


def _capture(value):
    # Untrusted arbitrary PathLike.__fspath__ may run code and expose secrets.
    if type(value) not in (str, type(Path("."))):
        _fail()
    p = Path(value)
    return p if p.is_absolute() else Path.cwd() / p


def _shape(row, *, trials, reviewers, count_field, reviewer_field):
    if (type(row) is not dict or type(row.get("schema_version")) is not int\n            or row["schema_version"] != 1
            or row.get("milestone_pass") is not False
            or type(row.get(count_field)) is not int
            or row[count_field] != trials
            or (reviewer_field is not None
                and (type(row.get(reviewer_field)) is not int
                     or row[reviewer_field] != reviewers))):
        _fail()


def compose_m1_gate_reports(binding, assignment, position, pair, reviewer, *, rating_count):
    """Cross-check complete outputs, not unvalidated stand-alone PASS labels.

    This pure step is independently mutation-tested; the public entry point
    ALWAYS invokes the underlying real PCM and full-rating implementations.
    """
    if type(rating_count) is not int or not 3 <= rating_count <= 5:
        _fail()
    if (type(binding) is not dict or type(binding.get("schema_version")) is not int\n            or binding["schema_version"] != 1
            or binding.get("study_pack_metadata_consistent_with_pinned_id") is not True
            or binding.get("milestone_pass") is not False
            or type(binding.get("trial_count")) is not int
            or not 5 <= binding["trial_count"] <= 10):
        _fail()
    n = binding["trial_count"]
    _shape(assignment, trials=n, reviewers=rating_count,
           count_field="trial_count", reviewer_field=None)
    _shape(position, trials=n, reviewers=rating_count,
           count_field="trial_count", reviewer_field="reviewer_count")
    _shape(pair, trials=n, reviewers=rating_count,
           count_field="frozen_pair_count", reviewer_field="reviewer_file_count")
    _shape(reviewer, trials=n, reviewers=rating_count,
           count_field="frozen_pair_count", reviewer_field="reviewer_file_count")
    fields = (
        (assignment, "side_assignment_review_required"),
        (position, "sufficient_for_position_screen"),
        (position, "aggregate_position_dominance_review"),
        (position, "individual_position_pattern_review"),
        (pair, "minimum_data_for_pair_reference"),
        (pair, "pair_sensitivity_review_required"),
        (pair, "audio_confounds_reported"),
        (reviewer, "sufficient_for_reviewer_influence_screen"),
        (reviewer, "reviewer_influence_review_required"),
        (reviewer, "official_audio_confounds_reported"),
    )
    for report, key in fields:
        if type(report.get(key)) is not bool:
            _fail()
    # Both analyses operated on the same exact frozen PCM+ballot inventory.
    if pair["audio_confounds_reported"] != reviewer["official_audio_confounds_reported"]:
        _fail()
    risks = {
        "assignment-bias": assignment["side_assignment_review_required"],
        "position-bias-or-insufficient-data": (
            not position["sufficient_for_position_screen"]
            or position["aggregate_position_dominance_review"]
            or position["individual_position_pattern_review"]
        ),
        "pair-sensitivity-or-insufficient-data": (
            not pair["minimum_data_for_pair_reference"]
            or pair["pair_sensitivity_review_required"]
        ),
        "reviewer-influence-or-insufficient-data": (
            not reviewer["sufficient_for_reviewer_influence_screen"]
            or reviewer["reviewer_influence_review_required"]
        ),
        "audio-confounds": pair["audio_confounds_reported"],
    }
    return {
        "schema_version": 1,
        "technical_screen": "REVIEW_REQUIRED" if any(risks.values()) else "SCREENED",
        "frozen_pair_count": n,
        "reviewer_file_count": rating_count,
        "mandatory_gates_executed": [
            "frozen-pcm-binding", "private-assignment", "listener-position",
            "pair-sensitivity", "reviewer-influence",
        ],
        "review_reasons": sorted(k for k, flagged in risks.items() if flagged),
        "source_rights_independently_authenticated": False,
        "independent_human_listeners_authenticated": False,
        "human_musical_preference_proven": False,
        "milestone_pass": False,
    }


def inspect_real_m1_gate_bundle(study_path, pack_path, expected_study_id, rating_paths):
    """Run all five private checks, refuse mutation before/after the full run."""
    if (type(expected_study_id) is not str
            or _SHA.fullmatch(expected_study_id) is None
            or type(rating_paths) not in (tuple, list)
            or not 3 <= len(rating_paths) <= 5):
        _fail()
    study, pack = _capture(study_path), _capture(pack_path)
    ratings = [_capture(p) for p in rating_paths]
    if len(set(map(str, ratings))) != len(ratings):
        _fail()
    # Pin the source study and every individual ballot using strict nofollow
    # regular-file descriptors before performing any private PCM traversal.
    paths = [study, pack / "receipt.json", pack / "private" / "answer-key.json",
             pack / "private" / "evidence.json", *ratings]
    try:
        before = [_read_snapshot(p) for p in paths]
        binding = verify_study_pack_binding(study, pack, expected_study_id)
        assignment = audit_study_assignment(study, pack, expected_study_id)
        position = inspect_listener_sides(pack, ratings)
        pair = inspect_real_pilot(study, pack, expected_study_id, ratings)
        reviewer = inspect_real_reviewer_influence(study, pack, expected_study_id, ratings)
        report = compose_m1_gate_reports(
            binding, assignment, position, pair, reviewer, rating_count=len(ratings))
        after = [_read_snapshot(p) for p in paths]
        if before != after or verify_study_pack_binding(study, pack, expected_study_id) != binding:
            _fail()
        return report
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError,
            RecursionError):
        raise M1GateBundleError(_ERROR) from None


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            self.exit(2, "MixLab M1 gate: invalid arguments\n")

    parser = Parser(description="Private M1 technical gate bundle; never music approval")
    parser.add_argument("study")
    parser.add_argument("pack")
    parser.add_argument("ratings", nargs="+")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_real_m1_gate_bundle(
            args.study, args.pack, args.expected_study_id, args.ratings)
    except (OSError, ValueError, TypeError, RecursionError):
        parser.exit(2, "MixLab M1 gate: invalid or changed private inputs\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 3 if report["technical_screen"] == "REVIEW_REQUIRED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
