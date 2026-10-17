"""Opt-in, private post-rating A/B-position consistency preflight.

Does not identify a preference winner or certify listener independence.
Official MixLab aggregation/PCM verification remains the source of truth for
rating admissibility; this only flags possible positional answering behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from ..evaluation import aggregate
from .repeatability import _open_no_symlink_components, _identity

_MAX_RATING_BYTES = 64 * 1024
_MAX_REVIEWERS = 16
_ERROR = "Invalid or changed private listener evidence"


class ListenerPositionError(ValueError):
    """No input pathname, pseudonym, trial or answer key in this exception."""


def _fail() -> None:
    raise ListenerPositionError(_ERROR)


def _read_snapshot(path: Path) -> tuple[bytes, tuple[int, ...]]:
    """Read one bounded regular-file descriptor, with full-path no-symlinks.

    The lexical path is captured once by the caller; identity is compared to
    a second named descriptor before returning. Another pass after the real
    aggregator refuses observable mutation. This is not atomic against a
    continuously malicious writer; frozen inputs must be immutable.
    """
    fd = _open_no_symlink_components(path)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= _MAX_RATING_BYTES:
            _fail()
        with os.fdopen(fd, "rb", buffering=0) as source:
            fd = -1
            raw = source.read(_MAX_RATING_BYTES + 1)
            after = os.fstat(source.fileno())
        if (len(raw) > _MAX_RATING_BYTES or len(raw) != before.st_size
                or _identity(before) != _identity(after)):
            _fail()
    finally:
        if fd >= 0:
            os.close(fd)

    # Guard against a replaced basename OR symlinked ancestor directory.
    named = _open_no_symlink_components(path)
    try:
        if _identity(os.fstat(named)) != _identity(before):
            _fail()
    finally:
        os.close(named)
    return hashlib.sha256(raw).digest(), _identity(before)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _read_votes(path: Path) -> tuple[dict, tuple[bytes, tuple[int, ...]]]:
    """Load only tiny private reviewer JSON and retain an anonymous snapshot."""
    snapshot = _read_snapshot(path)
    # The normal capped single-descriptor read above should be parsed rather
    # than reopening a possibly changed pathname. Fetch it with the same
    # strict descriptor method, retaining bytes only ephemerally.
    fd = _open_no_symlink_components(path)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 2 <= info.st_size <= _MAX_RATING_BYTES:
            _fail()
        with os.fdopen(fd, "rb", buffering=0) as source:
            fd = -1
            raw = source.read(_MAX_RATING_BYTES + 1)
            end = os.fstat(source.fileno())
        if len(raw) != info.st_size or _identity(info) != _identity(end):
            _fail()
        if (hashlib.sha256(raw).digest(), _identity(info)) != snapshot:
            _fail()
    finally:
        if fd >= 0:
            os.close(fd)

    try:
        vote = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: _fail(),
        )
    except (UnicodeError, ValueError, RecursionError):
        _fail()
    if not isinstance(vote, dict):
        _fail()
    return vote, snapshot


def inspect_listener_sides(pack_path, rating_paths) -> dict:
    """Flag aggregate and within-reviewer A/B response patterns, never IDs.

    Each vote passes the unchanged official aggregate() validation, including
    reviewer uniqueness, trial completeness, checksum-bound real WAVs and
    correct pack ID. A warning is a prompt for human methodological review,
    NOT evidence that any listener is fake or that a particular mix is good.
    """
    if (not isinstance(rating_paths, (list, tuple))
            or not 1 <= len(rating_paths) <= _MAX_REVIEWERS):
        _fail()
    try:
        paths = [Path(os.fspath(item)) for item in rating_paths]
        pack = Path(os.fspath(pack_path))
        # No aliasing the same file under two input paths.
        if len(set(map(str, paths))) != len(paths):
            _fail()
        snapshots = []
        side_counts = {"A": 0, "B": 0, "Tie": 0, "Both unusable": 0}
        extreme_reviewers = 0
        for path in paths:
            vote, snapshot = _read_votes(path)
            snapshots.append(snapshot)
            rows = vote.get("ratings")
            if not isinstance(rows, list) or not 1 <= len(rows) <= 10:
                _fail()
            # Aggregator validates exact IDs, admissible choices and full
            # coverage. Here count only known labels, never echo unknowns.
            a = b = 0
            for row in rows:
                if not isinstance(row, dict):
                    _fail()
                preference = row.get("preference")
                if preference not in side_counts:
                    _fail()
                side_counts[preference] += 1
                a += preference == "A"
                b += preference == "B"
            if a + b >= 5 and max(a, b) * 5 >= (a + b) * 4:
                extreme_reviewers += 1

        # Genuine checksum-bound audio+ratings validator; never replace it
        # with a copied grammar or mocked success.
        evidence = aggregate(pack, paths)
        if (evidence["reviewers"] != len(paths)
                or not 5 <= evidence["trials"] <= 10
                or sum(side_counts.values()) != evidence["trials"] * len(paths)):
            _fail()
        for path, snapshot in zip(paths, snapshots):
            if _read_snapshot(path) != snapshot:
                _fail()
    except (OSError, ValueError, KeyError, TypeError, IndexError,
            OverflowError, RecursionError) as exc:
        raise ListenerPositionError(_ERROR) from None

    decisive = side_counts["A"] + side_counts["B"]
    sufficient = len(paths) >= 3 and decisive >= 12
    dominance = (
        max(side_counts["A"], side_counts["B"]) * 5 >= decisive * 4
        if sufficient else None
    )
    return {
        "schema_version": 1,
        "reviewer_count": len(paths),
        "trial_count": evidence["trials"],
        "decisive_vote_count": decisive,
        "sufficient_for_position_screen": sufficient,
        "aggregate_position_dominance_review": dominance,
        "individual_position_pattern_review": extreme_reviewers > 0,
        "source_permissions_independently_authenticated": False,
        "independent_listener_identity_authenticated": False,
        "human_preference_proven": False,
        "milestone_pass": False,
    }


def main(argv=None) -> int:
    class SafeParser(argparse.ArgumentParser):
        def error(self, _message):
            self.exit(2, "MixLab listener position: invalid arguments\n")

    parser = SafeParser(description="Offline private reviewer A/B bias screen (no preference verdict)")
    parser.add_argument("pack")
    parser.add_argument("ratings", nargs="+")
    args = parser.parse_args(argv)
    try:
        result = inspect_listener_sides(args.pack, args.ratings)
    except (OSError, ValueError, TypeError, RecursionError):
        parser.exit(2, "MixLab listener position: private inputs invalid or changed\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    if (result["aggregate_position_dominance_review"] is True
            or result["individual_position_pattern_review"]):
        return 3
    if not result["sufficient_for_position_screen"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
