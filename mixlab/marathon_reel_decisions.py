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


def _validated_choices(plan_path, original_wav, blended_wav, previous_hybrid_wav=None):
    """Validate exact real source pair and every manually chosen join."""
    (_, _), (source, blend), fades, _ = _pair(original_wav, blended_wav)
    plan = _read_plan(plan_path)
    allowed = {"schema_version", "kind", "original_sha256", "blend_sha256",
               "private_only", "blind_study", "joins"}
    if (not isinstance(plan, dict) or set(plan) not in (allowed, allowed | {"parent_hybrid_sha256"}) or
            type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or
            plan["kind"] != KIND or plan["private_only"] is not True or
            plan["blind_study"] is not False or
            plan["original_sha256"] != source["wav_sha256"] or
            plan["blend_sha256"] != blend["wav_sha256"]):
        raise ValueError("Join master selections do not match both real private Marathon masters")
    parent_sha = plan.get("parent_hybrid_sha256")
    if (parent_sha is None) != (previous_hybrid_wav is None):
        raise ValueError("A revision must include both a previous WAV and its bound parent SHA")
    if parent_sha is not None:
        from .event_vault import _marathon_duration, _read_small_json
        previous = Path(previous_hybrid_wav).absolute()
        if previous.name != "marathon.wav":
            raise ValueError("Previous revision must be an existing completed Marathon WAV")
        _, previous_count, previous_kind = _marathon_duration(previous.parent, previous)
        receipt = _read_small_json(previous.parent / "marathon.receipt.private.json")
        if (previous_kind != "marathon_blend" or
                parent_sha != receipt["wav_sha256"] or
                receipt["source_marathon_sha256"] != source["wav_sha256"] or
                previous_count != len(source["sections"])):
            raise ValueError("This revision does not descend from the exact verified private hybrid master")
        from .marathon_operator_transfer import _validate
        old = _read_plan(previous.parent / "master-picks.private.json")
        _validate(previous, old)
        if old.get("source_blend_sha256") != blend["wav_sha256"]:
            raise ValueError("Existing parent was not compared with these exact original/blended sources")
        if not isinstance(old.get("joins"), list) or len(old["joins"]) != len(fades):
            raise ValueError("Existing parent has no matching complete per-join decisions")
        for old_row, fade in zip(old["joins"], fades):
            if old_row.get("fade_seconds") != fade:
                raise ValueError("Existing parent cannot be revised against a different fade baseline")
        if not isinstance(plan.get("joins"), list) or not any(
                current.get("choice") != past.get("choice")
                for current, past in zip(plan["joins"], old["joins"])
                if isinstance(current, dict) and isinstance(past, dict)):
            raise ValueError("No audio transitions changed; keep the existing approved WAV")
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
    return source, blend, results, parent_sha


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
                     bitrate_kbps=192, reels_output=None, reels_usb=False, operator_notes_usb=False,
                     previous_hybrid_wav=None, revision_reels_output=None,
                     read=input, write=print):
    if type(reels_usb) is not bool or (reels_usb and reels_output is None):
        raise ValueError("Optional real hybrid handoff ZIP requires --reels-output")
    if revision_reels_output is not None and previous_hybrid_wav is None:
        raise ValueError("Actual revision comparison clips require a verified --previous-hybrid WAV")
    source, blend, choices, parent_sha = _validated_choices(
        plan_path, original_wav, blended_wav, previous_hybrid_wav)
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
            **({"parent_hybrid_sha256": parent_sha} if parent_sha else {}),
            "private_only": True, "blind_study": False, "music_rights_proven": False
        }
        _write_private(decision_file, (json.dumps(
            decision, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        _write_private(brief_file, _brief_html(source, blend, choices, result["wav_sha256"]))
        result["private_master_picks"] = str(decision_file)
        result["private_printable_cue_sheet"] = str(brief_file)
        try:
            from .marathon_hybrid_stage import create_stage
            result["private_stage_navigator"] = create_stage(
                result["continuous_wav"], decision_file,
                folder / "master-picks.stage.html")
        except (ValueError, TypeError, KeyError, OSError, wave.Error):
            result["stage_navigator_warning"] = (
                "Actual hybrid WAV and printed operator cues remain available; "
                "optional local live stage navigator could not be published.")
    except (OSError, ValueError, UnicodeError):
        result["cue_sheet_warning"] = ("Approved actual hybrid WAV remains intact; "
              "the optional local operator-notes handoff could not be completed.")
    if operator_notes_usb:
        try:
            from .marathon_operator_transfer import pack
            result["private_operator_notes_usb"] = pack(
                result["continuous_wav"], folder / "master-operator-notes.private.zip",
                read=read, write=write)
        except (ValueError, TypeError, KeyError, OSError, EOFError,
                UnicodeError, wave.Error):
            result["operator_notes_usb_warning"] = (
                "Approved real hybrid WAV and private local operator notes "
                "remain intact; the optional separate private-notes ZIP "
                "was not released.")
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
    if revision_reels_output is not None:
        try:
            from .marathon_revision_reels import create_revision_audition
            result["actual_revision_reels"] = create_revision_audition(
                previous_hybrid_wav, result["continuous_wav"],
                revision_reels_output, read=read, write=write)
        except (ValueError, TypeError, KeyError, OSError, EOFError, wave.Error):
            result["revision_reels_warning"] = (
                "The real original, parent and newly completed revised WAV masters "
                "were retained. Optional short changed-join revision WAV "
                "comparisons could not be published.")
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
    parser.add_argument("--previous-hybrid", help="Required exact completed previous-hybrid WAV when a revision JSON names parent_hybrid_sha256")
    parser.add_argument("--revision-reels-output", help="Optional NEW private folder with genuine short previous-vs-revision PCM16 WAVs for only changed joins, with another typed approval; requires --previous-hybrid")
    parser.add_argument("--start", help="Optional local HH:MM start")
    parser.add_argument("--reels-output", help="Optional NEW private real PCM16 original-versus-hybrid short WAV listening folder; extra typed approval")
    parser.add_argument("--reels-usb", action="store_true",
                        help="Also create opt-in private short PCM16 ZIP; requires --reels-output")
    parser.add_argument("--operator-notes-usb", action="store_true",
                        help="Opt-in SEPARATE USB ZIP of private human cue notes ONLY; another typed yes, never music")
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
            reels_output=args.reels_output, reels_usb=args.reels_usb,
            operator_notes_usb=args.operator_notes_usb,
            previous_hybrid_wav=args.previous_hybrid,
            revision_reels_output=args.revision_reels_output)
    except (ValueError, TypeError, KeyError, OSError, UnicodeError,
            EOFError, KeyboardInterrupt, wave.Error):
        parser.exit(2, "MixLab hybrid: plan, approved real WAVs, explicit consent or new private destination invalid.\n")
    print(json.dumps(output, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
