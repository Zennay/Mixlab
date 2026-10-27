"""Hash-bound local playback and chapter navigation for complete MixLab WAV sets.

This is a private creative player, not a blind study or automatic musical
analysis. All chapter boundaries come from the exact canonical export plan.
"""
from __future__ import annotations

import argparse
from array import array
import json
import math
import os
from pathlib import Path
import stat
import sys
import wave

from .ingest import digest
from .set_composer import _parse_json, _secure_file, _session_catalog
from .set_export import MAX_PAIRS, MAX_SET_BYTES, _admit, _unique_pairs
from .cueprep import _read_spec

PAGE = """<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>MixLab / Full Set Player</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#f7f7fb;background:#0d0e15}
*{box-sizing:border-box}body{margin:0}main{max-width:1050px;margin:auto;padding:50px 20px 90px}
h1{font-size:clamp(3rem,7vw,5.6rem);letter-spacing:-.065em;margin:10px 0 25px}
h2{font-size:1.25rem}p{line-height:1.6}
.eyebrow{color:#c2afff;text-transform:uppercase;letter-spacing:.16em;font-size:.7rem;font-weight:800}
.muted{color:#a9b0c3}.hero,.section{border:1px solid #363a51;background:#1e2130;padding:25px;border-radius:20px;margin:20px 0}
audio{width:100%;margin:18px 0}.wave-wrap{border:1px solid #3e415b;border-radius:11px;overflow:hidden;background:#141628}
canvas{display:block;width:100%;height:110px;cursor:crosshair}
canvas:focus-visible{outline:3px solid #cdbbff;outline-offset:-3px}
button{border:1px solid #8e83c0;background:#38355d;color:#fff;
font:inherit;padding:12px 16px;border-radius:12px;cursor:pointer}
button:focus-visible{outline:3px solid #ccbcff;outline-offset:2px}button:hover{background:#4d477a}
.controls{display:flex;gap:9px;flex-wrap:wrap}.controls button{flex:1}
#chapters{list-style:none;padding:0;margin:0}#chapters li{display:grid;
grid-template-columns:105px 1fr auto;gap:18px;align-items:center;border-bottom:1px solid #33374b;padding:13px 0}
#chapters li span{overflow-wrap:anywhere}#event-title{overflow-wrap:anywhere}
.chapter-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.chapter-actions button{padding:10px 12px}
.chapter-actions button[aria-pressed=true]{background:#256153;border-color:#75e3bd}
#transition-audition-status{color:#bee6d8;min-height:1.5em}

#chapters li[aria-current=true]{background:#292641;border-radius:10px;padding-left:10px;padding-right:10px}
@media(max-width:600px){#chapters li{grid-template-columns:65px 1fr;gap:8px}
.chapter-actions{grid-column:1/3;justify-content:stretch}.chapter-actions button{flex:1}}
.time{font-variant-numeric:tabular-nums;color:#c6c2dc}small{color:#9faac2}
button:disabled{opacity:.42;cursor:not-allowed}
#event-board{display:none}
.event-mode .hero{position:fixed;inset:0;z-index:30;overflow-y:auto;margin:0;
  border:0;border-radius:0;padding:clamp(20px,4vw,60px);
  background:#080b15;color:#fff;display:flex;flex-direction:column;gap:16px}
.event-mode main>p,.event-mode main>h1,.event-mode main>section:not(.hero){display:none}
 .event-mode audio{display:none}
.event-mode #event-board{display:grid;grid-template-columns:1fr auto;gap:14px;
  border:1px solid #514d7b;background:#19192d;padding:22px;border-radius:18px}
.event-mode #event-title{font-size:clamp(1.5rem,3.8vw,3rem);font-weight:850}
.event-mode #event-countdown{font-size:clamp(2.3rem,7vw,5.5rem);
  font-weight:850;letter-spacing:-.06em;font-variant-numeric:tabular-nums}
.event-mode .wave-wrap{margin-top:auto}
.event-mode canvas{height:clamp(110px,22vh,240px)}
.event-mode .controls{display:none}
.event-mode #meta{display:none}
.event-mode #now{font-size:1.25rem;font-weight:700}
#event-controls{display:flex;flex-wrap:wrap;gap:12px;align-self:start}
#event-controls button{font-size:1.2rem;padding:15px 24px}
@media(max-width:650px){.event-mode #event-board{grid-template-columns:1fr}}

</style></head><body><main>
<p class="eyebrow">MIXLAB / COMPLETE PRIVÉ MIX</p><h1>Playthrough.</h1>
<p class="muted">Een volledige lokale mix met hoofdstukken voor iedere passage en overgang.
De cuepunten komen uit jouw handmatig goedgekeurde Studio-sessie.</p>
<section class="hero">
<h2>Luister de hele set</h2>
<button id="event-toggle" type="button" aria-pressed="false">⛶ Eventmodus</button>
<p class="muted">Eventmodus toont live het huidige fragment en telt af tot de volgende overgang.
Springknoppen, de golfvorm-seek en de normale audiobediening worden dan vergrendeld.
De pauzeknop blijft altijd beschikbaar.</p>
<div id="event-board" aria-live="polite">
 <div><small>NU OP DE SET</small><div id="event-title">Set gereed</div>
 <p id="event-next" class="muted">Volgende overgang</p></div>
 <div><small>TIJD TOT VOLGEND MOMENT</small><div id="event-countdown">00:00:00</div>
 <div id="event-controls"><button id="event-play" type="button">▶ Speel</button>
 <button id="event-exit" type="button">Verlaat eventmodus</button></div></div>
</div>
<audio id="player" controls preload="metadata"></audio>
<div class="wave-wrap"><canvas id="waveform" width="900" height="110" tabindex="0"
role="slider" aria-label="Waveform. Klik of gebruik pijltjes links/rechts om te navigeren"
aria-valuemin="0" aria-valuemax="0" aria-valuenow="0"></canvas></div>
<small>Gesamplede amplitudeweergave (geen nauwkeurige loudness-meting). Klik of gebruik ←/→ om te springen.</small>
<p id="now" aria-live="polite">Kies play om je set te luisteren.</p>
<div class="controls"><button id="prev">◀ Vorige passage</button><button id="next">Volgende passage ▶</button></div>
<p class="muted" id="meta"></p>
</section>
<section class="section"><h2>Interactieve tijdlijn</h2>
<p class="muted">Luister naar een overgang of herhaal precies dat fragment.
Herhalen stopt zodra je naar een ander hoofdstuk springt of de eventmodus opent.</p>
<p id="transition-audition-status" role="status" aria-live="polite">Geen overgang in herhaling.</p>
<ol id="chapters"></ol></section>
<section class="section"><h2>Neem je cuepunten mee</h2>
<p class="muted">Bewaar de hoofdstukken als JSON (inclusief SHA-binding) of als
standaard CUE-indeling voor lokale muziekspelers. Beide bestanden bevatten geen bronpaden.</p>
<div class="controls"><button id="download-json">Download hoofdstukken JSON</button>
<button id="download-cue">Download CUE</button></div></section>
<p class="muted">Geen upload, analytics, stream of externe libraries. Dit is een
creatieve afspeelpagina, geen onafhankelijke DJ-beoordeling of rechtenverklaring.</p>
</main><script type="application/json" id="mixlab-player-data">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-player-data").textContent);
const audio=document.getElementById("player");
const waveform=document.getElementById("waveform");
const eventToggle=document.getElementById("event-toggle");
const eventPlay=document.getElementById("event-play");
const eventExit=document.getElementById("event-exit");
let eventMode=false;
const chapterButtons=[];
const loopButtons=[];
let loopIndex=null;
const auditionStatus=document.getElementById("transition-audition-status");
audio.src="./"+encodeURIComponent(data.wav_name);
function drawWaveform(){
  const width=Math.max(1,Math.round(waveform.clientWidth*(window.devicePixelRatio||1)));
  const height=Math.max(1,Math.round(110*(window.devicePixelRatio||1)));
  if(waveform.width!==width||waveform.height!==height){
    waveform.width=width;waveform.height=height;
  }
  const ctx=waveform.getContext("2d");ctx.clearRect(0,0,width,height);
  const step=width/data.waveform.length;
  ctx.fillStyle="#ac9bff";
  data.waveform.forEach((level,i)=>{
    const bar=Math.max(1,Math.round(level*(height-16)));
    ctx.fillRect(i*step,(height-bar)/2,Math.max(1,step*.83),bar);
  });
  ctx.strokeStyle="#4acbdb";ctx.lineWidth=Math.max(1,window.devicePixelRatio||1);
  data.chapters.forEach(ch=>{
    const x=(ch.start_seconds/data.duration_seconds)*width;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();
  });
  ctx.fillStyle="#f8de96";
  ctx.fillRect((audio.currentTime/data.duration_seconds)*width,0,Math.max(2,window.devicePixelRatio||1),height);
}
waveform.addEventListener("click",e=>{
  if(eventMode)return;
  const box=waveform.getBoundingClientRect();
  if(box.width>0){clearTransitionLoop();
    audio.currentTime=Math.max(0,Math.min(data.duration_seconds,
      (e.clientX-box.left)/box.width*data.duration_seconds));}
});
waveform.addEventListener("keydown",e=>{
  if(eventMode)return;
  if(e.key!=="ArrowLeft" && e.key!=="ArrowRight")return;
  e.preventDefault();
  clearTransitionLoop();
  audio.currentTime=Math.max(0,Math.min(data.duration_seconds,
    (audio.currentTime||0)+(e.key==="ArrowRight"?5:-5)));
});
window.addEventListener("resize",drawWaveform);
const list=document.getElementById("chapters");
const now=document.getElementById("now");
document.getElementById("meta").textContent=
  data.duration_label+" · "+data.chapters.length+" hoofdstukken · WAV SHA-256 "+data.wav_sha256.slice(0,12)+"…";
const rows=[];
function format(t) {
  const n=Math.max(0,Math.floor(t));
  return String(Math.floor(n/3600)).padStart(2,"0")+":"+
    String(Math.floor(n%3600/60)).padStart(2,"0")+":"+
    String(n%60).padStart(2,"0");
}
function clearTransitionLoop(){
  loopIndex=null;
  loopButtons.forEach(({button,label})=>{
    button.setAttribute("aria-pressed","false");
    button.setAttribute("aria-label","Herhaal overgang: "+label);
    button.textContent="Herhaal overgang";
  });
  auditionStatus.textContent="Geen overgang in herhaling.";
}
function toggleTransitionLoop(i){
  if(eventMode)return; // a live set must never accidentally replay a section
  if(loopIndex===i){clearTransitionLoop();return;}
  const ch=data.chapters[i];
  if(ch.kind!=="transition" || !Number.isFinite(ch.start_seconds) ||
     !Number.isFinite(ch.duration_seconds) || ch.duration_seconds<=0)return;
  clearTransitionLoop();
  loopIndex=i;
  const label=ch.display_name||ch.label;
  loopButtons.forEach(({button,index})=>{
    if(index===i){button.setAttribute("aria-pressed","true");
      button.setAttribute("aria-label","Stop herhalen: "+label);
      button.textContent="Stop herhalen";}
  });
  auditionStatus.textContent="Herhaalt: "+label;
  audio.currentTime=ch.start_seconds;
  audio.play().catch(()=>{
    if(loopIndex===i){
      clearTransitionLoop();
      auditionStatus.textContent="Lokaal WAV-bestand kan niet worden afgespeeld.";
    }
  });
}
function jump(n){
  if(eventMode)return; // no accidental live-set seeks from chapter controls
  clearTransitionLoop();
  audio.currentTime=data.chapters[n].start_seconds;
  audio.play().catch(()=>{now.textContent="Lokaal WAV-bestand kan niet worden afgespeeld.";});
}
data.chapters.forEach((ch,i)=>{
  const li=document.createElement("li");
  const time=document.createElement("span");
  time.className="time";time.textContent=format(ch.start_seconds);
  const title=document.createElement("span");
  title.textContent=ch.kind==="transition"?
    "Overgang "+(ch.display_name||ch.label)+" · "+ch.family.replaceAll("_"," "):
    (ch.display_name||"Track "+ch.label);
  const actions=document.createElement("div");actions.className="chapter-actions";
  const button=document.createElement("button");button.textContent="Luister vanaf hier";
  button.addEventListener("click",()=>jump(i));chapterButtons.push(button);
  actions.append(button);
  if(ch.kind==="transition"){
    const loopButton=document.createElement("button");
    loopButton.textContent="Herhaal overgang";
    loopButton.setAttribute("aria-pressed","false");
    loopButton.setAttribute("aria-label","Herhaal overgang: "+(ch.display_name||ch.label));
    loopButton.addEventListener("click",()=>toggleTransitionLoop(i));
    actions.append(loopButton);loopButtons.push({button:loopButton,index:i,
      label:ch.display_name||ch.label});
  }
  li.append(time,title,actions);list.append(li);rows.push(li);
});
let current=0;
function highlight(){
  const t=Number.isFinite(audio.currentTime)?audio.currentTime:0;
  current=0; // Recompute when seeking backwards; never keep a later chapter stale.
  for(let i=0;i<data.chapters.length;i++){
    if(data.chapters[i].start_seconds<=t+0.01)current=i;
    else break;
  }
  rows.forEach((li,i)=>li.setAttribute("aria-current",String(i===current)));
  waveform.setAttribute("aria-valuenow",String(Math.floor(t)));
  drawWaveform();
  now.textContent="Nu: "+(data.chapters[current].display_name||data.chapters[current].label)+" ("+
    (data.chapters[current].kind==="transition"?"overgang":"track")+") · "+format(t);
  updateEventClock(t);
}
function enforceTransitionLoop(){
  if(loopIndex===null || eventMode)return;
  const chapter=data.chapters[loopIndex];
  const start=chapter.start_seconds;
  const end=Math.min(data.duration_seconds,start+chapter.duration_seconds);
  // Loop only the already rendered, SHA-bound transition WAV segment.
  // Browser timeupdate can be sparse, so seek when the segment is passed.
  if(audio.currentTime>=end-.012 && !audio.seeking){
    audio.currentTime=start;
    if(audio.paused)audio.play().catch(()=>{clearTransitionLoop();});
  }
}
audio.addEventListener("timeupdate",()=>{enforceTransitionLoop();highlight();});
audio.addEventListener("seeked",()=>{
  if(loopIndex!==null){
    const part=data.chapters[loopIndex];
    if(audio.currentTime<part.start_seconds-.03 ||
       audio.currentTime>part.start_seconds+part.duration_seconds+.03)
      clearTransitionLoop();
  }
  highlight();
});
audio.addEventListener("ended",()=>{
  if(loopIndex!==null && !eventMode){
    const part=data.chapters[loopIndex];
    audio.currentTime=part.start_seconds;
    audio.play().catch(()=>{clearTransitionLoop();});
  }
});
audio.addEventListener("play",()=>{eventPlay.textContent="❚❚ Pauzeer";});
audio.addEventListener("pause",()=>{eventPlay.textContent="▶ Hervat";});
function updateEventClock(t){
  const chapter=data.chapters[current];
  document.getElementById("event-title").textContent=
    (chapter.kind==="transition"?"Overgang ":"Track ")+
    (chapter.display_name||chapter.label);
  const upcoming=data.chapters.find(ch=>ch.kind==="transition" && ch.start_seconds>t+.05);
  const seconds=Math.max(0,(upcoming?upcoming.start_seconds:data.duration_seconds)-t);
  document.getElementById("event-countdown").textContent=format(seconds);
  document.getElementById("event-next").textContent=upcoming?
    "Volgende overgang: "+(upcoming.display_name||upcoming.label)+" over "+format(seconds):
    "Geen verdere overgang · resterend tot einde "+format(seconds);
}
function enterEventMode(active){
  if(active)clearTransitionLoop(); // entering live mode always cancels audition
  eventMode=active;
  document.body.classList.toggle("event-mode",active);
  audio.controls=!active;
  waveform.setAttribute("aria-disabled",String(active));
  waveform.tabIndex=active?-1:0;
  const disabled=Boolean(active);
  document.getElementById("prev").disabled=disabled;
  document.getElementById("next").disabled=disabled;
  chapterButtons.forEach(button=>{button.disabled=disabled;});
  loopButtons.forEach(({button})=>{button.disabled=disabled;});
  eventToggle.setAttribute("aria-pressed",String(active));
  eventToggle.textContent=active?"Verlaat eventmodus":"⛶ Eventmodus";
  if(active){
    if(document.documentElement.requestFullscreen){
      document.documentElement.requestFullscreen().catch(()=>{});
    }
  }else if(document.fullscreenElement && document.exitFullscreen){
    document.exitFullscreen().catch(()=>{});
  }
  highlight();
}
eventToggle.addEventListener("click",()=>enterEventMode(!eventMode));
eventExit.addEventListener("click",()=>enterEventMode(false));
eventPlay.addEventListener("click",()=>{
  if(audio.paused)audio.play().catch(()=>{
    document.getElementById("event-next").textContent=
      "Audio niet beschikbaar. Controleer of de originele WAV naast deze HTML staat.";
  });
  else audio.pause();
});
window.addEventListener("keydown",e=>{
  if(!eventMode || e.key.toLowerCase()!=="p" || e.altKey || e.ctrlKey || e.metaKey)return;
  if(e.target instanceof HTMLElement && ["BUTTON","INPUT","TEXTAREA"].includes(e.target.tagName))return;
  e.preventDefault();eventPlay.click();
});
document.getElementById("prev").addEventListener("click",()=>{
  if(audio.currentTime>data.chapters[current].start_seconds+3)jump(current);
  else jump(Math.max(0,current-1));
});
document.getElementById("next").addEventListener("click",()=>jump(Math.min(rows.length-1,current+1)));
function save(filename,contents,mime){
  const url=URL.createObjectURL(new Blob([contents],{type:mime}));
  const a=document.createElement("a");a.href=url;a.download=filename;
  document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.getElementById("download-json").addEventListener("click",()=>{
  save("mixlab-chapters.private.json",JSON.stringify({
    schema_version:1,kind:"mixlab-private-wav-chapters",
    wav_sha256:data.wav_sha256,duration_seconds:data.duration_seconds,
    chapters:data.chapters},null,2)+"\\n","application/json");
});
document.getElementById("download-cue").addEventListener("click",()=>{
  const escape=s=>s.replaceAll('"',"'").replaceAll("\\r"," ").replaceAll("\\n"," ");
  const lines=['REM COMMENT "MixLab private manual transition session"',
    'FILE "'+escape(data.wav_name)+'" WAVE'];
  data.chapters.forEach((ch,i)=>{
    const frames=Math.round(ch.start_seconds*75);
    const mm=Math.floor(frames/(75*60));
    const ss=Math.floor(frames/75)%60;
    const ff=frames%75;
    lines.push("  TRACK "+String(i+1).padStart(2,"0")+" AUDIO");
    lines.push('    TITLE "'+escape((ch.display_name||ch.label)+(ch.family?" - "+ch.family:""))+'"');
    lines.push("    INDEX 01 "+String(mm).padStart(2,"0")+":"+
      String(ss).padStart(2,"0")+":"+String(ff).padStart(2,"0"));
  });
  save("mixlab-full-set.cue",lines.join("\\r\\n")+"\\r\\n","text/plain");
});
waveform.setAttribute("aria-valuemax",String(Math.floor(data.duration_seconds)));
audio.addEventListener("loadedmetadata",drawWaveform);
highlight();
</script></body></html>"""


