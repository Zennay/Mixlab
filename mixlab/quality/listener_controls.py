"""Static, read-only accessibility/response-integrity preflight for blind review HTML.

This tests visible, keyboard-operable markup contracts; it does NOT execute JS,
read WAV audio or certify music preference. Exact generated-template verification
and review-pack PCM validation are separate requirements.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat
import tempfile

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


@lru_cache(maxsize=1)
def _official_assets():
    """Reference the shipped form generator, without opening private pack data.

    Generated markup is created only in a temporary directory with a fake
    pack ID. The comparison checks unchanged JS/CSS bytes; it does not execute
    JavaScript or certify browser behaviour.
    """
    from ..cli import write_review

    with tempfile.TemporaryDirectory(prefix="mixlab-review-qa-") as temp:
        page = Path(temp) / "index.html"
        write_review(page, ["trial-001"], "0" * 64)
        reference = page.read_text(encoding="utf-8")
    try:
        return tuple(
            reference.split(f"<{tag}>", 1)[1].split(f"</{tag}>", 1)[0]
            for tag in ("script", "style")
        )
    except (IndexError, ValueError) as exc:
        raise ValueError(_ERROR) from None


def _attributes(attrs):
    keys = [key for key, _ in attrs]
    if len(keys) != len(set(keys)):
        _deny()
    result = dict(attrs)
    if (any(name in result for name in ("hidden", "inert", "disabled", "style", "tabindex"))
            or any(name.startswith("on") for name in result)
            or result.get("aria-hidden", "").lower() == "true"):
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
        self.doctype = False
        self.assets = {"script": [], "style": []}
        self.current_asset = None
        self.legend_open = False
        self.button_text = None

    def handle_starttag(self, tag, attrs):
        a = _attributes(attrs)
        # A browser can suppress or reinterpret otherwise valid-looking HTML
        # inside these containers. HTMLParser alone is not a browser DOM.
        if tag in {"template", "noscript", "plaintext", "xmp", "textarea",
                   "iframe", "object", "embed", "video", "source", "img",
                   "base", "link"}:
            _deny()
        if tag in {"script", "style", "label"} and a:
            _deny()
        if tag in ("script", "style"):
            if self.current_asset is not None:
                _deny()
            self.current_asset = tag
            self.assets[tag].append([])
        if tag == "html":
            self.lang = self.lang or a.get("lang") == "en"
        if a.get("aria-live") in ("polite", "assertive") and a.get("id") == "status":
            self.status_announcers += 1
        if tag == "form":
            if self.form_count or self.form_open or self.field or self.label or set(a) != {"data-pack-id"}:
                _deny()
            self.form_count += 1
            self.form_open = True
            self.pack_id = a.get("data-pack-id")
        elif tag == "fieldset":
            if (not self.form_open or self.field is not None or self.label is not None
                    or set(a) != {"data-trial"}):
                _deny()
            trial = a.get("data-trial")
            if not isinstance(trial, str) or not _TRIAL.fullmatch(trial):
                _deny()
            self.field = {"id": trial, "labels": [], "legend": [], "legends": 0}
        elif tag == "legend":
            if (self.field is None or self.label is not None
                    or self.legend_open or self.field["legends"]
                    or self.field["labels"] or a):
                _deny()
            self.legend_open = True
            self.field["legends"] = 1
        elif tag == "label":
            if not self.form_open or self.label is not None or self.legend_open:
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
            if (not self.form_open or self.field is not None
                    or self.button_text is not None or a.get("type", "submit") != "submit"):
                _deny()
            self.button_text = []

    def handle_data(self, data):
        if self.current_asset is not None:
            self.assets[self.current_asset][-1].append(data)
        if self.legend_open and self.field is not None:
            self.field["legend"].append(data)
        if self.button_text is not None:
            self.button_text.append(data)
        if self.label is not None and self.option is None:
            self.label["text"].append(data)
        if self.option is not None:
            self.option["text"].append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if self.current_asset != tag:
                _deny()
            self.current_asset = None
        elif tag == "legend":
            if not self.legend_open:
                _deny()
            self.legend_open = False
        elif tag == "button":
            if self.button_text is None:
                _deny()
            if " ".join("".join(self.button_text).split()) != "Download my ratings":
                _deny()
            self.buttons += 1
            self.button_text = None
        elif tag == "option":
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
            if self.field is None or self.label is not None or self.legend_open:
                _deny()
            self._check_fieldset(self.field)
            self.trials.append(self.field["id"])
            self.field = None
        elif tag == "form":
            if not self.form_open or self.field is not None or self.label is not None:
                _deny()
            self.form_open = False

    def handle_comment(self, data):
        # Comments in a review page can leak hidden trial identity.
        _deny()

    def handle_decl(self, decl):
        if self.doctype or decl.strip().lower() != "doctype html":
            _deny()
        self.doctype = True

    def handle_pi(self, data):
        _deny()

    def unknown_decl(self, data):
        _deny()

    def _check_fieldset(self, field):
        trial = field["id"]
        if (field["legends"] != 1
                or " ".join("".join(field["legend"]).split()) != trial):
            _deny()
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
                or self.option is not None or not self.lang or not self.doctype
                or self.current_asset is not None or self.legend_open
                or self.button_text is not None
                or not isinstance(self.pack_id, str)
                or not _PACK.fullmatch(self.pack_id)):
            _deny()
        if not 1 <= len(self.trials) <= MAX_TRIALS:
            _deny()
        expected_script, expected_style = _official_assets()
        if (len(self.assets["script"]) != 1 or len(self.assets["style"]) != 1
                or "".join(self.assets["script"][0]) != expected_script
                or "".join(self.assets["style"][0]) != expected_style):
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
            "official_inline_script_unchanged": True,
            "official_stylesheet_unchanged": True,
            "trial_legends_verified": True,
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
