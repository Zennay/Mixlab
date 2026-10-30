"""Manual approval board for local energy-based DJ cue ideas.

Consumes the existing non-mutating mixlab.cue_suggest results, never claims
beat/phrase detection or human musical preference. Produces new immutable
development manifests only after the DJ explicitly selects every transition.
"""
from __future__ import annotations

from .private_output import write_private_new

import argparse
import copy
import json
import math
import os
from pathlib import Path
import stat

from .cueprep import _read_spec
from .ingest import digest
from .set_composer import _parse_json, _secure_file
from .studio import ID

MAX_BOARD_BYTES = 2 * 1024 * 1024
MAX_CHOICES_BYTES = 32768
MAX_IDEAS_PER_PAIR = 4
KIND = "mixlab-manual-transition-idea-selection"

HTML = """<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self' file:; connect-src 'none'; base-uri 'none'; object-src 'none'">
<meta name="color-scheme" content="dark"><title>MixLab · Transition Idea Board</title>
<style>
:root{font-family:system-ui,sans-serif;background:#0d0e15;color:#f3f4fc}
*{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:auto;padding:42px 18px 100px}
h1{font-size:clamp(2.7rem,7vw,5.2rem);letter-spacing:-.07em;line-height:1.02;margin:13px 0}
p{line-height:1.65}.eyebrow{font-size:.75rem;font-weight:800;text-transform:uppercase;
letter-spacing:.2em;color:#baa5ff}.lede{max-width:790px;color:#b4bed1}
.pair{border:1px solid #3c4054;background:#1b1e2b;margin:20px 0;padding:22px;border-radius:18px}
.option{display:block;padding:14px 16px;border:1px solid #3b415c;border-radius:12px;
background:#292c3c;margin:10px 0;cursor:pointer}
.option:has(input:checked){border-color:#beadff;background:#37314d}
input{accent-color:#ad97ff;margin-right:10px}button{font:inherit;cursor:pointer;border-radius:10px;
padding:13px 19px;border:1px solid #a195c5;background:#594c91;color:white}
button:focus-visible,input:focus-visible{outline:3px solid #e2d9ff;outline-offset:3px}
.muted{color:#a7b0c4}.option label{display:block;cursor:pointer}
.preview-controls{display:flex;flex-wrap:wrap;gap:10px;margin-top:9px}
.preview-controls button{padding:8px 12px;font-size:.88rem}
code{color:#e6dbff}pre{white-space:pre-wrap;overflow-wrap:anywhere;
padding:18px;background:#232537;border-radius:12px}#message{min-height:2em}
</style></head><body><main>
<p class="eyebrow">MIXLAB / PRIVÉ CUE-IDEEËN</p><h1>Find the<br>moment.</h1>
<p class="lede">Vergelijk mogelijke overgangsmomenten uit je <strong>handmatig
vastgelegde</strong> BPM en downbeat-grid met lokale RMS-energie. Het zijn
heuristieken, geen gedetecteerde phrases of muzikale kwaliteitscores.
Elke keuze vereist jouw uitdrukkelijke bevestiging. Beluister A en B afzonderlijk
op de voorgestelde cue-tijd; deze previews zijn nog geen gerenderde
overgang en bevatten geen automatische beatmatching.</p>
<div id="pairs"></div>
<button id="download">Bewaar goedgekeurde cuekeuzes</button>
<p id="message" aria-live="polite" role="status"></p>
<p class="muted">Download het JSON-keuzeplan en maak daarmee een
<strong>nieuw, privé</strong> manifest. Je originele manifest en WAV's
worden niet gewijzigd.</p>
<pre>python3 -m mixlab.idea_board apply
  /private/session/sources/source_manifest.json
  /private/session/cue-suggestions.private.json
  /private/approved-cues.json
  /private/session/sources/approved-development.json</pre>
<p class="muted">Daarna kun je een nieuwe MixLab Studio-sessie renderen met het
goedgekeurde manifest. Geen internet, uploads of automatische acceptatie.</p>
</main><script type="application/json" id="board">__BOARD__</script><script>
"use strict";
const board=JSON.parse(document.getElementById("board").textContent);
const pairs=document.getElementById("pairs"), message=document.getElementById("message");
let playing=null;
function previewSong(track,start,duration){
 if(playing){playing.pause();playing.src="";playing=null;}
 const audio=new Audio("audio/"+encodeURIComponent(track)+".wav");
 playing=audio;audio.preload="metadata";
 const end=start+duration;
 audio.addEventListener("loadedmetadata",()=>{
   if(playing!==audio)return;
   if(start>=audio.duration){message.textContent="Dit fragment valt buiten de track.";return;}
   audio.currentTime=start;
   audio.play().catch(()=>{message.textContent="Kan lokale WAV niet beluisteren. Controleer het bronbestand.";});
 },{once:true});
 audio.addEventListener("timeupdate",()=>{
   if(audio.currentTime>=end){audio.pause();if(playing===audio)playing=null;}
 });
 audio.addEventListener("error",()=>{
   if(playing===audio)message.textContent="Lokaal bronbestand ontbreekt of wordt niet ondersteund.";
 });
 audio.load();
 message.textContent="Voorbeeld: het losse lokale nummerfragment, geen gemengde overgang.";
}
for (const pair of board.pairs) {
 const section=document.createElement("section");section.className="pair";
 const head=document.createElement("h2");head.textContent=pair.a+" → "+pair.b;section.append(head);
 const note=document.createElement("p");note.className="muted";
 note.textContent="Bestaande overgang "+pair.id+" · "+pair.bpm+" BPM, "+pair.beats+" beats";
 section.append(note);
 for (const option of pair.options){
  const card=document.createElement("div");card.className="option";
  const label=document.createElement("label");
  const input=document.createElement("input");input.type="radio";input.name=pair.id;
  input.value=option.key; input.checked=option.key==="manual";
  const strong=document.createElement("strong");
  strong.textContent=option.key==="manual"?"Huidige handmatige cues":"Energie-idee "+option.key;
  const info=document.createElement("span");
  info.textContent=" · A "+option.a_start_seconds+"s → B "+option.b_start_seconds+
  "s · "+(option.key==="manual"?"origineel bevestigd":"energieverschil "+option.energy_gap_db+" dB");
  label.append(input,strong,info);card.append(label);
  const controls=document.createElement("div");controls.className="preview-controls";
  for(const [name,id,time] of [
    ["▶ Beluister uitgaand",pair.a,option.a_start_seconds],
    ["▶ Beluister inkomend",pair.b,option.b_start_seconds]
  ]){
    const button=document.createElement("button");
    button.type="button";button.textContent=name;
    button.addEventListener("click",()=>{input.checked=true;
      previewSong(id,time,pair.beats*60/pair.bpm);});
    controls.append(button);
  }
  card.append(controls);section.append(card);
 }
 pairs.append(section);
}
document.getElementById("download").addEventListener("click",()=>{
 const selections=[], lastIncomingEnds=new Map();
 for(const pair of board.pairs){
  const selected=document.querySelector('input[name="'+pair.id+'"]:checked');
  if(!selected){message.textContent="Bevestig een cuekeuze voor ieder paar.";return;}
  const chosen=pair.options.find(option=>option.key===selected.value);
  if(!chosen){message.textContent="Ongeldige cuekeuze voor "+pair.id;return;}
  const minCue=lastIncomingEnds.get(pair.a);
  if(minCue!==undefined && chosen.a_start_seconds+1e-8<minCue){
    message.textContent=pair.id+" springt achteruit in een al afgespeeld nummer. Kies andere cues.";return;
  }
  lastIncomingEnds.set(pair.b,chosen.b_start_seconds+pair.beats*60/pair.bpm);
  selections.push({pair:pair.id,option:selected.value});
 }
 const receipt={schema_version:1,kind:"mixlab-manual-transition-idea-selection",
   source_manifest_sha256:board.source_manifest_sha256,
   suggestions_sha256:board.suggestions_sha256,selections};
 const blob=new Blob([JSON.stringify(receipt,null,2)+"\\n"],{type:"application/json"});
 const link=URL.createObjectURL(blob);const a=document.createElement("a");
 a.href=link;a.download="mixlab-approved-cues.private.json";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(link),1000);
 message.textContent="Keuzes lokaal bewaard. Render alleen na handmatige goedkeuring.";
});
</script></body></html>"""


