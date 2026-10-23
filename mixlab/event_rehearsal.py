"""Offline rehearsal desk for an already rendered, receipt-verified MixLab set.

This is a local private practice player, not a live mixer or audio analysis.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .set_player import build_chapters

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; media-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / Rehearsal Desk</title>
<style>
:root{color-scheme:dark;--bg:#0b111c;--panel:#162437;--border:#344c65;--fg:#eef6ff;--dim:#adbed2;--a:#94f4c5}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 20% 0%,#1e4347,var(--bg) 65%);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1370px;margin:auto;padding:clamp(16px,3vw,44px)}
h1{font-size:clamp(32px,5vw,64px);line-height:1.05;letter-spacing:-.055em;margin:8px 0}
h2{font-size:21px;margin:0 0 12px}.muted{color:var(--dim)}.eyebrow{font-size:11px;color:var(--a);letter-spacing:.2em;font-weight:800}
.layout{display:grid;grid-template-columns:minmax(270px,1fr) minmax(360px,1.65fr);gap:20px;margin:24px 0}
.panel{border:1px solid var(--border);border-radius:22px;background:var(--panel);padding:22px;min-width:0}
ol{list-style:none;padding:0;margin:0;max-height:600px;overflow-y:auto}li{margin:0 0 7px}
button{font:inherit;font-weight:750;border-radius:10px;padding:10px 14px;background:#29455d;color:var(--fg);border:1px solid #567089;cursor:pointer}
button:hover{background:#35637a}button:focus-visible,textarea:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--a);outline-offset:2px}
button:disabled{opacity:.5;cursor:not-allowed}.chapter{width:100%;text-align:left;display:flex;align-items:center;gap:12px;font-weight:650}
.chapter[aria-current=true]{border-color:var(--a);background:#235047}.chapter small{margin-left:auto;font-size:12px;color:#bed0db}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}.primary{background:var(--a);color:#10291e;border-color:transparent}
audio{width:100%;margin:10px 0}
.timer{font-variant-numeric:tabular-nums;font-size:clamp(28px,5vw,53px);font-weight:850;letter-spacing:-.045em}
label{display:block;font-weight:700;font-size:13px;margin:12px 0 6px}
select,textarea{font:inherit;background:#0e1c2b;border:1px solid #6b8195;border-radius:10px;color:var(--fg);padding:10px;width:100%}
textarea{resize:vertical;min-height:130px}input[type=file]{max-width:100%}
.details{border-left:4px solid var(--a);padding-left:16px;margin-top:18px}.hash{font-size:11px;overflow-wrap:anywhere;color:var(--dim);font-family:ui-monospace,monospace}
.status{font-size:13px;color:#bfffe0;min-height:20px}kbd{border:1px solid #627b93;border-radius:5px;padding:2px 5px}
@media(max-width:780px){.layout{grid-template-columns:1fr}.panel{padding:16px}ol{max-height:310px}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / PRIVATE OFFLINE PRACTICE</div>
<h1>Rehearsal Desk.</h1>
<p class="muted">Rehearse the <strong>actual rendered set</strong>, jump to verified chapters and loop around a transition. This is one WAV playback stream, not two-deck mixing or an automatic beat match.</p>
<div class="layout">
<section class="panel"><h2>Verified set chapters</h2>
<p class="muted">Choose a passage or transition to practice. Chapter timestamps come from the original full-set WAV receipt.</p>
<ol id="chapters" aria-label="Rendered set chapters"></ol></section>
<section class="panel">
<h2 id="selected">Select a chapter</h2>
<div class="timer" id="timer">00:00 / 00:00</div>
<audio id="audio" controls preload="metadata"></audio>
<div class="controls">
<button class="primary" id="play" type="button">Play / pause</button>
<button id="previous" type="button">Previous chapter</button>
<button id="next" type="button">Next chapter</button>
</div>
<div class="details">
<label for="before">Listen before chapter</label>
<select id="before"><option value="4">4 seconds</option><option value="8" selected>8 seconds</option><option value="16">16 seconds</option></select>
<label for="after">Listen after chapter</label>
<select id="after"><option value="4">4 seconds</option><option value="8" selected>8 seconds</option><option value="16">16 seconds</option></select>
<div class="controls"><button id="preview" type="button">Rehearse excerpt</button><button id="loop" type="button" aria-pressed="false">Loop excerpt: off</button></div>
<p id="range" class="muted">No excerpt selected.</p>
<p id="status" class="status" role="status" aria-live="polite"></p>
</div>
<label for="note">Private operator notes for this chapter</label>
<textarea id="note" maxlength="1000" placeholder="What should I listen for? What would I change next time?"></textarea>
<div class="controls">
<button id="save" type="button">Export all practice notes</button>
<label for="import" style="margin:0"><span>Import notes (.json)</span><input id="import" type="file" accept=".json,application/json"></label>
</div>
<p class="muted">Notes live in this page only until you export them; no uploads or browser storage. Imported notes must belong to this exact master WAV SHA-256.</p>
</section>
</div>
<p class="hash" id="hash"></p>
<p class="muted">Shortcuts: <kbd>Space</kbd> play/pause, <kbd>N</kbd> next, <kbd>P</kbd> previous, <kbd>L</kbd> toggle excerpt loop. Focus a text field to type normally. Your normal local player remains the event playback fallback. No live performance, human preference or source rights are certified by this page.</p>
</main>
<script id="mixlab-rehearsal-data" type="application/json">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-rehearsal-data").textContent);
const $=id=>document.getElementById(id), audio=$("audio"), chapters=data.chapters;
const notes=chapters.map(()=>"");
let current=0,loop=false,clip=null;
const fmt=seconds=>{
 const s=Math.max(0,Math.floor(Number(seconds)||0));
 return String(Math.floor(s/3600)).padStart(2,"0")+":"+
 String(Math.floor((s%3600)/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0");
};
const status=msg=>{$("status").textContent=msg};
function bounds(){
 const ch=chapters[current];
 const pre=Number($("before").value),post=Number($("after").value);
 // Track passages are long; preview only the first 20s, transition chapters
 // use their exact complete duration, bounded to 35s for operator ergonomics.
 const length=ch.kind==="transition"?Math.min(35,ch.duration_seconds):Math.min(20,ch.duration_seconds);
 return [Math.max(0,ch.start_seconds-pre),
         Math.min(data.duration_seconds,ch.start_seconds+Math.max(1,length)+post)];
}
function mark(){
 document.querySelectorAll(".chapter").forEach((b,i)=>{
  b.setAttribute("aria-current",String(i===current));
 });
 $("selected").textContent=(chapters[current].kind==="transition"?"Transition: ":"Track: ")+chapters[current].label;
 $("note").value=notes[current];
}
function choose(i){
 notes[current]=$("note").value;
 current=(i+chapters.length)%chapters.length;
 clip=null;loop=false;toggleLabel();mark();
 audio.currentTime=chapters[current].start_seconds;
 $("range").textContent="Choose Rehearse excerpt to hear a short section.";
 status("Chapter selected. Play normally or rehearse the excerpt.");
}
function toggleLabel(){
 $("loop").setAttribute("aria-pressed",String(loop));
 $("loop").textContent="Loop excerpt: "+(loop?"on":"off");
}
function preview(){
 clip=bounds();
 if(!(clip[1]>clip[0])){status("Cannot rehearse an empty chapter.");return}
 audio.currentTime=clip[0];
 $("range").textContent="Excerpt "+fmt(clip[0])+" – "+fmt(clip[1]);
 const promise=audio.play();if(promise)promise.catch(()=>status("Browser audio unavailable. Open the WAV in a local player."));
}
function changeLoop(){loop=!loop;toggleLabel();if(loop&&!clip)preview()}
function tick(){
 $("timer").textContent=fmt(audio.currentTime)+" / "+fmt(data.duration_seconds);
 if(!clip||audio.paused)return;
 if(audio.currentTime>=clip[1]-0.09){
  if(loop){audio.currentTime=clip[0];}else{audio.pause();clip=null;status("Excerpt finished. Select Rehearse excerpt to repeat.");}
 }
}
const list=$("chapters");
chapters.forEach((ch,i)=>{
 const li=document.createElement("li"),b=document.createElement("button"),time=document.createElement("small");
 b.type="button";b.className="chapter";
 b.textContent=String(i+1)+". "+(ch.kind==="transition"?"↝ ":"♫ ")+ch.label+" ";
 time.textContent=fmt(ch.start_seconds);b.append(time);
 b.addEventListener("click",()=>choose(i));li.append(b);list.append(li);
});
audio.src="./"+encodeURIComponent(data.wav_name);
audio.addEventListener("timeupdate",tick);
audio.addEventListener("error",()=>status("This browser cannot decode the local WAV. Use the original private player or another offline audio application."));
$("play").addEventListener("click",()=>{
 if(audio.paused){const p=audio.play();if(p)p.catch(()=>status("Browser refused playback; use the WAV in a local audio player."));}
 else audio.pause();
});
$("previous").addEventListener("click",()=>choose(current-1));
$("next").addEventListener("click",()=>choose(current+1));
$("preview").addEventListener("click",preview);
$("loop").addEventListener("click",changeLoop);
$("before").addEventListener("change",()=>{if(clip)clip=bounds()});
$("after").addEventListener("change",()=>{if(clip)clip=bounds()});
$("note").addEventListener("input",()=>{notes[current]=$("note").value});
document.addEventListener("keydown",e=>{
 if(e.ctrlKey||e.metaKey||e.altKey||e.repeat||/^(TEXTAREA|INPUT|SELECT|BUTTON)$/.test(document.activeElement.tagName))return;
 const key=e.key.toLowerCase();
 if(key===" "){e.preventDefault();$("play").click();}
 else if(key==="n")$("next").click();
 else if(key==="p")$("previous").click();
 else if(key==="l")$("loop").click();
});
$("save").addEventListener("click",()=>{
 notes[current]=$("note").value;
 const result={schema_version:1,kind:"mixlab-private-rehearsal-notes",
 wav_sha256:data.wav_sha256,chapter_count:chapters.length,notes:notes};
 const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"}));
 const a=document.createElement("a");a.href=url;a.download="mixlab-rehearsal.private.json";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 status("Local notes exported. Store them privately beside your event files.");
});
$("import").addEventListener("change",async e=>{
 const file=e.target.files&&e.target.files[0];e.target.value="";
 if(!file)return;
 if(file.size>131072){status("Import refused: notes file is too large.");return}
 try{
  const parsed=JSON.parse(await file.text());
  if(!parsed||parsed.kind!=="mixlab-private-rehearsal-notes"||parsed.schema_version!==1||
     parsed.wav_sha256!==data.wav_sha256||parsed.chapter_count!==chapters.length||
     !Array.isArray(parsed.notes)||parsed.notes.length!==chapters.length||
     parsed.notes.some(x=>typeof x!=="string"||x.length>1000)){
    throw new Error("notes do not match this exact master WAV");
  }
  parsed.notes.forEach((note,i)=>{notes[i]=note});
  $("note").value=notes[current];status("Notes restored for this exact WAV.");
 }catch(_){status("Notes import refused: invalid format or different WAV SHA.");}
});
$("hash").textContent="Receipt-verified WAV SHA-256: "+data.wav_sha256;
$("timer").textContent="00:00 / "+fmt(data.duration_seconds);
mark();
</script></body></html>"""


