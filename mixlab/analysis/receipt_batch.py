"""Bounded private operator desk: compare up to eight source-bound cue receipts.

No audio, private path, annotator, source SHA, authenticity claim or mix
recommendation is exported into offline HTML. A changed/mismatched pair aborts
the complete export instead of silently omitting an unverified item.
"""
from __future__ import annotations

import argparse
from html import escape
import json

from .cue_timeline import render_cue_timeline
from .receipt_compare import compare_receipt, _cue
from .receipt_session import load_session
from .source_receipt import source_identity, verify_source

MAX_PAIRS = 8


def compare_batch(pairs):
    if not isinstance(pairs, (list, tuple)) or not 1 <= len(pairs) <= MAX_PAIRS:
        raise ValueError("Choose one to eight explicit local receipt/source pairs")
    clips = []
    seen = set()
    observed_sources = []
    for index, pair in enumerate(pairs, 1):
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2 or
                any(not isinstance(part, str) or not part for part in pair)):
            raise ValueError("Invalid private receipt/source selection")
        observed = source_identity(pair[0])
        current = compare_receipt(pair[0], pair[1])
        sha = current["source_sha256"]
        if sha in seen:
            raise ValueError("Duplicate audio source in private comparison")
        seen.add(sha)
        observed_sources.append((pair[0], observed, sha))
        clips.append({"id": f"clip-{index:02d}", "comparison": current})
    # A report is valid only if the *entire selection* still refers to all
    # the same physical PCM bytes at completion. Do not emit a partial
    # report after the first source changes while later clips are analysed.
    for path, identity, sha in observed_sources:
        verify_source(path, identity, sha)
    return {
        "schema_version": 1,
        "kind": "private_operator_cue_batch",
        "clip_count": len(clips),
        "clips": clips,
        "audio_uploaded": False,
        "source_paths_exported": False,
        "render_authorized": False,
        "human_confirmation_independently_verified": False,
        "rights_verified": False,
        "limitations": [
            "Input order is not a recommended DJ order.",
            "Saved manual receipts are unsigned self-declarations.",
            "Differences are not accuracy scores or musical compatibility evidence.",
            "A matched local SHA is not proof that a person listened or holds rights.",
        ],
    }


def render_html(document):
    clips = document["clips"]
    common_duration = max(c["comparison"]["duration_seconds"] for c in clips)
    rows = []
    panels = []
    for entry in clips:
        item = entry["comparison"]
        proposal, manual = item["proposals"], item["operator_declaration"]
        ident = escape(entry["id"])
        def val(x):
            return escape(str(x)) if x is not None else "Onbekend"
        rows.append(
            "<tr><th scope=\"row\">" + ident + "</th><td>" +
            val(proposal["bpm"]) + "</td><td>" + val(manual["bpm"]) +
            "</td><td>" + val(proposal["key"]) + "</td><td>" +
            val(manual["key"]) + "</td></tr>"
        )
        proposals = {
            "beat_seconds": proposal["beats"],
            "downbeat_seconds": proposal["downbeats"],
            "phrase_seconds": proposal["phrases"],
        }
        declared = {
            "downbeat_seconds": manual["downbeats"],
            "phrase_seconds": manual["phrases"],
        }
        duration = item["duration_seconds"]
        proposal_svg = render_cue_timeline(
            duration, proposals, clip_id=entry["id"] + "-proposal",
            scale_seconds=common_duration
        )
        manual_svg = render_cue_timeline(
            duration, declared, clip_id=entry["id"] + "-operator",
            scale_seconds=common_duration, include_beats=False
        )
        panels.append(
            "<details><summary>" + ident + " · privé cue-review op dezelfde bron</summary>"
            "<h3>Automatische voorstellen · niet bevestigd</h3>" +
            proposal_svg + _cue("Beats", proposal["beats"]) +
            _cue("Maatstarts", proposal["downbeats"]) +
            _cue("Frasestarts", proposal["phrases"]) +
            "<h3>Opgeslagen eigen invoer · niet onafhankelijk bevestigd</h3>" +
            "<p>Eigen BPM: " + val(manual["bpm"]) +
            " · eigen eerste beat: " + val(manual["first_beat_seconds"]) +
            "s · eigen toonsoort: " + val(manual["key"]) +
            ". Een volledig handmatig beatgrid is niet opgeslagen.</p>" +
            manual_svg + _cue("Zelf ingevoerde maatstarts", manual["downbeats"]) +
            _cue("Zelf ingevoerde frasestarts", manual["phrases"]) +
            "</details>"
        )
    limits = "".join("<li>" + escape(s) + "</li>" for s in document["limitations"])
    return (
        '<!doctype html><html lang="nl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        '<title>MixLab · privé cue-review van eigen fragmenten</title>'
        '<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;'
        'padding:0 1rem;line-height:1.5;color:#202124}'
        'table{border-collapse:collapse}th,td{border:1px solid #adb7c0;padding:.55rem}'
        'section{overflow-x:auto}details{border:1px solid #bac4cc;'
        'border-radius:.7rem;padding:1rem;margin:1rem 0}'
        'summary{font-weight:650;cursor:pointer}'
        '.cue-timeline svg{width:100%;height:auto;display:block}'
        '.cue-timeline{margin:.8rem 0}.cue-timeline figcaption{font-size:.85rem;color:#444}'
        '@media print{details{break-inside:avoid}}</style></head><body>'
        '<main><h1>MixLab · privé cue-review</h1>'
        '<p>Maximaal acht expliciet gekozen audiobronnen met ieder hun eigen '
        'opgeslagen handmatige notitie; geen automatische DJ-volgorde of '
        'bevestigde muziekfeiten. Alles heeft één absolute seconden-as. '
        'De gestippelde grens markeert waar een korter fragment ophoudt.</p>'
        '<section><table><thead><tr><th>Fragment</th>'
        '<th>BPM-voorstel</th><th>Eigen BPM</th>'
        '<th>Toonsoortvoorstel</th><th>Eigen toonsoort</th></tr>'
        '</thead><tbody>' + "".join(rows) + '</tbody></table></section>'
        '<h2>Bekijk details per fragment</h2>' + "".join(panels) +
        '<h2>Grenzen</h2><ul>' + limits + '</ul>'
        '<p>Bronhashes, private paden, persoonsnamen en audio staan niet '
        'in deze HTML. Er is geen opname verzonden, niets automatisch '
        'goedgekeurd en geen render gestart.</p></main></body></html>\n'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare one to eight ordered, local PCM16/manual receipt pairs offline")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pair", nargs=2, action="append",
                        metavar=("WAV", "RECEIPT"),
                        help="exact source plus its own private manual-review JSON")
    source.add_argument("--session",
                        help="private local JSON session with 1-8 relative WAV/receipt pairs")
    parser.add_argument("--format", choices=("html", "json"), default="html")
    args = parser.parse_args(argv)
    try:
        pairs = load_session(args.session) if args.session else args.pair
        result = compare_batch(pairs)
        rendered = render_html(result) if args.format == "html" else json.dumps(
            result, allow_nan=False, sort_keys=True, indent=2) + "\n"
    except (OSError, ValueError, TypeError, OverflowError, KeyError, RecursionError):
        parser.exit(2, "MixLab cue desk: invalid, duplicate, changed or unavailable private pair (details withheld)\n")
    print(rendered, end="")


if __name__ == "__main__":
    main()
