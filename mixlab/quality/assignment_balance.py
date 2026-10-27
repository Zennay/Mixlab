"""Private, opt-in A/B side-assignment preflight for a frozen listening study.

This supplements pinned ML-07 study/PCM verification. It identifies position
confounds, not audio merit, reviewer identity or a statistically powered result.
Never serialize the secret per-trial answer mapping.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..evaluation.json_admission import load_bounded_json
from .study_binding import verify_study_pack_binding


class AssignmentBalanceError(ValueError):
    """Path-free invalid private preflight input."""


def _refuse() -> None:
    raise AssignmentBalanceError("Invalid or changed private study assignment")


def inspect_assignments(answer_key: object) -> dict:
    """Pure bounded assignment diagnostics; results never expose individual sides.

    No PCM, source names, pack identifiers, or individual correct answers are
    included. For small (5–10) pilot studies, review imbalanced sides *before*
    collecting preferences; imbalance is not itself evidence of listener bias.
    """
    if not isinstance(answer_key, list) or not 5 <= len(answer_key) <= 10:
        _refuse()
    sides = []
    groups: dict[str, list[str]] = {}
    for index, trial in enumerate(answer_key, 1):
        if not isinstance(trial, dict) or trial.get("trial") != f"trial-{index:03d}":
            _refuse()
        a, b = trial.get("A"), trial.get("B")
        if not isinstance(a, str) or not isinstance(b, str):
            _refuse()
        if (a == "baseline") == (b == "baseline") or a == b:
            _refuse()
        family = b if a == "baseline" else a
        if not family or family == "baseline":
            _refuse()
        side = "A" if a == "baseline" else "B"
        sides.append(side)
        groups.setdefault(family, []).append(side)
    total_imbalance = abs(sides.count("A") - sides.count("B")) > 1
    family_imbalance = any(abs(row.count("A") - row.count("B")) > 1
                           for row in groups.values())
    # A long consecutive run makes accidental position preference particularly
    # difficult to distinguish in a tiny pilot, even if the totals balance.
    longest = 1
    current = 1
    for previous, following in zip(sides, sides[1:]):
        current = current + 1 if previous == following else 1
        longest = max(longest, current)
    streak = longest >= 3
    return {
        "schema_version": 1,
        "trial_count": len(sides),
        "global_side_imbalance": total_imbalance,
        "candidate_family_side_imbalance": family_imbalance,
        "consecutive_side_streak": streak,
        "side_assignment_review_required": total_imbalance or family_imbalance or streak,
        "source_rights_authenticated": False,
        "human_preference_proven": False,
        "milestone_pass": False,
    }



def propose_private_balanced_sides(candidate_families, seed: int) -> tuple[str, ...]:
    """Optional pure pre-rating plan; never publish the returned answer map.

    Brute-force is deliberately safe for at most ten trials (2**10 masks).
    Choose among acceptable schedules using a seeded digest ranking, not a
    deterministic alternating pattern. The actual producer and pack identity
    remain owned by ML-05; this does NOT rewrite an existing frozen pack.
    """
    import hashlib
    from ..models import FAMILY_NAMES

    if (type(candidate_families) not in (tuple, list)
            or not 5 <= len(candidate_families) <= 10
            or type(seed) is not int or not 0 <= seed < 2 ** 63):
        _refuse()
    supported = set(FAMILY_NAMES) - {"baseline"}
    if any(type(family) is not str or family not in supported
           for family in candidate_families):
        _refuse()
    winner = None
    for mask in range(1 << len(candidate_families)):
        assignments = tuple("A" if mask & (1 << i) else "B"
                            for i in range(len(candidate_families)))
        secret_key = [
            {"trial": f"trial-{i:03d}",
             "A": "baseline" if side == "A" else family,
             "B": family if side == "A" else "baseline"}
            for i, (family, side) in enumerate(
                zip(candidate_families, assignments), 1)
        ]
        if inspect_assignments(secret_key)["side_assignment_review_required"]:
            continue
        rank = hashlib.sha256(f"{seed}:{mask}".encode("ascii")).digest()
        candidate = (rank, assignments)
        if winner is None or candidate < winner:
            winner = candidate
    if winner is None:
        _refuse()
    return winner[1]


def audit_study_assignment(study_path, pack_path, expected_study_id) -> dict:
    """Require genuine external-ID/pinned WAV verification and stable answer key.

    Existing ML-07 binding validates the private answer key against checksum-
    bound WAVs. The extra before/after key comparison refuses observable drift.
    As with existing local checks, this is not a malicious concurrent-writer
    transaction or a substitute for immutable study-pack storage.
    """
    root = Path(pack_path)
    private = root / "private" / "answer-key.json"
    before = load_bounded_json(private)
    report = inspect_assignments(before)
    verify_study_pack_binding(study_path, root, expected_study_id)
    after = load_bounded_json(private)
    if after != before:
        _refuse()
    return report


def main(argv=None) -> int:
    class SafeParser(argparse.ArgumentParser):
        def error(self, _message):
            self.exit(2, "MixLab side assignment: invalid arguments\n")

    parser = SafeParser(description="Private A/B side-bias QA; NOT a music preference result")
    parser.add_argument("study")
    parser.add_argument("pack")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        report = audit_study_assignment(args.study, args.pack, args.expected_study_id)
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError):
        parser.exit(2, "MixLab side assignment: private inputs invalid or changed\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 3 if report["side_assignment_review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
