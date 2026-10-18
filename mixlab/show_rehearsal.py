"""Private, source-bound manual rehearsal journal for offline Show Conductor.

This parses a browser/operator event log, not measured venue timing, audience
preference, an audio capture, or proof that playback reached the speakers.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import stat
from pathlib import Path
import wave

from .marathon_sequence import _private_html_destination
from .show_conductor import _sources

KIND = "mixlab-private-show-rehearsal-v1"
EVENT_KINDS = frozenset({"arm", "play", "mark", "stop", "ended"})
MAX_EVENTS = 256
MAX_REPORT_BYTES = 192 * 1024
MAX_JOURNAL_BYTES = 192 * 1024
MAX_ELAPSED_MS = 48 * 60 * 60 * 1000



def _read_journal(path: str) -> object:
    source = Path(path).absolute()
    if (source.suffix.lower() != ".json" or source.is_symlink() or
            any(parent.is_symlink() for parent in source.parents)):
        raise ValueError("Choose a regular private, non-symlink JSON journal")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(source, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= MAX_JOURNAL_BYTES:
            raise ValueError("Private rehearsal journal is oversized or not regular")
        body = stream.read(MAX_JOURNAL_BYTES + 1)
        after = os.fstat(stream.fileno())
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(body) != before.st_size or any(
            getattr(before, key) != getattr(after, key) for key in keys
        ):
            raise ValueError("Private rehearsal journal changed during reading")
    return json.loads(body.decode("utf-8"))


def _validate(raw: object, sources: list[dict]) -> list[dict]:
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version", "kind", "source_sha256s", "events",
        "private_only", "automatic_playback", "clock_claim",
    } or type(raw["schema_version"]) is not int or raw["schema_version"] != 1 or (
        raw["kind"] != KIND
        or raw["source_sha256s"] != [item["wav_sha256"] for item in sources]
        or raw["private_only"] is not True
        or raw["automatic_playback"] is not False
        or raw["clock_claim"] != "browser-monotonic-operator-only"
    ):
        raise ValueError("Rehearsal journal metadata does not match original real WAV sources")
    events = raw["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError("Rehearsal journal requires 1-256 operator entries")
    last_elapsed = -1
    for n, event in enumerate(events, start=1):
        required = {"seq", "kind", "set_index", "wav_position_seconds", "elapsed_ms"}
        if (not isinstance(event, dict) or
            (set(event) != required and not (
                event.get("kind") == "mark" and set(event) == required | {"note"}
            ))
        ) or type(event["seq"]) is not int or event["seq"] != n or (
            not isinstance(event["kind"], str) or event["kind"] not in EVENT_KINDS
        ) or type(event["set_index"]) is not int or not (
            0 <= event["set_index"] < len(sources)
        ) or type(event["elapsed_ms"]) is not int or not (
            last_elapsed <= event["elapsed_ms"] <= MAX_ELAPSED_MS
        ):
            raise ValueError("Invalid or out-of-order manual rehearsal event")
        seconds = event["wav_position_seconds"]
        if type(seconds) not in (float, int) or not math.isfinite(seconds) or not (
            0 <= seconds <= sources[event["set_index"]]["duration_seconds"] + .5
        ):
            raise ValueError("Rehearsal event position exceeds original verified WAV")
        if "note" in event:
            note = event["note"]
            if (not isinstance(note, str) or not 1 <= len(note) <= 120 or
                    any(ord(c) < 32 and c not in "\n\t" for c in note)):
                raise ValueError("Invalid private manual cue annotation")
        last_elapsed = event["elapsed_ms"]
    return events


def print_rehearsal(journal_json: str, private_report_html: str, *source_pairs: str) -> dict:
    sources = _sources(source_pairs)
    data = _read_journal(journal_json)
    events = _validate(data, sources)
    out = _private_html_destination(private_report_html)
    if any(out.is_relative_to(Path(raw).absolute().parent) or
           out.is_relative_to(Path(raw).absolute()) for raw in source_pairs):
        raise ValueError("Keep the private journal outside original audio and session folders")

    rows = []
    for e in events:
        index = e["set_index"]
        track = sources[index]
        elapsed = e["elapsed_ms"] / 1000
        wavpos = e["wav_position_seconds"]
        cue_text = "—"
        delta_text = "—"
        if e["kind"] == "mark" and track["chapters"]:
            # This is a WAV-position comparison to receipt chapter metadata,
            # not a measure of how the music sounded or a venue timestamp.
            chapter = min(track["chapters"],
                          key=lambda ch: abs(wavpos - ch["start_seconds"]))
            delta = wavpos - chapter["start_seconds"]
            if abs(delta) <= 60:
                cue_text = str(chapter["label"]) + " · " + str(chapter["kind"])
                delta_text = f"{delta:+.2f}s"
            else:
                cue_text = "No approved chapter within 60s"
        rows.append(
            "<tr><td>" + str(e["seq"]) + "</td><td>" +
            f"{elapsed:.2f}s" + "</td><td>" +
            html.escape(str(e["kind"]), quote=True) + "</td><td>" +
            str(index + 1) + " · " + html.escape(track["label"], quote=True) +
            "</td><td>" + f"{wavpos:.2f}s" + "</td><td>" +
            html.escape(cue_text, quote=True) + "</td><td>" +
            html.escape(delta_text, quote=True) + "</td><td class='annotation'>" +
            html.escape(e.get("note", "—"), quote=True) + "</td></tr>"
        )
    set_summaries = []
    for i, src in enumerate(sources):
        scoped = [event for event in events if event["set_index"] == i]
        marks = sum(event["kind"] == "mark" for event in scoped)
        starts = sum(event["kind"] == "play" for event in scoped)
        completions = sum(event["kind"] == "ended" for event in scoped)
        last = scoped[-1]["kind"] if scoped else "none"
        set_summaries.append(
            "<li><strong>Set " + str(i + 1) + " · " +
            html.escape(src["label"], quote=True) + "</strong> — " +
            str(starts) + " browser play action(s), " +
            str(marks) + " operator cue mark(s), " +
            str(completions) + " browser ended event(s); last recorded action: " +
            html.escape(last, quote=True) + ".</li>"
        )
    summary_html = "<h2>Per-set browser event overview</h2><ol>" + (
        "".join(set_summaries)) + "</ol><p>Event counts, not listening or playback proof.</p>"
    receipt_lines = "".join(
        "<li>Set " + str(i + 1) + " · " + html.escape(s["label"], quote=True) +
        " · <code>" + s["wav_sha256"] + "</code></li>"
        for i, s in enumerate(sources)
    )
    page = ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none';form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MixLab · Private operator rehearsal record</title>
<style>body{max-width:1040px;margin:auto;padding:28px;font:15px/1.5 system-ui;color:#1a333c}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #889da5;padding:8px;text-align:left}
tr:nth-child(even){background:#e7f1f3}code{overflow-wrap:anywhere}
.annotation{white-space:pre-wrap;overflow-wrap:anywhere}
.warn{background:#f4f0e2;padding:16px}@media print{body{padding:0}tr{break-inside:avoid}}
</style><h1>Private Show Conductor rehearsal journal</h1>
<p class="warn">Operator/browser actions and page-relative monotonic times only.
Not independently measured playback, wall clock, audible output, venue performance,
music rights, DJ quality, or blind listening evidence.</p>
<p>No audio, full file path, set-level operator note or web request is stored.
Only optional cue annotations explicitly entered when marking are included here.</p>
<table><thead><tr><th>Entry</th><th>Page elapsed</th><th>Action</th>
<th>Approved set</th><th>WAV seek position</th>
<th>Closest source chapter (marks)</th><th>WAV-position delta</th>
<th>Private operator cue annotation</th></tr></thead><tbody>"""
            + "".join(rows) + "</tbody></table>" + summary_html +
            "<h2>Exact source-verified completed WAVs</h2><ol>"
            + receipt_lines + "</ol></html>").encode("utf-8")
    if not 0 < len(page) <= MAX_REPORT_BYTES:
        raise ValueError("Private rehearsal report exceeds size limit")
    with out.open("xb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(page)
    return {"private_rehearsal_report": str(out), "operator_events": len(events),
            "exact_original_sets": len(sources), "audio_uploaded": False,
            "actual_venue_playback_proven": False}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a private operator-only rehearsal journal re-bound to original SHA-verified WAVs"
    )
    parser.add_argument("private_journal_json")
    parser.add_argument("new_private_mixlab_report_html")
    parser.add_argument("session_and_wav_pairs", nargs="+")
    args = parser.parse_args()
    try:
        result = print_rehearsal(
            args.private_journal_json, args.new_private_mixlab_report_html,
            *args.session_and_wav_pairs,
        )
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, wave.Error):
        parser.exit(2, "MixLab Show Rehearsal: original WAV, private journal or destination invalid.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
