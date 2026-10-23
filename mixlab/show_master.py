"""Explicit, bounded local WAV assembly from an approved multi-set show plan.

Copies actual source PCM16 frames and manual silence gaps, never browser-mixes,
time-stretches, guesses permissions or alters original music.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import wave

from .event_marathon import _new_folder, MAX_BYTES, BLOCK_FRAMES, _meta_key
from .show_conductor import _sources, KIND, CLOCK
from .marathon_sequence import _read_plan

RECEIPT_KIND="mixlab-private-complete-show-master-v1"
MAX_HTML=512*1024

_PAGE=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';media-src 'self' file:;connect-src 'none';img-src 'none';object-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Real Full Show WAV</title>
<style>:root{color-scheme:dark;--bg:#081520;--card:#142d3e;--line:#4b6d7d;--mint:#abffdc;--muted:#bfd3df}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 75% 0,#255747,var(--bg) 66%);font:15px/1.55 system-ui;color:#f3fdff}
main{max-width:1100px;margin:auto;padding:clamp(18px,5vw,66px)}h1{font-size:clamp(38px,7vw,78px);line-height:1.04;letter-spacing:-.05em}
h2{font-size:23px}p,small{color:var(--muted)}.eyebrow{font-size:12px;letter-spacing:.19em;font-weight:900;color:var(--mint)}
section{border:1px solid var(--line);border-radius:19px;background:var(--card);padding:clamp(19px,4vw,29px);margin:19px 0}
audio{width:100%;margin:13px 0}button{background:#266557;border:1px solid #83ad9e;border-radius:12px;padding:12px 16px;color:white;cursor:pointer;font:inherit}
button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
ol{list-style:none;display:grid;gap:10px;padding:0}
li{background:#0b2735;border:1px solid #4b7280;border-radius:12px;padding:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
li button{flex:1;text-align:left}li small{flex-basis:100%;padding-left:7px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px}
.stat{padding:15px;background:#0e332e;border:1px solid #417869;border-radius:13px}
.stat strong{font-size:30px;display:block;color:var(--mint)}.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
@media print{audio,button{display:none!important}body{background:white;color:black}section,li{background:white;color:black}}
</style></head><body><main>
<div class="eyebrow">MIXLAB · COMPLETE REAL PCM16 SHOW / PRIVATE</div>
<h1>One actual<br>complete event WAV.</h1>
<p>Every set is copied from its individually SHA-verified original MixLab WAV.
Each optional planned changeover gap contains true PCM16 digital silence,
not a DJ transition. No tempo changes, browser mixing, music license,
synchronization guarantee, external service or automatic event playback.</p>
<div class="stats">
<div class="stat"><small>Source sets</small><strong id="sets"></strong></div>
<div class="stat"><small>Exact total duration</small><strong id="duration"></strong></div>
<div class="stat"><small>Manual silence breaks</small><strong id="breaks"></strong></div></div>
<section><h2>Play the actually rendered source-bound show</h2>
<audio src="./show.wav" controls id="player" preload="metadata"></audio>
<p id="status" role="status">Actual complete local PCM16 file. Open with a native offline audio app if the browser cannot decode it.</p>
<div><button type="button" id="begin">Cue beginning</button>
<button type="button" id="end">Cue final set</button></div></section>
<section><h2>Receipt-bound event timeline</h2>
<ol id="chapters"></ol>
<p class="hash" id="hashes"></p></section>
<p>This is a separately approved permanent offline rendering, useful for
an archive, fixed playlist or private rehearsal. Human live DJ operation
requires a separate sound setup. Never redistribute music without rights.</p>
</main><script id="show-data" type="application/json">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("show-data").textContent),$=id=>document.getElementById(id);
const clock=s=>{const v=Math.max(0,Math.floor(s));return [Math.floor(v/3600),
 Math.floor(v%3600/60),v%60].map(n=>String(n).padStart(2,"0")).join(":");};
$("sets").textContent=data.sets.length;
$("duration").textContent=clock(data.duration_seconds);
$("breaks").textContent=data.sets.slice(0,-1).filter(s=>s.gap_seconds>0).length;
const audio=$("player");
data.sets.forEach((item,index)=>{
 const line=document.createElement("li"),button=document.createElement("button");
 button.type="button";button.textContent=clock(item.start_seconds)+
  " · "+item.label+" · "+clock(item.duration_seconds)+" real audio";
 button.addEventListener("click",()=>{audio.currentTime=item.start_seconds;});
 const note=document.createElement("small");note.textContent=item.note||"No operator note";
 line.append(button,note);$("chapters").append(line);
 if(item.gap_seconds){
  const rest=document.createElement("li"),text=document.createElement("small");
  text.textContent="DIGITAL SILENCE · "+clock(item.gap_seconds)+" planned break";
  rest.append(text);$("chapters").append(rest);
 }
});
$("begin").addEventListener("click",()=>{audio.currentTime=0;});
$("end").addEventListener("click",()=>{audio.currentTime=data.sets.at(-1).start_seconds;});
audio.addEventListener("error",()=>{$("status").textContent="This local WAV cannot play in the browser. Use a trusted native offline music player.";});
$("hashes").textContent="Entire finished WAV SHA-256: "+data.wav_sha256+
 " · Original approved source SHA-256s: "+data.source_sha256s.join(" · ");
</script></body></html>"""


