"""Real WAV-only changed-join audition between adjacent private hybrid masters.

This compares source-verified completed PCM16 masters, never browser mixes or
fake sample-aligned transitions. No media is uploaded or auto-shared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import wave

from .event_marathon import _new_folder
from .event_vault import _marathon_duration, _read_small_json
from .marathon_operator_transfer import _validate
from .marathon_sequence import _read_plan
from .marathon_join_reels import _clip, MAX_PRIVATE_REELS

PAGE_KIND="mixlab-private-real-hybrid-revision-audition-v1"
PAGE_LIMIT=512*1024
BEFORE=8
AFTER=8

_PAGE=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';media-src 'self' file:;connect-src 'none';img-src 'none';object-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Actual Revised Transition Audition</title>
<style>:root{color-scheme:dark;--bg:#061824;--panel:#193545;--line:#527e89;--mint:#b1ffd9;--muted:#bbd5df}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 85% 0,#1a5b49,var(--bg) 70%);color:#f5ffff;font:15px/1.55 system-ui}
main{max-width:1050px;margin:auto;padding:clamp(18px,5vw,64px)}
h1{font-size:clamp(37px,7vw,76px);line-height:1.02;letter-spacing:-.05em}
p,small{color:var(--muted)}h2{font-size:23px}.tag{color:var(--mint);font-size:12px;letter-spacing:.14em;font-weight:900}
section{background:var(--panel);border:1px solid var(--line);border-radius:21px;padding:22px;margin:21px 0}
button{background:#29645b;border:1px solid #81a69e;color:white;padding:12px 16px;border-radius:10px;font:inherit;font-weight:850;cursor:pointer}
button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
button[aria-pressed=true]{background:#397d69}audio{width:100%;margin:12px 0}
ol{list-style:none;margin:0;padding:0;display:grid;gap:12px}
li{padding:15px;border:1px solid var(--line);border-radius:12px;background:#0d2734}
li.selected{border-color:var(--mint)}li strong{display:block}
.actions{display:flex;flex-wrap:wrap;gap:12px}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
@media print{button,audio{display:none!important}}</style></head><body><main>
<div class="tag">MIXLAB / TRUE WAV REVISION AUDITION · PRIVATE</div>
<h1>Hear what<br>really changed.</h1>
<p>Short stereo PCM16 excerpts copied without resampling from two
<em>already completed</em>, receipt-verified private hybrid masters:
your parent mix and newly approved revision. Only joins where the human
transition decision actually changed appear below. This is not blind
preference research, musical superiority or music-rights evidence.</p>
<section><h2 id="title">Choose a changed handoff</h2>
<audio id="player" controls preload="none"></audio>
<div class="actions"><button id="before" type="button">1 · Previous approved WAV</button>
<button id="after" type="button">2 · Newly rendered WAV</button>
<button id="prev" type="button">← Previous change</button><button id="next" type="button">Next change →</button></div>
<p id="status" role="status">Open one short genuine WAV excerpt at a time.
Keys 1 / 2 switch actual versions. Left / right switch changed join.</p></section>
<section><h2>Updated transition decisions</h2><ol id="joins"></ol></section>
<section><h2>Private operator context</h2>
<p>The clips were created from separately approved full WAVs and SHA-256
receipts. Listen to the full new master before an event. This local file
contains no audio bytes or paths embedded in the HTML. There is no network
connection, upload, account, browser storage or automatic feedback log.</p>
<p id="fingerprints" class="hash"></p></section></main>
<script type="application/json" id="mixlab-revision-data">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-revision-data").textContent);
const $=id=>document.getElementById(id),audio=$("player");
let current=0,side="after";
function listen(i,version,play=true){
 if(i<0||i>=data.changes.length||!["before","after"].includes(version))return;
 current=i;side=version;const join=data.changes[current];
 audio.pause();audio.src="./"+encodeURIComponent(join[version].filename);
 audio.load();
 $("title").textContent="Join "+join.index+" / "+join.from+" → "+join.to;
 $("before").setAttribute("aria-pressed",version==="before"?"true":"false");
 $("after").setAttribute("aria-pressed",version==="after"?"true":"false");
 $("prev").disabled=current===0;
 $("next").disabled=current===data.changes.length-1;
 $("status").textContent=(version==="before"?"Previous: ":"Revised: ")+
   join[version].fade_seconds+"s real join overlap, boundary at "+
   join[version].boundary_seconds.toFixed(3)+"s in that version's own WAV.";
 document.querySelectorAll("#joins li").forEach((item,index)=>
  item.classList.toggle("selected",index===current));
 if(play){const p=audio.play();if(p)p.catch(()=>{$("status").textContent="Press Play in the local WAV player; your browser may restrict automatic playback.";});}
}
data.changes.forEach((join,index)=>{
 const row=document.createElement("li"),name=document.createElement("strong");
 name.textContent=join.index+". "+join.from+" → "+join.to;
 const p=document.createElement("p");
 p.textContent="Previous: "+join.before.fade_seconds+"s → Revised: "+
 join.after.fade_seconds+"s (actual WAV output).";
 const buttons=document.createElement("div");buttons.className="actions";
 for(const version of ["before","after"]){
  const b=document.createElement("button");b.type="button";
  b.textContent="Hear real "+(version==="before"?"previous":"new")+" WAV";
  b.addEventListener("click",()=>listen(index,version));
  buttons.append(b);
 }
 row.append(name,p,buttons);$("joins").append(row);
});
$("before").addEventListener("click",()=>listen(current,"before"));
$("after").addEventListener("click",()=>listen(current,"after"));
$("prev").addEventListener("click",()=>listen(current-1,side));
$("next").addEventListener("click",()=>listen(current+1,side));
document.addEventListener("keydown",e=>{
 if(["INPUT","TEXTAREA","SELECT","BUTTON"].includes(e.target?.tagName))return;
 if(e.key==="1"){e.preventDefault();listen(current,"before");}
 else if(e.key==="2"){e.preventDefault();listen(current,"after");}
 else if(e.key==="ArrowLeft"){e.preventDefault();listen(current-1,side);}
 else if(e.key==="ArrowRight"){e.preventDefault();listen(current+1,side);}
});
audio.addEventListener("error",()=>{
 $("status").textContent="Local WAV playback unavailable in this browser. Use a trusted offline PCM16 player.";});
$("fingerprints").textContent="Previous full WAV SHA-256: "+data.previous_sha256+
 " · Real revision SHA-256: "+data.revision_sha256+
 " · Original full source SHA-256: "+data.source_sha256;
listen(0,"after",false);
</script></body></html>"""