def _number(value, key):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Invalid " + key)
    return float(value)


def _candidate_gap(outgoing, incoming):
    left = _number(outgoing.get("end_rms_dbfs"), "exit RMS")
    right = _number(incoming.get("start_rms_dbfs"), "entry RMS")
    return round(abs(left - right), 3)


def _build_pairs(source, proposals):
    """Return exact, reproducible alternatives, not guessed song metadata."""
    if not isinstance(source, dict) or not isinstance(proposals, dict):
        raise ValueError("Source and cue suggestions must be JSON objects")
    tracks = source.get("tracks")
    pairs = source.get("pairs")
    if (source.get("purpose") != "development-pilot"
            or not isinstance(tracks, list) or not isinstance(pairs, list)
            or not 2 <= len(tracks) <= 20 or not 1 <= len(pairs) <= 10):
        raise ValueError("Idea Board admits only local development-pilot track/pair manifests")
    known = {}
    for track in tracks:
        if not isinstance(track, dict) or track.get("partition") != "development":
            raise ValueError("All tracks must belong to the development partition")
        tid, sha = track.get("id"), track.get("sha256")
        if not isinstance(tid, str) or not ID.fullmatch(tid) or tid in known or not isinstance(sha, str):
            raise ValueError("Invalid or repeated track identity")
        known[tid] = track
    given = {}
    items = proposals.get("tracks")
    if not isinstance(items, list) or len(items) != len(known):
        raise ValueError("Every source track requires matching manual-grid cue suggestions")
    if proposals.get("kind") != "heuristic-manual-grid-cue-suggestions":
        raise ValueError("Not a supported local energy suggestion file")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid energy proposal")
        tid = item.get("track_id")
        if (tid not in known or tid in given
                or item.get("full_track_sha256") != known[tid]["sha256"]
                or item.get("declared_bpm") != known[tid].get("bpm")):
            raise ValueError("Energy ideas do not belong to the source track")
        given[tid] = item
    result, used = [], set()
    for pair in pairs:
        if not isinstance(pair, dict):
            raise ValueError("Invalid source pair")
        pid, a, b = pair.get("id"), pair.get("a"), pair.get("b")
        if (not isinstance(pid, str) or not ID.fullmatch(pid) or pid in used
                or a not in known or b not in known or a == b):
            raise ValueError("Invalid or duplicate source pair")
        used.add(pid)
        bpm, beats = _number(pair.get("bpm"), "pair BPM"), pair.get("beats", 8)
        if (bpm != known[a]["bpm"] or bpm != known[b]["bpm"]
                or type(beats) is not int or not 1 <= beats <= 64):
            raise ValueError("Manual BPM and pair duration mismatch")
        a0 = _number(pair.get("a_start_seconds"), "approved A cue")
        b0 = _number(pair.get("b_start_seconds"), "approved B cue")
        if not 0 <= a0 <= 900 or not 0 <= b0 <= 900:
            raise ValueError("Manual pair cues out of range")
        options = [{"key": "manual", "a_start_seconds": a0, "b_start_seconds": b0,
                    "energy_gap_db": None}]
        exit_cues = given[a].get("exit")
        entry_cues = given[b].get("entry")
        if not isinstance(exit_cues, list) or not isinstance(entry_cues, list):
            raise ValueError("Missing entry/exit suggestion candidates")
        ranked = []
        for exit_cue in exit_cues[:8]:
            for entry_cue in entry_cues[:8]:
                if not isinstance(exit_cue, dict) or not isinstance(entry_cue, dict):
                    raise ValueError("Invalid suggested cue entry")
                left = _number(exit_cue.get("start_seconds"), "exit start")
                right = _number(entry_cue.get("start_seconds"), "entry start")
                if not 0 <= left <= 900 or not 0 <= right <= 900:
                    continue
                gap = _candidate_gap(exit_cue, entry_cue)
                # Do not call this music quality: merely rank how similar
                # manually gridded transition-window endpoint RMS happens to be.
                ranked.append((gap, left, right))
        ranked.sort()
        seen_times = {(round(a0, 6), round(b0, 6))}
        for gap, left, right in ranked:
            key = (round(left, 6), round(right, 6))
            if key in seen_times:
                continue
            seen_times.add(key)
            options.append({"key": f"idea-{len(options):02d}",
                            "a_start_seconds": left, "b_start_seconds": right,
                            "energy_gap_db": gap})
            if len(options) > MAX_IDEAS_PER_PAIR + 1:
                break
        result.append({"id": pid, "a": a, "b": b, "bpm": bpm, "beats": beats,
                       "options": options})
    return result