def _plan(sources, path):
    data=_read_plan(path)
    fields={"schema_version","kind","source_sha256s","start_local",
            "break_minutes","private_notes","private_only",
            "automatic_playback","blind_study"}
    if (not isinstance(data,dict) or set(data)!=fields or
            type(data["schema_version"]) is not int or data["schema_version"]!=1 or
            data["kind"]!=KIND or data["private_only"] is not True or
            data["automatic_playback"] is not False or data["blind_study"] is not False or
            data["source_sha256s"] != [s["wav_sha256"] for s in sources] or
            not isinstance(data["start_local"],str) or not CLOCK.fullmatch(data["start_local"])):
        raise ValueError("Source-locked show plan does not match all original completed sets")
    breaks,notes=data["break_minutes"],data["private_notes"]
    if (not isinstance(breaks,list) or not isinstance(notes,list) or
            len(breaks)!=len(sources) or len(notes)!=len(sources)):
        raise ValueError("Source-locked manual show has missing breaks or private notes")
    for i,(gap,note) in enumerate(zip(breaks,notes)):
        if (type(gap) is not int or not 0<=gap<=120 or
                (i==len(sources)-1 and gap!=0) or
                not isinstance(note,str) or len(note)>300 or
                any(ord(c)<32 and c not in "\n\t" for c in note)):
            raise ValueError("Private show has an invalid manual break or cue note")
    return data


