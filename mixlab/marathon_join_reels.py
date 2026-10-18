"""Produce short, genuine PCM16 A/B handoff excerpts from two approved Marathons.

This is not a blind-study/evaluation tool. Only manually approved, already
rendered, SHA-receipt-verified local media can enter private output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import wave

from .event_marathon import BLOCK_FRAMES, _meta_key, _new_folder
from .marathon_master_review import _pair

BEFORE_SECONDS = 8
AFTER_SECONDS = 8
MAX_PRIVATE_REELS = 192 * 1024 * 1024
MAX_PAGE = 512 * 1024
KIND = "mixlab-private-real-marathon-join-reels-v1"

_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self' file:; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / Actual Audio Handoffs</title><style>
:root{color-scheme:dark;--bg:#0c1420;--card:#1c3040;--line:#4d7380;--mint:#a2ffcd;--pale:#c1d4df}
*{box-sizing:border-box}body{background:radial-gradient(at 80% 0,#1b5349,var(--bg) 65%);color:white;font:15px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1120px;margin:auto;padding:clamp(16px,5vw,64px)}
h1{font-size:clamp(38px,7vw,80px);letter-spacing:-.065em;line-height:1.04;margin:12px 0}
h2{font-size:23px;margin:0 0 10px}.eyebrow{font-size:12px;letter-spacing:.17em;color:var(--mint);font-weight:900}
p,small{color:var(--pale)}.panel{border:1px solid var(--line);border-radius:20px;padding:23px;background:var(--card);margin:22px 0}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}button{font:inherit;font-weight:850;cursor:pointer;color:white;border:1px solid #7399a5;border-radius:11px;background:#2b5967;padding:12px 16px}
button:hover,button[aria-pressed=true]{background:#2d785c}button:focus-visible,textarea:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
audio{width:100%;margin:16px 0}.counts{display:flex;gap:10px;flex-wrap:wrap}.counts span{border:1px solid var(--line);border-radius:11px;padding:9px 14px;color:var(--mint);font-weight:850}
ul{list-style:none;margin:0;padding:0;display:grid;gap:10px}li{display:flex;gap:15px;flex-wrap:wrap;align-items:center;border:1px solid #52707a;border-radius:11px;padding:13px}
li[data-current=true]{border-color:var(--mint);background:#19483c}
li strong{flex:1;min-width:210px;overflow-wrap:anywhere}
li small{font-size:12px}.note{width:100%;min-height:60px;background:#0c202f;color:white;font:inherit;border:1px solid var(--line);padding:12px;border-radius:10px;resize:vertical}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
@media(max-width:650px){li button{flex:1}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / PRIVATE REAL-WAV TRANSITION AUDITION</div>
<h1>Hear the handoff.<br>Not the whole night.</h1>
<p>Short, exact samples copied from your two real, already finished PCM16
Marathon masters. Use them to choose your own set, not to claim blind
human preference or public music rights. Every WAV remains on this device.</p>
<div class="counts"><span id="counter"></span><span id="runtime"></span><span>2 real PCM16 recordings per boundary</span></div>
<section class="panel"><h2 id="playing-title">Choose a handoff</h2>
<audio id="audio" controls preload="none"></audio>
<p id="status" role="status">Only actual master frames, copied without resampling, synthesis or any browser-created transition.</p>
<div class="controls"><button id="prev" type="button">← Previous join</button>
<button id="original" type="button">1 · Original hard join</button>
<button id="blend" type="button">2 · Real crossfade</button>
<button id="next" type="button">Next join →</button></div>
<p>Keyboard: <strong>1</strong> original, <strong>2</strong> blended,
<strong>← / →</strong> adjacent join (outside notes), <strong>space</strong>
play/pause. A and B are openly labelled, so this is NOT a blinded benchmark.</p></section>
<section class="panel"><h2>Original sources, paired by actual event boundary</h2>
<ul id="joins"></ul></section>
<section class="panel"><h2>Private DJ handoff notes</h2><p>Notes stay in this open page until
you explicitly export them. There is no persistent storage or network access.</p>
<textarea class="note" maxlength="300" id="note" aria-label="Current handoff operator note" placeholder="Personal energy, mix feel, equipment cue…"></textarea>
<div class="controls"><button type="button" id="export">Export private rehearsal notes</button></div>
<p class="hash" id="hashes"></p></section></main>
<script id="join-data" type="application/json">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("join-data").textContent);
const $=key=>document.getElementById(key),audio=$("audio");
const notes=new Array(data.joins.length).fill("");
let current=0,version="original";
$("counter").textContent=data.joins.length+" actual handoffs";
$("runtime").textContent="up to "+data.window_seconds+"s per clip";
$("hashes").textContent="Exact full original source WAV SHA-256: "+data.original_sha256+
 " / real blended source SHA-256: "+data.blend_sha256;
const label=(i)=>data.joins[i].from+" → "+data.joins[i].to;
function setPosition(pos,which,autoplay=true){
 if(pos<0||pos>=data.joins.length||!["original","blend"].includes(which))return;
 notes[current]=$("note").value;current=pos;version=which;
 $("note").value=notes[current];
 const join=data.joins[current];
 $("playing-title").textContent="Join "+(current+1)+" / "+label(current);
 $("original").setAttribute("aria-pressed",which==="original"?"true":"false");
 $("blend").setAttribute("aria-pressed",which==="blend"?"true":"false");
 $("prev").disabled=current===0;$("next").disabled=current===data.joins.length-1;
 document.querySelectorAll("#joins li").forEach((row,index)=>{
  row.dataset.current=index===current?"true":"false";
 });
 audio.pause();audio.src="./"+encodeURIComponent(join[which].filename);audio.load();
 $("status").textContent="Actual "+which+" source master: "+
  join[which].source_position_seconds.toFixed(2)+"s reference boundary; "+
  join.fade_seconds+"s selected real crossfade. Audio is NOT a browser approximation.";
 if(autoplay){
  const attempt=audio.play();
  if(attempt)attempt.catch(()=>{
   $("status").textContent="Browser blocked automatic playback; press Play in the audio player.";
  });
 }
}
const items=$("joins");
data.joins.forEach((join,index)=>{
 const row=document.createElement("li"),name=document.createElement("strong");
 name.textContent=(index+1)+". "+label(index);
 const meta=document.createElement("small");
 meta.textContent=join.fade_seconds+"s real fade · "+
   join.original.duration_seconds.toFixed(1)+"s excerpts";
 row.append(name,meta);
 for(const option of ["original","blend"]){
  const btn=document.createElement("button");btn.type="button";
  btn.textContent=option==="original"?"Hear original":"Hear actual blend";
  btn.setAttribute("aria-label",(index+1)+" "+option+" "+label(index));
  btn.addEventListener("click",()=>setPosition(index,option));row.append(btn);
 }
 items.append(row);
});
$("prev").addEventListener("click",()=>setPosition(current-1,version));
$("next").addEventListener("click",()=>setPosition(current+1,version));
$("original").addEventListener("click",()=>setPosition(current,"original"));
$("blend").addEventListener("click",()=>setPosition(current,"blend"));
$("note").addEventListener("input",()=>{notes[current]=$("note").value;});
document.addEventListener("keydown",event=>{
 const target=event.target;
 if(target&&(target.tagName==="INPUT"||target.tagName==="TEXTAREA"||
             target.tagName==="BUTTON"||target.tagName==="SELECT"))return;
 if(event.key==="1"){event.preventDefault();setPosition(current,"original");}
 else if(event.key==="2"){event.preventDefault();setPosition(current,"blend");}
 else if(event.key==="ArrowLeft"){event.preventDefault();setPosition(current-1,version);}
 else if(event.key==="ArrowRight"){event.preventDefault();setPosition(current+1,version);}
 else if(event.code==="Space"){event.preventDefault();audio.paused?audio.play().catch(()=>{}):audio.pause();}
});
$("export").addEventListener("click",()=>{
 notes[current]=$("note").value;
 const obj={schema_version:1,kind:"mixlab-private-marathon-join-rehearsal-v1",
   original_sha256:data.original_sha256,blend_sha256:data.blend_sha256,
   per_join_operator_notes:notes,private_local_use_only:true,blind_study:false};
 const file=new Blob([JSON.stringify(obj,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(file),link=document.createElement("a");
 link.href=url;link.download="mixlab-marathon-join-rehearsal.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("status").textContent="Private operator notes downloaded. No music or WAV bytes were exported.";
});
setPosition(0,"original",false);
</script></body></html>"""


