"""Offline, source-verified comparison of two manually edited MixLab cue plans.

Never analyses beats, uploads audio, writes a source manifest, or treats a
synthetic timing comparison as human listening evidence.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import os
from pathlib import Path

from .cue_editor import _admit_library
from .ingest import digest


def _timeline(tracks, pairs):
    """Calculate exact PCM-frame set boundaries; reject overlapping cues."""
    if not pairs:
        raise ValueError("Cue comparison requires transition pairs")
    route = [pairs[0]["a"], *(pair["b"] for pair in pairs)]
    if (len(route) != len(tracks) or len(set(route)) != len(route)
            or set(route) != set(tracks)):
        raise ValueError("Cue plans must use every registered track exactly once")
    if any(left["b"] != right["a"] for left, right in zip(pairs, pairs[1:])):
        raise ValueError("Cue plans contain disconnected transitions")

    rate = tracks[route[0]]["sample_rate"]
    if any(tracks[tid]["sample_rate"] != rate for tid in route):
        raise ValueError("Cue plans require one PCM sample rate")
    position = round(pairs[0]["a_start_seconds"] * rate)
    starts = []
    for index, pair in enumerate(pairs):
        frames = round(pair["beats"] * 60 / pair["bpm"] * rate)
        starts.append(position)
        position += frames
        incoming_end = round(pair["b_start_seconds"] * rate) + frames
        if index + 1 < len(pairs):
            outgoing = round(pairs[index + 1]["a_start_seconds"] * rate)
            if outgoing < incoming_end:
                raise ValueError("Outgoing cue overlaps an incoming transition")
            position += outgoing - incoming_end
        else:
            if incoming_end > tracks[pair["b"]]["frame_count"]:
                raise ValueError("Incoming cue extends beyond source PCM")
            position += tracks[pair["b"]]["frame_count"] - incoming_end
    return rate, position, starts


def compare(old_manifest, new_manifest):
    """Read-only: require exactly the same SHA-checked tracks, plan and rights.

    Only manual a_start_seconds/b_start_seconds edits may differ.
    """
    before = Path(old_manifest).absolute()
    after = Path(new_manifest).absolute()
    if before == after or before.parent != after.parent:
        raise ValueError("Compare two different cue manifests in one private source directory")
    if digest(before) == digest(after):
        raise ValueError("There are no source-manifest changes to compare")

    old_spec, old_tracks, old_pairs = _admit_library(before, calculate_waveforms=False)
    new_spec, new_tracks, new_pairs = _admit_library(after, calculate_waveforms=False)
    if old_spec.get("tracks") != new_spec.get("tracks"):
        raise ValueError("Source tracks, rights and audio provenance must be identical")
    if set(old_spec) != set(new_spec) or any(
        old_spec[k] != new_spec[k] for k in old_spec if k != "pairs"
    ):
        raise ValueError("Non-cue source manifest metadata differs")
    if len(old_pairs) != len(new_pairs):
        raise ValueError("Transition count changed")
    for original, revised in zip(old_spec["pairs"], new_spec["pairs"]):
        if (set(original) != set(revised) or
                {k: v for k, v in original.items() if k not in ("a_start_seconds", "b_start_seconds")} !=
                {k: v for k, v in revised.items() if k not in ("a_start_seconds", "b_start_seconds")}):
            raise ValueError("Only manual A/B cue seconds may change")
    rate, old_frames, old_starts = _timeline(old_tracks, old_pairs)
    new_rate, new_frames, new_starts = _timeline(new_tracks, new_pairs)
    if rate != new_rate:
        raise ValueError("Source sample rate changed")

    edits = []
    for before_pair, after_pair, begin, end in zip(old_pairs, new_pairs, old_starts, new_starts):
        edits.append({
            "pair_id": before_pair["id"],
            "outgoing_cue_before_seconds": before_pair["a_start_seconds"],
            "outgoing_cue_after_seconds": after_pair["a_start_seconds"],
            "incoming_cue_before_seconds": before_pair["b_start_seconds"],
            "incoming_cue_after_seconds": after_pair["b_start_seconds"],
            "start_before_frames": begin,
            "start_after_frames": end,
            "start_shift_frames": end - begin,
            "cues_changed": any(
                before_pair[side] != after_pair[side]
                for side in ("a_start_seconds", "b_start_seconds")
            ),
        })
    if not any(item["cues_changed"] for item in edits):
        raise ValueError("No manual cue positions changed; only manifest formatting differs")
    return {
        "kind": "private-manual-cue-comparison",
        "source_audio_sha256_verified": True,
        "same_original_tracks_and_rights": True,
        "source_manifest_sha256_before": digest(before),
        "source_manifest_sha256_after": digest(after),
        "sample_rate": rate,
        "total_frames_before": old_frames,
        "total_frames_after": new_frames,
        "total_shift_frames": new_frames - old_frames,
        "duration_seconds_before": round(old_frames / rate, 6),
        "duration_seconds_after": round(new_frames / rate, 6),
        "edited_pair_count": sum(item["cues_changed"] for item in edits),
        "pairs": edits,
        "music_uploaded": False,
        "rendered_audio_created": False,
        "blind_listening_evidence": False,
    }


def _private_html(report):
    rows = "".join(
        "<tr><th scope='row'>" + escape(item["pair_id"], quote=True) +
        "</th><td>" + str(item["outgoing_cue_before_seconds"]) + " → " +
        str(item["outgoing_cue_after_seconds"]) + "</td><td>" +
        str(item["incoming_cue_before_seconds"]) + " → " +
        str(item["incoming_cue_after_seconds"]) + "</td><td>" +
        str(round(item["start_shift_frames"] / report["sample_rate"], 6)) +
        " s</td><td>" + ("Ja" if item["cues_changed"] else "Nee") +
        "</td></tr>" for item in report["pairs"]
    )
    return ("""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; object-src 'none'">
