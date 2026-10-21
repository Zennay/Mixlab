"""Private cue overview for a small set of explicitly supplied audio excerpts.

Proposals are not mix recommendations, tempo-matching authorization or proof
that any recording can be distributed. No file names, paths or PCM are emitted.
"""
from __future__ import annotations

import argparse
from html import escape
import json

from .preview import preview

MAX_CLIPS = 8


def compare(paths, *, verified_bpm=None, first_beat=0., beats_per_bar=4,
            phrase_bars=8):
    """Produce a bounded, source-bound read-only overview in input order."""
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_CLIPS:
        raise ValueError("Require between 1 and 8 local excerpts")
    if any(not isinstance(path, str) or not path for path in paths):
        raise ValueError("Invalid local excerpt")
    rows = []
    seen_hashes = set()
    for position, path in enumerate(paths, start=1):
        item = preview(path, verified_bpm=verified_bpm, first_beat=first_beat,
                       beats_per_bar=beats_per_bar, phrase_bars=phrase_bars)
        source_hash = item["source_sha256"]
        if source_hash in seen_hashes:
            # Identical input bytes should not be interpreted as two candidates.
            raise ValueError("Duplicate audio excerpt")
        seen_hashes.add(source_hash)
        rows.append({
            "id": f"clip-{position:02d}",
            "source_sha256": source_hash,
            "duration_seconds": item["duration_seconds"],
            "bpm": item["rhythm"]["bpm"],
            "tempo_source": item["rhythm"]["source"],
            "beat_count": item["rhythm"]["beat_cues"]["count"],
            "key": item["tonality"]["key"],
            "key_source": item["tonality"]["source"],
            "downbeat_count": item["structure"]["downbeat_cues"]["count"],
            "phrase_count": item["structure"]["phrase_cues"]["count"],
            "assumed_beats_per_bar": item["structure"]["assumed_beats_per_bar"],
            "assumed_phrase_bars": item["structure"]["assumed_phrase_bars"],
            "requires_manual_review": True,
            "has_unknown_critical_cues": (
                item["rhythm"]["bpm"] is None or
                item["tonality"]["key"] is None or
                item["structure"]["downbeat_cues"]["count"] == 0),
        })
    return {
        "schema_version": 1,
        "kind": "private_musical_cue_overview",
        "clip_count": len(rows),
        "clips": rows,
        "audio_uploaded": False,
        "paths_exported": False,
        "mix_recommendations_authorized": False,
        "render_authorized": False,
        "rights_or_accuracy_verified": False,
        "limitations": [
            "Input order is not a recommended play order.",
            "Missing key/downbeat/phrase evidence is unknown, not silence.",
            "BPM and tonal similarity alone cannot establish musical compatibility.",
            "All proposals need human verification on permitted audio before use.",
        ],
    }


def _render_html(document):
    rows = []
    for track in document["clips"]:
        cells = [
            track["id"], track["bpm"], track["key"],
            track["beat_count"], track["downbeat_count"],
            track["phrase_count"],
            "Onvolledig" if track["has_unknown_critical_cues"] else "Controle vereist",
        ]
        rows.append("<tr>" + "".join(
            "<td>" + escape(str(v) if v is not None else "Onbekend") + "</td>"
            for v in cells) + "</tr>")
    notes = "".join("<li>" + escape(x) + "</li>" for x in document["limitations"])
    return (
        "<!doctype html><html lang=\"nl\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"referrer\" content=\"no-referrer\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>MixLab · privé cue-overzicht</title>"
        "<style>body{font:16px system-ui,sans-serif;max-width:1020px;margin:2rem auto;"
        "padding:0 1rem;line-height:1.5;color:#202124}"
        "table{border-collapse:collapse}th,td{border:1px solid #bbb;padding:.45rem;text-align:left}"
        "section{overflow:auto}small{color:#555}</style></head><body>"
        "<h1>MixLab · privé cue-overzicht</h1>"
        "<p>Lokale voorstellen — geen audio of bestandsnamen geëxporteerd. "
        "Geen trackselectie, remixadvies, release- of rechtenverklaring.</p>"
        "<section><table><thead><tr><th>Fragment</th><th>BPM</th><th>Toonsoort</th>"
        "<th>Beats</th><th>Maatstarts</th><th>Frasestarts</th><th>Status</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
        "<h2>Beperkingen</h2><ul>" + notes +
        "</ul><small>Bronhashes en fysieke paden worden niet in deze HTML opgenomen.</small>"
        "</body></html>\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Private side-by-side measured cue overview (1–8 local PCM16 clips)")
    parser.add_argument("wav", nargs="+", help="ordered permitted local PCM16 excerpts")
    parser.add_argument("--verified-bpm", type=float,
                        help="optional common BPM entered by an operator, not audio accuracy proof")
    parser.add_argument("--first-beat", type=float, default=0.)
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--phrase-bars", type=int, default=8)
    parser.add_argument("--format", choices=("json", "html"), default="html")
    args = parser.parse_args(argv)
    try:
        document = compare(args.wav, verified_bpm=args.verified_bpm,
                           first_beat=args.first_beat, beats_per_bar=args.beats_per_bar,
                           phrase_bars=args.phrase_bars)
    except (OSError, ValueError, TypeError, OverflowError):
        parser.exit(2, "MixLab cue overview: invalid, duplicate, changed or inaccessible input (details withheld)\n")
    if args.format == "html":
        print(_render_html(document), end="")
    else:
        print(json.dumps(document, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