def _clip(reader_path, target, *, start_frame, frames, expected_rate):
    """Copy real stereo PCM16 frames without allocating an entire WAV in RAM."""
    src = Path(reader_path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(src, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Actual master is no longer a regular file")
        with wave.open(source, "rb") as reader:
            if (reader.getframerate() != expected_rate or reader.getnchannels() != 2 or
                    reader.getsampwidth() != 2 or reader.getcomptype() != "NONE" or
                    frames <= 0 or start_frame < 0 or
                    start_frame + frames > reader.getnframes()):
                raise ValueError("Actual master is incompatible with requested handoff frames")
            with target.open("xb") as sink:
                os.fchmod(sink.fileno(), 0o600)
                with wave.open(sink, "wb") as writer:
                    writer.setnchannels(2)
                    writer.setsampwidth(2)
                    writer.setframerate(expected_rate)
                    writer.setnframes(frames)
                    reader.setpos(start_frame)
                    remaining=frames
                    while remaining:
                        n=min(remaining, BLOCK_FRAMES)
                        payload=reader.readframes(n)
                        if len(payload)!=n*4:
                            raise ValueError("Actual master was shortened while excerpting")
                        writer.writeframesraw(payload)
                        remaining-=n
        if _meta_key(before)!=_meta_key(os.fstat(source.fileno())):
            raise ValueError("Original approved PCM16 master changed while excerpting")


def create_join_reels(original_wav, blend_wav, new_private_folder, *, read=input, write=print):
    """Render a private actual-WAV join reel room from two already-approved masters."""
    (original, blend), (receipt0, receipt1), fades, durations = _pair(original_wav,blend_wav)
    rate=receipt0["rate"]
    folder=_new_folder(new_private_folder,[original.parent,blend.parent])
    joins=[]
    proposed=0
    for idx in range(1,len(receipt0["sections"])):
        from_row=receipt0["sections"][idx-1]
        original_row=receipt0["sections"][idx]
        blend_row=receipt1["sections"][idx]
        fade=fades[idx-1]
        pair={
            "from":from_row["label"],"to":original_row["label"],
            "fade_seconds":fade
        }
        for which,reader,row,receipt in (
                ("original",original,original_row,receipt0),
                ("blend",blend,blend_row,receipt1)):
            boundary=row["start_frame"]
            lead=min(BEFORE_SECONDS*rate,boundary)
            tail=min((fade+AFTER_SECONDS)*rate,receipt["frames"]-boundary)
            start=boundary-lead
            frames=lead+tail
            if frames <= 0:
                raise ValueError("Real source transition has no audible frames")
            filename=f"join-{idx:02d}-{which}.wav"
            pair[which]={
                "filename":filename,"start_frame":start,"frames":frames,
                "source_position_seconds":boundary/rate,
                "duration_seconds":frames/rate
            }
            proposed+=frames*4+64
        joins.append(pair)
    if not 0 < proposed <= MAX_PRIVATE_REELS:
        raise ValueError("Real private join reel package exceeds 192 MiB")
    write("MixLab personal handoff listening package: two already-produced local WAVs.")
    write("Original WAV SHA-256: "+receipt0["wav_sha256"])
    write("Blended WAV SHA-256: "+receipt1["wav_sha256"])
    write(f"{len(joins)} real joins, 2 PCM excerpts each; up to 8s before and fade+8s after each actual boundary.")
    write("Private local use only. This is NOT blind preference evidence, a model, or music rights.")
    if read("Type yes to create separate bounded private handoff WAVs: ").strip()!="yes":
        raise ValueError("Private short-audio production was not explicitly approved")
    folder.mkdir(mode=0o700)
    published=False
    created=[]
    try:
        for row in joins:
            for name,path in (("original",original),("blend",blend)):
                meta=row[name]
                dest=folder/meta["filename"]
                created.append(dest)
                _clip(path,dest,start_frame=meta["start_frame"],frames=meta["frames"],expected_rate=rate)
                h=hashlib.sha256()
                with dest.open("rb") as handle:
                    for block in iter(lambda:handle.read(65536),b""):
                        h.update(block)
                meta["wav_sha256"]=h.hexdigest()
        # Detect post-approval replacement of either source after copying.
        (_, _), (new0,new1), _, _ = _pair(original,blend)
        if (new0["wav_sha256"]!=receipt0["wav_sha256"] or
                new1["wav_sha256"]!=receipt1["wav_sha256"]):
            raise ValueError("The source Marathon changed before local snippets were finished")
        data={"schema_version":1,"kind":KIND,"original_sha256":receipt0["wav_sha256"],
              "blend_sha256":receipt1["wav_sha256"],"rate":rate,
              "window_seconds":BEFORE_SECONDS+max(fades)+AFTER_SECONDS,
              "joins":joins,"private_only":True,"source_media_embedded":False,
              "blind_study":False}
        blob=json.dumps(data,ensure_ascii=True,separators=(",",":"),allow_nan=False)
        blob=blob.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
        page=_PAGE.replace("__DATA__",blob).encode("utf-8")
        if len(page)>MAX_PAGE:
            raise ValueError("The actual-WAV listening studio is too large")
        html_path=folder/"index.html"
        created.append(html_path)
        with html_path.open("xb") as out:
            os.fchmod(out.fileno(),0o600)
            out.write(page)
        manifest=folder/"join-reels.receipt.private.json"
        created.append(manifest)
        with manifest.open("xb") as out:
            os.fchmod(out.fileno(),0o600)
            out.write((json.dumps(data,sort_keys=True,indent=2,allow_nan=False)+"\n").encode("utf-8"))
        published=True
    finally:
        if not published:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            folder.rmdir()
    return {"private_join_reels":str(folder),"offline_player":str(html_path),
            "private_receipt":str(manifest),"real_pcm_snippets":len(joins)*2,
            "original_wav_sha256":receipt0["wav_sha256"],
            "blended_wav_sha256":receipt1["wav_sha256"],
            "private":True,"music_licensing_proven":False,"blind_preference_proven":False}


def main():
    parser=argparse.ArgumentParser(
        description="Copy short actual WAV handoff clips from two already approved private Marathons for offline A/B audition")
    parser.add_argument("original_marathon_wav")
    parser.add_argument("blended_marathon_wav")
    parser.add_argument("new_private_folder")
    args=parser.parse_args()
    try:
        result=create_join_reels(args.original_marathon_wav,args.blended_marathon_wav,
                                 args.new_private_folder)
    except (ValueError,TypeError,KeyError,OSError,EOFError,KeyboardInterrupt,wave.Error):
        parser.exit(2,"MixLab actual join reels: private source approval, exact WAV receipts or new destination unavailable.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