<title>MixLab — privé cue-vergelijking</title><style>
:root{font:16px system-ui;color:#ecedf7;background:#10121b;color-scheme:dark}
main{max-width:940px;margin:5vh auto;padding:24px}
h1{font-size:clamp(2rem,5vw,3.5rem);letter-spacing:-.04em}
p{line-height:1.5;color:#bec4d8}table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:13px 9px;border-bottom:1px solid #414961}
caption{text-align:left;margin:20px 0;font-weight:700}
@media(max-width:650px){table{font-size:.85rem}th,td{padding:8px 4px}}
</style></head><body><main><h1>Cuepunten vergelijken</h1>
<p>Privé, offline en alleen handmatige keuzes. Geen audio geüpload of gerenderd.
Dit is geen automatische BPM/key-analyse of blinde luistertest.</p>
<p>Complete set: """ + str(report["duration_seconds_before"]) + " → " +
            str(report["duration_seconds_after"]) + " seconden · " +
            str(report["edited_pair_count"]) + """ overgang(en) aangepast.</p>
<table><caption>Per overgang — bron-SHA van beide versies gecontroleerd</caption>
<thead><tr><th scope='col'>Paar</th><th scope='col'>Deck A (s)</th>
<th scope='col'>Deck B (s)</th><th scope='col'>Startverschil</th>
<th scope='col'>Cue aangepast?</th></tr></thead><tbody>""" + rows +
            "</tbody></table></main></body></html>")


def write_html(report, destination, source_manifest, revised_manifest):
    # The source reports can be edited between comparison and publication.
    # Never publish a stale or misleading source-SHA receipt as a new HTML.
    if (digest(source_manifest) != report["source_manifest_sha256_before"] or
            digest(revised_manifest) != report["source_manifest_sha256_after"]):
        raise ValueError("Cue source changed since comparison; compare again")
    output = Path(destination).absolute()
    source_root = Path(source_manifest).absolute().parent
    if output.suffix.lower() != ".html" or output.parent != source_root:
        raise ValueError("Choose a new private HTML filename beside the source manifest")
    if output.exists() or output.is_symlink() or any(
        (ancestor / ".git").exists() for ancestor in (output.parent, *output.parent.parents)
    ):
        raise ValueError("Private cue report cannot overwrite data or be stored in Git")
    with output.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(_private_html(report).encode("utf-8"))
    return output


def main():
    parser = argparse.ArgumentParser(description="Compare two private SHA-pinned manual DJ cue plans offline")
    parser.add_argument("original_manifest")
    parser.add_argument("revised_manifest")
    parser.add_argument("--html", help="Optional new private static HTML next to both manifests")
    args = parser.parse_args()
    try:
        report = compare(args.original_manifest, args.revised_manifest)
        if args.html:
            write_html(report, args.html, args.original_manifest, args.revised_manifest)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, "MixLab cue comparison: " + str(exc) + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
