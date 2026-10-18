"""Make one continuous offline event from already approved, receipt-verified sets.

This is sample-preserving, gapless concatenation. No automatic beat/key
matching, stem work, crossfades or new rights inference is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import wave
import zipfile

from .set_player import build_chapters

BLOCK_FRAMES = 16384
MAX_EVENTS = 8
MAX_BYTES = 768 * 1024 * 1024
MAX_HTML = 512 * 1024
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,59}\Z")
SOURCE_FINGERPRINT = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self'; connect-src 'none'; object-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / Private Event Marathon</title>
<style>
:root{color-scheme:dark;--bg:#09111b;--panel:#192638;--line:#3e546b;--fg:#f1f8ff;--muted:#b5c8d8;--accent:#9cf9cc}
*{box-sizing:border-box}body{background:radial-gradient(at 70% -20%,#21554e,var(--bg) 64%);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1200px;margin:auto;padding:clamp(18px,4vw,58px)}
.eyebrow{font-weight:800;letter-spacing:.18em;color:var(--accent);font-size:11px}
h1{font-size:clamp(38px,6vw,78px);letter-spacing:-.06em;line-height:1;margin:10px 0 20px}
h2{font-size:22px;margin:0 0 12px}p{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);padding:clamp(16px,3vw,30px);border-radius:22px;margin:20px 0}
audio{width:100%;margin:12px 0}
.controls{display:flex;gap:11px;flex-wrap:wrap;margin:17px 0}
button,a.action{color:#f5fbff;background:#2c5069;border:1px solid #668ba0;padding:11px 16px;border-radius:12px;font:inherit;font-weight:800;cursor:pointer;text-decoration:none}
button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
button:hover,a:hover{background:#3b6684}
.timeline{width:100%;accent-color:var(--accent)}
.time{font-size:clamp(25px,4vw,44px);font-weight:850;font-variant-numeric:tabular-nums}
.list{display:grid;gap:10px;padding:0;list-style:none;margin:0}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:15px;border:1px solid var(--line);border-radius:14px}
.row button{flex:1;text-align:left}
.row .stamp{color:var(--accent);font-variant-numeric:tabular-nums}
.row[aria-current=true]{border-color:var(--accent);background:#21433e}
.muted{color:var(--muted)}.hash{word-break:break-word;font:11px ui-monospace,monospace;color:var(--muted)}
</style></head><body><main>
<div class="eyebrow">MIXLAB / PRIVATE CONTINUOUS EVENT</div>
<h1>One long<br>uninterrupted set.</h1>
<p>A gapless assembly of real, independently completed private MixLab sets. No artificial remix, automatic harmonic matching, tempo shift or re-encoding.</p>
<section class="panel"><h2>Play the continuous master</h2>
<audio id="audio" controls preload="metadata"></audio>
<div class="time" id="clock">00:00:00 / 00:00:00</div>
<label for="timeline" class="muted">Seek in the full event</label>
<input id="timeline" class="timeline" type="range" min="0" step="0.1" value="0">
<div class="controls"><button id="prev" type="button">Previous set</button>
<button id="next" type="button">Next set</button>
<a id="download" class="action" download>Save original continuous WAV</a>
<button id="cue" type="button">Download chapter CUE</button><a id="showbook" class="action" hidden>Open show runbook</a></div>
<p id="status" class="muted" role="status">The actual output PCM16 WAV must remain alongside this offline page. Your media player may provide better performance than a browser with large WAV files.</p>
</section>
<section class="panel"><h2>Actual event sequence</h2><ol class="list" id="sections"></ol></section>
<p>The original events and source songs are not embedded in this page. Each joint is an intentional, sample-exact boundary between completed sets. This is not a DJ-quality transition or evidence of listening preference. Only play this event where you have separately verified the required permissions.</p>
<p class="hash" id="hash"></p>
</main>
<script id="mixlab-event-data" type="application/json">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-event-data").textContent);
const $=id=>document.getElementById(id),audio=$("audio");
const secs=data.sections;
let selected=-1;
const clock=s=>{
 const n=Math.max(0,Math.floor(s));
 return String(Math.floor(n/3600)).padStart(2,"0")+":"+String(Math.floor(n%3600/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0");
};
const media="./"+encodeURIComponent(data.wav_name);
audio.src=media;$("download").href=media;
if(data.showbook){$("showbook").href="./"+encodeURIComponent(data.showbook);$("showbook").hidden=false;}
$("timeline").max=String(data.duration_seconds);
const rendered=[];
secs.forEach((section,i)=>{
 const row=document.createElement("li");row.className="row";
 const button=document.createElement("button");button.type="button";
 button.textContent=String(i+1)+". "+section.label;
 button.addEventListener("click",()=>{
  audio.currentTime=section.start_seconds;
  const p=audio.play();if(p)p.catch(()=>$("status").textContent="Browser blocked playback; open the WAV in a local audio player.");
 });
 const stamp=document.createElement("span");stamp.className="stamp";
 stamp.textContent=clock(section.start_seconds);
 row.append(button,stamp);$("sections").append(row);rendered.push(row);
});
function update(){
 $("clock").textContent=clock(audio.currentTime)+" / "+clock(data.duration_seconds);
 $("timeline").value=String(audio.currentTime);
 const index=Math.max(0,secs.findLastIndex(x=>x.start_seconds<=audio.currentTime+0.05));
 if(index!==selected){selected=index;rendered.forEach((row,i)=>row.setAttribute("aria-current",String(i===index)));}
}
audio.addEventListener("timeupdate",update);
audio.addEventListener("error",()=>$("status").textContent="Local WAV unsupported by this browser. Open the original WAV file in a desktop audio player.");
$("timeline").addEventListener("input",e=>{audio.currentTime=Number(e.target.value);update()});
$("prev").addEventListener("click",()=>{const index=Math.max(0,selected-1);audio.currentTime=secs[index].start_seconds;update()});
$("next").addEventListener("click",()=>{const index=Math.min(secs.length-1,selected+1);audio.currentTime=secs[index].start_seconds;update()});
$("cue").addEventListener("click",()=>{
 const lines=["REM GENRE \"Mixed event\"","FILE \""+data.wav_name+"\" WAVE"];
 secs.forEach((section,i)=>{
  const f=Math.floor(section.start_seconds*75);
  const t=String(Math.floor(f/75/60)).padStart(2,"0")+":"+
          String(Math.floor(f/75%60)).padStart(2,"0")+":"+
          String(f%75).padStart(2,"0");
  lines.push("  TRACK "+String(i+1).padStart(2,"0")+" AUDIO",
    "    TITLE \"Event "+String(i+1)+"\"","    INDEX 01 "+t);
 });
 const url=URL.createObjectURL(new Blob([lines.join("\r\n")+"\r\n"],{type:"text/plain"}));
 const a=document.createElement("a");a.href=url;a.download="mixlab-marathon.private.cue";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$("hash").textContent="Exact continuous WAV SHA-256: "+data.wav_sha256;
update();
</script></body></html>"""


