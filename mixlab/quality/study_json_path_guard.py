"""Read-only all-component path stability gate for private frozen-study inputs.

A supplementary ML-07 quality gate, not a signature or source-rights proof.
Avoid changing the shared ML-05 JSON decoder or altering any private files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

from .repeatability import _open_no_symlink_components
from .study_binding import verify_study_pack_binding

_ID = re.compile(r"[0-9a-f]{64}\Z")
_ERROR = "unsafe or incompatible private pilot inputs (details withheld)"
_MAX_JSON = 4 * 1024 * 1024


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _snapshot_file(path):
    """Pin lexical ancestors and file as opened by the kernel, not lstat(path)."""
    fd = _open_no_symlink_components(Path(path))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= _MAX_JSON:
            raise ValueError(_ERROR)
        # Do not trust an fstat alone. Refuse a pathname already replaced
        # after the first open, or mutated while descriptors were inspected.
        second_fd = _open_no_symlink_components(Path(path))
        try:
            current = os.fstat(second_fd)
        finally:
            os.close(second_fd)
        after = os.fstat(fd)
        if _identity(before) != _identity(after) or _identity(before) != _identity(current):
            raise ValueError(_ERROR)
        return _identity(before)
    finally:
        os.close(fd)


def _snapshot_directory(path):
    """No-follow the complete lexical directory tree for private/review roots."""
    fd = _open_no_symlink_components(Path(path))
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(_ERROR)
        return _identity(info)
    finally:
        os.close(fd)


def _capture_path(value):
    """Resolve a custom PathLike exactly once and suppress its private errors.

    A malicious PathLike can alternate destinations between preflight and
    verification; use the one lexical string throughout the whole transaction.
    """
    try:
        raw = os.fspath(value)
        if type(raw) is not str or chr(0) in raw:
            raise ValueError(_ERROR)
        # Anchor relative paths against exactly one cwd observation. Path.absolute()
        # deliberately retains lexical '..' and does not resolve symlinks.
        return Path(raw).absolute()
    except Exception:
        raise ValueError(_ERROR) from None


def _inventory(study, root):
    root = Path(root)
    return (
        _snapshot_file(study),
        _snapshot_file(root / "receipt.json"),
        _snapshot_file(root / "private" / "evidence.json"),
        _snapshot_file(root / "private" / "answer-key.json"),
        _snapshot_directory(root),
        _snapshot_directory(root / "private"),
        _snapshot_directory(root / "review"),
    )


def inspect_pinned_study_json_paths(study, pack, expected_study_id):
    """Validate a real frozen pack only if all JSON ancestor paths are safe.

    Exposes no filenames, study hashes, reviewer identifiers or audio in output.
    The existing private verify_study_pack_binding still authenticates pack
    PCM hashes and compares the study with an EXTERNALLY supplied ID.
    This additional gate does not examine public listener HTML/accessibility.
    """
    try:
        if not isinstance(expected_study_id, str) or _ID.fullmatch(expected_study_id) is None:
            raise ValueError(_ERROR)
        source = _capture_path(study)
        root = _capture_path(pack)
        before = _inventory(source, root)
        verified = verify_study_pack_binding(source, root, expected_study_id)
        if (_inventory(source, root) != before
                or verified.get("study_pack_metadata_consistent_with_pinned_id") is not True
                or verified.get("milestone_pass") is not False):
            raise ValueError(_ERROR)
        return {
            "schema_version": 1,
            "metric": "frozen_study_all_component_json_path_and_binding",
            "technical_gate": "pass",
            "no_symlink_json_ancestors_verified": True,
            "externally_pinned_study_binding_verified": True,
            "public_review_ui_verified": False,
            "actual_source_rights_authenticated": False,
            "independent_human_preference_proven": False,
            "release_authorized": False,
        }
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            OverflowError, UnicodeError, RecursionError, AssertionError):
        raise ValueError(_ERROR) from None


class _PrivateParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "MixLab JSON path QA: invalid arguments (details withheld)\n")


def main(argv=None):
    parser = _PrivateParser(description="Offline all-component JSON path admission and frozen-study binding")
    parser.add_argument("study")
    parser.add_argument("pack")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_pinned_study_json_paths(args.study, args.pack,
                                                 args.expected_study_id)
    except ValueError:
        parser.exit(2, "MixLab JSON path QA: unsafe or invalid source (details withheld)\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