def _source_wave_header(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Source WAV is no longer a regular file")
        with wave.open(stream,"rb") as src:
            if src.getcomptype()!="NONE" or src.getnchannels()!=2 or src.getsampwidth()!=2:
                raise ValueError("A continuous real show needs stereo PCM16 source sets")
            rate,frames=src.getframerate(),src.getnframes()
            if rate<8000 or rate>96000 or frames<=0 or before.st_size!=44+frames*4:
                raise ValueError("Original source frame count or WAV size is not canonical")
        if _meta_key(before)!=_meta_key(os.fstat(stream.fileno())):
            raise ValueError("Original WAV changed during source admission")
    return rate,frames


def render_show(plan_path,new_private_folder,*source_pairs,read=input,write=print):
    sources=_sources(source_pairs)
    plan=_plan(sources,plan_path)
    wavs=[Path(path).absolute() for path in source_pairs[1::2]]
    folder=_new_folder(new_private_folder,[p.parent for p in wavs])
    layouts=[_source_wave_header(w) for w in wavs]
    rate=layouts[0][0]
    if any(r!=rate for r,_ in layouts):
        raise ValueError("Completed sets use different PCM sample rates; no hidden resampling is permitted")
    durations=[frames for _,frames in layouts]
    breaks=[round(gap*60*rate) for gap in plan["break_minutes"]]
    frames=sum(durations)+sum(breaks)
    if not 1<=frames or frames*4+44>MAX_BYTES:
        raise ValueError("Planned full show plus actual PCM silence exceeds the 768 MiB safety budget")
    write("MixLab: creating a NEW exact-source stereo PCM16 show WAV.")
    for i,(source,gap) in enumerate(zip(sources,plan["break_minutes"]),1):
        write(f"Set {i}: {source['label']}, SHA {source['wav_sha256']}, silence after {gap} minutes")
    write("No crossfade, beatmatching, rights licensing, browser audio or real-time playback.")
    if read("Type yes to create this separate full real-show WAV from authorised original sets: ").strip()!="yes":
        raise ValueError("User did not approve new full private show WAV")
    folder.mkdir(mode=0o700)
    master=folder/"show.wav"
    private_receipt=folder/"show.receipt.private.json"
    private_page=folder/"index.html"
    published=False
    try:
        positions=[]
        current=0
        with master.open("xb") as out:
            os.fchmod(out.fileno(),0o600)
            with wave.open(out,"wb") as writer:
                writer.setnchannels(2);writer.setsampwidth(2)
                writer.setframerate(rate);writer.setnframes(frames)
                for i,(path,(_,num_frames),gap,src) in enumerate(
                        zip(wavs,layouts,breaks,sources)):
                    positions.append({"label":src["label"],"source_sha256":src["wav_sha256"],
                                      "start_frame":current,"frames":num_frames,
                                      "gap_frames":gap,"private_note":plan["private_notes"][i]})
                    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
                    with os.fdopen(fd,"rb") as source_stream:
                        before=os.fstat(source_stream.fileno())
                        if not stat.S_ISREG(before.st_mode):
                            raise ValueError("Original WAV changed file type during rendering")
                        with wave.open(source_stream,"rb") as reader:
                            if reader.getnframes()!=num_frames or reader.getframerate()!=rate or reader.getnchannels()!=2 or reader.getsampwidth()!=2 or reader.getcomptype()!="NONE":
                                raise ValueError("Original finished WAV metadata changed during streaming")
                            remaining=num_frames
                            while remaining:
                                take=min(remaining,BLOCK_FRAMES)
                                payload=reader.readframes(take)
                                if len(payload)!=take*4:
                                    raise ValueError("Source WAV truncated while streaming")
                                writer.writeframesraw(payload)
                                remaining-=take
                        if _meta_key(before)!=_meta_key(os.fstat(source_stream.fileno())):
                            raise ValueError("Original source WAV mutated during new show rendering")
                    current+=num_frames
                    silence=gap
                    while silence:
                        take=min(silence,BLOCK_FRAMES)
                        writer.writeframesraw(bytes(take*4))
                        silence-=take
                    current+=gap
        if current!=frames or master.stat().st_size!=44+frames*4:
            raise ValueError("Real show WAV byte/frame count differs from exact planned content")
        # The same full SHA/receipt verification is repeated after streaming:
        # refuse silently changed sources before publishing an output receipt.
        current_sources=_sources(source_pairs)
        if [s["wav_sha256"] for s in current_sources] != [s["wav_sha256"] for s in sources]:
            raise ValueError("A source completed WAV changed while the new show was rendered")
        sha=hashlib.sha256()
        with master.open("rb") as stream:
            for chunk in iter(lambda:stream.read(65536),b""):
                sha.update(chunk)
        output_sha=sha.hexdigest()
        receipt={"schema_version":1,"kind":RECEIPT_KIND,"wav_sha256":output_sha,
                 "sample_rate":rate,"channels":2,"frames":frames,
                 "start_local":plan["start_local"],"sets":positions,
                 "private_only":True,"external_music_rights_verified":False,
                 "automatic_dj_transition":False,"blind_study":False}
        with private_receipt.open("xb") as sink:
            os.fchmod(sink.fileno(),0o600)
            sink.write((json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8"))
        page_data={"wav_sha256":output_sha,"duration_seconds":frames/rate,
                   "source_sha256s":[s["wav_sha256"] for s in sources],
                   "sets":[{"label":row["label"],"note":row["private_note"],
                            "start_seconds":row["start_frame"]/rate,
                            "duration_seconds":row["frames"]/rate,
                            "gap_seconds":row["gap_frames"]/rate}
                           for row in positions]}
        compact=json.dumps(page_data,separators=(",",":"),ensure_ascii=True,allow_nan=False)
        compact=compact.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
        page=_PAGE.replace("__DATA__",compact).encode("utf-8")
        if not 0<len(page)<=MAX_HTML:
            raise ValueError("The private source-bound full-show player exceeds size limits")
        with private_page.open("xb") as writer:
            os.fchmod(writer.fileno(),0o600)
            writer.write(page)
        published=True
    finally:
        if not published:
            for item in (private_page,private_receipt,master):
                item.unlink(missing_ok=True)
            folder.rmdir()
    return {"private_complete_show_wav":str(master),"private_receipt":str(private_receipt),
            "private_offline_player":str(private_page),"actual_sha256":output_sha,
            "source_sets":len(sources),"actual_duration_seconds":round(frames/rate,3),
            "digital_silence_breaks":sum(gap>0 for gap in breaks),
            "source_masters_unchanged":True,
            "music_rights_proven":False,"automatic_mix_quality_proven":False}


def main():
    parser=argparse.ArgumentParser(description="Render one independent, bounded true PCM16 WAV by joining completed approved private MixLab sets and manual silent breaks")
    parser.add_argument("private_show_conductor_json")
    parser.add_argument("new_private_complete_show_folder")
    parser.add_argument("session_and_completed_wav_pairs",nargs="+")
    args=parser.parse_args()
    try:
        result=render_show(args.private_show_conductor_json,
                           args.new_private_complete_show_folder,
                           *args.session_and_completed_wav_pairs)
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,EOFError,
            KeyboardInterrupt,wave.Error):
        parser.exit(2,"MixLab full show: exact authorised real WAVs, operator consent, source plan or new private folder unavailable.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