def _meta_key(st):
    return tuple(getattr(st, name) for name in SOURCE_FINGERPRINT)


def _new_folder(path, source_dirs):
    dest = Path(path).absolute()
    if (dest.name in ("", ".", "..") or not NAME.fullmatch(dest.name) or
            dest.exists() or dest.is_symlink() or not dest.parent.is_dir()):
        raise ValueError("Choose a NEW private event folder with a simple name")
    for a in (dest, *dest.parents):
        if a.is_symlink() or (a / ".git").exists():
            raise ValueError("Cannot publish a private music master under Git or a symlink")
    if any(dest.is_relative_to(folder) or folder.is_relative_to(dest) for folder in source_dirs):
        raise ValueError("Output folder must be separate from every private source event")
    return dest


def _admit(session, source):
    session = Path(session).absolute()
    wav = Path(source).absolute()
    if (not session.is_dir() or session.is_symlink() or wav.is_symlink() or
            not wav.is_file()):
        raise ValueError("Source set and private Studio session must be ordinary local files")
    for part in (wav, *wav.parents, session, *session.parents):
        if part.is_symlink():
            raise ValueError("No symlinked private event source or Studio directories allowed")
    meta = build_chapters(session, wav)
    fd = os.open(wav, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as src:
        before = os.fstat(src.fileno())
        if not stat.S_ISREG(before.st_mode) or not 44 <= before.st_size <= MAX_BYTES:
            raise ValueError("A source completed WAV is too large or not regular")
        with wave.open(src, "rb") as reader:
            if (reader.getnchannels() != 2 or reader.getsampwidth() != 2 or
                    reader.getcomptype() != "NONE"):
                raise ValueError("Only completed stereo PCM16 MixLab masters can be concatenated")
            frame_rate=reader.getframerate()
            count=reader.getnframes()
            if not 8000 <= frame_rate <= 96000 or count <= 0:
                raise ValueError("Invalid completed source PCM16 header")
        if _meta_key(before) != _meta_key(os.fstat(src.fileno())):
            raise ValueError("Source WAV changed during metadata inspection")
    return {"session":session,"wav":wav,"wav_sha256":meta["wav_sha256"],
            "duration":meta["duration_seconds"],"frames":count,
            "rate":frame_rate,"stamp":_meta_key(before),
            "chapters":meta["chapters"]}


def _digest_file(path):
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
    fd=os.open(path,flags)
    with os.fdopen(fd,"rb") as src:
        h=hashlib.sha256()
        while True:
            data=src.read(65536)
            if not data:break
            h.update(data)
    return h.hexdigest()


def create_marathon(new_private_folder, *set_pairs, read=input, write=print, bundle=False, start=None):
    if not 2 <= len(set_pairs) <= MAX_EVENTS:
        raise ValueError("Choose 2 to 8 completed private events")
    items=[_admit(session,wav) for session,wav in set_pairs]
    if len({item["wav"] for item in items}) != len(items):
        raise ValueError("One private completed event cannot be repeated as two sources")
    rates={item["rate"] for item in items}
    if len(rates)!=1:
        raise ValueError("Completed events use different PCM sample rates; no silent resampling")
    rate=items[0]["rate"]
    total_frames=sum(item["frames"] for item in items)
    if total_frames*4>MAX_BYTES:
        raise ValueError("Combined event would exceed the 768 MiB private WAV budget")
    destination=_new_folder(new_private_folder,[item["wav"].parent for item in items])
    write("MixLab private continuous event: original approved masters only.")
    for i,item in enumerate(items,1):
        write(f"  {i}. {item['wav'].parent.name}: {item['duration']:.1f} seconds, {len(item['chapters'])} chapters")
    write("All sets are appended without crossfade, tempo alignment or any quality claim.")
    write("You must independently confirm permission to play or distribute this combined result.")
    if read("Type yes to create this exact private continuous event: ").strip()!="yes":
        raise ValueError("Explicit private-event compilation approval not given")

    if start is not None:
        from .marathon_showbook import CLOCK
        if not isinstance(start, str) or not CLOCK.fullmatch(start):
            raise ValueError("Planned local Marathon start must be HH:MM")
    destination.mkdir(mode=0o700)
    wav=destination/"marathon.wav"
    receipt=destination/"marathon.receipt.private.json"
    player=destination/"index.html"
    created=[]
    try:
        with wav.open("xb") as outfile:
            created.append(wav)
            os.fchmod(outfile.fileno(),0o600)
            with wave.open(outfile,"wb") as dest:
                dest.setnchannels(2);dest.setsampwidth(2);dest.setframerate(rate)
                dest.setnframes(total_frames)
                sections=[]
                offset=0
                for idx,item in enumerate(items,1):
                    sections.append({"index":idx,"label":item["wav"].parent.name,
                                     "source_sha256":item["wav_sha256"],
                                     "start_frame":offset,"frames":item["frames"],
                                     "start_seconds":round(offset/rate,5)})
                    fd=os.open(item["wav"],os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|
                               getattr(os,"O_NONBLOCK",0))
                    with os.fdopen(fd,"rb") as stream:
                        if _meta_key(os.fstat(stream.fileno()))!=item["stamp"]:
                            raise ValueError("An approved original WAV changed before joining")
                        with wave.open(stream,"rb") as src:
                            if (src.getnframes()!=item["frames"] or
                                    src.getframerate()!=rate or
                                    src.getnchannels()!=2 or src.getsampwidth()!=2):
                                raise ValueError("A private source's PCM format changed")
                            remaining=item["frames"]
                            while remaining:
                                want=min(remaining,BLOCK_FRAMES)
                                pcm=src.readframes(want)
                                if len(pcm)!=want*4:
                                    raise ValueError("Original completed WAV was truncated")
                                dest.writeframesraw(pcm)
                                remaining-=want
                        if _meta_key(os.fstat(stream.fileno()))!=item["stamp"]:
                            raise ValueError("Source changed during private event compilation")
                    offset+=item["frames"]
                if offset!=total_frames:
                    raise ValueError("Sample count of private joined event did not match preflight")
        observed=_digest_file(wav)
        payload={"schema_version":1,"kind":"mixlab-private-continuous-event-v1",
                 "wav_name":wav.name,"wav_sha256":observed,
                 "rate":rate,"channels":2,"sample_width_bytes":2,
                 "frames":total_frames,"duration_seconds":total_frames/rate,
                 "sections":sections,"no_automatic_tempo_matching":True,
                 "sample_preserving_joins":True,"private_local_use_only":True,
                 "automatic_licensing":False,"musical_preference_proven":False}
        with receipt.open("xb") as output:
            created.append(receipt);os.fchmod(output.fileno(),0o600)
            output.write((json.dumps(payload,sort_keys=True,indent=2,allow_nan=False)+"\n").encode("utf-8"))
        showbook = None
        showbook_warning = None
        try:
            from .marathon_showbook import create_runbook
            showbook = create_runbook(wav, destination / "marathon.runbook.private.html", start=start)
            created.append(showbook)
        except (ValueError, TypeError, KeyError, OSError):
            showbook_warning = "Completed WAV exists; optional private Marathon runbook unavailable"
        viewer={"wav_name":wav.name,"wav_sha256":observed,
                "showbook":showbook.name if showbook else None,
                "duration_seconds":payload["duration_seconds"],
                "sections":[{"label":row["label"],"start_seconds":row["start_seconds"]}
                            for row in sections]}
        blob=json.dumps(viewer,ensure_ascii=True,separators=(",",":"),allow_nan=False)
        blob=blob.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
        html=_PAGE.replace("__DATA__",blob).encode("utf-8")
        if len(html)>MAX_HTML:
            raise ValueError("Private event HTML exceeded its local budget")
        with player.open("xb") as output:
            created.append(player);os.fchmod(output.fileno(),0o600);output.write(html)
    except Exception:
        for artifact in reversed(created):
            artifact.unlink(missing_ok=True)
        destination.rmdir()
        raise
    result = {"continuous_wav":str(wav),"private_receipt":str(receipt),
              "private_player":str(player),"events_joined":len(items),
              "duration_seconds":payload["duration_seconds"],"wav_sha256":observed,
              "automatic_tempo_matching":False,"private":True,"rights_proven":False,
              "private_show_runbook":str(showbook) if showbook else None}
    if showbook_warning:
        result["showbook_warning"] = showbook_warning
    if bundle:
        # Packaging is optional; never remove the already completed WAV if
        # the USB archive exceeds disk or file limits.
        try:
            from .marathon_bundle import export_marathon_bundle
            result["portable_bundle"] = export_marathon_bundle(
                wav, destination / "marathon.private.zip")
        except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile):
            result["portable_bundle"] = None
            result["bundle_warning"] = "Real continuous WAV exists; optional USB ZIP was not published"
    return result


def main():
    parser=argparse.ArgumentParser(
        description="Join 2–8 original receipt-verified private MixLab event WAVs, sample-exact and offline")
    parser.add_argument("new_private_folder")
    parser.add_argument("session_wav_pairs",nargs="+",help="Alternating Studio SESSION and original completed WAV")
    parser.add_argument("--bundle",action="store_true",help="Also create an optional trusted private USB ZIP")
    parser.add_argument("--start",help="Optional planned local show start HH:MM")
    args=parser.parse_args()
    if not 4<=len(args.session_wav_pairs)<=MAX_EVENTS*2 or len(args.session_wav_pairs)%2:
        parser.exit(2,"Provide 2–8 SESSION WAV pairs after the new output folder\n")
    pairs=list(zip(args.session_wav_pairs[0::2],args.session_wav_pairs[1::2]))
    try:
        out=create_marathon(args.new_private_folder,*pairs,bundle=args.bundle,start=args.start)
    except (ValueError,TypeError,KeyError,OSError,EOFError,KeyboardInterrupt,wave.Error):
        parser.exit(2,"MixLab event marathon: source admission, approval or private export failed; "
                       "no completed new event was published.\n")
    print(json.dumps(out,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