def prepare_board(source_manifest, suggestions_file, output_html):
    source_path = Path(source_manifest).absolute()
    ideas_path = Path(suggestions_file).absolute()
    output = Path(output_html).absolute()
    if output.suffix.lower() != ".html" or output.exists() or output.is_symlink():
        raise ValueError("Choose a new .html Idea Board")
    if output.parent != source_path.parent or not output.parent.is_dir():
        raise ValueError("Save offline Idea Board next to normalized private source manifest")
    for folder in (output.parent, *output.parents):
        if (folder / ".git").exists():
            raise ValueError("Private audio products must stay outside Git")
    source = _read_spec(source_path)
    ideas = _read_spec(ideas_path)
    if not isinstance(ideas, dict):
        raise ValueError("Energy suggestions must be a JSON object")
    if ideas.get("source_manifest_sha256") != digest(source_path):
        raise ValueError("Energy suggestions are stale or belong to another source")
    data = {"schema_version": 1, "source_manifest_sha256": digest(source_path),
            "suggestions_sha256": digest(ideas_path),
            "pairs": _build_pairs(source, ideas)}
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    rendered = HTML.replace("__BOARD__", raw).encode("utf-8")
    if len(rendered) > MAX_BOARD_BYTES:
        raise ValueError("Idea Board HTML exceeds 2 MiB")
    return write_private_new(output, rendered)


