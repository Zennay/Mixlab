"""One-command, private, read-only musical cue preview for one PCM16 excerpt.

Preview only: no render recipe, manual confirmation, cache, external service or
writing to disk. Paths and audio are deliberately absent from stdout.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from . import EnergyOnsetProvider, ManualProvider
from .meter import AccentMeterProvider
from .source_receipt import source_identity, verify_source
from .tonal import ChromaKeyProvider
from ..ingest import number

MAX_CUES = 64


def _cue_preview(values):
    """Keep displays bounded while retaining the source's true cue count."""
    return {
        "count": len(values),
        "seconds": [round(t, 4) for t in values[:MAX_CUES]],
        "truncated": len(values) > MAX_CUES,
    }


def preview(path, *, verified_bpm=None, first_beat=0.,
            beats_per_bar=4, phrase_bars=8):
    """Build a single source-bound musical cue proposal, never render authority.

    An explicit verified BPM is manual *timing input*, not automatic verification
    of key/downbeats/phrases. Without it, meter analysis is only attempted if
    the beat provider supplies a sufficiently long beatgrid.
    """
    if verified_bpm is not None:
        number(verified_bpm, "verified BPM", 30, 300)
    number(first_beat, "first beat", 0, 250)
    if verified_bpm is None and first_beat != 0.:
        raise ValueError("First beat requires manually supplied verified BPM")
    # Check parameter constraints before reading any private audio.
    meter_provider = AccentMeterProvider(beats_per_bar, phrase_bars)
    original_identity = source_identity(path)
    beat = (ManualProvider(verified_bpm, first_beat, annotator="operator-cli").analyze(path)
            if verified_bpm is not None else EnergyOnsetProvider().analyze(path))
    if source_identity(path) != original_identity:
        raise ValueError("Private PCM changed during rhythm analysis")
    key = ChromaKeyProvider().analyze(path)
    if (beat.source_sha256 != key.source_sha256 or
            source_identity(path) != original_identity):
        raise ValueError("Audio changed between provider reads")
    meter = None
    if len(beat.beats_seconds) >= 4 * beats_per_bar:
        meter = meter_provider.analyze(path, list(beat.beats_seconds))
        if (meter.source_sha256 != beat.source_sha256 or
                source_identity(path) != original_identity):
            raise ValueError("Audio changed between provider reads")
    # Final single-descriptor checksum plus physical identity refuses ordinary
    # source swaps and in-place edits between independent provider reads.
    verify_source(path, original_identity, beat.source_sha256)
    automatic = verified_bpm is None
    return {
        "schema_version": 1,
        "kind": "private_musical_cue_preview",
        "render_authorized": False,
        "manual_confirmation_required": True,
        "audio_uploaded": False,
        "source_sha256": beat.source_sha256,
        "duration_seconds": round(beat.duration_seconds, 4),
        "rhythm": {
            "bpm": beat.bpm,
            "source": "measured-heuristic" if automatic else "manual-operator-input",
            "provider_version": beat.provider_version,
            "score_type": "uncalibrated_heuristic" if automatic else "not_applicable_manual",
            "tempo_score": beat.tempo_confidence if automatic else None,
            "beat_cues": _cue_preview(beat.beats_seconds),
        },
        "tonality": {
            "key": key.key,
            "source": key.key_source,
            "provider_version": key.provider_version,
            "correlation_not_probability": key.correlation,
            "margin": key.margin,
            "tonal_frames": key.tonal_frames,
        },
        "structure": {
            "provider_version": meter_provider.version,
            "assumed_beats_per_bar": beats_per_bar,
            "assumed_phrase_bars": phrase_bars,
            "source": "measured-heuristic" if meter else "unavailable",
            "downbeat_cues": _cue_preview(meter.downbeats_seconds if meter else ()),
            "phrase_cues": _cue_preview(meter.phrase_starts_seconds if meter else ()),
            "downbeat_contrast": meter.downbeat_contrast if meter else None,
            "downbeat_margin": meter.downbeat_margin if meter else None,
            "downbeat_consistency": meter.downbeat_consistency if meter else None,
            "phrase_contrast": meter.phrase_contrast if meter else None,
            "phrase_margin": meter.phrase_margin if meter else None,
            "phrase_consistency": meter.phrase_consistency if meter else None,
        },
        "warnings": list(dict.fromkeys(
            [*beat.warnings, *key.warnings,
             *(meter.warnings if meter else (
                 "no sufficiently long beatgrid; bar/phrase analysis not attempted",
             )),
             "Not a calibrated accuracy score, track-rights proof or a DJ mixpoint.",
             "Manually check meter, downbeats, key and transition suitability.",
             "Physical identity and final checksum checks are not an immutable audio snapshot."])),
    }


