"""Private operator showbook for a completed exact-receipt MixLab WAV set.

No new media decoding, research shortcuts, network or actual live mixer.
The canonical set_player.build_chapters validates original session, audio and
all selected transition receipts before providing the authoritative timeline.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .set_player import build_chapters

_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Live Show Runbook</title>
<style>
:root{color-scheme:dark;--ink:#eef7ff;--muted:#b5c6d9;--bg:#0b121d;--panel:#18283b;--line:#3a5470;--accent:#83f3c1}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 85% -10%,#234452,var(--bg) 60%);font:15px/1.5 system-ui,sans-serif;color:var(--ink)}
main{margin:auto;max-width:1160px;padding:clamp(18px,4vw,62px)}h1{font-size:clamp(31px,5vw,58px);line-height:1.1;letter-spacing:-.04em;margin:6px 0}h2{font-size:21px}
p{color:var(--muted)}.eyebrow{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.17em}
.panel{border:1px solid var(--line);border-radius:20px;background:var(--panel);padding:clamp(16px,2.5vw,29px);margin:20px 0}
.row{display:flex;gap:20px;align-items:end;flex-wrap:wrap}.row>*{flex:1;min-width:170px}
label{display:block;font-size:13px;margin-bottom:5px;color:#d7e9f5;font-weight:700}
input,textarea{font:inherit;color:var(--ink);background:#101d2c;border:1px solid #58718b;border-radius:10px;padding:10px 12px;width:100%}
textarea{resize:vertical;min-height:60px}.time{font-variant-numeric:tabular-nums;font-weight:800}
.badge{display:inline-block;border:1px solid #4d697a;border-radius:20px;background:#1e3944;padding:8px 14px;margin:5px 7px 5px 0;font-size:12px}
button{background:var(--accent);color:#0c291c;font:inherit;font-weight:800;border:none;border-radius:12px;padding:12px 17px;cursor:pointer}
button:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
button:hover{background:#b0ffdd}.subtle{background:#2b4861;color:white}
ul{padding:0;list-style:none}.cue{display:grid;grid-template-columns:95px minmax(0,1fr) 108px;gap:13px;align-items:start;padding:15px 0;border-bottom:1px solid var(--line)}
.cue:last-child{border-bottom:none}.label{font-weight:800;overflow-wrap:anywhere;font-size:15px}
.meta{font-size:12px;color:var(--muted)}.clock{font-size:15px}.track{border-left:3px solid var(--accent);padding-left:12px}.transition{border-left:3px solid #86b8ff;padding-left:12px}
kbd{background:#183c37;border:1px solid #447b6c;border-radius:5px;padding:2px 5px}
.checklist{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.check{display:flex;align-items:start;gap:9px;color:#daebf7;line-height:1.35}
.check input{width:auto;margin:3px 0;accent-color:var(--accent)}
.warning{border-left:3px solid #f8c178;padding-left:14px}
.hash{overflow-wrap:anywhere;font-family:ui-monospace,monospace;font-size:12px}
.actions{display:flex;gap:10px;flex-wrap:wrap}.actions button{flex:1}
@media(max-width:750px){.cue{grid-template-columns:74px minmax(0,1fr)}.cue .clock{grid-column:2}.checklist{grid-template-columns:1fr}}
@media print {
 :root{color-scheme:light}body{background:white;color:#111;font-size:12px}main{padding:5mm}.panel{background:white;color:#111;border:1px solid #aaa;border-radius:0;padding:10px;margin:10px 0;break-inside:avoid}
 p,.meta,.warning{color:#444}.eyebrow{color:#222}.cue{border-color:#bbb;break-inside:avoid}.label,.time,.clock{color:#111}
 button,.actions,.no-print{display:none!important}textarea,input{border:none;color:#222;padding:0}
 .track{border-color:#333}.transition{border-color:#888}.badge{background:white;border:1px solid #aaa;color:#222}
}
</style>
</head>
<body><main>
<div class="eyebrow">MIXLAB / PRIVATE SHOW CONTROL</div><h1>Run of show.</h1>
<p>Operator companion for your already-rendered, hash-verified MixLab set. Chapter offsets are from the actual PCM16 WAV; wall-clock slots assume uninterrupted playback from your chosen start time.</p>
<section class="panel">
<div class="row">
<div><label for="start">Planned start time (local clock, optional)</label><input id="start" type="time" aria-describedby="clock-note"></div>
<div><label>Running time</label><div id="duration" class="time"></div></div>
<div><label>Planned end time</label><div id="ends" class="time">Choose a start time</div></div>
</div>
<p id="clock-note" class="meta">Wall-clock times are projections. Pauses, computer sleep, start delays and hardware interruption shift the actual schedule; use the normal WAV player clock as source of truth during an event.</p>
<div id="quick" aria-label="Set details"></div>
</section>
<section class="panel">
<h2>Performance checklist</h2>
<div class="checklist" id="checklist"></div>
<p class="meta">Checks are operator reminders only. They do not establish rights, audio hardware reliability or successful playback.</p>
</section>
<section class="panel">
<h2>Exact rendered chapter sequence</h2>
<p>Blue left edge = transition. Green = source track passage. The *offset* times below come from the verified complete WAV and are not computed from expected source lengths.</p>
<ul id="chapters"></ul>
</section>
<section class="panel">
<h2>Export &amp; print</h2>
<p class="meta">Save an offline CSV cue sheet including your own operator notes, chapter offsets, projected wall-clock times and full WAV SHA. It never includes original media paths or recordings.</p>
<div class="actions no-print"><button id="csv" type="button">Export private cue-sheet CSV</button><button id="notes-export" type="button" class="subtle">Export notes JSON</button><button id="print" type="button" class="subtle">Print / save as PDF in browser</button></div>
<div class="no-print"><label for="notes-import">Import notes from Rehearsal Desk (same verified WAV SHA only)</label>
<input id="notes-import" type="file" accept=".json,application/json">
<p id="notes-status" class="meta" role="status" aria-live="polite">Imported notes also appear in your printable runbook and CSV export. Nothing is uploaded.</p></div>
<p class="hash" id="sha"></p>
</section>
<section class="panel warning">
<h2>Live event boundary</h2>
<p>This is a **schedule and paper backup**, not a live mixing engine or a guarantee of uninterrupted playback. Keep a local independent fallback player or copy of a permitted set, verify output devices, and use the already-rendered offline WAV and its separate playback page.</p>
</section>
</main>
<script id="mixlab-runbook" type="application/json">__DATA__</script>
<script>
"use strict";
const metadata=JSON.parse(document.getElementById("mixlab-runbook").textContent);
const chapters=metadata.chapters;
const el=id=>document.getElementById(id);
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n};
const start=el("start");
start.value=metadata.default_start||"";
const notes=[];
function formatTime(seconds){
 const v=Math.max(0,Math.floor(seconds));
 return String(Math.floor(v/3600)).padStart(2,"0")+":"+
  String(Math.floor(v%3600/60)).padStart(2,"0")+":"+String(v%60).padStart(2,"0");
}
function wallClock(seconds){
 if(!start.value)return "—";
 const pieces=start.value.split(":").map(Number);
 if(pieces.length!==2||!Number.isFinite(pieces[0])||!Number.isFinite(pieces[1]))return "—";
 const all=pieces[0]*3600+pieces[1]*60+Math.floor(seconds);
 const day=Math.floor(all/86400),t=all%86400;
 const label=String(Math.floor(t/3600)).padStart(2,"0")+":"+
  String(Math.floor(t%3600/60)).padStart(2,"0")+":"+String(t%60).padStart(2,"0");
 return label+(day?" (+"+day+" day"+(day===1?"":"s")+")":"");
}
function makeChecklist(){
 const labels=[
  "Audio sources and usage rights explicitly confirmed",
  "Local WAV playback and independent fallback available",
  "Laptop/device charged, do-not-sleep setup checked",
  "Output routing, speakers and safe volume checked",
  "Start cue and room schedule confirmed with host",
  "Offline master/player saved and accessible without Wi-Fi"
 ];
 const root=el("checklist");
 labels.forEach(label=>{
  const row=node("label","check"),check=document.createElement("input");
  check.type="checkbox";row.append(check,node("span","",label));root.append(row);
 });
}
function build(){
 el("duration").textContent=formatTime(metadata.duration_seconds);
 el("sha").textContent="Private WAV SHA-256: "+metadata.wav_sha256;
 const quick=el("quick");
 [chapters.length+" rendered chapters",
  chapters.filter(x=>x.kind==="transition").length+" transitions",
  metadata.wav_name+" · offline PCM16 WAV"].forEach(t=>quick.append(node("span","badge",t)));
 const root=el("chapters");root.replaceChildren();
 chapters.forEach((ch,index)=>{
  const row=node("li","cue"),left=node("span","time",formatTime(ch.start_seconds)),
   details=node("div",ch.kind==="transition"?"transition":"track");
  details.append(node("div","label",(ch.kind==="transition"?"Transition ":"Track ")+ch.label));
  const duration=Math.max(0,Math.min(ch.duration_seconds,metadata.duration_seconds-ch.start_seconds));
  details.append(node("div","meta","Section duration "+formatTime(duration)+
    (ch.family?" · Style "+ch.family.replaceAll("_"," "):"")));
  const input=document.createElement("textarea");input.rows=2;input.maxLength=1000;
  input.setAttribute("aria-label","Operator note for chapter "+String(index+1));
  input.placeholder="Operator note (optional, private)";details.append(input);notes.push(input);
  const wall=node("div","clock",wallClock(ch.start_seconds));wall.dataset.offset=String(ch.start_seconds);
  row.append(left,details,wall);root.append(row);
 });
 makeChecklist();
 el("ends").textContent=wallClock(metadata.duration_seconds);
}
function updateClock(){
 document.querySelectorAll(".clock[data-offset]").forEach(cell=>{
  cell.textContent=wallClock(Number(cell.dataset.offset));
 });
 el("ends").textContent=start.value?wallClock(metadata.duration_seconds):"Choose a start time";
}
function csvCell(raw){
 let str=String(raw??"");
 // Prevent spreadsheet applications from interpreting user notes as formulas.
 if(/^[\s]*[=+\-@]/.test(str))str="'"+str;
 return '"'+str.replaceAll('"','""')+'"';
}
function exportCsv(){
 const output=[
  ["mixlab_wav_sha256",metadata.wav_sha256],
  ["start_time",start.value||"not_set"],
  ["chapter","kind","label","family","offset","wall_clock_if_uninterrupted","duration","operator_note"]
 ];
 chapters.forEach((ch,index)=>{
  output.push([index+1,ch.kind,ch.label,ch.family||"",
   formatTime(ch.start_seconds),wallClock(ch.start_seconds),
   formatTime(ch.duration_seconds),notes[index].value]);
 });
 const csv=output.map(row=>row.map(csvCell).join(",")).join("\r\n")+"\r\n";
 const blob=new Blob([csv],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob);
 const a=document.createElement("a");a.download="mixlab-show-runbook.private.csv";a.href=url;
 document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function exportNotesJson(){
 const payload={schema_version:1,kind:"mixlab-private-rehearsal-notes",
  wav_sha256:metadata.wav_sha256,chapter_count:chapters.length,
  notes:notes.map(input=>input.value)};
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)+"\n"],
   {type:"application/json"}));
 const a=document.createElement("a");a.href=url;a.download="mixlab-rehearsal.private.json";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 el("notes-status").textContent="Private SHA-bound notes exported for the Rehearsal Desk.";
}
async function importNotes(event){
 const file=event.target.files&&event.target.files[0];event.target.value="";
 if(!file)return;
 if(file.size>131072){
  el("notes-status").textContent="Notes import refused: file exceeds 128 KiB.";return;
 }
 try{
  const incoming=JSON.parse(await file.text());
  if(!incoming||incoming.kind!=="mixlab-private-rehearsal-notes"||
      incoming.schema_version!==1||incoming.wav_sha256!==metadata.wav_sha256||
      incoming.chapter_count!==chapters.length||
      !Array.isArray(incoming.notes)||incoming.notes.length!==chapters.length||
      incoming.notes.some(value=>typeof value!=="string"||value.length>1000))
   throw new Error("incompatible rehearsal notes");
  incoming.notes.forEach((value,i)=>{notes[i].value=value;});
  el("notes-status").textContent="Rehearsal notes imported into this exact WAV runbook.";
 }catch(_){
  el("notes-status").textContent="Notes import refused: malformed data or a different WAV SHA.";
 }
}
build();start.addEventListener("input",updateClock);
el("csv").addEventListener("click",exportCsv);
el("notes-export").addEventListener("click",exportNotesJson);
el("notes-import").addEventListener("change",importNotes);
el("print").addEventListener("click",()=>window.print());
</script></body></html>"""