def apply_board(source_manifest, suggestions_file, selection_file, new_source_manifest):
    source_path = Path(source_manifest).absolute()
    ideas_path = Path(suggestions_file).absolute()
    target = Path(new_source_manifest).absolute()
    if (target.parent != source_path.parent or target.suffix.lower() != ".json"
            or target.exists() or target.is_symlink()):
        raise ValueError("Choose a new .json alongside normalized private audio")
    for folder in (target.parent, *target.parents):
        if (folder / ".git").exists():
            raise ValueError("Cannot publish private music manifests to Git")
    source, ideas = _read_spec(source_path), _read_spec(ideas_path)
    if not isinstance(ideas, dict):
        raise ValueError("Energy suggestions must be a JSON object")
    if ideas.get("source_manifest_sha256") != digest(source_path):
        raise ValueError("Energy suggestions changed or are stale")
    current_pairs = _build_pairs(source, ideas)
    approval_path = Path(selection_file).absolute()
    if approval_path.resolve(strict=True).is_relative_to(source_path.parent):
        raise ValueError("Approval JSON must be outside immutable source session")
    approvals = _parse_json(_secure_file(approval_path, MAX_CHOICES_BYTES))
    if (not isinstance(approvals, dict)
            or set(approvals) != {"schema_version", "kind", "source_manifest_sha256",
                                 "suggestions_sha256", "selections"}
            or type(approvals["schema_version"]) is not int
            or approvals["schema_version"] != 1 or approvals["kind"] != KIND
            or approvals["source_manifest_sha256"] != digest(source_path)
            or approvals["suggestions_sha256"] != digest(ideas_path)):
        raise ValueError("Approval JSON does not belong to the current original session")
    chosen = approvals["selections"]
    if not isinstance(chosen, list) or len(chosen) != len(current_pairs):
        raise ValueError("Every original pair must have exactly one approved idea")
    mapping = {}
    for record in chosen:
        if (not isinstance(record, dict) or set(record) != {"pair", "option"}
                or not isinstance(record["pair"], str) or not isinstance(record["option"], str)
                or record["pair"] in mapping):
            raise ValueError("Invalid, duplicate or forged idea approval")
        mapping[record["pair"]] = record["option"]
    updates = {}
    for pair in current_pairs:
        if pair["id"] not in mapping:
            raise ValueError("Missing approval for a registered pair")
        matched = [x for x in pair["options"] if x["key"] == mapping[pair["id"]]]
        if len(matched) != 1:
            raise ValueError("Approval refers to a nonexisting candidate")
        updates[pair["id"]] = matched[0]
    renewed = copy.deepcopy(source)
    # Reject new combinations whose cues would silently backtrack the song
    # being played after the preceding incoming transition. We preserve
    # the user's original pair order and never auto-correct a bad route.
    prev_incoming_end = {}
    for pair in renewed["pairs"]:
        option = updates[pair["id"]]
        length = pair.get("beats", 8) * 60 / pair["bpm"]
        incoming_start = option["b_start_seconds"]
        outgoing_start = option["a_start_seconds"]
        last_end = prev_incoming_end.get(pair["a"])
        if last_end is not None and outgoing_start + 1e-8 < last_end:
            raise ValueError("Ideas would backtrack a previously playing track; select another cue")
        pair["a_start_seconds"] = outgoing_start
        pair["b_start_seconds"] = incoming_start
        prev_incoming_end[pair["b"]] = incoming_start + length
    payload = (json.dumps(renewed, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > 1024 * 1024:
        raise ValueError("Revised private manifest too large")
    return write_private_new(target, payload)



def finish_approved_ideas(source_manifest, suggestions_file, selection_file,
                          new_source_manifest, new_session, *, timeout_seconds=600):
    """Apply DJ choices and render their *actual* revised transitions.

    Unlike the browser's isolated source preview, this emits real M1 Studio
    DSP transition WAVs for the approved source windows and a new Set
    Composer. The original session, music, suggestions and approval record
    remain immutable. No automatic preference / phrase decisions.
    """
    from .session import _private_project_dir, make_session
    from .set_composer import create_composer
    from .cue_editor import prepare as prepare_visual_editor

    source_path = Path(source_manifest).absolute()
    approved_path = Path(new_source_manifest).absolute()
    destination = Path(new_session).absolute()
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 900:
        raise ValueError("Audio decoder timeout must be 30..900 seconds")
    if not source_path.parent.is_dir() or source_path.parent.is_symlink():
        raise ValueError("Private normalized source directory missing or redirected")
    # Reject nesting a new render inside an existing finished Studio. The
    # original receipts remain an independent immutable project, including
    # when the caller uses a nonstandard project folder name.
    parent_project = source_path.parent.parent
    if (source_path.parent.name == "sources"
            and (parent_project / "session-receipt.private.json").is_file()
            and destination.is_relative_to(parent_project)):
        raise ValueError("Write the new approved render outside the original MixLab session")
    _private_project_dir(destination, approved_path)
    # A successful apply is durable even if later audio import fails: the DJ
    # can rerender this exact hash-bound approved manifest in a fresh folder.
    saved_manifest = apply_board(
        source_path, suggestions_file, selection_file, approved_path)
    studio = make_session(saved_manifest, destination,
                          timeout_seconds=timeout_seconds)
    warnings = []
    composer = None
    editor = None
    try:
        composer = create_composer(destination)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        warnings.append("Optional Set Composer unavailable: " + str(exc))
    normalized = destination / "sources" / "source_manifest.json"
    try:
        editor = prepare_visual_editor(normalized, destination / "sources" / "cue-editor.html")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        warnings.append("Optional visual editor unavailable: " + str(exc))
    return {
        "ready": True, "mode": "local-manually-approved-transition-renders",
        "approved_manifest": str(saved_manifest),
        "new_session": str(destination), "studio": str(studio),
        "set_composer": str(composer) if composer else None,
        "visual_cue_editor": str(editor) if editor else None,
        "warnings": warnings, "audio_uploaded": False,
        "automatic_phrase_detection": False, "human_preference_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Private manual-grid energy cue ideas for DJ approval")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="Create offline browser suggestions")
    create.add_argument("normalized_manifest")
    create.add_argument("energy_suggestions")
    create.add_argument("new_html")
    apply = actions.add_parser("apply", help="Apply approved ideas to a NEW development source manifest")
    apply.add_argument("normalized_manifest")
    apply.add_argument("energy_suggestions")
    apply.add_argument("approved_json")
    apply.add_argument("new_manifest")
    finish = actions.add_parser("finish", help="Approve cue ideas and render a complete NEW playable Studio")
    finish.add_argument("normalized_manifest")
    finish.add_argument("energy_suggestions")
    finish.add_argument("approved_json")
    finish.add_argument("new_manifest")
    finish.add_argument("new_session")
    finish.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        if args.action == "create":
            result = prepare_board(args.normalized_manifest, args.energy_suggestions, args.new_html)
        elif args.action == "apply":
            result = apply_board(args.normalized_manifest, args.energy_suggestions,
                                 args.approved_json, args.new_manifest)
        else:
            result = finish_approved_ideas(
                args.normalized_manifest, args.energy_suggestions,
                args.approved_json, args.new_manifest, args.new_session,
                timeout_seconds=args.timeout_seconds)
            print(json.dumps(result, ensure_ascii=False))
            return
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, "MixLab Idea Board: " + str(exc) + "\n")
    print(json.dumps({"saved_private": str(result), "manual_confirmation_required": True,
                      "automatic_phrase_detection": False, "human_preference_proven": False}))


if __name__ == "__main__":
    main()