def _render_html(record):
    """Offline document without scripts, source paths, audio, or external links."""
    def val(value):
        return escape(str(value)) if value is not None else "Onbekend"
    def rows(data):
        return "".join(
            "<tr><th scope=\"row\">" + val(label) + "</th><td>" + val(value) + "</td></tr>"
            for label, value in data)
    def cue(label, item):
        times = ", ".join(f"{t:.2f}s" for t in item["seconds"])
        return (f"<p><strong>{escape(label)}:</strong> {item['count']} — "
                + escape(times or "geen voorstel") +
                (" … (eerste 64 zichtbaar)" if item["truncated"] else "") + "</p>")
    rhythm, tonality, structure = record["rhythm"], record["tonality"], record["structure"]
    warnings = "".join("<li>" + val(w) + "</li>" for w in record["warnings"])
    return ("<!doctype html><html lang=\"nl\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta name=\"referrer\" content=\"no-referrer\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
            "<title>MixLab · privé analysevoorbeeld</title>"
            "<style>body{font:16px system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;"
            "line-height:1.5;color:#202124}main{display:grid;gap:1rem}section{border:1px solid #ccc;"
            "padding:1rem;border-radius:.6rem}th{text-align:left;padding-right:2rem}td{overflow-wrap:anywhere}"
            "ul{padding-left:1.2rem}small{color:#555}</style></head><body><main>"
            "<h1>MixLab · privé cue-voorstellen</h1><p>Alleen-lezen, lokaal verwerkt. "
            "Geen audio of bestandslocatie in dit overzicht. Geen renderautorisatie.</p>"
            "<section><h2>Tempo en beatgrid</h2><table>" +
            rows([("BPM", rhythm["bpm"]), ("Herkomst", rhythm["source"]),
                  ("Indicatieve score", rhythm["tempo_score"]),
                  ("Provider", rhythm["provider_version"])]) +
            "</table>" + cue("Beats", rhythm["beat_cues"]) + "</section>"
            "<section><h2>Toonsoort</h2><table>" +
            rows([("Voorstel", tonality["key"]), ("Herkomst", tonality["source"]),
                  ("Correlatie (geen kans)", tonality["correlation_not_probability"]),
                  ("Provider", tonality["provider_version"])]) + "</table></section>"
            "<section><h2>Maat en frasen</h2><table>" +
            rows([("Aangenomen beats per maat", structure["assumed_beats_per_bar"]),
                  ("Aangenomen maten per frase", structure["assumed_phrase_bars"]),
                  ("Provider", structure["provider_version"]),
                  ("Maatconsistentie", structure["downbeat_consistency"]),
                  ("Fraseconsistentie", structure["phrase_consistency"])]) + "</table>" +
            cue("Maatstarts", structure["downbeat_cues"]) +
            cue("Frasestarts", structure["phrase_cues"]) + "</section>"
            "<section><h2>Beperkingen en controlepunten</h2><ul>" +
            warnings + "</ul></section><small>Voorstellen zijn geen bevestigde muzikale feiten. "
            "Verifieer alles handmatig voordat je mixt.</small></main></body></html>\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="View one private WAV's proposed key, beats, bars and phrases without rendering")
    parser.add_argument("wav", help="local permitted short PCM16 WAV excerpt")
    parser.add_argument("--verified-bpm", type=float, help="human-verified timing input; does not confirm bar/key")
    parser.add_argument("--first-beat", type=float, default=0.)
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--phrase-bars", type=int, default=8)
    parser.add_argument("--format", choices=("json", "html"), default="json")
    args = parser.parse_args(argv)
    try:
        result = preview(args.wav, verified_bpm=args.verified_bpm,
                         first_beat=args.first_beat,
                         beats_per_bar=args.beats_per_bar,
                         phrase_bars=args.phrase_bars)
    except ValueError as exc:
        # Never echo errors from external media / path exceptions verbatim.
        parser.exit(2, "MixLab cue preview: invalid or changed input / unsupported timing\n")
    except (OSError, TypeError, OverflowError):
        parser.exit(2, "MixLab cue preview: input unavailable (details withheld)\n")
    if args.format == "html":
        print(_render_html(result), end="")
    else:
        print(json.dumps(result, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
