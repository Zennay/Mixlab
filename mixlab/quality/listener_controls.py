"""Static, read-only accessibility/response-integrity preflight for blind review HTML.

This tests visible, keyboard-operable markup contracts; it does NOT execute JS,
read WAV audio or certify music preference. Exact generated-template verification
and review-pack PCM validation are separate requirements.
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
MAX_TRIALS = 60
_PACK = re.compile(r"[0-9a-f]{64}\Z")
_TRIAL = re.compile(r"trial-[0-9]{3}\Z")
_OPTIONS = (("", "Choose…"), ("A", "A"), ("B", "B"),
            ("Tie", "Tie"), ("Both unusable", "Both unusable"))
_ERROR = "invalid or inaccessible offline review controls"


def _deny():
    raise ValueError(_ERROR)


def _attributes(attrs):
    keys = [key for key, _ in attrs]
    if len(keys) != len(set(keys)):
        _deny()
    result = dict(attrs)
    if (any(name in result for name in ("hidden", "inert", "disabled"))
            or result.get("aria-hidden", "").lower() == "true"
            or result.get("tabindex") == "-1"):
        _deny()
    return result


class _ReviewControls(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.form_open = False
        self.form_count = 0
        self.pack_id = None
        self.trials = []
        self.field = None
        self.label = None
        self.selection = None
        self.option = None
        self.reviewers = []
        self.buttons = 0
        self.status_announcers = 0
        self.lang = False

    def handle_starttag(self, tag, attrs):
        a = _attributes(attrs)
        if tag == "html":
            self.lang = self.lang or bool(a.get("lang", "").strip())
        if a.get("aria-live") in ("polite", "assertive") and a.get("id") == "status":
            self.status_announcers += 1
        if tag == "form":
            if self.form_count or self.form_open or self.field or self.label:
                _deny()
            self.form_count += 1
            self.form_open = True
            self.pack_id = a.get("data-pack-id")
        elif tag == "fieldset":
            if not self.form_open or self.field is not None or self.label is not None:
                _deny()
            trial = a.get("data-trial")
            if not isinstance(trial, str) or not _TRIAL.fullmatch(trial):
                _deny()
            self.field = {"id": trial, "labels": []}
        elif tag == "label":
            if not self.form_open or self.label is not None:
                _deny()
            self.label = {"text": [], "audio": [], "input": [], "select": []}
        elif tag == "audio":
            if self.field is None or self.label is None:
                _deny()
            if (set(a) != {"controls", "preload", "src"}
                    or a["controls"] is not None
                    or a["preload"] != "none"):
                _deny()
            self.label["audio"].append(a["src"])
        elif tag == "input":
            if (not self.form_open or self.field is not None
                    or self.label is None or self.selection is not None):
                _deny()
            if (a.get("name") != "reviewer" or "required" not in a
                    or a.get("maxlength") != "40"
                    or a.get("type", "text") != "text"):
                _deny()
            self.label["input"].append(a)
        elif tag == "select":
            if (self.field is None or self.label is None
                    or self.selection is not None):
                _deny()
            self.selection = {"attributes": a, "options": []}
        elif tag == "option":
            if self.selection is None or self.option is not None:
                _deny()
            self.option = {"attributes": a, "text": []}
        elif tag == "button":
            if not self.form_open or self.field is not None:
                _deny()
            if a.get("type", "submit") != "submit":
                _deny()
            self.buttons += 1

    def handle_data(self, data):
        if self.label is not None:
            self.label["text"].append(data)
        if self.option is not None:
            self.option["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "option":
            if self.option is None or self.selection is None:
                _deny()
            option = self.option
            label = " ".join("".join(option["text"]).split())
            value = option["attributes"].get("value", label)
            self.selection["options"].append((value, label))
            self.option = None
        elif tag == "select":
            if self.selection is None or self.option is not None or self.label is None:
                _deny()
            self.label["select"].append(self.selection)
            self.selection = None
        elif tag == "label":
            if self.label is None or self.selection is not None:
                _deny()
            label = self.label
            label["text"] = " ".join("".join(label["text"]).split())
            if self.field is None:
                self.reviewers.append(label)
            else:
                self.field["labels"].append(label)
            self.label = None
        elif tag == "fieldset":
            if self.field is None or self.label is not None:
                _deny()
            self._check_fieldset(self.field)
            self.trials.append(self.field["id"])
            self.field = None
        elif tag == "form":
            if not self.form_open or self.field is not None or self.label is not None:
                _deny()
            self.form_open = False

    def _check_fieldset(self, field):
        trial = field["id"]
        labels = field["labels"]
        if len(labels) != 3:
            _deny()
        for label, variant in zip(labels[:2], ("A", "B")):
            if (label["text"] != variant or label["audio"] != [f"{trial}-{variant}.wav"]
                    or label["input"] or label["select"]):
                _deny()
        rating = labels[2]
        if (rating["text"] != "Preference" or rating["audio"] or rating["input"]
                or len(rating["select"]) != 1):
            _deny()
        select = rating["select"][0]
        if (select["attributes"] != {"required": None, "name": trial}
                or tuple(select["options"]) != _OPTIONS):
            _deny()

    def finish(self):
        if (self.form_count != 1 or self.form_open or self.field is not None
                or self.label is not None or self.selection is not None
                or self.option is not None or not self.lang
                or not isinstance(self.pack_id, str)
                or not _PACK.fullmatch(self.pack_id)):
            _deny()
        if not 1 <= len(self.trials) <= MAX_TRIALS:
            _deny()
        expected = [f"trial-{n:03d}" for n in range(1, len(self.trials) + 1)]
        if self.trials != expected:
            _deny()
        if (len(self.reviewers) != 1 or self.reviewers[0]["text"] != "Anonymous reviewer code"
                or len(self.reviewers[0]["input"]) != 1
                or self.reviewers[0]["audio"] or self.reviewers[0]["select"]
                or self.buttons != 1 or self.status_announcers != 1):
            _deny()
        return {
            "schema_version": 1,
            "trial_count": len(self.trials),
            "playback_controls": 2 * len(self.trials),
            "required_rating_controls": len(self.trials),
            "labelled_reviewer_input": True,
            "status_announcement": True,
            "static_listener_controls_verified": True,
            "javascript_or_browser_verified": False,
            "human_musical_preference_verified": False,
        }


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def check_review_controls(path):
    """Reject linked/swapped/oversize markup without exposing source paths."""
    source = Path(path)
    try:
        fd = _open_no_symlink_components(source)
        with os.fdopen(fd, "rb", buffering=0) as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_HTML_BYTES:
                _deny()
            raw = handle.read(MAX_HTML_BYTES + 1)
            if len(raw) != before.st_size:
                _deny()
            after = os.fstat(handle.fileno())
            fd2 = _open_no_symlink_components(source)
            try:
                named = os.fstat(fd2)
            finally:
                os.close(fd2)
            if _identity(before) != _identity(after) or _identity(before) != _identity(named):
                _deny()
        page = raw.decode("utf-8", errors="strict")
        parser = _ReviewControls()
        parser.feed(page)
        parser.close()
        return parser.finish()
    except (OSError, UnicodeError, ValueError, TypeError, AssertionError) as exc:
        raise ValueError(_ERROR) from None


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "review controls: invalid arguments (details withheld)\n")


def main(argv=None):
    parser = _PrivateParser(description="Static offline blind listening markup QA")
    parser.add_argument("review_html", help="Private local review/index.html")
    args = parser.parse_args(argv)
    try:
        result = check_review_controls(args.review_html)
    except ValueError:
        parser.exit(3, "review controls: invalid or inaccessible page (details withheld)\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
