"""Offline manual transition-arrangement page for an ORIGINAL verified Marathon.

Only emits a SHA-locked private plan. Actual DSP rendering happens later in
marathon_blend after a fresh typed human approval. Browser prelisten is a
local best-effort approximation, not the canonical rendered PCM16 mix.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from .event_vault import _marathon_duration, _read_small_json

MAX_HTML = 512 * 1024

_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / Marathon Join Studio</title>
<style>
:root{color-scheme:dark;--bg:#090e1a;--panel:#19283a;--stroke:#405b70;--ink:#f2f8ff;--muted:#adc3d8;--accent:#91f7c6}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;color:var(--ink);background:radial-gradient(at 10% 0%,#205052,var(--bg) 60%)}
main{max-width:1180px;padding:clamp(18px,4vw,55px);margin:auto}
h1{font-size:clamp(35px,6vw,72px);letter-spacing:-.06em;line-height:1;margin:12px 0 20px}
h2{font-size:21px;margin:0 0 13px}.eyebrow{font-size:12px;letter-spacing:.18em;color:var(--accent);font-weight:800}
p,.muted{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--stroke);border-radius:22px;padding:clamp(18px,3vw,28px);margin:18px 0}
.join{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:20px;padding:21px 0;border-bottom:1px solid var(--stroke)}
.join:last-child{border-bottom:0}.title{font-weight:850;font-size:18px;overflow-wrap:anywhere}
label{display:grid;gap:6px;font-weight:750;font-size:13px}
select{font:inherit;padding:12px;background:#0e1e2e;color:var(--ink);border:1px solid #6d8799;border-radius:10px}
button{font:inherit;font-weight:800;background:var(--accent);color:#0e3325;border:0;border-radius:11px;padding:12px 16px;cursor:pointer}
button:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
button:hover{filter:brightness(1.08)}button:disabled{opacity:.4}
.actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:22px 0}
.actions>*{flex:1}.stat{font-size:26px;font-weight:850;font-variant-numeric:tabular-nums}
.hash{font:11px ui-monospace,monospace;word-break:break-all;color:var(--muted)}
#status{min-height:2em}
@media(max-width:720px){.join{grid-template-columns:1fr}.join select,.join button{width:100%}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / OFFLINE JOIN ARRANGEMENT</div>
<h1>Make every<br>handoff count.</h1>
<p>Choose how long the actual audio crossfade should be at each boundary of your already completed private event. This page never edits the original WAV. Export a SHA-locked local plan, then render it with the real MixLab PCM16 engine after explicit human approval.</p>
<section class="panel"><h2>Event route &amp; local transition ideas</h2>
<div id="joins"></div></section>
<section class="panel"><h2>Your planned duration</h2>
<div id="runtime" class="stat"></div>
<p>Proposed running time after the chosen overlapping fades. The canonical renderer will recompute every PCM frame, source SHA and final offset; this browser estimate is not published audio.</p>
<div class="actions"><button id="download" type="button">Export private render plan (.json)</button>
<button id="stop" type="button" disabled>Stop preview</button></div>
<p id="status" role="status" class="muted">All selections remain local to this browser page until you export. There are no uploads, analytics, accounts or music requests.</p>
<p class="hash" id="hash"></p></section>
<section class="panel"><h2>Render the actual audio</h2>
<p>Save the plan JSON and provide it to:</p>
<code>python3 -m mixlab.marathon_blend /private/original/marathon.wav /private/edited --join-plan /private/render-plan.private.json</code>
<p>MixLab accepts the plan only when its original master SHA, event list, sample rate and exact event count still match. It then asks for a new typed <strong>yes</strong> before writing a new WAV. The short browser prelisten uses two temporary local audio streams and approximate volume changes, <strong>not</strong> the canonical PCM16 renderer or proof of good DJ transitions.</p>
</section></main>
<script id="mixlab-join-data" type="application/json">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-join-data").textContent);
const $=id=>document.getElementById(id);
const options=[2,4,8,16];
const selects=[],audios=[new Audio(),new Audio()];
const url="./"+encodeURIComponent(data.wav_name);
audios.forEach(a=>{a.src=url;a.preload="metadata";});
let token=0,raf=0,active=false;
function secs(s){
 const n=Math.max(0,Math.floor(s));
 return String(Math.floor(n/3600)).padStart(2,"0")+":"+
 String(Math.floor(n%3600/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0");
}
function choices(){return selects.map(el=>Number(el.value));}
function stopPreview(msg="Preview stopped."){
 token++;active=false;cancelAnimationFrame(raf);
 audios.forEach(a=>{a.pause();a.volume=1;});
 $("stop").disabled=true;$("status").textContent=msg;
}
function refresh(){
 const chosen=choices();
 const seconds=data.frames/data.rate-chosen.reduce((a,b)=>a+b,0);
 $("runtime").textContent=secs(seconds)+" · "+chosen.length+" real joins";
}
function ready(audio){
 if(audio.readyState>=1)return Promise.resolve();
 return new Promise((resolve,reject)=>{
  const done=()=>{audio.removeEventListener("loadedmetadata",loaded);audio.removeEventListener("error",failed)};
  const loaded=()=>{done();resolve()};
  const failed=()=>{done();reject(new Error("browser could not load this local WAV"))};
  audio.addEventListener("loadedmetadata",loaded,{once:true});
  audio.addEventListener("error",failed,{once:true});
  audio.load();
 });
}
async function prelisten(index){
 stopPreview("Preparing a local two-stream approximation…");
 const request=token;
 const duration=choices()[index],join=data.sections[index],next=data.sections[index+1];
 const outgoing=(join.start_frame+join.frames)/data.rate-duration;
 const incoming=next.start_frame/data.rate;
 try{
  await Promise.all(audios.map(ready));
  if(request!==token)return;
  audios[0].currentTime=outgoing;
  audios[1].currentTime=incoming;
  audios[0].volume=1;audios[1].volume=0;
  // All playback is private and user initiated. Browser audio support varies.
  await Promise.all(audios.map(a=>a.play()));
  if(request!==token){audios.forEach(a=>a.pause());return;}
  active=true;$("stop").disabled=false;
  const started=performance.now(),span=duration*1000;
  const frame=()=>{
   if(request!==token||!active)return;
   const elapsed=performance.now()-started,blend=Math.min(1,elapsed/span);
   audios[0].volume=1-blend;audios[1].volume=blend;
   if(blend<1&&audios.every(a=>!a.paused))raf=requestAnimationFrame(frame);
   else stopPreview("Preview ended. Export your plan to render and hear the actual mix.");
  };
  $("status").textContent="Approximate "+duration+"s local crossfade. The exported WAV may differ.";
  raf=requestAnimationFrame(frame);
 }catch(_){stopPreview("Local browser playback is unavailable. You can still export a valid render plan.");}
}
data.sections.slice(0,-1).forEach((section,i)=>{
 const next=data.sections[i+1],row=document.createElement("div");row.className="join";
 const details=document.createElement("div"),title=document.createElement("div");
 title.className="title";title.textContent=(i+1)+". "+section.label+" → "+next.label;
 const description=document.createElement("p");
 description.textContent="Original hard-cut boundary "+secs(next.start_frame/data.rate);
 details.append(title,description);
 const label=document.createElement("label");label.textContent="Crossfade duration";
 const select=document.createElement("select");
 options.forEach(sec=>{const item=document.createElement("option");item.value=String(sec);
 item.textContent=sec+" seconds";if(sec===8)item.selected=true;select.append(item)});
 select.addEventListener("change",()=>{if(active)stopPreview("Selection changed; preview stopped.");refresh()});
 selects.push(select);label.append(select);
 const btn=document.createElement("button");btn.type="button";btn.textContent="Listen to approximation";
 btn.addEventListener("click",()=>prelisten(i));
 row.append(details,label,btn);$("joins").append(row);
});
$("stop").addEventListener("click",()=>stopPreview());
$("download").addEventListener("click",()=>{
 stopPreview("Your private plan is ready. Move the downloaded JSON to your preferred secure folder.");
 const plan={schema_version:1,kind:"mixlab-private-manual-join-plan-v1",
   original_wav_sha256:data.wav_sha256,original_frames:data.frames,rate:data.rate,
   source_event_sha256s:data.sections.map(s=>s.source_sha256),
   fade_seconds_by_join:choices(),private_only:true};
 const blob=new Blob([JSON.stringify(plan,null,2)+"\n"],{type:"application/json"});
 const ref=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=ref;a.download="mixlab-marathon-joins.private.json";document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(ref),1000);
});
$("hash").textContent="Original receipt-bound Marathon WAV SHA-256: "+data.wav_sha256;
refresh();
</script></body></html>"""


