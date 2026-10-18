"""Printable private showbook for a real, receipt-verified MixLab Event Marathon.

Wall-clock projections are for human scheduling, never a live-performance or
audio-device reliability guarantee.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from .event_vault import _marathon_duration, _read_small_json

CLOCK = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")
MAX_HTML = 512 * 1024

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; media-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / Marathon Show Runbook</title>
<style>
:root{color-scheme:dark;--bg:#0b111d;--panel:#1a2c3e;--edge:#40596d;--text:#f3f9ff;--muted:#b0c3d4;--mint:#a1fbd5}
*{box-sizing:border-box}body{background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1170px;margin:auto;padding:clamp(17px,4vw,54px)}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.18em;color:var(--mint)}
h1{font-size:clamp(34px,6vw,65px);letter-spacing:-.06em;line-height:1.1;margin:10px 0 20px}
h2{font-size:22px;margin:0 0 12px}p,.muted{color:var(--muted)}
.panel{border:1px solid var(--edge);background:var(--panel);border-radius:20px;padding:clamp(15px,3vw,29px);margin:18px 0}
.row{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.row>*{flex:1;min-width:150px}
label{display:grid;gap:6px;font-weight:750;font-size:13px}
input,textarea{background:#0f1e2c;color:var(--text);border:1px solid #607990;padding:11px;border-radius:9px;font:inherit;width:100%}
input:focus-visible,textarea:focus-visible,button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
textarea{resize:vertical;min-height:76px}button{background:var(--mint);color:#103325;font:inherit;font-weight:850;border:0;padding:12px 17px;cursor:pointer;border-radius:9px}
.actions{display:flex;gap:12px;flex-wrap:wrap}.actions button{flex:1}
.checklist{display:grid;gap:10px;grid-template-columns:1fr 1fr}
.check{display:flex;gap:10px;align-items:start}.check input{width:auto;margin:5px 0}
.list{list-style:none;padding:0;margin:0}
.event{padding:20px 0;border-bottom:1px solid var(--edge);display:grid;grid-template-columns:100px minmax(0,1fr) 140px;gap:20px}
.event:last-child{border:none}.title{font-size:18px;font-weight:850;overflow-wrap:anywhere}.clock{font-variant-numeric:tabular-nums;font-weight:800}
.meta{font-size:12px;color:var(--muted)}
.hash{font:11px ui-monospace,monospace;word-break:break-all}
@media(max-width:700px){.event{grid-template-columns:1fr}.checklist{grid-template-columns:1fr}}
@media print{ :root{color-scheme:light}body{background:white;color:#111;font-size:12px}
 main{padding:8mm}.panel{background:white;color:#111;border:1px solid #999;border-radius:0;break-inside:avoid;padding:10px}
 p,.meta,.muted{color:#444}.clock,.title{color:#111}
 .event{break-inside:avoid;border-color:#aaa}.actions,.no-print{display:none!important}
 textarea,input{background:white;border:none;color:#111;padding:0}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / PRIVATE EVENT OPERATIONS</div>
<h1>Marathon<br>run of show.</h1>
<p>Every section below is a receipt-derived completed event within the actual output WAV, including any optional manually selected crossfades. The planned wall-clock time is a projection: pauses and device problems shift the real schedule.</p>
<section class="panel">
<div class="row">
<label for="start">Local planned start<input id="start" type="time"></label>
<div><label>Actual running time</label><div id="duration" class="clock"></div></div>
<div><label>Projected event end</label><div id="end" class="clock"></div></div>
</div>
<p class="muted">Use the normal WAV player time as source of truth when the event is underway. This is a print/CSV companion, not a dependable live mixing console.</p>
</section>
<section class="panel"><h2>Operator checklist</h2>
<div id="checks" class="checklist"></div>
<p class="meta">Manual reminders do not certify music rights or live playback readiness.</p></section>
<section class="panel"><h2>Real full-set sequence</h2>
<ol id="events" class="list"></ol></section>
<section class="panel">
<h2>Take the cue sheet with you</h2>
<p>Save notes locally as CSV for your event team or print the runbook. Notes are only in this browser page until exported; they are not uploaded or automatically saved.</p>
<div class="actions no-print"><button id="csv" type="button">Export private cue CSV</button><button id="print" type="button">Print / Save PDF</button></div>
<div id="sha" class="hash"></div></section>
<p>These are human-approved event joins: hard cuts or optional PCM16 gain-crossfades, <strong>not</strong> automatically beatmatched transitions. Independently confirm venue/playback rights, speakers, backup media and manual interventions before a real show.</p>
</main><script type="application/json" id="data">__DATA__</script><script>
"use strict";
const payload=JSON.parse(document.getElementById("data").textContent);
const $=id=>document.getElementById(id),start=$("start");
start.value=payload.default_start||"";
const notes=[],clockNodes=[];
const fmt=s=>{const n=Math.max(0,Math.floor(s));
 return String(Math.floor(n/3600)).padStart(2,"0")+":"+
 String(Math.floor(n%3600/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0")};
function projected(seconds){
 if(!start.value)return "—";
 const [h,m]=start.value.split(":").map(Number);
 if(!Number.isFinite(h)||!Number.isFinite(m))return "—";
 const secondsFromMidnight=h*3600+m*60+Math.floor(seconds);
 const day=Math.floor(secondsFromMidnight/86400),within=secondsFromMidnight%86400;
 const value=String(Math.floor(within/3600)).padStart(2,"0")+":"+
 String(Math.floor(within%3600/60)).padStart(2,"0")+":"+
 String(within%60).padStart(2,"0");
 return value+(day?" (+"+day+" day)":"");
}
const checks=[
 "Local permission for every included master and the venue confirmed",
 "Primary WAV and independent playback backup available",
 "Speakers, output routing and safe volume checked",
 "Device power, notifications and screen sleep checked",
 "Programme start, breaks and stage handoff agreed with host",
 "Offline player and paper showbook available without Wi-Fi"
];
checks.forEach(label=>{const wrap=document.createElement("label");wrap.className="check";
 const box=document.createElement("input");box.type="checkbox";
 const span=document.createElement("span");span.textContent=label;
 wrap.append(box,span);$("checks").append(wrap);
});
payload.sections.forEach((sec,i)=>{
 const row=document.createElement("li");row.className="event";
 const stamp=document.createElement("div");stamp.className="clock";stamp.textContent=fmt(sec.start_seconds);
 const center=document.createElement("div");
 const title=document.createElement("div");title.className="title";
 title.textContent=String(i+1)+". "+sec.label;
 const meta=document.createElement("div");meta.className="meta";
 meta.textContent="Duration "+fmt(sec.duration_seconds)+" • starts at "+fmt(sec.start_seconds);
 const textarea=document.createElement("textarea");textarea.maxLength=1000;
 textarea.placeholder="Manual cue / handoff notes for this event";textarea.setAttribute("aria-label","Notes for event "+String(i+1));
 notes.push(textarea);center.append(title,meta,textarea);
 const wall=document.createElement("div");wall.className="clock";clockNodes.push(wall);
 row.append(stamp,center,wall);$("events").append(row);
});
function updateClocks(){
 $("duration").textContent=fmt(payload.duration_seconds);
 $("end").textContent=projected(payload.duration_seconds);
 payload.sections.forEach((sec,i)=>clockNodes[i].textContent=projected(sec.start_seconds));
}
function csvCell(raw){
 let value=String(raw??"");
 if(/^\s*[=+\-@]/.test(value))value="'"+value;
 return '"'+value.replaceAll('"','""')+'"';
}
$("csv").addEventListener("click",()=>{
 const lines=[["wav_sha256",payload.wav_sha256],["planned_start",start.value||"not_set"],
  ["event","label","offset","planned_clock","duration","operator_note"]];
 payload.sections.forEach((sec,i)=>lines.push([i+1,sec.label,
   fmt(sec.start_seconds),projected(sec.start_seconds),fmt(sec.duration_seconds),notes[i].value]));
 const text=lines.map(row=>row.map(csvCell).join(",")).join("\r\n")+"\r\n";
 const url=URL.createObjectURL(new Blob([text],{type:"text/csv;charset=utf-8"}));
 const a=document.createElement("a");a.href=url;a.download="mixlab-marathon-show.private.csv";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$("print").addEventListener("click",()=>window.print());
start.addEventListener("input",updateClocks);
$("sha").textContent="Joined WAV SHA-256: "+payload.wav_sha256;
updateClocks();
</script></body></html>"""


