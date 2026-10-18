"""Turn human A/B choices from genuine Join Reels into a real private hybrid WAV.

This is operator-directed post-production, NOT a blind-study rating or MIR/DSP
claim. Both original sources are independently verified against SHA receipts.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import wave

from .marathon_master_review import _pair
from .marathon_sequence import _read_plan
from .marathon_blend import publish_blended_marathon

KIND = "mixlab-private-join-master-picks-v1"
MAX_NOTE = 300
MAX_BRIEF = 64 * 1024


def _validated_choices(plan_path, original_wav, blended_wav):
    """Validate exact real source pair and every manually chosen join."""
    (_, _), (source, blend), fades, _ = _pair(original_wav, blended_wav)
    plan = _read_plan(plan_path)
    if (not isinstance(plan, dict) or set(plan) != {
            "schema_version", "kind", "original_sha256", "blend_sha256",
            "private_only", "blind_study", "joins"} or
            type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or
            plan["kind"] != KIND or plan["private_only"] is not True or
            plan["blind_study"] is not False or
            plan["original_sha256"] != source["wav_sha256"] or
            plan["blend_sha256"] != blend["wav_sha256"]):
        raise ValueError("Join master selections do not match both real private Marathon masters")
    rows = plan["joins"]
    if not isinstance(rows, list) or len(rows) != len(fades) or len(rows) != len(source["sections"]) - 1:
        raise ValueError("Each real join needs one manually reviewed selection")
    results = []
    for i, (row, duration) in enumerate(zip(rows, fades), 1):
        if (not isinstance(row, dict) or set(row) != {
                "index", "from", "to", "fade_seconds", "choice", "note"} or
                type(row["index"]) is not int or row["index"] != i or
                row["from"] != source["sections"][i-1]["label"] or
                row["to"] != source["sections"][i]["label"] or
                type(row["fade_seconds"]) is not int or row["fade_seconds"] != duration or
                row["choice"] not in ("original", "blend") or
                not isinstance(row["note"], str) or len(row["note"]) > MAX_NOTE or
                any(ord(c) < 32 and c not in "\n\t" for c in row["note"])):
            raise ValueError("Join decision is incomplete or not tied to approved source audio")
        results.append(row)
    return source, blend, results


def _brief_html(source, blend, rows, master_sha):
    safe = lambda text: html.escape(str(text), quote=True)
    blocks = []
    for row in rows:
        preference = "Original hard cut · 0 s" if row["choice"] == "original" else (
            "Actual manual crossfade · " + str(row["fade_seconds"]) + " s")
        blocks.append(
            "<section><h2>" + str(row["index"]) + ". " + safe(row["from"]) +
            " → " + safe(row["to"]) + "</h2><p><strong>" +
            safe(preference) + "</strong></p><p class='note'>" +
            safe(row["note"] or "No private operator note") + "</p></section>")
    page = ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none';form-action 'none'">
<title>MixLab · human-selected hybrid master cues</title>
<style>body{font:16px/1.5 system-ui;max-width:860px;margin:auto;padding:35px;color:#14252d}
h1{font-size:40px;line-height:1.1}section{border-top:1px solid #789;padding:15px 0}
small{display:block;overflow-wrap:anywhere;color:#465b69}.note{white-space:pre-wrap;overflow-wrap:anywhere}
@media print{body{padding:0}section{break-inside:avoid}}</style>
<h1>Final real-audio handoff decisions</h1>
<p>Personal, unblinded DJ notes. Audio stays offline. No rights,
automated beatmatch or human preference study is certified.</p>
<small>Original SHA-256: """ + safe(source["wav_sha256"]) +
        "</small><small>Compared blend SHA-256: " + safe(blend["wav_sha256"]) +
        "</small><small>Actually rendered hybrid WAV SHA-256: " +
        safe(master_sha) + "</small>" + "".join(blocks) + "</html>")
    encoded = page.encode("utf-8")
    if not 0 < len(encoded) <= MAX_BRIEF:
        raise ValueError("Private master cue sheet exceeds bound")
    return encoded


def _write_private(path, data):
    with Path(path).open("xb") as target:
        os.fchmod(target.fileno(), 0o600)
        target.write(data)