def create_join_studio(original_marathon_wav, new_private_html):
    wav = Path(original_marathon_wav).absolute()
    page = Path(new_private_html).absolute()
    if (wav.name != "marathon.wav" or page.parent != wav.parent or
            page.suffix.lower() != ".html" or page.exists() or page.is_symlink()):
        raise ValueError("New offline Join Studio must be a fresh HTML beside original Marathon WAV")
    for parent in (page, *page.parents):
        if parent.is_symlink() or (parent / ".git").exists():
            raise ValueError("Join Studio cannot be created in Git or symlinked directories")
    _, count, evidence = _marathon_duration(wav.parent, wav)
    if evidence != "marathon" or not 2 <= count <= 8:
        raise ValueError("Join planning needs an original sample-preserving private Marathon")
    receipt = _read_small_json(wav.parent / "marathon.receipt.private.json")
    record = {
        "schema_version": 1,
        "kind": "mixlab-private-local-join-editor",
        "wav_name": "marathon.wav",
        "wav_sha256": receipt["wav_sha256"],
        "frames": receipt["frames"],
        "rate": receipt["rate"],
        "sections": [
            {"label": section["label"], "start_frame": section["start_frame"],
             "frames": section["frames"], "source_sha256": section["source_sha256"]}
            for section in receipt["sections"]
        ],
    }
    serialized = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    data = _PAGE.replace("__DATA__", serialized).encode("utf-8")
    if len(data) > MAX_HTML:
        raise ValueError("Join Studio private page exceeds bounded HTML size")
    created = False
    try:
        with page.open("xb") as output:
            created = True
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
    except Exception:
        if created:
            page.unlink(missing_ok=True)
        raise
    return page


def main():
    parser = argparse.ArgumentParser(
        description="Make an offline transition editor and SHA-locked render-plan exporter for an existing verified private Marathon")
    parser.add_argument("original_marathon_wav")
    parser.add_argument("new_join_studio_html")
    args = parser.parse_args()
    try:
        result = create_join_studio(args.original_marathon_wav, args.new_join_studio_html)
    except (ValueError, TypeError, KeyError, OSError):
        parser.exit(2, "MixLab Join Studio: no valid private editor was published.\n")
    print(json.dumps({"offline_join_studio":str(result),"private":True,
                      "audio_sources_uploaded":False,"actual_audio_rendered":False}))


if __name__ == "__main__":
    main()
