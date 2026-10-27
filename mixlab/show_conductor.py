"""Offline multi-set operator cockpit using real finished, SHA-verified MixLab WAVs.

This is a MANUAL run-of-show, not live beatmixing, playback redundancy,
timing automation, a rights license, or blind listening evidence.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import stat
import wave

from .set_player import build_chapters
from .browser_sha256 import SHA256_BROWSER_JS
from .marathon_sequence import _private_html_destination, _read_plan

KIND = "mixlab-private-multi-set-show-v1"
MAX_SETS = 6
MAX_PAGE = 512 * 1024
MAX_REPORT = 192 * 1024
CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")
_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';media-src blob:;connect-src 'none';img-src 'none';object-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Offline Show Conductor</title><style>
:root{color-scheme:dark;--bg:#07131e;--card:#152b3b;--line:#506c7e;--mint:#a7ffdc;--muted:#bdd2df}
*{box-sizing:border-box}body{margin:0;color:#effdff;background:radial-gradient(at 88% 0,#245445,var(--bg) 60%);font:15px/1.55 system-ui}
main{max-width:1320px;margin:auto;padding:clamp(18px,4vw,56px)}
h1{font-size:clamp(42px,6vw,79px);line-height:1.02;letter-spacing:-.06em}
h2{font-size:22px;margin:0 0 12px}.tag{color:var(--mint);font-weight:900;letter-spacing:.18em;font-size:12px}
p,small{color:var(--muted)}.layout{display:grid;grid-template-columns:minmax(310px,1fr) minmax(320px,1.15fr);gap:20px}
.panel{border:1px solid var(--line);border-radius:20px;background:var(--card);padding:clamp(16px,2vw,28px);margin:18px 0}
ol{margin:0;padding:0;list-style:none;display:grid;gap:11px}
li{border:1px solid var(--line);border-radius:13px;background:#0e2534;padding:15px}
li.selected{border-color:var(--mint);background:#1e493f}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.row>*{min-width:0}
.row strong{flex:1;font-size:17px;overflow-wrap:anywhere}.description{font-size:12px}
input,textarea{background:#0b2031;color:white;border:1px solid #748e9f;border-radius:9px;font:inherit;padding:9px}
input[type=file]{max-width:100%;font-size:12px}input[type=number]{width:90px}
textarea{width:100%;min-height:66px;resize:vertical}
button{color:#fff;background:#28685b;border:1px solid #75a898;border-radius:11px;padding:10px 14px;cursor:pointer;font:inherit;font-weight:750}
button:hover{background:#378877}button:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
button:disabled{opacity:.4}.accent{background:#98ffcf;color:#0c291e}
audio{width:100%;margin:14px 0}.controls{display:flex;gap:9px;flex-wrap:wrap;margin:13px 0}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.stat{padding:14px;border-radius:12px;border:1px solid #42796e;background:#10372f}
.stat strong{display:block;font-size:clamp(19px,3vw,34px);color:var(--mint);overflow-wrap:anywhere}
.stat small{font-size:11px}.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
#chapters li{display:flex;gap:12px;align-items:center}#chapters button{flex:1;text-align:left}
@media(max-width:940px){.layout{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr 1fr}}
@media(max-width:480px){.stats{grid-template-columns:1fr}}
@media print{button,audio,input,textarea{display:none!important}body{background:white;color:black}.panel,li{background:white;color:black}}
</style></head><body><main>
<div class="tag">MIXLAB · COMPLETE REAL WAV SETS / PRIVATE MANUAL STAGE</div>
<h1>Run the whole<br>show, not just a mix.</h1>
<p>Arrange finished, source-verified local WAV sets into a single event.
Attach each actual file on this computer, set planned gaps and operator
notes, and manually advance when the room is ready. No automatic mixing,
fade, timed playback, website requests, or master modifications.</p>
<div class="stats"><div class="stat"><small>Planned show runtime</small><strong id="total">—</strong></div>
<div class="stat"><small>Playing now</small><strong id="current">—</strong></div>
<div class="stat"><small>Next cue</small><strong id="next-cue">—</strong></div></div>
<div class="layout"><section class="panel"><h2>1 / Your approved WAV setlist</h2>
<p>Every listed full set was source- and SHA-verified by MixLab at page creation.
The browser verifies the complete local file SHA-256 in 1 MiB chunks before playback.
A filename, duration or byte-size match alone never grants playback.
Do not substitute unknown recordings. No music is embedded in this page.</p>
<div class="panel"><strong>Load a full local show folder</strong>
<p>Optional: choose a parent folder containing the original finished WAVs in
subfolders. Only files matching an approved WAV name and exact byte length
are read. Each candidate is fully SHA-256 verified before being armed.
No folder paths, music or files are uploaded; individual pickers remain available.</p>
<input type="file" id="folder" webkitdirectory multiple
 aria-label="Choose the local parent folder of approved show WAVs">
<p id="folder-status" role="status">No folder selected.</p></div>
<ol id="setlist"></ol></section>
<section><div class="panel"><h2>2 / Playback & manually controlled changeover</h2>
<audio id="player" controls preload="metadata"></audio>
<div class="controls"><button id="previous" type="button">← Previous set</button>
<button id="next" type="button">Arm next set →</button>
<button id="cue-prev" type="button">← Prior chapter</button>
<button id="cue-next" type="button">Next chapter →</button>
<button id="stop" type="button">Stop / detach file</button>
<button id="mark" type="button">Mark local WAV cue position</button>
<button id="full" type="button">Fullscreen</button></div>
<p id="player-status" role="status">Select an approved set and attach its WAV. Sets never auto-start or advance.</p>
<label>Optional private note for the next manual cue mark (up to 120 characters)
<textarea id="cue-note" maxlength="120"
placeholder="Lighting cue, transition intent, timing note…"></textarea></label>
<ol id="chapters"></ol><div id="selected-cues-panel" hidden>
<h2>Selected previous rehearsal cues (private)</h2>
<p>These human-chosen WAV positions are operator notes, not measured show
timing. Buttons seek only; music always needs manual Play.</p>
<ol id="selected-cues"></ol></div></div>
<div class="panel"><h2>3 / Operator run-of-show</h2>
<label>Planned show start (local clock) <input type="time" id="start"></label>
<p>This timetable is a planning estimate from real WAV lengths and your
manually chosen breaks. It is not a wall-clock controller or professional
playback guarantee. No telemetry or persistent state.</p>
<div class="controls"><button id="export" type="button" class="accent">Download source-locked run-of-show plan</button></div>
<p id="export-status" role="status"></p>
<div class="controls"><button id="journal-export" type="button">
Download private rehearsal journal</button></div>
<p id="journal-status" role="status">No rehearsal actions recorded.
Marks are your own browser audio positions, not venue performance evidence.</p>
<p class="hash" id="fingerprint"></p>
</div></section></div>
</main><script type="application/json" id="mixlab-show-data">__DATA__</script><script>
__SHA_JS__
"use strict";
const data=JSON.parse(document.getElementById("mixlab-show-data").textContent);
const $=id=>document.getElementById(id),audio=$("player");
const attached=new Map(),attachGeneration=data.sets.map(()=>0);
const breaks=data.saved_breaks?data.saved_breaks.slice():
 data.sets.map((_,i)=>i===data.sets.length-1?0:data.default_break);
const notes=data.saved_notes?data.saved_notes.slice():
 data.sets.map(()=>""),rows=[],chapterButtons=[];
let active=-1,attachedURL=null;
const rehearsal=[],rehearsalOpenedAt=performance.now();
function recordRehearsal(kind){
 if(active<0||!attached.get(active)||!audio.src){
  $("journal-status").textContent="Attach and arm an SHA-verified WAV to record a cue.";
  return;
 }
 const elapsed=Math.max(0,Math.floor(performance.now()-rehearsalOpenedAt));
 if(rehearsal.length>=256||elapsed>48*3600*1000){
  $("journal-status").textContent="Private rehearsal log limit reached. Export before continuing.";
  return;
 }
 const pos=Number.isFinite(audio.currentTime)?Math.max(0,Math.min(
  audio.currentTime,data.sets[active].duration_seconds)):0;
 const event={seq:rehearsal.length+1,kind,set_index:active,
  wav_position_seconds:Math.round(pos*1000)/1000,elapsed_ms:elapsed};
 if(kind==="mark"){
  const note=$("cue-note").value.trim();
  if(note)event.note=note;
  $("cue-note").value="";
 }
 rehearsal.push(event);
 $("journal-status").textContent=rehearsal.length+
  " private manual playback/cue records (not exported until requested).";
}
const time=seconds=>{const n=Math.max(0,Math.floor(seconds));return [Math.floor(n/3600),Math.floor(n%3600/60),n%60].map(x=>String(x).padStart(2,"0")).join(":");};
const clock=minutes=>String(Math.floor(minutes/60)%24).padStart(2,"0")+":"+
 String(Math.floor(minutes%60)).padStart(2,"0");
function drop(){audio.pause();audio.removeAttribute("src");audio.load();
 if(attachedURL){URL.revokeObjectURL(attachedURL);attachedURL=null;}}
function label(set){return set.label+" · "+time(set.duration_seconds);}
function timetable(){
 let minutes=Number($("start").value.slice(0,2))*60+Number($("start").value.slice(3));
 if(!Number.isFinite(minutes))minutes=19*60;
 const before=minutes;
 data.sets.forEach((set,i)=>{
  const start=minutes;minutes+=set.duration_seconds/60;
  rows[i].schedule.textContent=clock(start)+"–"+clock(minutes)+
   (i<data.sets.length-1?" · next break "+breaks[i]+" min":" · end");
  if(i<data.sets.length-1)minutes+=breaks[i];
 });
 $("total").textContent=time((minutes-before)*60);
}
function info(){
 const pos=Number.isFinite(audio.currentTime)?audio.currentTime:0;
 if(active<0){$("current").textContent="No set armed";$("next-cue").textContent="Attach a local WAV";return;}
 const set=data.sets[active],upcoming=set.chapters.find(ch=>ch.start_seconds>pos+.5);
 $("current").textContent=set.label;
 $("next-cue").textContent=upcoming?time(upcoming.start_seconds-pos):
  active<data.sets.length-1?"Manual set change":"End of show";
}
function select(i){
 if(i<0||i>=data.sets.length)return;
 drop();active=i;
 rows.forEach((row,n)=>row.card.classList.toggle("selected",n===i));
 const file=attached.get(i);
 if(file){attachedURL=URL.createObjectURL(file);audio.src=attachedURL;audio.load();
  $("player-status").textContent="SHA-256 verified original WAV attached: "+
    data.sets[i].label+". PRESS PLAY manually. No auto-switch or crossfade.";
  recordRehearsal("arm");
  audio.onloadedmetadata=()=>{
   if(!Number.isFinite(audio.duration)||
       Math.abs(audio.duration-data.sets[i].duration_seconds)>.3){
    drop();$("player-status").textContent="Decoded duration mismatch; refused this local file.";
   }
  };
 }else $("player-status").textContent="Arm "+data.sets[i].label+
   ": select its original completed local WAV below. No playback until you press Play.";
 $("chapters").replaceChildren();chapterButtons.length=0;
 data.sets[i].chapters.forEach((ch,n)=>{
  const row=document.createElement("li"),button=document.createElement("button");
  button.type="button";button.textContent=time(ch.start_seconds)+" · "+ch.kind+" · "+ch.label;
  button.addEventListener("click",()=>{
   if(!attached.get(active)||!audio.src){$("player-status").textContent="Attach the real WAV before cueing.";return;}
   audio.currentTime=ch.start_seconds;info();
  });row.append(button);$("chapters").append(row);chapterButtons.push(button);
 });
 const selected=data.selected_rehearsal;
 $("selected-cues-panel").hidden=!selected;
 $("selected-cues").replaceChildren();
 if(selected){
  const marks=selected.marks.filter(mark=>mark.set_index===i);
  for(const mark of marks){
   const row=document.createElement("li"),btn=document.createElement("button");
   btn.type="button";btn.textContent="Seek selected cue "+time(mark.position);
   btn.addEventListener("click",()=>{
    if(!attached.get(active)||!audio.src){
     $("player-status").textContent="Attach and SHA-verify original WAV first.";return;
    }
    audio.currentTime=mark.position;info();
    $("player-status").textContent="Manual seek complete; press Play separately.";
   });
   const note=document.createElement("p");note.className="description";
   note.textContent=(mark.chapter===null?"No nearby approved chapter":
    mark.chapter+" · "+mark.chapter_kind+" · "+
    (mark.chapter_delta>=0?"+":"")+mark.chapter_delta.toFixed(3)+"s")+
    (mark.note?" · private note: "+mark.note:"");
   row.append(btn,note);$("selected-cues").append(row);
  }
  if(!marks.length){
   const li=document.createElement("li");
   li.textContent="No marked cues for this set in the chosen take.";
   $("selected-cues").append(li);
  }
 }
 $("previous").disabled=i===0;$("next").disabled=i===data.sets.length-1;info();
}
data.sets.forEach((set,i)=>{
 const card=document.createElement("li"),heading=document.createElement("div");
 heading.className="row";const name=document.createElement("strong");
 name.textContent=(i+1)+". "+label(set);
 const arm=document.createElement("button");arm.type="button";arm.textContent="Arm set";
 arm.addEventListener("click",()=>select(i));heading.append(name,arm);
 const schedule=document.createElement("p");schedule.className="description";
 const fileInput=document.createElement("input");fileInput.type="file";fileInput.accept=".wav,audio/wav";
 fileInput.setAttribute("aria-label","Attach permitted WAV for "+set.label);
 const status=document.createElement("p");status.className="description";
 status.textContent="No full WAV attached. SHA-256 verification is required before playback.";
 fileInput.addEventListener("change",async()=>{
  const file=fileInput.files?.[0];
  if(!file)return;
  const generation=++attachGeneration[i];
  // Detach even a previously verified file: a new choice must pass again.
  attached.delete(i);
  if(i===active)select(i);
  if(file.name!==set.wav_name||file.size!==set.size_bytes){
   status.textContent="Rejected: local WAV filename/byte length does not match.";
   return;
  }
  fileInput.disabled=true;
  status.textContent="Verifying the full local WAV SHA-256; audio stays locked…";
  try{
   const verifiedHash=await sha256LocalFile(file,percent=>{
    status.textContent="Verifying full original WAV locally: "+percent+"% (no upload).";
   });
   if(generation!==attachGeneration[i])return;
   if(verifiedHash!==set.wav_sha256){
    status.textContent="Rejected: WAV content SHA-256 differs from the approved original. No playback.";
    return;
   }
   attached.set(i,file);
   status.textContent="Verified full SHA-256 · original WAV ready; no audio uploaded.";
   if(i===active)select(i);
  }catch(_error){
   // Never expose local filename or filesystem details from browser errors.
   status.textContent="Could not verify complete local SHA-256; playback remains locked.";
  }finally{fileInput.disabled=false;}
 });
 const breakline=document.createElement("label");breakline.className="row";
 if(i<data.sets.length-1){
  breakline.textContent="Planned changeover break (minutes) ";
  const input=document.createElement("input");input.type="number";input.min="0";input.max="120";
  input.step="1";input.value=String(breaks[i]);input.setAttribute("aria-label","Minutes between set "+(i+1)+" and next");
  input.addEventListener("change",()=>{
   const val=Number(input.value);if(!Number.isInteger(val)||val<0||val>120){input.value=String(breaks[i]);return;}
   breaks[i]=val;timetable();
  });breakline.append(input);
 }
 const note=document.createElement("textarea");note.maxLength=300;
 note.setAttribute("aria-label","Private handoff cue note for "+set.label);
 note.placeholder="Microphone intro, guest requests, lighting, safety cue (operator-only).";
 note.value=notes[i];
 note.addEventListener("input",()=>{notes[i]=note.value;});
 card.append(heading,schedule,fileInput,status,breakline,note);
 $("setlist").append(card);rows.push({card,schedule,status});
});
// Folder selection is an optional offline convenience, not filesystem access
// outside the user's explicitly granted FileList.
$("folder").addEventListener("change",async()=>{
 const input=$("folder"),status=$("folder-status");
 const files=Array.from(input.files||[]);
 if(!files.length)return;
 if(files.length>1000){
  status.textContent="Folder contains too many files (>1000). Use individual approved WAV pickers.";
  return;
 }
 const candidates=files.filter(file=>data.sets.some(set=>
  file.name===set.wav_name&&file.size===set.size_bytes));
 if(candidates.length>24){
  status.textContent="Too many plausible full WAVs (>24). Choose a smaller private show folder.";
  return;
 }
 if(!candidates.length){
  status.textContent="No filename/byte-length candidates found. Original WAVs were not attached.";
  return;
 }
 // A newer manual picker always wins over a stale asynchronous folder scan.
 const generation=attachGeneration.map((value,i)=>++attachGeneration[i]);
 let accepted=0,rejected=0;
 input.disabled=true;
 try{
  for(const file of candidates){
   status.textContent="Checking private show WAV "+(accepted+rejected+1)+"/"+
    candidates.length+" locally…";
   let digest;
   try{
    digest=await sha256LocalFile(file,percent=>{
     status.textContent="Verifying full local WAV "+(accepted+rejected+1)+"/"+
      candidates.length+" · "+percent+"% (offline)";
    });
   }catch(_error){rejected++;continue;}
   const idx=data.sets.findIndex(set=>set.wav_name===file.name&&
    set.size_bytes===file.size&&set.wav_sha256===digest);
   if(idx<0||generation[idx]!==attachGeneration[idx]){rejected++;continue;}
   attached.set(idx,file);accepted++;
   rows[idx].status.textContent="Verified complete WAV SHA-256 from private folder. Arm manually.";
  }
  status.textContent="Folder finished: "+accepted+" verified WAV"+
   (accepted===1?"":"s")+"; "+rejected+" unmatched/failed candidates. "+
   "Previously armed audio was not started or switched.";
 }finally{input.disabled=false;}
});
$("previous").addEventListener("click",()=>select(active-1));
$("next").addEventListener("click",()=>select(active+1));
$("stop").addEventListener("click",()=>{recordRehearsal("stop");drop();$("player-status").textContent="Audio stopped and local file URL detached. Press Arm set to reattach.";info();});
function chapterJump(direction){
 if(active<0||!audio.src)return;
 const set=data.sets[active],pos=audio.currentTime||0;
 const matches=direction<0?set.chapters.filter(ch=>ch.start_seconds<pos-1):
  set.chapters.filter(ch=>ch.start_seconds>pos+1);
 const target=direction<0?matches.at(-1):matches[0];
 if(target){audio.currentTime=target.start_seconds;info();}
}
$("cue-prev").addEventListener("click",()=>chapterJump(-1));
$("cue-next").addEventListener("click",()=>chapterJump(1));
$("full").addEventListener("click",()=>{
 const result=document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.();
 if(result?.catch)result.catch(()=>{});
});
$("mark").addEventListener("click",()=>recordRehearsal("mark"));
audio.addEventListener("play",()=>recordRehearsal("play"));
audio.addEventListener("timeupdate",info);audio.addEventListener("ended",()=>{
 recordRehearsal("ended");
 $("player-status").textContent="Completed current set; NEXT ONE WILL NOT START automatically. Check the room and arm it manually.";
});
audio.addEventListener("error",()=>{$("player-status").textContent="Browser failed to decode local WAV. Use a trusted offline native audio player.";});
$("start").value=data.default_start;$("start").addEventListener("change",timetable);
$("fingerprint").textContent="Source full SHA-256s: "+data.sets.map(s=>s.wav_sha256).join(" · ");
$("export").addEventListener("click",()=>{
 const plan={schema_version:1,kind:"mixlab-private-multi-set-show-v1",
  source_sha256s:data.sets.map(s=>s.wav_sha256),
  start_local:$("start").value,break_minutes:breaks.slice(),
  private_notes:notes.slice(),private_only:true,
  automatic_playback:false,blind_study:false};
 if(!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(plan.start_local)){
  $("export-status").textContent="Choose a real HH:MM local start time first.";return;
 }
 const blob=new Blob([JSON.stringify(plan,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),link=document.createElement("a");
 link.href=url;link.download="mixlab-show-conductor.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("export-status").textContent="Private SHA-bound set schedule downloaded. No audio/notes uploaded or auto-started.";
});
$("journal-export").addEventListener("click",()=>{
 if(!rehearsal.length){
  $("journal-status").textContent="No verified WAV rehearsal actions to export yet.";
  return;
 }
 const journal={schema_version:1,kind:"mixlab-private-show-rehearsal-v1",
  source_sha256s:data.sets.map(set=>set.wav_sha256),
  events:rehearsal.slice(),private_only:true,automatic_playback:false,
  clock_claim:"browser-monotonic-operator-only"};
 const blob=new Blob([JSON.stringify(journal,null,2)+"\n"],{type:"application/json"});
 const link=document.createElement("a"),url=URL.createObjectURL(blob);
 link.href=url;link.download="mixlab-show-rehearsal.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("journal-status").textContent="Private journal exported explicitly; no audio, operator notes, "+
  "source paths or venue-clock claims included.";
});
window.addEventListener("pagehide",drop);timetable();select(0);
</script></body></html>"""


