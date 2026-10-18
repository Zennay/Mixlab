"""Full offline DJ Event Brief Studio based on rights-safe manual song notes.

Exports a private unapproved energy-journey plan for Playlist Studio. No
automatic musical analysis, online calls, source copying or audio decoding.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .journey import NOTE_KIND, _private_json_path, _read_json, _records, _source_root

MAX_BOARD_BYTES = 1024 * 1024

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; img-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Event Brief Studio</title>
<style>
:root {color-scheme:dark;--ink:#f1f7ff;--muted:#afc5d8;--panel:#172438;--deep:#0b131f;--line:#344b64;--mint:#84efbd;--blue:#83b7ff;--danger:#ff9b9b}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% -10%,#264458,#09121e 55%);font:15px/1.5 system-ui,-apple-system,Arial,sans-serif;color:var(--ink)}
main{max-width:1420px;margin:0 auto;padding:clamp(18px,3.5vw,58px)}
.eyebrow{font-size:11px;color:var(--mint);text-transform:uppercase;letter-spacing:.24em;font-weight:850}
h1{font-size:clamp(32px,5vw,58px);line-height:1.05;letter-spacing:-.035em;margin:10px 0 16px;max-width:820px}h2{font-size:22px;margin:0}h3{font-size:16px;margin:10px 0}
p{color:var(--muted)}.caption{max-width:820px}
.layout{display:grid;grid-template-columns:minmax(300px,370px) minmax(0,1fr);gap:24px;align-items:start;margin-top:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:22px;padding:clamp(16px,2.1vw,26px);box-shadow:0 24px 60px #0002}
.controls{display:grid;gap:15px;position:sticky;top:12px}
.field{display:grid;gap:6px}label,.fieldname{font-size:13px;color:#d7e6f7;font-weight:700}
select,input{width:100%;padding:11px 12px;background:#0e1b2b;border:1px solid #557086;border-radius:10px;color:var(--ink);font:inherit}
select:focus-visible,input:focus-visible,button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
button{border:1px solid #547c91;border-radius:11px;background:#304c66;color:#fff;padding:10px 15px;cursor:pointer;font:inherit;font-weight:700}
button:hover{background:#3d607b}button:disabled{opacity:.3;cursor:not-allowed}
button.primary{background:var(--mint);border-color:transparent;color:#091e17}button.primary:hover{background:#a8f8d6}
.tags,.exclude{display:flex;flex-wrap:wrap;gap:8px}.check{display:inline-flex;align-items:center;gap:6px;border:1px solid #526b81;background:#162d42;border-radius:22px;padding:5px 11px;font-size:12px;font-weight:600}
.check input{width:auto;accent-color:var(--mint);margin:0}.check:has(input:checked){border-color:var(--mint)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:11px}.dim{font-size:12px;color:var(--muted)}
ul,ol{padding-left:0;list-style:none}.timeline{display:grid;gap:9px;margin:14px 0}
.track{display:flex;align-items:center;gap:12px;padding:12px 13px;background:#0e1a2b;border:1px solid #37506b;border-radius:14px;min-width:0}
.number{padding:10px 13px;border-radius:11px;background:#29415c;font-weight:850}.desc{flex:1;min-width:0}
.title{font-weight:750;overflow-wrap:anywhere}.detail{font-size:12px;color:var(--muted);overflow-wrap:anywhere}
.actions{display:flex;gap:5px}.actions button{padding:8px 10px}
.chart{display:block;width:100%;max-height:285px;background:#0f1b2d;border:1px solid var(--line);border-radius:13px;margin:17px 0}
.grid{stroke:#334d68;stroke-width:1}.curve{stroke:var(--mint);stroke-width:4;fill:none}.target{stroke:var(--blue);stroke-width:3;stroke-dasharray:8 6;fill:none}
.legend{font-size:12px;color:var(--muted)}.badge{display:inline-flex;font-size:12px;color:var(--mint);background:#123b36;border:1px solid #296959;padding:6px 10px;border-radius:30px;margin:8px 8px 4px 0}
.notice{border-left:3px solid var(--blue);padding:7px 0 7px 13px;color:var(--muted);font-size:13px}
.feedback{font-size:13px;min-height:22px}.feedback[role=alert]{color:var(--danger)}
.explain{margin:0;color:var(--muted);font-size:12px}.footer{margin:24px 0;color:var(--muted);font-size:12px}
@media(max-width:930px){.layout{grid-template-columns:1fr}.controls{position:static}.wide{order:2}}
@media(max-width:580px){.row{grid-template-columns:1fr}.track{flex-wrap:wrap}.actions{margin-left:auto}.card{padding:16px}}
</style>
</head>
<body><main>
<div class="eyebrow">MIXLAB / PRIVATE EVENT PLANNING</div>
<h1>From a brief to your next DJ set.</h1>
<p class="caption">Describe the flow, choose a few must-plays and generate an editable set order from your <strong>human-confirmed</strong> BPM, energy and mood notes. Every suggestion stays offline. MixLab still requires your approval, usage rights and exact music cues before any WAV or MP3 is rendered.</p>
<div class="layout">
<section class="card controls" aria-labelledby="brief-title">
<h2 id="brief-title">Your event brief</h2>
<div class="row">
<div class="field"><label for="shape">Energy storyline</label><select id="shape">
<option value="build">Build the room</option><option value="late-peak">Peak near the end</option>
<option value="peak">Peak midway</option><option value="release">Ease the room down</option></select></div>
<div class="field"><label for="count">Number of songs</label><select id="count"></select></div>
</div>
<div class="row">
<div class="field"><label for="tempo">Verified BPM</label><select id="tempo"></select></div>
<div class="field"><label for="tag">Prefer a mood/genre</label><select id="tag"></select></div>
</div>
<div class="field"><label for="opening">Must-play opener</label><select id="opening"></select></div>
<div class="field"><label for="closing">Must-play finale</label><select id="closing"></select></div>
<div class="field"><span class="fieldname">Skip these songs</span><div id="exclude" class="exclude" role="group" aria-label="Tracks not to include"></div></div>
<button id="generate" type="button" class="primary">Generate my set order</button>
<div id="feedback" class="feedback" role="status" aria-live="polite"></div>
<p class="notice">Selections are suggestions from subjective notes. No automatic beat, key, phrase, lyrics or stem processing; different BPM groups never mix.</p>
</section>
<section class="card wide" aria-labelledby="set-title">
<h2 id="set-title">Your track journey</h2>
<div id="summary"><p>Choose your event brief and generate an ordered set.</p></div>
<svg id="chart" class="chart" viewBox="0 0 820 285" role="img" aria-label="Energy shape comparison"></svg>
<div class="legend">Green = manual track energy · Dashed blue = target energy curve · Scale 1–10</div>
<ol id="timeline" class="timeline"></ol>
<div class="row"><button id="regenerate" type="button" disabled>Reset to suggestion</button>
<button id="export" type="button" class="primary" disabled>Save private set plan</button></div>
<p id="export-status" class="feedback" role="status" aria-live="polite"></p>
<p class="dim">Your export contains source SHA-256 hashes, not audio or source permissions. Save it in your private music folder. The regular Playlist Studio checks each recording again and asks you for rights, cues and final approval.</p>
</section>
</div>
<div class="footer">PRIVATE OFFLINE TOOL · NO NETWORK · NO AUDIO UPLOAD · SUGGESTIONS ARE NOT RESEARCH VALIDATION OR AUDIBLY BETTER TRANSITIONS</div>
</main>
<script id="mixlab-notes" type="application/json">__NOTES_JSON__</script>
<script>
"use strict";
const bundle=JSON.parse(document.getElementById("mixlab-notes").textContent);
const tracks=bundle.tracks, MAX_BEAM=192;
let generated=null, order=null, choices=null, target=null, bpm=null;
const el=(id)=>document.getElementById(id);
const node=(tag,cls,value)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=String(value);return n};
const opt=(value,title)=>{const o=node("option","",title);o.value=String(value);return o};
const names=tracks.map(t=>t.path);
function numberOption(){
 const select=el("count");for(let n=2;n<=Math.min(11,tracks.length);n++)select.append(opt(n,n+" songs"));
 select.value=String(Math.min(5,tracks.length));
}
function createOptions(select,values,empty){
 select.replaceChildren();if(empty!==undefined)select.append(opt("",empty));
 values.forEach(value=>select.append(opt(value,value)));
}
function refreshOptions(){
 const bpmValue=el("tempo").value;
 const possible=tracks.filter(t=>!bpmValue||String(t.bpm)===bpmValue).map(t=>t.path);
 for(const id of ["opening","closing"]){
  const input=el(id),prior=input.value;createOptions(input,possible,"Any "+(id==="opening"?"opener":"finale"));
  if(possible.includes(prior))input.value=prior;
 }
 const excluded=el("exclude");const checked=new Set(Array.from(excluded.querySelectorAll("input:checked")).map(c=>c.value));
 excluded.replaceChildren();
 tracks.filter(t=>!bpmValue||String(t.bpm)===bpmValue).forEach(t=>{
  const label=node("label","check"),input=document.createElement("input");
  input.type="checkbox";input.value=t.path;input.checked=checked.has(t.path);
  label.append(input,node("span","",t.path));excluded.append(label)
 });
}
function setup(){
 numberOption();
 const tempos=Array.from(new Set(tracks.map(t=>t.bpm))).sort((a,b)=>a-b);
 createOptions(el("tempo"),tempos,"Any matching group");
 const tags=Array.from(new Set(tracks.flatMap(t=>t.tags||[]))).sort();
 createOptions(el("tag"),tags,"Any mood/genre");
 el("tempo").onchange=refreshOptions;
 refreshOptions();
 for(const id of ["generate","regenerate"])el(id).onclick=()=>generate();
 el("export").onclick=save;
}
function targets(shape,count){
 const out=[];
 for(let i=0;i<count;i++){
  const t=i/(count-1),v=shape==="build"?2+7*t:
  shape==="release"?9-7*t:shape==="peak"?2+7*(1-Math.abs(2*t-1)):
  2+7*Math.min(1,t/.8)-2*Math.max(0,(t-.8)/.2);
  out.push(Number(v.toFixed(3)));
 }
 return out;
}
function compare(a,b){
 const d=Math.round(a.score*1e9)-Math.round(b.score*1e9);
 if(d)return d;
 const x=a.order.map(i=>a.group[i].path.toLowerCase()).join("\u0001");
 const y=b.order.map(i=>b.group[i].path.toLowerCase()).join("\u0001");
 return x<y?-1:x>y?1:0;
}
function search(request){
 const needed=request.count,tgt=targets(request.shape,needed),excluded=request.excluded;
 const allTempos=Array.from(new Set(tracks.map(t=>t.bpm))).sort((a,b)=>a-b);
 let winner=null;
 for(const speed of allTempos){
  if(request.tempo && String(speed)!==request.tempo)continue;
  const group=tracks.filter(t=>t.bpm===speed&&!excluded.has(t.path))
    .slice().sort((a,b)=>a.path.toLowerCase().localeCompare(b.path.toLowerCase(),"en"));
  if(group.length<needed)continue;
  if(request.opening&&!group.some(t=>t.path===request.opening))continue;
  if(request.closing&&!group.some(t=>t.path===request.closing))continue;
  let states=[{score:0,order:[],mask:0,group}];
  for(let pos=0;pos<needed;pos++){
   const next=[];
   for(const state of states){
    for(let i=0;i<group.length;i++){
     const song=group[i];
     if(state.mask&(1<<i))continue;
     if(request.opening && (pos===0)!==(song.path===request.opening))continue;
     if(request.closing && (pos===needed-1)!==(song.path===request.closing))continue;
     let jump=0;
     if(state.order.length){
      const delta=Math.abs(song.energy-group[state.order[state.order.length-1]].energy);
      jump=.65*Math.max(0,delta-2)**2;
     }
     const mismatch=1.5*(song.energy-tgt[pos])**2;
     const boost=request.tag&&song.tags.includes(request.tag)?-.25:0;
     next.push({score:state.score+jump+mismatch+boost,order:state.order.concat(i),
       mask:state.mask|(1<<i),group});
    }
   }
   next.sort(compare);states=next.slice(0,MAX_BEAM);
   if(!states.length)break;
  }
  if(states.length){
   const candidate=states[0];
   if(!winner||compare(candidate,winner)<0)winner=candidate;
  }
 }
 if(!winner)return null;
 return {selected:winner.order.map(i=>winner.group[i]),bpm:winner.group[0].bpm,
         targets:tgt,score:winner.score};
}
function getRequest(){
 const excluded=new Set(Array.from(el("exclude").querySelectorAll("input:checked")).map(x=>x.value));
 return {shape:el("shape").value,count:Number(el("count").value),
   tempo:el("tempo").value,tag:el("tag").value,opening:el("opening").value,
   closing:el("closing").value,excluded};
}
function feedback(message,error){
 const target=el("feedback");target.textContent=message;
 target.setAttribute("role",error?"alert":"status");
}
function generate(){
 const request=getRequest();
 generated=null;order=null;choices=null;el("export").disabled=true;
 el("regenerate").disabled=true;el("timeline").replaceChildren();
 el("chart").replaceChildren();el("summary").replaceChildren();
 if(request.opening&&request.closing&&request.opening===request.closing){
  feedback("Opening and finale must be different songs.",true);return;
 }
 if(request.excluded.has(request.opening)||request.excluded.has(request.closing)){
  feedback("A required opener or finale cannot also be excluded.",true);return;
 }
 const selection=search(request);
 if(!selection){
  feedback("No compatible same-BPM route for these settings. Choose fewer songs, remove an exclusion or relax the must-plays.",true);return;
 }
 generated=request;choices=selection.selected;order=choices.slice();target=selection.targets;
 bpm=selection.bpm;
 feedback("Proposed "+order.length+" songs at "+bpm+" manually verified BPM. Adjust order if needed, then export.",false);
 el("export").disabled=false;el("regenerate").disabled=false;
 show();
}
function polyline(svg,points,klass){
 const p=document.createElementNS("http://www.w3.org/2000/svg","polyline");
 p.setAttribute("points",points.map((e,i)=>(45+730*i/(points.length-1))+","+(242-202*(e-1)/9)).join(" "));
 p.setAttribute("class",klass);svg.append(p);
}
function show(){
 const summary=el("summary");summary.replaceChildren();
 for(const v of [order.length+" selected tracks",bpm+" verified BPM",generated.shape+" energy arc",
  "Local/manual annotations"]){summary.append(node("span","badge",v))}
 const svg=el("chart");svg.replaceChildren();
 for(const y of [1,5,10]){
  const l=document.createElementNS("http://www.w3.org/2000/svg","line");
  l.setAttribute("x1","45");l.setAttribute("x2","775");
  l.setAttribute("y1",String(242-202*(y-1)/9));
  l.setAttribute("y2",String(242-202*(y-1)/9));l.setAttribute("class","grid");svg.append(l);
 }
 polyline(svg,target,"target");polyline(svg,order.map(t=>t.energy),"curve");
 const list=el("timeline");list.replaceChildren();
 order.forEach((song,i)=>{
  const item=node("li","track");item.append(node("span","number",i+1));
  const detail=node("div","desc");
  detail.append(node("div","title",song.path));
  const drift=(song.energy-target[i]).toFixed(1);
  detail.append(node("div","detail","Energy "+song.energy+"/10 · Goal "+target[i]+"/10 · Delta "+drift+
    " · "+(song.tags.join(", ")||"no tags")));
  item.append(detail);
  const buttons=node("div","actions");
  for(const [delta,label] of [[-1,"↑"],[1,"↓"]]){
   const b=node("button","",label),other=i+delta;
   b.type="button";b.disabled=other<0||other>=order.length;
   if(generated.opening&&(i===0||other===0))b.disabled=true;
   if(generated.closing&&(i===order.length-1||other===order.length-1))b.disabled=true;
   b.setAttribute("aria-label","Move "+song.path+(delta<0?" earlier":" later"));
   b.onclick=()=>{[order[i],order[other]]=[order[other],order[i]];show()};
   buttons.append(b);
  }
  item.append(buttons);list.append(item);
 });
}
function save(){
 if(!generated||!order)return;
 const entries=order.map((song,i)=>({
  path:song.path,sha256:song.sha256,bpm:song.bpm,energy:song.energy,
  tags:song.tags.slice(),target_energy:target[i]
 }));
 const payload={kind:"mixlab-private-energy-plan-v1",shape:generated.shape,
  source_notes_sha256:bundle.source_sha256,bpm:bpm,
  preference_proven:false,automatic_tempo_matching:false,
  selection_method:"offline-human-brief-energy-heuristic-v1",
  requested_opening:generated.opening||null,requested_closing:generated.closing||null,
  excluded_tracks:Array.from(generated.excluded),entries:entries};
 const blob=new Blob([JSON.stringify(payload,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=url;a.download="mixlab-event-journey.private.json";
 document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 el("export-status").textContent="Exported a NEW private plan. Move it beside your local music, then use Playlist Studio --journey-plan. Changes to sources invalidate hashes.";
}
setup();
</script>
</body></html>
"""


