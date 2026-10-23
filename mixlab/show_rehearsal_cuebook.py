"""Print an explicitly human-selected, source-bound private rehearsal cuebook.

All live WAV/source provenance and input rehearsal journals are read again.
This is operator metadata, not music rights, audio approval, listening
preference, measured venue timing or an automatically selected DJ mix.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import wave

from .marathon_sequence import _private_html_destination
from .show_rehearsal import _read_journal
from .show_rehearsal_compare import _admit_sources_and_takes

SELECTION_KIND = "mixlab-private-rehearsal-take-selection-v1"
MAX_PAGE = 384 * 1024


def load_selected(selection_path: str, source_pairs: tuple[str, ...],
                  journals: tuple[str, ...]) -> tuple[list[dict], dict, dict]:
    selection = _read_journal(selection_path)
    sources, takes = _admit_sources_and_takes(source_pairs, journals)
    required = {
        "schema_version", "kind", "source_sha256s", "journal_sha256s",
        "selected_take_index", "private_only", "operator_selected",
        "automatically_ranked", "blind_study",
    }
    if (not isinstance(selection, dict) or set(selection) != required or
            type(selection["schema_version"]) is not int or selection["schema_version"] != 1 or
            selection["kind"] != SELECTION_KIND or
            selection["source_sha256s"] != [s["wav_sha256"] for s in sources] or
            selection["journal_sha256s"] != [t["journal_sha256"] for t in takes] or
            type(selection["selected_take_index"]) is not int or
            not 0 <= selection["selected_take_index"] < len(takes) or
            selection["private_only"] is not True or
            selection["operator_selected"] is not True or
            selection["automatically_ranked"] is not False or
            selection["blind_study"] is not False):
        raise ValueError("Selection is not the original human-selected, source-bound take")
    return sources, takes[selection["selected_take_index"]], selection


def private_destination(output_path: str, selection_path: str,
                        source_pairs: tuple[str, ...],
                        journals: tuple[str, ...]) -> Path:
    out = _private_html_destination(output_path)
    parents = [Path(raw).absolute() for raw in (
        selection_path, *source_pairs, *journals
    )]
    if any(out.is_relative_to(path) or out.is_relative_to(path.parent) for path in parents):
        raise ValueError("Keep cuebook separate from original WAV, sessions and JSON")
    return out


def _fmt(seconds: float) -> str:
    seconds = max(0, round(seconds))
    return f"{int(seconds//3600):02d}:{int((seconds//60)%60):02d}:{int(seconds%60):02d}"


def print_cuebook(new_private_html: str, selection_path: str,
                  source_pairs: tuple[str, ...], journals: tuple[str, ...]) -> dict:
    sources, take, _selection = load_selected(selection_path, source_pairs, journals)
    out = private_destination(new_private_html, selection_path, source_pairs, journals)
    sections = []
    for index, source in enumerate(sources):
        marks = sorted(
            (mark for mark in take["marks"] if mark["set_index"] == index),
            key=lambda mark: (mark["position"], mark["seq"]),
        )
        rows = []
        for mark in marks:
            origin = "Unpaired (outside 60 WAV seconds of any source chapter)"
            if mark["chapter"] is not None:
                diff = mark["chapter_delta"]
                origin = (mark["chapter"] + " / " + mark["chapter_kind"] +
                          f" · {'+' if diff >= 0 else ''}{diff:.2f} s from chapter")
            rows.append(
                "<tr><td>" + str(mark["seq"]) + "</td><td>" + _fmt(mark["position"]) +
                f" ({mark['position']:.3f} s)</td><td>" +
                html.escape(origin, quote=True) + "</td><td class='note'>" +
                html.escape(mark["note"] or "No private cue note", quote=True) + "</td></tr>"
            )
        if not rows:
            rows.append("<tr><td colspan='4'>No manual cue marks in this selected take for this set.</td></tr>")
        chapters = "".join(
            "<li>" + _fmt(ch["start_seconds"]) + " · " +
            html.escape(str(ch["kind"]), quote=True) + " · " +
            html.escape(str(ch["label"]), quote=True) + "</li>"
            for ch in source["chapters"]
        )
        sections.append(
            "<section><h2>" + str(index + 1) + " · " +
            html.escape(source["label"], quote=True) + "</h2><p>" +
            "Original complete WAV: " + _fmt(source["duration_seconds"]) + "</p>" +
            "<p class='hash'>SHA-256: " + source["wav_sha256"] + "</p>" +
            "<h3>Manually marked selected-take cues</h3>" +
            "<table><thead><tr><th>Original entry</th><th>WAV position</th>" +
            "<th>Nearest original chapter</th><th>Private operator note</th>" +
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>" +
            "<details><summary>All original source chapters</summary><ol>" + chapters +
            "</ol></details></section>"
        )
    page = ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none';form-action 'none'">
<title>MixLab · Selected manual rehearsal cuebook</title>
<style>body{max-width:1100px;margin:auto;padding:30px;font:15px/1.5 system-ui;color:#192f38}
h1{font-size:42px;line-height:1.1}section{border-top:2px solid #9ab;padding:20px 0;break-inside:avoid}
table{width:100%;border-collapse:collapse}th,td{padding:9px;border:1px solid #8ca6ae;text-align:left;vertical-align:top}
tr{break-inside:avoid}th{background:#e4f3ed}.note{white-space:pre-wrap;overflow-wrap:anywhere;max-width:350px}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
.notice{background:#eff5f5;border-left:4px solid #317c67;padding:17px}
@media print{body{padding:0}details{display:block}details>*{display:block!important}}</style>
<h1>Private DJ cuebook · """ + html.escape(take["label"]) + """</h1>
<p class="notice">A human chose this rehearsal take from several private,
source-bound browser/operator logs. The positions are local WAV seek
coordinates, <strong>not</strong> independent evidence of audience hearing,
real venue time, acoustic playback, rights, key/stem accuracy, quality or
blind-listening preference. Nothing starts playback automatically.</p>
<p>This private printout includes only manually supplied cue notes from the
selected rehearsal take, original chapter metadata and SHA fingerprints.
It contains no WAV audio, absolute source paths or set-level operator notes.</p>
<p class="hash">Canonical selected journal SHA-256: """ +
            take["journal_sha256"] + "</p>" + "".join(sections) +
            "</html>").encode("utf-8")
    if not 0 < len(page) <= MAX_PAGE:
        raise ValueError("Private cuebook HTML exceeds size limit")
    with out.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(page)
    return {
        "private_selected_cuebook": str(out), "selected_take": take["label"],
        "manual_cues": len(take["marks"]), "source_verified_sets": len(sources),
        "source_sha256s": [s["wav_sha256"] for s in sources],
        "actual_audio_included": False, "musical_quality_proven": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a human-selected, source-verified private show cuebook")
    parser.add_argument("new_private_mixlab_html")
    parser.add_argument("selected_private_take_json")
    parser.add_argument("session_and_wav_pairs", nargs="+")
    parser.add_argument("--journal", action="append", required=True,
                        help="Original private take journals, in comparison order (2–6)")
    args = parser.parse_args()
    try:
        result = print_cuebook(args.new_private_mixlab_html, args.selected_private_take_json,
                               tuple(args.session_and_wav_pairs), tuple(args.journal))
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, wave.Error):
        parser.exit(2, "MixLab Cuebook: selected take, original WAV, source receipts or destination invalid.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