def create_runbook(marathon_wav, new_html, *, start=None):
    wav = Path(marathon_wav).absolute()
    target = Path(new_html).absolute()
    if wav.name != "marathon.wav" or target.suffix.lower() != ".html" or (
            target.parent != wav.parent or target.exists() or target.is_symlink()):
        raise ValueError("Runbook must be NEW private HTML beside the original Marathon WAV")
    for entry in (target, *target.parents):
        if entry.is_symlink() or (entry / ".git").exists():
            raise ValueError("Marathon showbook must stay outside Git and symlinked paths")
    if start is not None and (not isinstance(start, str) or not CLOCK.fullmatch(start)):
        raise ValueError("Showbook start must be a valid local HH:MM time")
    duration, count, _ = _marathon_duration(wav.parent, wav)
    receipt = _read_small_json(wav.parent / "marathon.receipt.private.json")
    sections = receipt["sections"]
    if len(sections) != count:
        raise ValueError("Marathon sections differ from actual verified WAV")
    entries = []
    for i, section in enumerate(sections):
        end = sections[i+1]["start_frame"] if i + 1 < count else receipt["frames"]
        entries.append({"label": section["label"], "start_seconds": section["start_frame"] / receipt["rate"],
                        "duration_seconds": (end - section["start_frame"]) / receipt["rate"]})
    record = {"schema_version": 1, "wav_sha256": receipt["wav_sha256"],
              "duration_seconds": duration, "default_start": start, "sections": entries}
    serialized = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _PAGE.replace("__DATA__", serialized).encode("utf-8")
    if len(page) > MAX_HTML:
        raise ValueError("Private Marathon showbook exceeds page budget")
    created = False
    try:
        with target.open("xb") as dst:
            created = True
            os.fchmod(dst.fileno(), 0o600)
            dst.write(page)
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return target


def main():
    parser=argparse.ArgumentParser(description="Make a private printable operator runbook from a completed Marathon WAV")
    parser.add_argument("marathon_wav")
    parser.add_argument("new_private_html")
    parser.add_argument("--start",help="Planned local start HH:MM")
    args=parser.parse_args()
    try:
        path=create_runbook(args.marathon_wav,args.new_private_html,start=args.start)
    except (ValueError,TypeError,KeyError,OSError):
        parser.exit(2,"MixLab Marathon Showbook: no private runbook was published.\n")
    print(json.dumps({"private_marathon_runbook":str(path),"offline":True,
                      "canonical_joined_master_required":True,
                      "live_hardware_certified":False},allow_nan=False))


if __name__=="__main__":
    main()