def create_workspace(music_folder, private_notes, new_html):
    root = _source_root(music_folder)
    notes = _private_json_path(root, private_notes, existing=True)
    output = Path(new_html).absolute()
    if (output.parent != root or output.suffix.lower() != ".html" or
            output.is_symlink() or output.exists()):
        raise ValueError("Use a NEW private .html output directly in your music folder")
    note_data, sha = _read_json(notes)
    if note_data.get("kind") != NOTE_KIND:
        raise ValueError("Expected private human-annotated energy notes")
    checked = _records(root, note_data.get("tracks"))
    embedded = json.dumps({"source_sha256": sha, "tracks": checked}, ensure_ascii=True,
                          allow_nan=False, separators=(",", ":"))
    embedded = embedded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _HTML.replace("__NOTES_JSON__", embedded).encode("utf-8")
    if len(page) > MAX_BOARD_BYTES:
        raise ValueError("Private event workspace exceeds 1 MiB")
    with output.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(page)
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Create private offline interactive event brief planner from human music notes")
    parser.add_argument("music_directory", help="Local, permitted music folder outside Git")
    parser.add_argument("private_energy_notes", help="Existing SHA-pinned human notes JSON in music folder")
    parser.add_argument("new_offline_html", help="NEW HTML in the same local music folder")
    args = parser.parse_args()
    try:
        result = create_workspace(args.music_directory, args.private_energy_notes,
                                  args.new_offline_html)
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"MixLab Event Brief Studio: {exc}\n")
    print(json.dumps({"offline_event_studio": str(result), "unapproved": True,
                      "audio_uploaded": False, "automatic_analysis": False}))


if __name__ == "__main__":
    main()
