"""Offline operator stage navigator for a real, human-selected hybrid WAV.

Uses only a locally verified MixLab Marathon WAV and its private operator
decisions. Contains no encoded audio, network calls or persistent browser data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import wave

from .event_vault import _marathon_duration, _read_small_json
from .marathon_sequence import _read_plan
from .marathon_reel_decisions import KIND

_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self' file:; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab | Real hybrid operator stage</title>
<style>
:root{color-scheme:dark;--bg:#06121c;--card:#122b39;--mint:#adffdc;--muted:#b6cfda;--line:#446776}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 80% 0,#244743,var(--bg) 65%);font:16px/1.55 system-ui;color:#f3fcff}
main{max-width:1250px;margin:auto;padding:clamp(15px,4vw,54px)}h1{font-size:clamp(35px,6vw,70px);line-height:1;letter-spacing:-.05em;margin:12px 0}
h2{font-size:clamp(20px,3vw,30px);margin:7px 0}p{color:var(--muted)}.tag{color:var(--mint);font-size:12px;letter-spacing:.16em;font-weight:900}
.panel{border:1px solid var(--line);border-radius:22px;background:var(--card);padding:clamp(18px,3vw,30px);margin:22px 0}
.statrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:13px}
.stat{background:#0b2231;border:1px solid var(--line);padding:20px;border-radius:16px}
.stat strong{display:block;color:var(--mint);font-size:clamp(22px,4vw,36px);overflow-wrap:anywhere}
.stat small{color:var(--muted)}audio{width:100%;margin:14px 0}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
button{cursor:pointer;background:#275f63;color:white;border:1px solid #70a09b;border-radius:12px;padding:13px 16px;font:inherit;font-weight:750}
button:hover{background:#397a70}button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
button:disabled{opacity:.45}.mark{background:#345a47}.observed{color:var(--mint);font-weight:750}ul{list-style:none;margin:0;padding:0;display:grid;gap:12px}
li{display:flex;gap:15px;align-items:center;flex-wrap:wrap;padding:17px;border:1px solid var(--line);border-radius:14px;background:#0e2231}
li[data-active="true"]{border-color:var(--mint);background:#144b42}
li .content{flex:1;min-width:240px}li strong,li span,li small{display:block}
li small{color:var(--muted)}li .note{color:#e1edf1;white-space:pre-wrap;overflow-wrap:anywhere}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
@media print{audio,.controls,button{display:none!important}body{background:white;color:black}.panel,.stat,li{background:white;color:black;border:1px solid #999}}
</style></head><body><main>
<div class="tag">MIXLAB / PRIVATE REAL HYBRID MASTER · OPERATOR MODE</div>
<h1>Know the next<br>handoff.</h1>
<p>One genuinely completed PCM16 hybrid WAV. Time positions come from the finished
SHA-verified receipt, not browser simulation. Audio is local and offline;
notes are private, operator-defined, and not a blind preference study.</p>
<div class="statrow">
<div class="stat"><small>Currently playing</small><strong id="now">—</strong></div>
<div class="stat"><small>Upcoming event</small><strong id="next">—</strong></div>
<div class="stat"><small>Until next actual join</small><strong id="countdown">—</strong></div>
</div>
<section class="panel"><h2 id="title">Your real master</h2>
<audio id="player" src="./marathon.wav" controls preload="metadata"></audio>
<p id="play-status" role="status">Only the actual local hybrid Marathon WAV is played. It is never uploaded.</p>
<div class="controls"><button type="button" id="previous">← Previous boundary</button>
<button type="button" id="minus">− 15 s</button>
<button type="button" id="plus">+ 15 s</button>
<button type="button" id="following">Next boundary →</button>
<button type="button" id="fullscreen">Fullscreen stage</button></div>
<p>Tap a boundary below to cue 8 seconds before it. The WAV is not modified,
and browsers might require clicking Play after seeking. Use your audio player
rather than browser timing for safety-critical event production.</p></section>
<section class="panel"><h2>Real joined-event cue sheet</h2><ul id="cue-list"></ul>
<p class="hash" id="hashes"></p></section>
<section class="panel"><h2>Playback rehearsal journal · optional</h2>
<p>During a private listening rehearsal, mark when you <em>hear</em> each
transition in the local WAV. Compare your manual marker against its exact
source-receipt boundary. Seek and pauses affect observations: these are not
real-world show timings, blind ratings or music permissions. No persistence
without your explicit download.</p>
<div class="controls"><button type="button" id="export-journal" disabled>Export private playback journal</button>
<button type="button" id="clear-journal">Clear marks</button></div>
<p id="journal-status" role="status">Mark at least one join during local WAV playback.</p></section>
</main><script type="application/json" id="stage-data">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("stage-data").textContent);
const $=id=>document.getElementById(id),player=$("player");
const pretty=time=>{
 const n=Math.max(0,Math.floor(Number.isFinite(time)?time:0));
 return [Math.floor(n/3600),Math.floor(n/60)%60,n%60]
  .map(x=>String(x).padStart(2,"0")).join(":");
};
const joins=data.joins,events=data.events;
const seek=time=>{
 const pos=Math.min(data.duration_seconds,Math.max(0,time));
 player.currentTime=pos;
 const p=player.play();if(p)p.catch(()=>{$("play-status").textContent="Select Play in the local WAV player to resume. No network is used.";});
 update();
};
const cardNodes=[];
const observed=new Array(joins.length).fill(null);
const observedLabels=[];
joins.forEach((join,index)=>{
 const row=document.createElement("li"),details=document.createElement("div");
 details.className="content";
 const name=document.createElement("strong");name.textContent=(index+1)+". "+join.from+" → "+join.to;
 const meta=document.createElement("small");
 meta.textContent=pretty(join.at_seconds)+" · "+(join.fade_seconds===0?"Exact original hard cut":join.fade_seconds+"s genuine approved crossfade");
 const note=document.createElement("span");note.className="note";
 note.textContent=join.note||"No private operator cue";
 details.append(name,meta,note);
 const btn=document.createElement("button");btn.type="button";btn.textContent="Cue this join";
 btn.setAttribute("aria-label","Cue "+join.from+" to "+join.to+" before actual boundary");
 btn.addEventListener("click",()=>seek(Math.max(0,join.at_seconds-8)));
 const mark=document.createElement("button");mark.type="button";
 mark.textContent="Mark heard NOW";mark.className="mark";
 mark.setAttribute("aria-label","Mark playback cue "+(index+1));
 const recorded=document.createElement("small");recorded.className="observed";
 recorded.textContent="Not marked";
 mark.addEventListener("click",()=>{
  if(!Number.isFinite(player.duration)||!Number.isFinite(player.currentTime)||
     player.currentTime<0||player.currentTime>data.duration_seconds){
   $("journal-status").textContent="Load the actual local WAV first.";return;
  }
  observed[index]=Number(player.currentTime.toFixed(3));refreshJournal();
 });
 row.append(details,btn,mark,recorded);
 $("cue-list").append(row);cardNodes.push(row);observedLabels.push(recorded);
});
function refreshJournal(){
 const count=observed.filter(value=>value!==null).length;
 observed.forEach((mark,index)=>{
  const delta=mark===null?0:mark-joins[index].at_seconds;
  observedLabels[index].textContent=mark===null?"Not marked":
   "Heard at "+pretty(mark)+" · playback delta "+(delta>=0?"+":"")+
    delta.toFixed(2)+" s";
 });
 $("export-journal").disabled=count===0;
 $("journal-status").textContent=count+" / "+joins.length+
 " manually marked joins, retained only in this page until export.";
}
$("clear-journal").addEventListener("click",()=>{
 observed.fill(null);refreshJournal();
});
$("export-journal").addEventListener("click",()=>{
 if(observed.every(value=>value===null))return;
 const journal={
  schema_version:1,kind:"mixlab-private-hybrid-playback-cue-journal-v1",
  actual_master_sha256:data.wav_sha256,source_original_sha256:data.source_sha256,
  duration_seconds:data.duration_seconds,private_only:true,
  playback_only:true,blind_study:false,
  joins:joins.map((join,index)=>({
   index:index+1,from:join.from,to:join.to,
   planned_seconds:join.at_seconds,fade_seconds:join.fade_seconds,
   observed_playback_seconds:observed[index],note:join.note
  }))
 };
 const blob=new Blob([JSON.stringify(journal,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),link=document.createElement("a");
 link.href=url;link.download="mixlab-hybrid-playback-journal.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("journal-status").textContent="Private playback journal downloaded; no music or telemetry uploaded.";
});
refreshJournal();
function update(){
 const pos=Number.isFinite(player.currentTime)?player.currentTime:0;
 let upcoming=joins.findIndex(row=>pos<row.at_seconds);
 if(upcoming<0)upcoming=joins.length;
 $("now").textContent=events[Math.min(upcoming,events.length-1)];
 $("next").textContent=upcoming<joins.length?joins[upcoming].to:"END OF SET";
 $("countdown").textContent=upcoming<joins.length?
  pretty(joins[upcoming].at_seconds-pos):"—";
 $("title").textContent=player.paused?"Master ready · "+pretty(pos):
  "Playing actual WAV · "+pretty(pos);
 cardNodes.forEach((row,index)=>row.dataset.active=index===upcoming?"true":"false");
 $("previous").disabled=joins.length===0;
 $("following").disabled=upcoming>=joins.length;
}
$("previous").addEventListener("click",()=>{
 const previous=[...joins].reverse().find(row=>row.at_seconds<player.currentTime-1);
 seek(previous?Math.max(0,previous.at_seconds-8):0);
});
$("following").addEventListener("click",()=>{
 const next=joins.find(row=>row.at_seconds>player.currentTime+8.01);
 if(next)seek(Math.max(0,next.at_seconds-8));
});
$("minus").addEventListener("click",()=>seek(player.currentTime-15));
$("plus").addEventListener("click",()=>seek(player.currentTime+15));
$("fullscreen").addEventListener("click",()=>{
 if(document.fullscreenElement){document.exitFullscreen().catch(()=>{});}
 else if(document.documentElement.requestFullscreen){
  document.documentElement.requestFullscreen().catch(()=>{});
 }
});
player.addEventListener("timeupdate",update);
player.addEventListener("play",update);player.addEventListener("pause",update);
player.addEventListener("error",()=>{
 $("play-status").textContent="Local marathon.wav cannot play in this browser; use a trusted native offline audio player.";
});
$("hashes").textContent="Actual finished WAV SHA-256: "+data.wav_sha256+
 " · Original approved source SHA-256: "+data.source_sha256+
 " · Local DJ operator choices are not evidence of licensed rights.";
update();
</script></body></html>"""


