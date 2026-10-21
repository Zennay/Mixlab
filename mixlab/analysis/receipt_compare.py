"""Source-bound offline comparison of heuristic cues and a saved operator receipt.

The receipt is unsigned operator input, not independent human verification.
This view never copies PCM, annotator identity, private filenames, source hashes
or audio rights into HTML. No rendering action is authorized.
"""
from __future__ import annotations

import argparse
from html import escape
import json

from .cue_timeline import render_cue_timeline
from .preview import _cue_preview, preview
from .receipt_reopen import reopen
from .source_receipt import source_identity, verify_source


def compare_receipt(path, receipt):
    """Compare independent measured proposals with one exact-source manual receipt."""
    original = source_identity(path)
    manual = reopen(path, receipt)
    suggestions = preview(path)
    if manual["source_sha256"] != suggestions["source_sha256"]:
        raise ValueError("Private cue sources do not match")
    # Different provider reads must still refer to this exact physical file
    # and contents at return. This cannot prove prior human listening or rights.
    verify_source(path, original, manual["source_sha256"])
    return {
        "schema_version": 1,
        "kind": "private_cue_receipt_comparison",
        "source_sha256": manual["source_sha256"],
        "duration_seconds": suggestions["duration_seconds"],
        "proposals": {
            "bpm": suggestions["rhythm"]["bpm"],
            "bpm_source": suggestions["rhythm"]["source"],
            "key": suggestions["tonality"]["key"],
            "key_source": suggestions["tonality"]["source"],
            "beats": suggestions["rhythm"]["beat_cues"],
            "downbeats": suggestions["structure"]["downbeat_cues"],
            "phrases": suggestions["structure"]["phrase_cues"],
        },
        "operator_declaration": {
            "bpm": manual["bpm"],
            "first_beat_seconds": manual["first_beat_seconds"],
            "key": manual["key"],
            "downbeats": _cue_preview(manual["downbeats_seconds"]),
            "phrases": _cue_preview(manual["phrase_starts_seconds"]),
            "source_match_rechecked": manual["file_identity_rechecked"],
            "human_confirmation_independently_verified": False,
            "receipt_authenticity_cryptographically_verified": False,
        },
        "audio_uploaded": False,
        "render_authorized": False,
        "rights_verified": False,
        "research_quality_verified": False,
        "warning": (
            "Manual values are self-declared, not independently verified. "
            "Different proposals are not evidence that either side is correct. "
            "Inspect the original permitted recording; no auto-adoption or release."
        ),
    }


def _cue(label, item):
    values = ", ".join(f"{value:.3f}s" for value in item["seconds"])
    text = values or "geen voorgestelde of verklaarde tijden"
    remainder = f" · eerste {len(item['seconds'])} van {item['count']} zichtbaar" if item["truncated"] else ""
    return ("<p><strong>" + escape(label) + "</strong> · " +
            escape(text + remainder) + "</p>")