def _sources(raw):
    if len(raw) < 4 or len(raw) > MAX_SETS * 2 or len(raw) % 2:
        raise ValueError("Supply 2–6 exact pairs SESSION_DIR FINAL_SET.wav in planned order")
    result, paths = [], []
    for i in range(0, len(raw), 2):
        session = Path(raw[i]).absolute()
        wav = Path(raw[i+1]).absolute()
        if (wav.is_symlink() or session.is_symlink() or
                any(p.is_symlink() for p in (wav, *wav.parents, session, *session.parents))):
            raise ValueError("Actual private WAV/session cannot use symlinked ancestor folders")
        metadata = build_chapters(session, wav)
        st = wav.lstat()
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("Actual finished set must be a regular local WAV")
        label = wav.parent.name[:60]
        if not label or any(ord(c)<32 for c in label):
            raise ValueError("Use a named private finished set folder")
        result.append({
            "label": label, "wav_name": wav.name,
            "wav_sha256": metadata["wav_sha256"],
            "duration_seconds": metadata["duration_seconds"],
            "size_bytes": st.st_size,
            "chapters": [{"kind": c["kind"], "label": c["label"],
                          "start_seconds": c["start_seconds"]}
                         for c in metadata["chapters"]]
        })
        paths.append(wav)
    if len(set(paths)) != len(paths) or len({s["wav_sha256"] for s in result}) != len(result):
        raise ValueError("A real completed set cannot appear twice in the same stage lineup")
    return result