def render_decisions(plan_path, original_wav, blended_wav, new_private_folder,
                     *, start=None, bundle=False, delivery=None,
                     bitrate_kbps=192, reels_output=None, reels_usb=False, read=input, write=print):
    if type(reels_usb) is not bool or (reels_usb and reels_output is None):
        raise ValueError("Optional real hybrid handoff ZIP requires --reels-output")
    source, blend, choices = _validated_choices(plan_path, original_wav, blended_wav)
    fade_choices = tuple(row["fade_seconds"] if row["choice"] == "blend" else 0
                         for row in choices)
    if not any(fade_choices):
        raise ValueError("All decisions chose original joins: the existing SHA-verified original WAV is already the chosen master")
    write("MixLab: an additional human-directed, exact-source private hybrid output.")
    write("Approved original: " + source["wav_sha256"])
    write("Compared full blend: " + blend["wav_sha256"])
    for row, seconds in zip(choices, fade_choices):
        write(f"  Join {row['index']}: {row['from']} -> {row['to']} : "
              + ("ORIGINAL hard join" if not seconds else f"ACTUAL {seconds}s fade"))
    write("One explicit render approval follows. This does NOT certify music rights or mixing quality.")
    result = publish_blended_marathon(
        original_wav, new_private_folder, join_fades=fade_choices,
        start=start, bundle=bundle, delivery=delivery,
        bitrate_kbps=bitrate_kbps, read=read, write=write)
    # The independently approved real WAV is never removed for a note/HTML failure.
    folder = Path(result["private_event_folder"])
    decision_file = folder / "master-picks.private.json"
    brief_file = folder / "master-picks.private.html"
    try:
        decision = {
            "schema_version": 1, "kind": KIND,
            "source_original_sha256": source["wav_sha256"],
            "source_blend_sha256": blend["wav_sha256"],
            "rendered_hybrid_sha256": result["wav_sha256"],
            "joins": choices, "actual_fade_seconds_by_join": list(fade_choices),
            "private_only": True, "blind_study": False, "music_rights_proven": False
        }
        _write_private(decision_file, (json.dumps(
            decision, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        _write_private(brief_file, _brief_html(source, blend, choices, result["wav_sha256"]))
        result["private_master_picks"] = str(decision_file)
        result["private_printable_cue_sheet"] = str(brief_file)
    except (OSError, ValueError, UnicodeError):
        result["cue_sheet_warning"] = ("Approved actual hybrid WAV remains intact; "
              "the optional local operator-notes handoff could not be completed.")
    if reels_output is not None:
        try:
            from .marathon_join_reels import create_join_reels
            result["actual_hybrid_reels"] = create_join_reels(
                original_wav, result["continuous_wav"], reels_output,
                read=read, write=write)
            if reels_usb:
                try:
                    from .marathon_reels_transfer import export_reels
                    result["hybrid_reels_usb"] = export_reels(
                        reels_output,
                        Path(reels_output).absolute() / "join-reels.private.zip")
                except (ValueError, TypeError, KeyError, OSError):
                    result["hybrid_reels_usb_warning"] = (
                        "Approved hybrid WAV and its actual short clips are retained; "
                        "only optional private transfer ZIP was not created.")
        except (ValueError, TypeError, KeyError, OSError, EOFError, wave.Error):
            result["hybrid_reels_warning"] = (
                "Approved actual hybrid master is retained; optional separate "
                "short original-versus-hybrid PCM16 excerpts were not created.")
    result["human_selected_hard_joins"] = fade_choices.count(0)
    result["human_selected_crossfades"] = len(fade_choices) - fade_choices.count(0)
    result["private_operator_preference_only"] = True
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Render a real private PCM16 hybrid Marathon from human A/B Join Reel choices")
    parser.add_argument("private_join_picks_json")
    parser.add_argument("original_marathon_wav")
    parser.add_argument("blended_marathon_wav")
    parser.add_argument("new_private_folder")
    parser.add_argument("--start", help="Optional local HH:MM start")
    parser.add_argument("--reels-output", help="Optional NEW private real PCM16 original-versus-hybrid short WAV listening folder; extra typed approval")
    parser.add_argument("--reels-usb", action="store_true",
                        help="Also create opt-in private short PCM16 ZIP; requires --reels-output")
    parser.add_argument("--bundle", action="store_true",
                        help="Optional private WAV package (operator notes are NOT included)")
    parser.add_argument("--delivery", choices=("mp3", "flac"),
                        help="Optional local portable encoding")
    parser.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320), default=192)
    args = parser.parse_args()
    try:
        output = render_decisions(
            args.private_join_picks_json, args.original_marathon_wav,
            args.blended_marathon_wav, args.new_private_folder,
            start=args.start, bundle=args.bundle, delivery=args.delivery,
            bitrate_kbps=args.bitrate_kbps,
            reels_output=args.reels_output, reels_usb=args.reels_usb)
    except (ValueError, TypeError, KeyError, OSError, UnicodeError,
            EOFError, KeyboardInterrupt, wave.Error):
        parser.exit(2, "MixLab hybrid: plan, approved real WAVs, explicit consent or new private destination invalid.\n")
    print(json.dumps(output, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
