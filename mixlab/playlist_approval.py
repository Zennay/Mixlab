"""Private offline approvals form and strict bridge to the canonical Playlist Studio.

A browser-entered rights declaration is *not* a license. The existing
source-hash-bound import, cue bounds and user confirmation stay mandatory.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from .ingest import RIGHTS
from .journey import (
    PLAN_KIND, _private_json_path, _read_json, _source_root, load_journey,
)
from .project_wizard import _nonblank
from .browser_sha256 import SHA256_BROWSER_JS
from .approval_draft import DRAFT_JS

KIND = "mixlab-private-approved-playlist-v1"
MAX_FORM = 1024 * 1024

_PAGE = r"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src blob:; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Approve Your Set</title>
<style>
:root{color-scheme:dark;--ink:#ecf4ff;--dim:#adbbd1;--panel:#192539;--line:#3a526e;--mint:#79f2bc;--bg:#091421}
*{box-sizing:border-box}body{background:radial-gradient(at 85% 0,#1d424c,var(--bg) 62%);color:var(--ink);font:15px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1080px;padding:clamp(16px,4vw,56px);margin:auto}
h1{font-size:clamp(32px,5vw,53px);line-height:1.12;margin:8px 0}h2{font-size:23px}
p,small{color:var(--dim)}.eyebrow{font-size:12px;font-weight:800;letter-spacing:.18em;color:var(--mint)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:21px;padding:clamp(17px,2.5vw,27px);margin:20px 0}
.song{border:1px solid #3c5067;border-radius:13px;padding:17px;margin:12px 0;background:#101e30}
.row{display:grid;grid-template-columns:1fr 1fr;gap:15px}
label{display:grid;gap:5px;font-size:13px;font-weight:700;margin:9px 0}
input,select{background:#101b2b;border:1px solid #66809b;border-radius:10px;color:var(--ink);font:inherit;width:100%;padding:11px 12px}
input:focus-visible,select:focus-visible,button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
strong{overflow-wrap:anywhere}.meta{font-size:12px;color:var(--dim)}
button{border:0;border-radius:11px;background:var(--mint);font:inherit;font-weight:800;padding:14px 20px;cursor:pointer;color:#092519}
button:hover{background:#abffda}button:disabled{opacity:.45;cursor:not-allowed}
.notice{border-left:4px solid #89b6ef;padding:8px 15px;color:var(--dim);margin:20px 0}
.check{display:flex;gap:10px;align-items:start;font-size:14px}.check input{width:auto;margin-top:5px;accent-color:var(--mint)}
.feedback{min-height:24px;font-weight:600}.bad{color:#ffaeac}.good{color:var(--mint)}
.audition{border:1px dashed #53728d;border-radius:13px;margin-top:15px;padding:14px}
.audition audio{width:100%;display:block;margin:10px 0}
.audition .buttons{display:flex;gap:8px;flex-wrap:wrap}
.audition button{padding:8px 10px;border:1px solid #507b93;background:#2b4b5b;color:#f3fbff;font-size:12px}
.audition button:hover{background:#416b79}
.audition button:disabled{opacity:.3;cursor:not-allowed}
.file-note{font-size:12px;color:var(--dim)}
.rehearsal{border:1px solid #457b74;border-radius:13px;background:#102a2b;margin-top:16px;padding:16px}
.rehearsal .buttons{display:flex;gap:10px;flex-wrap:wrap}
.rehearsal button{padding:10px 13px;font-size:13px}
.rehearsal button+button{background:#314654;color:white;border:1px solid #66899b}


@media(max-width:650px){.row{grid-template-columns:1fr}.card{padding:16px}}
</style>
</head>
<body><main>
<div class="eyebrow">MIXLAB / HUMAN CUE APPROVAL</div>
<h1>Approve your set, on one screen.</h1>
<p>Provide the actual usage-rights basis and exact checked audio cue seconds for each transition. This is a private local form, **not** automatic downbeat detection or an online licensing check.</p>
<div class="notice"><strong>Before you begin:</strong> you can now select each permitted audio file from your device and audition it directly in this offline form (nothing is uploaded), or use your own player. Capture the playhead as the first sample of a transition, then confirm every cue yourself. BPM and rights must be based on real information, not guessed. The browser verifies the entire local original SHA-256 before any preview; the Studio independently checks the source again.</div>
<section class="card"><h2>Set settings</h2>
<div class="row"><label>Shared manually verified tempo
<span id="bpm" class="meta"></span></label><label for="beats">Transition length, in beats (1–64)
<input id="beats" type="number" min="1" max="64" step="1" value="16" required></label></div>
<p class="meta">Use the same --beats value when starting Playlist Studio. Changing this value changes required cue spacing.</p></section>
<section class="card"><h2>Song rights and human-verified grid</h2>
<p class="meta">Optional: select up to 11 original songs at once.
Every full SHA-256 must match the exact planned source before either
individual cue listening or two-deck rehearsals can use a file.
You may still choose each source individually.</p>
<label for="bulk-sources">Attach original playlist music in one step
<input id="bulk-sources" type="file" multiple
accept=".wav,.mp3,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,audio/*"></label>
<p id="bulk-status" class="feedback" role="status" aria-live="polite">
No originals attached in bulk.</p>
<div id="tracks"></div></section>
<section class="card"><h2>Transitions · exact manual start positions</h2><p>The outgoing cue must not backtrack into the previous incoming transition, whose end is B cue + transition duration.</p><div id="pairs"></div></section>
<section class="card"><h2>Save & resume your private work</h2>
<p>Save unfinished human source-rights notes, downbeat/cue seconds and
transition style without sending music or information to a server.
A working draft is <strong>never an approval</strong>. When reopened,
both explicit rights and order consent boxes are reset and must be
confirmed again. Keep the file private: it contains your provenance notes.</p>
<div class="row">
<button id="draft-download" type="button">Download private working draft</button>
<label for="draft-open">Reopen a private working draft
<input id="draft-open" type="file" accept=".json,application/json"></label>
</div>
<p id="draft-status" class="feedback" role="status" aria-live="polite">
No working draft saved or loaded.</p></section>
<section class="card"><h2>Consent to create a private source manifest</h2>
<label class="check"><input type="checkbox" id="rights-ack">
<span>I explicitly confirm I have a valid basis to process and use each selected track, and have manually checked the rights, BPM and cues provided above. This is my declaration, not MixLab's legal proof.</span></label>
<label class="check"><input type="checkbox" id="order-ack">
<span>I approve the displayed order and understand that MixLab will ask me to confirm it again before source import and rendering.</span></label>
<p><button id="save" type="button">Export my private approved cues</button></p>
<p id="feedback" role="status" aria-live="polite" class="feedback"></p>
<small>Save the new JSON file beside your original permitted music. The Studio rechecks source SHA-256 and validates rights/cue details again; a form download alone has not rendered, licensed or approved any media.</small>
</section>
</main><script id="seed" type="application/json">__SEED__</script>
<script>
"use strict";
__SHA_JS__
const bundle=JSON.parse(document.getElementById("seed").textContent);
const tracks=bundle.entries;
const el=id=>document.getElementById(id);
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n};
function field(label,kind,attributes){
 const wrap=node("label",""),heading=node("span","",label),input=document.createElement("input");
 input.type=kind;for(const k in attributes)input.setAttribute(k,String(attributes[k]));
 wrap.append(heading,input);return {wrap,input};
}
const rights=["synthetic","licensed","user-permitted","public-domain"];
const inputs=[],pairs=[];

// Equal-power PRELISTEN from manually verified A/B cues. This browser-only
// audition is deliberately not a MixLab rendered DSP candidate or benchmark.
const auditions=[];
let activeRehearsal=null;
function stopRehearsal(message){
 const state=activeRehearsal;
 if(!state)return;
 activeRehearsal=null;
 if(state.frame!==null)cancelAnimationFrame(state.frame);
 for(const media of [state.a,state.b]){
  media.pause();media.removeAttribute("src");media.load();
 }
 if(message)state.status.textContent=message;
}
function mediaMetadata(audio,seconds){
 return new Promise((resolve,reject)=>{
  let done=false;
  const cleanup=()=>{
   audio.removeEventListener("loadedmetadata",ok);
   audio.removeEventListener("error",failed);
   clearTimeout(timer);
  };
  const ok=()=>{
   if(done)return;done=true;cleanup();
   if(!Number.isFinite(audio.duration)||seconds+0.02>=audio.duration){
    reject(new Error("A cue is beyond the playable audio duration."));return;
   }
   try{audio.currentTime=seconds;resolve()}
   catch(_){reject(new Error("Unable to seek this browser audio format."))}
  };
  const failed=()=>{if(done)return;done=true;cleanup();reject(new Error("Browser could not decode one selected file."))};
  const timer=setTimeout(()=>{if(done)return;done=true;cleanup();reject(new Error("Audio metadata was not available."))},12000);
  audio.addEventListener("loadedmetadata",ok);audio.addEventListener("error",failed);
  audio.load();
  if(audio.readyState>=1)ok();
 });
}
async function rehearsePair(index,status){
 stopRehearsal();
 const left=auditions[index],right=auditions[index+1];
 if(!left||!right||!left.getUrl()||!right.getUrl()){
  status.textContent="Choose the matching local music files for BOTH tracks first.";
  return;
 }
 if(!rights.includes(inputs[index].select.value)||
    !rights.includes(inputs[index+1].select.value)||
    !inputs[index].provenance.value.trim()||
    !inputs[index+1].provenance.value.trim()){
  status.textContent="Enter the permission declaration and provenance for both local tracks first.";
  return;
 }
 const numberOfBeats=Number(el("beats").value);
 if(!Number.isInteger(numberOfBeats)||numberOfBeats<1||numberOfBeats>64){
  status.textContent="Choose a valid 1–64 beat length first.";return;
 }
 let outgoing,incoming;
 try{
  outgoing=numeric(pairs[index].a);
  incoming=numeric(pairs[index].b);
 }catch(_){status.textContent="Set manually checked outgoing A and incoming B cue seconds first.";return}
 const length=numberOfBeats*60/bundle.bpm;
 const a=new Audio(),b=new Audio();
 a.preload="metadata";b.preload="metadata";
 a.src=left.getUrl();b.src=right.getUrl();
 a.volume=1;b.volume=0;
 const state={a,b,frame:null,status};
 activeRehearsal=state;
 status.textContent="Preparing local two-deck cue rehearsal…";
 try{
  await Promise.all([mediaMetadata(a,outgoing),mediaMetadata(b,incoming)]);
  if(activeRehearsal!==state)return;
  if(outgoing+length>a.duration+.01||incoming+length>b.duration+.01)
   throw new Error("Selected transition extends past the end of a local source. Move the cues earlier.");
  // Single-song playbacks must not compete with the two-deck preview.
  left.player.pause();right.player.pause();
  await Promise.all([a.play(),b.play()]);
  if(activeRehearsal!==state){a.pause();b.pause();return}
  // The browser provides a rough creative equal-power prelisten, not the
  // offline canonical PCM renderer. Use both local playback positions so
  // buffering never causes a silent clock to run ahead of real audio.
  function update(){
   if(activeRehearsal!==state)return;
   const elapsed=Math.max(0,Math.min(a.currentTime-outgoing,b.currentTime-incoming));
   const fraction=Math.max(0,Math.min(1,elapsed/length));
   a.volume=Math.max(0,Math.min(1,Math.cos(fraction*Math.PI/2)));
   b.volume=Math.max(0,Math.min(1,Math.sin(fraction*Math.PI/2)));
   status.textContent="Local rehearsal: "+Math.round(fraction*100)+"% · "+
     elapsed.toFixed(1)+" / "+length.toFixed(1)+
     " s. Browser approximation, not the actual MixLab DSP.";
   if(fraction>=1||a.ended||b.ended){
    stopRehearsal("Local cue rehearsal finished. Adjust cue seconds or export the manually approved choices.");
    return;
   }
   state.frame=requestAnimationFrame(update);
  }
  state.frame=requestAnimationFrame(update);
 }catch(error){
  if(activeRehearsal===state){
   stopRehearsal("Cannot prelisten: "+(error.message||"browser audio unavailable"));
  }else{a.pause();b.pause()}
 }
}
window.addEventListener("pagehide",()=>{stopRehearsal();auditions.forEach(x=>{
 if(x&&x.getUrl())URL.revokeObjectURL(x.getUrl());
})});

function auditionFor(track,index,downbeatInput){
 const panel=node("div","audition");
 const label=node("label","");
 label.append(node("span","","Local audio for cue audition (never uploaded)"));
 const file=document.createElement("input");file.type="file";
 file.accept=".wav,.mp3,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,audio/*";
 label.append(file);panel.append(label);
 const player=document.createElement("audio");player.controls=true;
 player.preload="none";panel.append(player);
 const status=node("p","file-note","No full original SHA-256 verified. Local player and two-deck rehearsal stay locked until verification.");
 status.setAttribute("role","status");status.setAttribute("aria-live","polite");
 let previousUrl=null,selectionEpoch=0;
 async function attachOriginal(selected){
  const epoch=++selectionEpoch;
  stopRehearsal("Preview stopped because a local source was changed.");
  player.pause();player.removeAttribute("src");player.load();
  if(previousUrl){URL.revokeObjectURL(previousUrl);previousUrl=null}
  if(!selected)return;
  if(selected.name!==track.path||selected.size<=0||selected.size>512*1024*1024){
   status.textContent="Choose the expected local source filename (max 512 MiB).";
   return false;
  }
  file.disabled=true;
  try{
   const observed=await sha256LocalFile(selected,percent=>{
    status.textContent="Verifying complete original source SHA-256: "+percent+"% · no upload";
   });
   if(epoch!==selectionEpoch)return false;
   if(observed!==track.sha256){
    status.textContent="Rejected: full source SHA-256 differs from the approved plan. Playback stays locked.";
    return false;
   }
   previousUrl=URL.createObjectURL(selected);player.src=previousUrl;
   status.textContent="Verified exact full source SHA-256. Press Play and mark cues yourself.";
   return true;
  }catch(_error){
   status.textContent="Local source could not be SHA-verified. Playback remains locked.";
   return false;
  }finally{file.disabled=false;file.value="";}
 }
 file.onchange=()=>attachOriginal(file.files&&file.files[0]);
 player.onerror=()=>{status.textContent="This browser cannot decode that local audio format; use a separate player and type the seconds manually."};
 const buttons=node("div","buttons");
 function action(name,fn){
  const b=node("button","",name);b.type="button";
  b.onclick=()=>{if(!previousUrl||!Number.isFinite(player.currentTime)){
   status.textContent="First select and play this exact local song.";return;
  }fn()};
  buttons.append(b);
 }
 function current(){return String(Math.round(Math.max(0,Math.min(900,player.currentTime))*1000)/1000)}
 action("Set first downbeat",()=>{downbeatInput.value=current();status.textContent="Set manually auditioned first-downbeat position."});
 if(index<tracks.length-1)action("Mark outgoing A cue",()=>{
  pairs[index].a.value=current();status.textContent="Set outgoing A cue for the next transition.";
 });
 if(index>0)action("Mark incoming B cue",()=>{
  pairs[index-1].b.value=current();status.textContent="Set incoming B cue for the preceding transition.";
 });
 action("−4 beats",()=>{
  player.currentTime=Math.max(0,player.currentTime-4*60/track.bpm);
 });
 action("+4 beats",()=>{
  const length=Number.isFinite(player.duration)?player.duration:900;
  player.currentTime=Math.min(length,player.currentTime+4*60/track.bpm);
 });
 panel.append(buttons,status);
 auditions[index]={player,getUrl:()=>previousUrl,attach:attachOriginal};
 return panel;
}
function build(){
 el("bpm").textContent=String(bundle.bpm)+" BPM";
 tracks.forEach((track,index)=>{
  const box=node("article","song");
  box.append(node("h3","",(index+1)+". "+track.path));
  box.append(node("p","meta","Human energy "+track.energy+"/10 · SHA-bound source · "+track.bpm+" BPM"));
  const row=node("div","row");
  const selection=node("label","");
  selection.append(node("span","","Declared source usage rights"));
  const select=document.createElement("select");select.required=true;
  select.append(new Option("Select explicit rights…","",true,true));
  rights.forEach(r=>select.append(new Option(r,r)));
  selection.append(select);row.append(selection);
  const provenance=field("Source provenance / your permission basis","text",{maxlength:300,required:"required",placeholder:"e.g. original recording by me"});
  row.append(provenance.wrap);box.append(row);
  const downbeat=field("Verified first downbeat, seconds (optional)","number",
  {min:0,max:900,step:0.001,placeholder:"Leave blank if unknown"});
  box.append(downbeat.wrap);
  box.append(auditionFor(track,index,downbeat.input));
  el("tracks").append(box);
  inputs.push({select,provenance:provenance.input,downbeat:downbeat.input,track});
 });
 tracks.slice(0,-1).forEach((track,index)=>{
  const box=node("article","song");
  box.append(node("h3","",track.path+" → "+tracks[index+1].path));
  const row=node("div","row");
  const a=field("Outgoing A cue: seconds","number",
   {min:0,max:900,step:0.001,required:"required",placeholder:"Exact verified cue"});
  const b=field("Incoming B cue: seconds","number",
   {min:0,max:900,step:0.001,required:"required",placeholder:"Exact verified cue"});
  row.append(a.wrap,b.wrap);box.append(row);
  const familyWrap=node("label","");
  familyWrap.append(node("span","","Real MixLab render style for this transition"));
  const family=document.createElement("select");
  family.append(new Option("Use --family default (bass_swap)","",true,true));
  [["baseline","Equal-power baseline"],
   ["bass_swap","Bass swap"],
   ["echo_exit","Echo exit"],
   ["hard_cut","Hard cut"]].forEach(choice=>family.append(new Option(choice[1],choice[0])));
  familyWrap.append(family);box.append(familyWrap);
  box.append(node("p","meta","Your local two-deck preview is an approximate equal-power fade; other render styles are implemented by the actual offline DSP renderer, NOT this browser."));
  pairs.push({a:a.input,b:b.input,family});
  const audition=node("div","rehearsal");
  const note=node("p","meta","Local two-deck equal-power prelisten. This approximates a baseline crossfade; it is NOT a renderer output, stem swap or musical quality claim.");
  const buttons=node("div","buttons");
  const play=node("button","","▶ Rehearse A→B transition");
  play.type="button";
  const stop=node("button","","■ Stop rehearsal");
  stop.type="button";
  const status=node("p","file-note","Select local files for both tracks and enter source permissions and exact A/B cues.");
  status.setAttribute("role","status");status.setAttribute("aria-live","polite");
  play.onclick=()=>{rehearsePair(index,status)};
  stop.onclick=()=>{stopRehearsal("Rehearsal stopped by operator.")};
  buttons.append(play,stop);audition.append(note,buttons,status);
  box.append(audition);el("pairs").append(box);
 });
}
function numeric(input,optional=false){
 const raw=input.value.trim();
 if(!raw){if(optional)return null;throw new Error("Enter each required start position.");}
 const n=Number(raw);
 if(!Number.isFinite(n)||n<0||n>900)throw new Error("Cue/downbeat seconds must be finite values 0–900.");
 return n;
}
function show(message,error){
 const target=el("feedback");target.textContent=message;
 target.className="feedback "+(error?"bad":"good");
 target.setAttribute("role",error?"alert":"status");
}
function exportApproval(){
 try{
  const beats=Number(el("beats").value);
  if(!Number.isInteger(beats)||beats<1||beats>64)throw new Error("Transition beats must be 1–64.");
  if(!el("rights-ack").checked||!el("order-ack").checked)
   throw new Error("Confirm both the usage-rights declaration and the exact set order.");
  const declared=inputs.map(x=>{
   if(!rights.includes(x.select.value))throw new Error("Select actual rights for every song.");
   const basis=x.provenance.value.trim();
   if(!basis||basis.length>300||Array.from(basis).some(c=>c.charCodeAt(0)<32))
    throw new Error("Enter a short, printable usage-rights basis for each track.");
   return {path:x.track.path,sha256:x.track.sha256,
    rights:x.select.value,provenance:basis,
    first_downbeat_seconds:numeric(x.downbeat,true)};
  });
  let lastIncomingEnd=0, length=beats*60/bundle.bpm;
  const approvedPairs=pairs.map((p,i)=>{
   const a=numeric(p.a),b=numeric(p.b);
   if(a+1e-8<lastIncomingEnd)throw new Error("Outgoing cue "+(i+1)+" overlaps the previous incoming transition.");
   lastIncomingEnd=b+length;
   return {a_start_seconds:a,b_start_seconds:b,family:p.family.value||null};
  });
  const result={kind:"mixlab-private-approved-playlist-v1",plan_sha256:bundle.plan_sha256,
   declared_source_rights:true,approved_order:true,beats:beats,tracks:declared,pairs:approvedPairs};
  const blob=new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob),anchor=document.createElement("a");
  anchor.href=url;anchor.download="mixlab-event-approved.private.json";
  document.body.append(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  show("A NEW private approval file was exported. Move it beside the original music and use --approval-file with --journey-plan in Playlist Studio.",false);
 }catch(err){show(err.message||"Check the supplied manual metadata.",true)}
}
build();
__DRAFT_JS__
el("bulk-sources").addEventListener("change",async function(){
 const picker=this,status=el("bulk-status");
 const files=Array.from(picker.files||[]);
 if(!files.length)return;
 if(files.length>20){
  status.textContent="Select at most 20 files per batch; playlist has at most 11 songs.";
  picker.value="";return;
 }
 picker.disabled=true;let verified=0,rejected=0;
 const seen=new Set();
 try{
  for(const file of files){
   const index=tracks.findIndex(track=>track.path===file.name);
   if(index<0||seen.has(file.name)){
    rejected++;continue;
   }
   seen.add(file.name);
   status.textContent="Checking original "+file.name+" ("+
    (verified+rejected+1)+"/"+files.length+") locally…";
   if(await auditions[index].attach(file))verified++;else rejected++;
  }
  status.textContent="Verified "+verified+" original song(s), rejected "+
   rejected+". You can now manually audition and mark cues. No upload.";
 }finally{picker.disabled=false;picker.value="";}
});
el("save").addEventListener("click",exportApproval);
</script>
</body></html>
"""


