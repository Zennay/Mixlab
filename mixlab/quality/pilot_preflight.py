"""One-command frozen MixLab pilot technical gate, without release approval.

This composes existing bound validators; it never reads ratings or re-encodes
review audio. All output is non-identifying and cannot authorize distribution.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import re

from .listener_controls import check_review_controls
from .pack import inspect_review_pack
from .study_binding import verify_study_pack_binding

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REFUSAL = "private study or review pack invalid (details withheld)"


def _identity(path, *, directory=False):
    """Stat a named canonical member without following its final symlink."""
    info = os.lstat(path)
    if directory and not stat.S_ISDIR(info.st_mode):
        raise ValueError(_REFUSAL)
    if not directory and not stat.S_ISREG(info.st_mode):
        raise ValueError(_REFUSAL)
    return (info.st_dev, info.st_ino, info.st_mode,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _private_inventory(root, study):
    """Bounded before/after inventory for the MULTI-PASS QA transaction.

    Individual scanners already detect their own mid-read changes. Without a
    wrapper snapshot a modified public HTML or receipt *after its check but
    before a different validator finishes* can still be marked a clean pass.
    This detects ordinary concurrent replacements; it is not an atomic lock
    or resistance to a malicious filesystem actor forging timestamps.
    """
    root = Path(root)
    review = root / "review"
    private = root / "private"
    dirs = (root, review, private)
    files = (study, root / "receipt.json",
             private / "answer-key.json", private / "evidence.json",
             review / "index.html")
    dir_info = tuple(_identity(path, directory=True) for path in dirs)
    file_info = tuple(_identity(path) for path in files)
    entries = list(review.iterdir())
    if not 2 <= len(entries) <= 121:
        raise ValueError(_REFUSAL)
    inventory = tuple(sorted((item.name, _identity(item)) for item in entries))
    return dir_info, file_info, inventory


def _inspect_pilot_preflight(pack_root, study_path, externally_pinned_study_id):
    """Check the exact generated A/B form, PCM and independent frozen study.

    Raises ValueError for malformed/unbound inputs; returns HOLD for any
    technical warning. A passing result is NEVER a human/listener approval.
    The caller must separately pin the study ID before any trial collection.
    """
    if (not isinstance(externally_pinned_study_id, str)
            or _SHA.fullmatch(externally_pinned_study_id) is None
            or study_path is None or pack_root is None):
        raise ValueError(_REFUSAL)

    root = Path(pack_root)
    before = _private_inventory(root, study_path)
    form = check_review_controls(root / "review" / "index.html")
    screen = inspect_review_pack(
        root / "review", require_generated_html=True, require_receipt=True
    )
    binding = verify_study_pack_binding(
        study_path, root, externally_pinned_study_id
    )

    n = binding["trial_count"]
    if (not 5 <= n <= 10
            or form.get("trial_count") != n
            or screen.get("trial_count") != n
            or form.get("playback_controls") != 2 * n
            or form.get("required_rating_controls") != n
            or not form.get("official_inline_script_unchanged")
            or not form.get("official_stylesheet_unchanged")
            or not form.get("trial_legends_verified")
            or not screen.get("official_generated_html_verified")
            or not screen.get("public_receipt_pack_id_verified")
            or not screen.get("review_page_audio_links_verified")
            or screen.get("answer_key_opened") is not False
            or not binding.get("study_pack_metadata_consistent_with_pinned_id")
            or binding.get("human_preference_proven") is not False
            or binding.get("milestone_pass") is not False):
        raise ValueError(_REFUSAL)

    warnings = screen.get("warning_trial_count")
    repeated = screen.get("cross_trial_repeated_variant_count")
    if (type(warnings) is not int or not 0 <= warnings <= n
            or type(repeated) is not int or not 0 <= repeated <= 2 * n):
        raise ValueError(_REFUSAL)
    clear = warnings == 0 and repeated == 0
    if _private_inventory(root, study_path) != before:
        raise ValueError(_REFUSAL)

    # Deliberately no trial-level metrics, filenames, pack-id or source hashes.
    return {
        "schema_version": 1,
        "technical_gate": "pass" if clear else "hold",
        "trial_count": n,
        "technical_warning_trial_count": warnings,
        "cross_trial_repeated_variant_count": repeated,
        "official_review_form_checked": True,
        "public_receipt_and_audio_checked": True,
        "externally_pinned_study_metadata_consistent": True,
        "actual_source_rights_independently_authenticated": False,
        "actual_source_audio_authenticated": False,
        "independent_listeners_verified": False,
        "human_preference_proven": False,
        "release_authorized": False,
        "milestone_pass": False,
    }


def inspect_pilot_preflight(pack_root, study_path, externally_pinned_study_id):
    """Public path-safe API: no source path escapes through error messages."""
    try:
        return _inspect_pilot_preflight(pack_root, study_path,
                                        externally_pinned_study_id)
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError):
        raise ValueError(_REFUSAL) from None


class _PrivateParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(3, "MixLab pilot preflight: invalid arguments (details withheld)\n")


def main(argv=None):
    parser = _PrivateParser(description="Offline pilot technical gate; never release approval")
    parser.add_argument("pack", help="Private pack root")
    parser.add_argument("--study", required=True, help="Private frozen study JSON")
    parser.add_argument("--expected-study-id", required=True,
                        help="Externally pinned 64-character SHA-256 study ID")
    args = parser.parse_args(argv)
    try:
        verdict = inspect_pilot_preflight(args.pack, args.study,
                                         args.expected_study_id)
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError):
        parser.exit(3, "MixLab pilot preflight: " + _REFUSAL + "\n")
    print(json.dumps(verdict, sort_keys=True, allow_nan=False))
    return 0 if verdict["technical_gate"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