def create_stage(master_wav, private_decisions, new_private_html):
    wav = Path(master_wav).absolute()
    dest = Path(new_private_html).absolute()
    if (wav.name != "marathon.wav" or wav.is_symlink() or
            dest.parent != wav.parent or dest.name != "master-picks.stage.html" or
            dest.exists() or dest.is_symlink() or
            any(parent.is_symlink() or (parent / ".git").exists()
                for parent in (dest, *dest.parents))):
        raise ValueError("Create a new operator stage HTML beside a verified private Marathon WAV")
    duration, count, kind = _marathon_duration(wav.parent, wav)
    receipt = _read_small_json(wav.parent / "marathon.receipt.private.json")
    decisions = _read_plan(private_decisions)
    if (kind != "marathon_blend" or not isinstance(decisions, dict) or
            decisions.get("kind") != KIND or decisions.get("schema_version") != 1 or
            decisions.get("private_only") is not True or
            decisions.get("blind_study") is not False or
            decisions.get("rendered_hybrid_sha256") != receipt["wav_sha256"] or
            decisions.get("source_original_sha256") != receipt["source_marathon_sha256"] or
            decisions.get("actual_fade_seconds_by_join") != receipt["fade_seconds_by_join"]):
        raise ValueError("Operator plan and actually completed private hybrid WAV do not match")
    rows = decisions.get("joins")
    sections = receipt["sections"]
    if not isinstance(rows, list) or len(rows) != count - 1:
        raise ValueError("Missing human decisions for actual Marathon join boundaries")
    joins = []
    for i, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or type(row.get("index")) is not int or
                row["index"] != i or row.get("from") != sections[i-1]["label"] or
                row.get("to") != sections[i]["label"] or
                row.get("choice") not in ("original", "blend") or
                type(row.get("fade_seconds")) is not int or
                row["fade_seconds"] not in (0, 2, 4, 8, 16) or
                (row["fade_seconds"] if row["choice"] == "blend" else 0) !=
                    receipt["fade_seconds_by_join"][i-1] or
                not isinstance(row.get("note"), str) or len(row["note"]) > 300):
            raise ValueError("Private operator cue does not match actual approved audio timeline")
        joins.append({
            "from": row["from"], "to": row["to"],
            "at_seconds": sections[i]["start_frame"] / receipt["rate"],
            "fade_seconds": receipt["fade_seconds_by_join"][i-1],
            "note": row["note"]
        })
    data = {
        "duration_seconds": duration, "wav_sha256": receipt["wav_sha256"],
        "source_sha256": receipt["source_marathon_sha256"],
        "events": [row["label"] for row in sections], "joins": joins
    }
    blob = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _PAGE.replace("__DATA__", blob).encode("utf-8")
    if not 0 < len(page) <= 128 * 1024:
        raise ValueError("Private stage UI exceeds bounded local HTML size")
    with dest.open("xb") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(page)
    return {"private_stage_html": str(dest), "actual_master_sha256": receipt["wav_sha256"],
            "real_boundaries": len(joins), "local_audio_only": True,
            "operator_notes_private": True, "blind_preference_proven": False}


def main():
    parser = argparse.ArgumentParser(description="Make a stage-readable local cue navigator for an already rendered human-selected hybrid WAV")
    parser.add_argument("actual_hybrid_marathon_wav")
    parser.add_argument("private_master_picks_json")
    parser.add_argument("new_private_stage_html")
    args = parser.parse_args()
    try:
        result = create_stage(args.actual_hybrid_marathon_wav, args.private_master_picks_json,
                              args.new_private_stage_html)
    except (ValueError, TypeError, KeyError, OSError, wave.Error):
        parser.exit(2, "MixLab stage: actual source WAV, private operator decisions or new local page invalid.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