def create_runbook(session_directory, complete_wav, new_html, *, start=None):
    """Render operator companion only from a fully verified canonical set."""
    if start is not None:
        import re
        if (not isinstance(start, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", start)):
            raise ValueError("Planned start must be local HH:MM or omitted")
    wav = Path(complete_wav).absolute()
    target = Path(new_html).absolute()
    if (target.suffix.lower() != ".html" or target.parent != wav.parent or
            target.is_symlink() or target.exists()):
        raise ValueError("Choose a NEW private .html beside the completed WAV")
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or (ancestor / ".git").exists():
            raise ValueError("Keep private showbook outside Git and symlinked paths")
    # Reuse the existing production receipt, source and render admission. This
    # checks the complete WAV's SHA, frame count and every selected transition.
    verified = build_chapters(session_directory, wav)
    data = {"schema_version": 1, "kind": "mixlab-private-wav-show-runbook",
            "wav_name": verified["wav_name"], "wav_sha256": verified["wav_sha256"],
            "duration_seconds": verified["duration_seconds"],
            "chapters": verified["chapters"], "default_start": start}
    blob = json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _PAGE.replace("__DATA__", blob).encode("utf-8")
    if len(page) > 512 * 1024:
        raise ValueError("Show runbook is too large")
    with target.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(page)
    return target


def main():
    parser = argparse.ArgumentParser(
        description="Generate a private printable DJ operator timeline from an existing verified full-set WAV")
    parser.add_argument("private_session", help="Original private Studio session")
    parser.add_argument("complete_wav", help="Existing full-set WAV with canonical SHA receipt")
    parser.add_argument("new_html", help="NEW private .html beside the complete WAV")
    parser.add_argument("--start", help="Optional planned local HH:MM clock time")
    args = parser.parse_args()
    try:
        target = create_runbook(args.private_session, args.complete_wav,
                                args.new_html, start=args.start)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, "MixLab show runbook: " + str(exc) + "\n")
    print(json.dumps({"runbook": str(target), "offline": True,
                      "canonical_wav_receipt_required": True,
                      "live_mixing": False, "event_reliability_proven": False}))


if __name__ == "__main__":
    main()