def _output_metadata(wav_path, receipt):
    if wav_path.is_symlink() or not wav_path.is_file():
        raise ValueError("The exported WAV is missing or redirected")
    entry = wav_path.lstat()
    if not stat.S_ISREG(entry.st_mode) or not 44 < entry.st_size <= MAX_SET_BYTES:
        raise ValueError("Invalid complete WAV size")
    if receipt.get("format") != "PCM16-WAV" or receipt.get("kind") != "private-continuous-manual-set":
        raise ValueError("Not a MixLab continuous WAV receipt")
    if not isinstance(receipt.get("output_sha256"), str) or digest(wav_path) != receipt["output_sha256"]:
        raise ValueError("Exported WAV hash differs from its private receipt")
    with wave.open(str(wav_path), "rb") as wav:
        ch, width, rate, frames, comp, _ = wav.getparams()
    if (width, comp) != (2, "NONE") or (ch, rate, frames) != (
            receipt.get("channels"), receipt.get("sample_rate"), receipt.get("frames")):
        raise ValueError("Actual WAV format or length differs from private receipt")
    if entry.st_size != 44 + frames * ch * 2:
        raise ValueError("Complete WAV has unexpected trailing/short PCM data")
    return rate, frames



def _sampled_envelope(wav_path, frames, channels):
    """Bounded, sparse, relative RMS preview. Not a loudness or quality metric.

    Read <= 640 * 4 * 256 frames independent of source duration, with at most
    one small PCM buffer in memory. True source/output integrity is checked
    separately by the full WAV SHA and immutable export receipt.
    """
    points = min(640, max(1, (frames + 1023) // 1024))
    window = min(256, frames)
    values = []
    with wave.open(str(wav_path), "rb") as source:
        for index in range(points):
            peak = 0.0
            for part in range(4):
                center = round(((index + (part + .5) / 4) / points) * frames)
                start = max(0, min(frames - window, center - window // 2))
                source.setpos(start)
                raw = source.readframes(window)
                if len(raw) != window * channels * 2:
                    raise ValueError("Sampled waveform encountered truncated PCM16")
                samples = array("h")
                samples.frombytes(raw)
                if sys.byteorder != "little":
                    samples.byteswap()
                power = sum((int(sample) / 32768.0) ** 2 for sample in samples) / len(samples)
                peak = max(peak, math.sqrt(power))
            values.append(peak)
    reference = max(.000001, max(values))
    return [round(min(1.0, value / reference), 3) for value in values]


def build_chapters(session_dir, wav_path):
    root, catalog = _session_catalog(session_dir)
    wav_path = Path(wav_path).absolute()
    if wav_path.resolve(strict=True).is_relative_to(root):
        raise ValueError("Complete set output must remain outside Studio session")
    for ancestor in (wav_path.parent, *wav_path.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Keep exported music outside Git")
    receipt_file = wav_path.with_name(wav_path.name + ".receipt.private.json")
    receipt = _parse_json(_secure_file(receipt_file, 65536))
    if not isinstance(receipt, dict) or receipt.get("source_session_sha256") != catalog["session_sha256"]:
        raise ValueError("Complete WAV receipt belongs to another private session")
    if receipt.get("studio_receipt_sha256") != catalog["studio_sha256"]:
        raise ValueError("Studio changed since the continuous set was rendered")
    rate, frames = _output_metadata(wav_path, receipt)
    chosen = receipt.get("selected_transitions")
    if not isinstance(chosen, list) or not 1 <= len(chosen) <= MAX_PAIRS:
        raise ValueError("Invalid selected transitions in WAV receipt")
    selections = []
    for item in chosen:
        if not isinstance(item, dict) or set(item) != {"pair", "family", "render_sha256"}:
            raise ValueError("Unexpected transition entry in set receipt")
        if not isinstance(item["pair"], str) or not isinstance(item["family"], str):
            raise ValueError("Invalid set transition ID or family")
        selections.append(item["pair"] + ":" + item["family"])
    _unique_pairs(selections)
    admitted = _admit(root, _unique_pairs(selections))
    if (admitted["rate"], admitted["channels"], admitted["frames"]) != (
            rate, receipt.get("channels"), frames):
        raise ValueError("Source session timeline differs from exported WAV")
    for chosen_entry, actual in zip(chosen, admitted["selected"]):
        if (chosen_entry["pair"], chosen_entry["family"], chosen_entry["render_sha256"]) != (
                actual["pair"], actual["family"], actual["render_sha256"]):
            raise ValueError("Transition WAV hash does not match selected full set")
    chapters = []
    cursor = 0
    selected = {item["pair"]: item for item in admitted["selected"]}
    for kind, identity, _start, part_frames in admitted["portions"]:
        if part_frames < 0:
            raise ValueError("Negative segment length in immutable source timeline")
        if part_frames:
            entry = {"kind": kind, "label": identity,
                     "start_seconds": round(cursor / rate, 6),
                     "duration_seconds": round(part_frames / rate, 6)}
            if kind == "transition":
                entry["family"] = selected[identity]["family"]
            chapters.append(entry)
        cursor += part_frames
    if cursor != frames or not chapters:
        raise ValueError("Complete set timeline differs from WAV duration")
    return {"schema_version": 1, "kind": "mixlab-private-wav-chapters",
            "wav_name": wav_path.name, "wav_sha256": receipt["output_sha256"],
            "duration_seconds": frames / rate, "duration_label": str(round(frames / rate / 60, 1)) + " minuten",
            "waveform_basis": "bounded sparse window RMS preview, normalized per output",
            "waveform": _sampled_envelope(wav_path, frames, receipt["channels"]),
            "chapters": chapters}


def publish_player(session_dir, complete_wav, *, display_names=None):
    wav_path = Path(complete_wav).absolute()
    metadata = build_chapters(session_dir, wav_path)
    if display_names is not None:
        if not isinstance(display_names, dict):
            raise ValueError("Private player labels must be an ID-to-name mapping")
        # Compare labels to the actual, already verified imported Studio
        # catalog (not only nonzero solo chapters; a zero-length solo is
        # possible between two valid human-specified transitions).
        normalized = _read_spec(Path(session_dir).absolute() / 'sources' / 'source_manifest.json')
        tracks = normalized.get('tracks')
        pairs = normalized.get('pairs')
        if not isinstance(tracks, list) or not isinstance(pairs, list):
            raise ValueError("Missing source-bound session labels")
        track_ids = [item.get('id') for item in tracks]
        by_pair = {item.get('id'): item for item in pairs}
        if (len(set(track_ids)) != len(tracks) or len(by_pair) != len(pairs) or
                set(display_names) != set(track_ids) or any(
                not isinstance(name, str) or not name or len(name) > 96 or
                any(ord(c) < 32 or ord(c) == 127 for c in name)
                for name in display_names.values())):
            raise ValueError("Private player names must match actual SHA-bound track IDs")
        for chapter in metadata['chapters']:
            if chapter['kind'] == 'solo':
                chapter['display_name'] = display_names[chapter['label']]
            elif chapter['kind'] == 'transition':
                pair = by_pair.get(chapter['label'])
                if not pair or pair.get('a') not in display_names or pair.get('b') not in display_names:
                    raise ValueError("Transition names are not tied to a verified source pair")
                chapter['display_name'] = (display_names[pair['a']] + ' → ' +
                                           display_names[pair['b']])
    # Names only enter this opt-in offline chapter page. They never change
    # the canonical WAV receipt, chapter times, or blind study artifacts.
    page = wav_path.with_name(wav_path.name + ".player.html")
    if page.exists() or page.is_symlink():
        raise ValueError("The offline player page already exists")
    raw = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    raw = raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    document = PAGE.replace("__DATA__", raw)
    with page.open("x", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(document)
    return page


def main():
    parser = argparse.ArgumentParser(description="Create a private offline full-set player with chapters")
    parser.add_argument("session", help="Original complete MixLab session directory")
    parser.add_argument("complete_wav", help="Already exported complete private WAV")
    args = parser.parse_args()
    try:
        result = publish_player(args.session, args.complete_wav)
    except (ValueError, OSError, TypeError, KeyError, wave.Error) as exc:
        parser.exit(2, "MixLab Set Player: " + str(exc) + "\n")
    print(json.dumps({"offline_player": str(result), "private": True,
                      "automatic_track_analysis": False, "musical_quality_claim": False}))


if __name__ == "__main__":
    main()