def render_html(document):
    """Produce a scriptless read-only comparison with separated provenances."""
    proposed = document["proposals"]
    manual = document["operator_declaration"]
    duration = document["duration_seconds"]
    def value(x):
        return escape(str(x)) if x is not None else "Onbekend"
    proposed_cues = {
        "beat_seconds": proposed["beats"],
        "downbeat_seconds": proposed["downbeats"],
        "phrase_seconds": proposed["phrases"],
    }
    # A manual receipt stores BPM and the first beat, not a reviewed beatgrid.
    # Never fabricate manual beat positions or treat generated beats as human cues.
    declared_cues = {
        "beat_seconds": {"count": 0, "seconds": [], "truncated": False},
        "downbeat_seconds": manual["downbeats"],
        "phrase_seconds": manual["phrases"],
    }
    proposed_panel = render_cue_timeline(duration, proposed_cues, clip_id="clip-01-proposal")
    manual_panel = render_cue_timeline(duration, declared_cues, clip_id="clip-01-operator")
    return (
        '<!doctype html><html lang="nl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        '<title>MixLab · privé cue-notitie vergelijken</title>'
        '<style>body{font:16px system-ui,sans-serif;max-width:1040px;'
        'margin:2rem auto;padding:0 1rem;line-height:1.5;color:#202124}'
        'main{display:grid;gap:1rem}section{border:1px solid #bbc5ce;'
        'padding:1rem;border-radius:.6rem;min-width:0}'
        'dl{display:grid;grid-template-columns:12em 1fr;gap:.3rem 1rem}'
        'dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere}'
        '.cue-timeline svg{width:100%;height:auto;display:block}'
        '.cue-timeline{margin:.8rem 0}.cue-timeline figcaption{font-size:.85rem;color:#454545}'
        'strong{font-weight:650}small{color:#444}</style></head><body><main>'
        '<h1>MixLab · eigen cue-notitie naast voorstellen</h1>'
        '<p>Zelf ingevoerde waarden zijn NIET onafhankelijk gecontroleerd. '
        'Beide panelen gebruiken de oorspronkelijke audiotijd (seconden), '
        'maar zijn géén aanbevolen mixpunten.</p>'
        '<section><h2>1. Automatische voorstellen · niet bevestigd</h2>'
        '<dl><dt>BPM-voorstel</dt><dd>' + value(proposed["bpm"]) +
        '</dd><dt>BPM-herkomst</dt><dd>' + value(proposed["bpm_source"]) +
        '</dd><dt>Toonsoortvoorstel</dt><dd>' + value(proposed["key"]) +
        '</dd><dt>Toonsoortbron</dt><dd>' + value(proposed["key_source"]) +
        '</dd></dl>' + proposed_panel +
        _cue("Beats", proposed["beats"]) +
        _cue("Maatstarts", proposed["downbeats"]) +
        _cue("Frasestarts", proposed["phrases"]) + '</section>'
        '<section><h2>2. Opgeslagen eigen invoer · niet onafhankelijk bevestigd</h2>'
        '<dl><dt>Eigen BPM</dt><dd>' + value(manual["bpm"]) +
        '</dd><dt>Eigen eerste beat</dt><dd>' + value(manual["first_beat_seconds"]) +
        's</dd><dt>Eigen toonsoort</dt><dd>' + value(manual["key"]) +
        '</dd></dl><p>Er is geen handmatig bevestigd volledig beatgrid. '
        'De lege beatrij hieronder is geen bewijs dat beats ontbreken.</p>' +
        manual_panel +
        _cue("Zelf ingevoerde maatstarts", manual["downbeats"]) +
        _cue("Zelf ingevoerde frasestarts", manual["phrases"]) + '</section>'
        '<section><h2>3. Beslissing blijft bij jou</h2><p>' +
        escape(document["warning"]) + '</p><p>De bron is lokaal opnieuw '
        'geverifieerd, maar de JSON-notitie is niet cryptografisch ondertekend. '
        'Geen audio, namen, bestandspaden of bronhashes opgenomen. '
        'Geen mix, cachewijziging, rechten- of releasegoedkeuring uitgevoerd.</p></section>'
        '</main></body></html>\n'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only, source-matched comparison of private cue proposals and an unsigned manual receipt")
    parser.add_argument("wav", help="original permitted local PCM16 excerpt")
    parser.add_argument("receipt", help="private saved manual-review JSON receipt")
    parser.add_argument("--format", choices=("html", "json"), default="html")
    args = parser.parse_args(argv)
    try:
        document = compare_receipt(args.wav, args.receipt)
        rendered = render_html(document) if args.format == "html" else json.dumps(
            document, allow_nan=False, sort_keys=True, indent=2) + "\n"
    except (OSError, ValueError, TypeError, OverflowError, RecursionError, KeyError):
        parser.exit(2, "MixLab cue comparison: invalid, changed or unavailable private input (details withheld)\n")
    print(rendered, end="")


if __name__ == "__main__":
    main()
