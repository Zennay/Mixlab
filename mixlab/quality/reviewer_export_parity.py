"""Read-only QA for browser reviewer-code versus rating-ingest compatibility.

This static *contract* check cannot prove the browser implements the pattern,
the inline JS is safe, the reviewer is independent, or musical preference.
The official full-page pack check remains mandatory.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat

from .repeatability import _open_no_symlink_components

MAX_HTML_BYTES = 1024 * 1024
# Match the exact pseudonym grammar in mixlab.evaluation.aggregate.
# Escape '-' for HTML pattern's JavaScript 'v' UnicodeSets character class.
BROWSER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_\-]{0,39}"
INGEST_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
_ERROR = "incompatible or unreadable reviewer export contract (details withheld)"


class _ReviewerFields(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = 0
        self.form_depth = 0
        self.reviewers = []
        self.bypass = False

    def handle_starttag(self, tag, attrs):
        names = [name for name, _ in attrs]
        duplicates = len(names) != len(set(names))
        values = dict(attrs)
        if tag == "form":
            self.forms += 1
            self.form_depth += 1
            if "novalidate" in values or duplicates:
                self.bypass = True
        elif tag == "input" and values.get("name") == "reviewer":
            self.reviewers.append((self.form_depth == 1, values, duplicates))
        elif tag == "button":
            if any(a in values for a in ("formnovalidate", "formaction")):
                self.bypass = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "form":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "form":
            self.form_depth -= 1
            if self.form_depth < 0:
                self.bypass = True

    def contract_matches(self):
        if self.forms != 1 or self.form_depth != 0 or self.bypass or len(self.reviewers) != 1:
            return False
        in_form, attrs, duplicates = self.reviewers[0]
        if not in_form or duplicates:
            return False
        if attrs.get("type", "text") != "text":
            return False
        # A missing pattern, preset reviewer, hidden/readonly/disabled field,
        # too-short limit or a browser validation bypass is a HOLD.
        if set(attrs) - {"name", "required", "maxlength", "pattern", "type",
                          "placeholder", "title", "autocomplete"}:
            return False
        if not (attrs.get("name") == "reviewer" and "required" in attrs
                and attrs["required"] is None
                and attrs.get("maxlength") == "40"
                and attrs.get("pattern") == BROWSER_PATTERN):
            return False
        # Assert representative grammar agreement in the QA implementation.
        allowed = ("A", "a9-_", "listener-01", "z" * 40)
        refused = ("", " ", "listener 01", "équipe", "a" * 41, "-bad", "_bad")
        return all(INGEST_PATTERN.fullmatch(value) is not None for value in allowed) and all(
            INGEST_PATTERN.fullmatch(value) is None for value in refused
        )


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inspect_reviewer_export_contract(path):
    """Statically check one nofollow local HTML against the ingest grammar.

    A HOLD is actionable, not an invalid audio or human-study verdict.
    Never report the actual path, reviewer codes or page text.
    """
    try:
        source = Path(path)
        fd = _open_no_symlink_components(source)
        with os.fdopen(fd, "rb", buffering=0) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_HTML_BYTES:
                raise ValueError(_ERROR)
            raw = stream.read(MAX_HTML_BYTES + 1)
            after = os.fstat(stream.fileno())
            check_fd = _open_no_symlink_components(source)
            try:
                named = os.fstat(check_fd)
            finally:
                os.close(check_fd)
            if (len(raw) != before.st_size or _identity(before) != _identity(after)
                    or _identity(before) != _identity(named)):
                raise ValueError(_ERROR)
        parser = _ReviewerFields()
        parser.feed(raw.decode("utf-8", errors="strict"))
        parser.close()
        match = parser.contract_matches()
        return {
            "schema_version": 1,
            "metric": "offline_reviewer_export_ingest_parity",
            "reviewer_input_contract_compatible": match,
            "technical_gate": "pass" if match else "hold",
            "browser_runtime_verified": False,
            "full_review_page_verified": False,
            "ratings_aggregate_verified": False,
            "human_musical_preference_proven": False,
            "release_authorized": False,
        }
    except (OSError, ValueError, TypeError, UnicodeError, AssertionError) as exc:
        raise ValueError(_ERROR) from None


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "reviewer parity: invalid arguments (details withheld)\n")


def main(argv=None):
    parser = _PrivateParser(description="Check HTML reviewer-code versus rating-ingest grammar")
    parser.add_argument("review_html")
    args = parser.parse_args(argv)
    try:
        report = inspect_reviewer_export_contract(args.review_html)
    except ValueError:
        parser.exit(2, "reviewer parity: invalid source (details withheld)\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report["technical_gate"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