def prepare_show(new_private_html, *source_pairs, start="19:00",
                 break_minutes=10, saved_plan=None,
                 rehearsal_selection=None, rehearsal_journals=()):
    if not isinstance(start, str) or not CLOCK.fullmatch(start):
        raise ValueError("Planned show start must be HH:MM")
    if type(break_minutes) is not int or not 0 <= break_minutes <= 120:
        raise ValueError("Initial planned changeover break must be 0–120 minutes")
    sources = _sources(source_pairs)
    output = _private_html_destination(new_private_html)
    if any(output.is_relative_to(Path(path).absolute().parent) or
           output.is_relative_to(Path(path).absolute())
           for path in source_pairs):
        raise ValueError("Keep a standalone private show page outside the original WAV/session folders")
    data = {"sets": sources, "default_start": start, "default_break": break_minutes}
    if saved_plan is not None:
        # Import lazily: the canonical actual-WAV renderer uses _sources from
        # this module. The operator plan shares its precise source identity.
        from .show_master import _plan
        approved = _plan(sources, saved_plan)
        data["default_start"] = approved["start_local"]
        data["saved_breaks"] = approved["break_minutes"]
        data["saved_notes"] = approved["private_notes"]
    if rehearsal_selection is None and rehearsal_journals:
        raise ValueError("Rehearsal journals require an explicit human-selected take")
    if rehearsal_selection is not None:
        from .show_rehearsal_cuebook import load_selected
        chosen_sources, chosen_take, _ = load_selected(
            rehearsal_selection, tuple(source_pairs), tuple(rehearsal_journals))
        if [s["wav_sha256"] for s in chosen_sources] != [
                s["wav_sha256"] for s in sources]:
            raise ValueError("Human-selected rehearsal source WAVs differ")
        roots = (rehearsal_selection, *rehearsal_journals)
        if any(output.is_relative_to(Path(raw).absolute().parent) or
               output.is_relative_to(Path(raw).absolute()) for raw in roots):
            raise ValueError("Private show stage must be outside rehearsal source folders")
        data["selected_rehearsal"] = {
            "take": chosen_take["label"],
            "journal_sha256": chosen_take["journal_sha256"],
            "marks": chosen_take["marks"],
        }
    json_blob = json.dumps(data, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    json_blob = json_blob.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    page = _HTML.replace("__DATA__", json_blob).replace("__SHA_JS__", SHA256_BROWSER_JS).encode("utf-8")
    if not 0 < len(page) < MAX_PAGE:
        raise ValueError("Private offline show page is oversized")
    with output.open("xb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(page)
    return {"private_show_conductor": str(output), "completed_actual_sets": len(sources),
            "actual_total_wav_seconds": round(sum(s["duration_seconds"] for s in sources), 3),
            "source_sha256s": [s["wav_sha256"] for s in sources],
            "audio_embedded": False, "automatic_advance": False,
            "music_rights_proven": False}


def print_show(plan_path, new_private_html, *source_pairs,
               rehearsal_selection=None, rehearsal_journals=()):
    sources = _sources(source_pairs)
    plan = _read_plan(plan_path)
    if (not isinstance(plan, dict) or set(plan) !=
            {"schema_version", "kind", "source_sha256s", "start_local",
             "break_minutes", "private_notes", "private_only",
             "automatic_playback", "blind_study"} or
            type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or
            plan["kind"] != KIND or
            plan["source_sha256s"] != [s["wav_sha256"] for s in sources] or
            plan["private_only"] is not True or
            plan["automatic_playback"] is not False or
            plan["blind_study"] is not False or
            not isinstance(plan["start_local"], str) or not CLOCK.fullmatch(plan["start_local"])):
        raise ValueError("Operator show plan does not match all real SHA-verified sets")
    breaks, notes = plan["break_minutes"], plan["private_notes"]
    if (not isinstance(breaks, list) or len(breaks) != len(sources) or
            not isinstance(notes, list) or len(notes) != len(sources)):
        raise ValueError("Each real set requires one planned break and private note")
    for idx, (b, note) in enumerate(zip(breaks, notes)):
        if (type(b) is not int or not 0 <= b <= 120 or
                (idx == len(breaks)-1 and b != 0) or
                not isinstance(note, str) or len(note) > 300 or
                any(ord(c)<32 and c not in "\n\t" for c in note)):
            raise ValueError("Operator break or private note is invalid")
    out = _private_html_destination(new_private_html)
    if any(out.is_relative_to(Path(path).absolute().parent) or
           out.is_relative_to(Path(path).absolute()) for path in source_pairs):
        raise ValueError("Keep a printable private runbook outside the original music/session folders")
    if rehearsal_selection is None and rehearsal_journals:
        raise ValueError("Rehearsal journals require a selected human take")
    chosen = None
    if rehearsal_selection is not None:
        from .show_rehearsal_cuebook import load_selected
        chosen_sources, chosen, _ = load_selected(
            rehearsal_selection, tuple(source_pairs), tuple(rehearsal_journals))
        if [s["wav_sha256"] for s in chosen_sources] != [
                s["wav_sha256"] for s in sources]:
            raise ValueError("Selected rehearsal has mismatched source WAV identity")
        roots = (rehearsal_selection, *rehearsal_journals)
        if any(out.is_relative_to(Path(raw).absolute().parent) or
               out.is_relative_to(Path(raw).absolute()) for raw in roots):
            raise ValueError("Print private selected cues outside original source folders")
    minute = int(plan["start_local"][:2])*60+int(plan["start_local"][3:])
    fmt = lambda m: f"{int(m // 60)%24:02d}:{int(m%60):02d}"
    body = []
    for i, (src, b, note) in enumerate(zip(sources, breaks, notes)):
        begin = minute
        minute += src["duration_seconds"]/60
        chapters = "".join(
            "<li>"+html.escape(str(c["label"]),quote=True)+" · "+
            html.escape(str(c["kind"]))+" · "+f"{c['start_seconds']:.1f}s"+"</li>"
            for c in src["chapters"]
        )
        selected_cues = ""
        if chosen is not None:
            selected_rows = []
            for mark in sorted(
                (m for m in chosen["marks"] if m["set_index"] == i),
                key=lambda m: (m["position"], m["seq"]),
            ):
                nearest = ("No nearby original chapter"
                           if mark["chapter"] is None else
                           str(mark["chapter"]) + " · " + str(mark["chapter_kind"]) +
                           f" · {mark['chapter_delta']:+.2f}s")
                selected_rows.append(
                    "<li><strong>" + f"{mark['position']:.2f}s" + "</strong> · " +
                    html.escape(nearest, quote=True) + "<p class='note'>" +
                    html.escape(mark["note"] or "No private note", quote=True) + "</p></li>"
                )
            selected_cues = (
                "<h3>Human-selected rehearsal cues · " +
                html.escape(chosen["label"], quote=True) + "</h3><ol>" +
                ("".join(selected_rows) or "<li>No manually marked cues in this take.</li>") +
                "</ol>"
            )
        body.append(
            "<section><h2>"+str(i+1)+". "+html.escape(src["label"],quote=True)+
            "</h2><strong>"+fmt(begin)+"–"+fmt(minute)+"</strong>"+
            "<p>Actual WAV runtime "+f"{src['duration_seconds']:.1f} s"+"</p>"+
            "<small>Full WAV SHA-256: "+src["wav_sha256"]+"</small>"+
            "<p class='note'>"+html.escape(note or "No operator cue",quote=True)+"</p>"+
            "<ol>"+chapters+"</ol>"+selected_cues+
            "<p>Manual break after set: "+str(b)+" minutes</p></section>"
        )
        minute += b
    page = ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none';form-action 'none'">
<title>MixLab · Private printed show</title><style>body{font:15px/1.5 system-ui;max-width:960px;margin:auto;padding:35px;color:#192e37}
h1{font-size:40px}section{border-top:1px solid #9aa;padding:17px 0;break-inside:avoid}
small{display:block;overflow-wrap:anywhere;font:11px ui-monospace,monospace}
.note{white-space:pre-wrap;overflow-wrap:anywhere}
@media print{body{padding:0}}</style><h1>Your private actual-WAV show</h1>
<p>Manual planned times, not reliable physical event-clock or auto playback.
Source rights, music quality and room response are not certified.</p>"""
            + "".join(body) + "</html>").encode("utf-8")
    if not 0 < len(page) < MAX_REPORT:
        raise ValueError("Private printable show plan exceeds its size limit")
    with out.open("xb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(page)
    return {"private_printable_show": str(out), "exact_verified_wav_sets": len(sources),
            "private_operator_notes": True, "audio_embedded": False,
            "real_world_show_timing_proven": False}


def main():
    parser=argparse.ArgumentParser(
        description="Plan and manually run several already finished SHA-verified private MixLab WAV sets")
    sub=parser.add_subparsers(dest="action",required=True)
    prepare=sub.add_parser("prepare",help="Create a NEW local manual stage HTML without embedding any audio")
    prepare.add_argument("new_private_mixlab_html")
    prepare.add_argument("session_and_wav_pairs",nargs="+")
    prepare.add_argument("--start",default="19:00",help="Planned local HH:MM event start")
    prepare.add_argument("--break-minutes",type=int,default=10)
    resumed=sub.add_parser("resume",help="Reopen a previously saved private show in a new source-reverified manual stage")
    resumed.add_argument("previous_sha_bound_private_plan")
    resumed.add_argument("new_private_mixlab_html")
    resumed.add_argument("session_and_wav_pairs",nargs="+")
    for command in (prepare, resumed):
        command.add_argument("--rehearsal-selection",
                             help="Original human-selected private rehearsal JSON")
        command.add_argument("--journal", action="append", default=[],
                             help="Private original rehearsal journals (in comparison order)")
    printed=sub.add_parser("print",help="Print an exported source-bound operator schedule with private notes")
    printed.add_argument("exported_private_operator_plan")
    printed.add_argument("new_private_mixlab_report_html")
    printed.add_argument("session_and_wav_pairs",nargs="+")
    printed.add_argument("--rehearsal-selection",
                         help="Previously human-selected private rehearsal JSON")
    printed.add_argument("--journal", action="append", default=[],
                         help="Original private journals in comparison order")
    args=parser.parse_args()
    try:
        if args.action=="prepare":
            result=prepare_show(args.new_private_mixlab_html,*args.session_and_wav_pairs,
                                start=args.start,break_minutes=args.break_minutes,
                                rehearsal_selection=args.rehearsal_selection,
                                rehearsal_journals=tuple(args.journal))
        elif args.action=="resume":
            result=prepare_show(args.new_private_mixlab_html,*args.session_and_wav_pairs,
                                saved_plan=args.previous_sha_bound_private_plan,
                                rehearsal_selection=args.rehearsal_selection,
                                rehearsal_journals=tuple(args.journal))
            result["saved_source_bound_operator_choices_restored"]=True
        else:
            result=print_show(args.exported_private_operator_plan,
                              args.new_private_mixlab_report_html,*args.session_and_wav_pairs,
                              rehearsal_selection=args.rehearsal_selection,
                              rehearsal_journals=tuple(args.journal))
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, wave.Error):
        parser.exit(2,"MixLab Show Conductor: existing verified private WAVs, output, or operator schedule invalid.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