def _check_sources(old_wav, new_wav):
    old, new = Path(old_wav).absolute(), Path(new_wav).absolute()
    if old == new or any(path.name!="marathon.wav" for path in (old,new)):
        raise ValueError("Choose two distinct completed real hybrid Marathon WAVs")
    before_seconds, n_before, kind_before=_marathon_duration(old.parent,old)
    after_seconds, n_after, kind_after=_marathon_duration(new.parent,new)
    a=_read_small_json(old.parent/"marathon.receipt.private.json")
    b=_read_small_json(new.parent/"marathon.receipt.private.json")
    past=_read_plan(old.parent/"master-picks.private.json")
    chosen=_read_plan(new.parent/"master-picks.private.json")
    _validate(old,past);_validate(new,chosen)
    if (kind_before!="marathon_blend" or kind_after!="marathon_blend" or
            n_before!=n_after or n_before<2 or
            chosen.get("parent_hybrid_sha256")!=a["wav_sha256"] or
            past.get("source_blend_sha256")!=chosen.get("source_blend_sha256") or
            a.get("source_marathon_sha256")!=b.get("source_marathon_sha256") or
            [(x["label"],x["source_sha256"],x["frames"]) for x in a["sections"]] !=
            [(x["label"],x["source_sha256"],x["frames"]) for x in b["sections"]]):
        raise ValueError("Not two exact, consecutive real WAV revisions of the same private original set")
    changes=[]
    for i, (prev,nxt) in enumerate(zip(past["joins"],chosen["joins"]),1):
        if prev["choice"]!=nxt["choice"]:
            changes.append(i)
    if not changes:
        raise ValueError("Adjacent real masters have no changed join decision")
    return old,new,a,b,changes,before_seconds,after_seconds