def create_rehearsal(private_session, complete_wav, new_html):
    """Publish a NEW offline rehearsal interface from the verified real WAV."""
    wav = Path(complete_wav).absolute()
    target = Path(new_html).absolute()
    if (target.parent != wav.parent or target.suffix.lower() != ".html" or
            target.exists() or target.is_symlink()):
        raise ValueError("Choose a NEW private rehearsal HTML beside the WAV")
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or (ancestor / ".git").exists():
            raise ValueError("Private rehearsal page must stay outside Git and symlink folders")
    # No unverified audio or speculative chapter positions admitted.
    data = build_chapters(private_session, wav)
    if not data["chapters"]:
        raise ValueError("Only a real completed chaptered set can be rehearsed")
    payload = {
        "schema_version": 1,
        "kind": "mixlab-private-event-rehearsal",
        "wav_name": data["wav_name"],
        "wav_sha256": data["wav_sha256"],
        "duration_seconds": data["duration_seconds"],
        "chapters": data["chapters"],
    }
    serialized = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _PAGE.replace("__DATA__", serialized).encode("utf-8")
    if len(page) > 512 * 1024:
        raise ValueError("Private rehearsal HTML exceeds 512 KiB")
    with target.open("xb") as result:
        os.fchmod(result.fileno(), 0o600)
        result.write(page)
    return target


def main():
    parser = argparse.ArgumentParser(
        description="Build an offline chapter/transition rehearsal desk from a real verified MixLab WAV")
    parser.add_argument("private_session")
    parser.add_argument("complete_wav")
    parser.add_argument("new_rehearsal_html")
    args = parser.parse_args()
    try:
        target = create_rehearsal(args.private_session,args.complete_wav,args.new_rehearsal_html)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, "MixLab rehearsal: "+str(exc)+"\n")
    print(json.dumps({"private_rehearsal":str(target),"offline":True,
                      "real_wav_receipt_required":True,"live_mixing":False,
                      "human_preference_proven":False}))


if __name__ == "__main__":
    main()