def prepare_form(music_folder, private_plan, new_html):
    root = _source_root(music_folder)
    plan = _private_json_path(root, private_plan, existing=True)
    html = Path(new_html).absolute()
    if (html.parent != root or html.suffix.lower() != ".html" or
            html.is_symlink() or html.exists()):
        raise ValueError("Choose a NEW private .html directly inside your music folder")
    selected = load_journey(root, plan)
    _, sha = _read_json(plan)
    embedded = json.dumps({"entries": selected, "bpm": selected[0]["bpm"],
                           "plan_sha256": sha},
                          ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    embedded = embedded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    data = (_PAGE.replace("__SEED__", embedded).replace("__SHA_JS__", SHA256_BROWSER_JS)
            .replace("__DRAFT_JS__", DRAFT_JS)).encode("utf-8")
    if len(data) > MAX_FORM:
        raise ValueError("Offline approval page is too large")
    # The rights/cue form is private from inode birth, even under umask 000.
    # Opening with Path.open("xb") would expose 0666 until fchmod runs.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(html, flags, 0o600)
    owned = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Never delete another writer's file after a replacement/race.
        try:
            current = os.stat(html, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                os.unlink(html)
        except FileNotFoundError:
            pass
        raise
    return html


def _seconds(value, name, optional=False):
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 900:
        raise ValueError("Invalid human-verified seconds for "+name)
    return value


def load_approval(music_folder, private_plan, private_approval, *, beats):
    """Require exact plan/file binding and validated human rights/cue fields.

    This does not mutate source media, the notes, source manifest or the plan.
    """
    root = _source_root(music_folder)
    plan = _private_json_path(root, private_plan, existing=True)
    approval = _private_json_path(root, private_approval, existing=True)
    if plan == approval:
        raise ValueError("Approval and plan must be separate private files")
    selected = load_journey(root, plan)
    _, sha = _read_json(plan)
    info, _ = _read_json(approval)
    if (info.get("kind") != KIND or info.get("plan_sha256") != sha or
            info.get("approved_order") is not True or
            info.get("declared_source_rights") is not True or
            type(beats) is not int or not 1 <= beats <= 64 or
            info.get("beats") != beats or type(info.get("beats")) is not int):
        raise ValueError("Approvals must match the exact SHA-bound plan and selected beat count")
    tracks=info.get("tracks")
    pairs=info.get("pairs")
    if (not isinstance(tracks,list) or len(tracks)!=len(selected)
            or not isinstance(pairs,list) or len(pairs)!=len(selected)-1):
        raise ValueError("Approval track and transition counts must match exact selected journey")
    approved_tracks=[]
    for i,(entry,planned) in enumerate(zip(tracks,selected)):
        if (not isinstance(entry,dict) or entry.get("path")!=planned["path"]
                or entry.get("sha256")!=planned["sha256"]
                or entry.get("rights") not in RIGHTS):
            raise ValueError("Approval has foreign track, stale SHA or unsupported rights declaration")
        basis = entry.get("provenance")
        if not isinstance(basis, str) or not basis.strip() or basis != basis.strip():
            raise ValueError("A nonblank, trimmed source permission basis is required")
        source_basis = _nonblank(basis)
        downbeat = _seconds(entry.get("first_downbeat_seconds"), "downbeat", optional=True)
        approved_tracks.append({"path":planned["path"],"sha256":planned["sha256"],
                                "rights":entry["rights"],"provenance":source_basis,
                                "first_downbeat_seconds":downbeat})
    length_seconds=beats*60/selected[0]["bpm"]
    last_incoming=0.
    approved_pairs=[]
    from .studio import FAMILY_NAMES
    for i,entry in enumerate(pairs):
        if not isinstance(entry,dict):
            raise ValueError("Invalid approved transition record")
        chosen_family = entry.get("family")
        if chosen_family is not None and chosen_family not in FAMILY_NAMES:
            raise ValueError("Unknown or unsupported manually chosen transition render style")
        a=_seconds(entry.get("a_start_seconds"),"outgoing cue")
        b=_seconds(entry.get("b_start_seconds"),"incoming cue")
        if a+1e-8<last_incoming:
            raise ValueError("Approved transition backtracks into previous incoming section")
        last_incoming=b+length_seconds
        approved_pairs.append({"a_start_seconds":a,"b_start_seconds":b,
                               "family": chosen_family})
    return {"tracks": approved_tracks, "pairs": approved_pairs}


def main():
    parser=argparse.ArgumentParser(description="Offline private playlist rights-and-cue approval form")
    parser.add_argument("music_directory")
    parser.add_argument("private_journey_plan")
    parser.add_argument("new_form_html")
    args=parser.parse_args()
    try:
        form=prepare_form(args.music_directory,args.private_journey_plan,args.new_form_html)
    except (ValueError,TypeError,OSError) as exc:
        parser.exit(2,"MixLab Playlist Approval: "+str(exc)+"\n")
    print(json.dumps({"offline_approval_form":str(form),"rights_proof":False,
                      "rendered":False,"uploaded":False}))


if __name__=="__main__":
    main()