def create_revision_audition(previous_wav, new_revision_wav, new_private_folder,
                            *, read=input, write=print):
    old,new,a,b,changed,seconds0,seconds1=_check_sources(previous_wav,new_revision_wav)
    folder=_new_folder(new_private_folder,[old.parent,new.parent])
    rate=a["rate"]
    pairs=[]
    total_bytes=0
    for index in changed:
        left=a["sections"][index];right=b["sections"][index]
        row={"index":index,"from":a["sections"][index-1]["label"],
             "to":left["label"]}
        for side,source,record,receipt in (("before",old,left,a),("after",new,right,b)):
            fade=receipt["fade_seconds_by_join"][index-1]
            boundary=record["start_frame"]
            lead=min(BEFORE*rate,boundary)
            tail=min((fade+AFTER)*rate,receipt["frames"]-boundary)
            frames=lead+tail
            if frames<=0:raise ValueError("Real transition contains no usable PCM frames")
            filename=f"change-{index:02d}-{side}.wav"
            row[side]={"filename":filename,"fade_seconds":fade,
                       "start_frame":boundary-lead,"frames":frames,
                       "boundary_seconds":boundary/rate,"duration_seconds":frames/rate}
            total_bytes+=frames*4+64
        pairs.append(row)
    if not 0<total_bytes<=MAX_PRIVATE_REELS:
        raise ValueError("Actual changed-transition audition exceeds bounded 192 MiB")
    write("MixLab: independently verified consecutive private full WAV revisions.")
    write("Parent WAV SHA-256: "+a["wav_sha256"])
    write("Revised WAV SHA-256: "+b["wav_sha256"])
    write(f"{len(pairs)} true PCM16 changed boundaries. Existing masters are never changed.")
    write("Private local excerpts only. No blind preference, sender identity or music rights claim.")
    if read("Type yes to make SEPARATE short real WAV clips for these revisions: ").strip()!="yes":
        raise ValueError("Private source excerpt production not explicitly authorised")
    folder.mkdir(mode=0o700)
    created=[];completed=False
    try:
        for row in pairs:
            for side,source in (("before",old),("after",new)):
                entry=row[side]
                dest=folder/entry["filename"];created.append(dest)
                _clip(source,dest,start_frame=entry["start_frame"],
                      frames=entry["frames"],expected_rate=rate)
                sha=hashlib.sha256()
                with dest.open("rb") as stream:
                    for part in iter(lambda:stream.read(65536),b""):sha.update(part)
                entry["wav_sha256"]=sha.hexdigest()
        # Verify both full real masters still match immutable approved source receipts.
        _, _, check_a,check_b,_,_,_=_check_sources(old,new)
        if check_a["wav_sha256"]!=a["wav_sha256"] or check_b["wav_sha256"]!=b["wav_sha256"]:
            raise ValueError("A master changed during real revision excerpt publication")
        info={"kind":PAGE_KIND,"schema_version":1,"private_only":True,
              "original_media_embedded":False,"blind_study":False,
              "previous_sha256":a["wav_sha256"],"revision_sha256":b["wav_sha256"],
              "source_sha256":a["source_marathon_sha256"],
              "rate":rate,"previous_duration_seconds":seconds0,
              "revision_duration_seconds":seconds1,"changes":pairs}
        inline=json.dumps(info,ensure_ascii=True,separators=(",",":"),allow_nan=False)
        inline=inline.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
        page=_PAGE.replace("__DATA__",inline).encode("utf-8")
        if len(page)>PAGE_LIMIT:raise ValueError("Offline genuine WAV revision page too large")
        html=folder/"index.html";created.append(html)
        with html.open("xb") as out:
            os.fchmod(out.fileno(),0o600);out.write(page)
        receipt_path=folder/"revision-clips.receipt.private.json";created.append(receipt_path)
        with receipt_path.open("xb") as out:
            os.fchmod(out.fileno(),0o600)
            out.write((json.dumps(info,sort_keys=True,indent=2,allow_nan=False)+"\n").encode("utf-8"))
        completed=True
    finally:
        if not completed:
            for path in reversed(created):path.unlink(missing_ok=True)
            folder.rmdir()
    return {"private_actual_revision_reels":str(folder),
            "private_offline_player":str(folder/"index.html"),
            "private_receipt":str(folder/"revision-clips.receipt.private.json"),
            "changed_join_count":len(pairs),"real_pcm16_clips":len(pairs)*2,
            "original_and_revision_masters_unchanged":True,
            "browser_mix":False,"music_rights_proven":False,
            "blind_preference_proven":False}


def main():
    parser=argparse.ArgumentParser(
        description="Copy real short PCM16 WAV clips from changed joins of two consecutive SHA-verified hybrid masters")
    parser.add_argument("previous_actual_hybrid_marathon_wav")
    parser.add_argument("new_actual_revised_marathon_wav")
    parser.add_argument("new_private_revision_listening_folder")
    args=parser.parse_args()
    try:
        result=create_revision_audition(
            args.previous_actual_hybrid_marathon_wav,
            args.new_actual_revised_marathon_wav,
            args.new_private_revision_listening_folder)
    except (ValueError,TypeError,KeyError,OSError,EOFError,KeyboardInterrupt,wave.Error):
        parser.exit(2,"MixLab actual revision clips: approved WAV provenance, source, consent or new folder unavailable.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
