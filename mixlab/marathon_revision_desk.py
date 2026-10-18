"""Offline private hybrid-master revision planner from actual completed WAV receipts.

This is a human arrangement editor. No browser DSP, models, server or playback
inference; only the separately approved canonical renderer publishes new audio.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import wave

from .event_vault import _marathon_duration, _read_small_json
from .marathon_master_review import _pair
from .marathon_operator_transfer import _validate
from .marathon_sequence import _private_html_destination, _read_plan

MAX_HTML = 512 * 1024

_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src blob:; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Private Hybrid Revision Desk</title>
<style>
:root{color-scheme:dark;--bg:#071722;--panel:#152f40;--line:#496b7b;--mint:#acffdc;--muted:#bbced9}
*{box-sizing:border-box}body{margin:0;color:#f4fbff;font:15px/1.5 system-ui;background:radial-gradient(at 90% 0,#235449,var(--bg) 67%)}
main{max-width:1120px;margin:auto;padding:clamp(19px,4vw,64px)}
h1{font-size:clamp(37px,6.5vw,72px);line-height:1.02;letter-spacing:-.05em;margin:12px 0}h2{font-size:21px}
p,small{color:var(--muted)}.eyebrow{color:var(--mint);font-size:12px;letter-spacing:.18em;font-weight:900}
section{border:1px solid var(--line);background:var(--panel);padding:clamp(18px,3vw,30px);border-radius:21px;margin:19px 0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px}
.stat{border:1px solid var(--line);padding:14px;border-radius:12px;background:#0b2631}
.stat strong{display:block;color:var(--mint);font-size:28px}
ol{list-style:none;padding:0;display:grid;gap:12px}
li{border:1px solid var(--line);padding:18px;border-radius:14px;background:#102c3c}
li.modified{border-color:var(--mint);background:#17413d}
.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.row strong{flex:1;min-width:190px}
select,textarea{color:#fff;background:#081f2f;border:1px solid #7298a4;border-radius:10px;font:inherit;padding:12px}
textarea{display:block;width:100%;min-height:66px;margin-top:11px;resize:vertical}
button{font:inherit;color:#f3fffc;background:#32645d;padding:12px 16px;border:1px solid #82a9a3;border-radius:11px;cursor:pointer}
button:hover{background:#408574}button:disabled{opacity:.4;cursor:not-allowed}
button:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}
.note{font:12px ui-monospace,monospace;overflow-wrap:anywhere}
mark{background:#236c4f;color:#fff;padding:2px 5px;border-radius:4px}
@media(max-width:620px){li .row>*{width:100%}}@media print{.controls,button{display:none}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / REAL PCM16 SOURCE-LOCKED REVISION</div>
<h1>Revise the<br>handoffs.</h1>
<p>Review an <strong>already completed</strong>, privately rendered hybrid
Marathon. Restore or change any previous Original/Blend transition choice;
the new mix is always a separately approved new WAV. Your prior completed
master is never edited. These are personal, unblinded human DJ decisions.</p>
<div class="stats"><div class="stat"><strong id="changes">0</strong><small>actual transition changes</small></div>
<div class="stat"><strong id="runtime">—</strong><small>estimated new real WAV runtime</small></div>
<div class="stat"><strong id="difference">—</strong><small>runtime difference vs source master</small></div></div>
<section><h2>1 / Choose what to keep or revise</h2>
<p>One manually selected real original hard cut or already approved real
crossfade at each existing boundary. No newly invented fade length, key,
tempo or sample processing. Changes show the estimated effect on actual
frame count before authorising a new CLI render.</p>
<ol id="joins"></ol>
<div class="controls"><button id="restore" type="button">Restore current decisions</button>
<button id="originals" type="button">All original hard cuts</button>
<button id="blends" type="button">All already approved crossfades</button></div>
<p id="status" role="status"></p></section>
<section id="audition" hidden><h2>Real WAV A/B before changing a decision</h2>
<p>Each source clip and its exact official private full-WAV receipt were
verified by the CLI before this page was made. There is no browser-made
fade, model audio or upload.</p>
<audio id="clip-audio" controls preload="none"></audio>
<p id="clip-status" role="status">Choose a short existing real WAV below.</p>
</section>
<section><h2>2 / Export a new exact-source revision</h2>
<p>The new local JSON names the previous finished WAV SHA-256 as
`parent_hybrid_sha256`. The renderer refuses this plan unless you supply
that <em>same completed previous WAV</em> with `--previous-hybrid`;
it also verifies the original and compared full blended source WAVs again.
Only changing a musical transition produces a new mix; if only your
private notes changed, keep the existing approved WAV and cue document.</p>
<div class="controls"><button id="export" type="button" disabled>Export new private source-bound mix revision</button></div>
<p>After export, run:<br>
<code>python3 -m mixlab.marathon_reel_decisions REVISED.json ORIGINAL/marathon.wav BLEND/marathon.wav NEW_PRIVATE_FOLDER --previous-hybrid CURRENT/marathon.wav</code></p>
<p>New full audio rendering asks for typed <strong>yes</strong>. Optional portable
music/cue USB delivery needs its own explicit approval. This page embeds
no audio or source paths, stores no cookies and cannot authorize music use.</p>
<p class="note" id="fingerprints"></p></section>
</main><script type="application/json" id="revision-data">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("revision-data").textContent);
const $=id=>document.getElementById(id);
const choices=data.joins.map(row=>row.choice);
const notes=data.joins.map(row=>row.note);
const duration=seconds=>{
 const x=Math.max(0,Math.round(seconds));
 return [Math.floor(x/3600),Math.floor(x%3600/60),x%60]
  .map(v=>String(v).padStart(2,"0")).join(":");
};
const cards=[],selects=[],textareas=[];
const clipPlayer=$("clip-audio");
$("audition").hidden=!data.reels_available;
window.addEventListener("pagehide",()=>clipPlayer.pause());
function currentFades(){return data.joins.map((join,i)=>choices[i]==="blend"?join.fade_seconds:0);}
function render(){
 let changed=0;const fades=currentFades();
 choices.forEach((choice,i)=>{
  const altered=choice!==data.joins[i].choice;
  if(altered)changed++;
  cards[i].classList.toggle("modified",altered);
  selects[i].value=choice;
 });
 const total=data.original_frames-fades.reduce((sum,value)=>sum+value*data.rate,0);
 const seconds=total/data.rate;
 const delta=seconds-data.current_duration;
 $("changes").textContent=String(changed);
 $("runtime").textContent=duration(seconds);
 $("difference").textContent=(delta>=0?"+":"−")+Math.abs(delta).toFixed(2)+"s";
 $("export").disabled=changed===0||fades.every(seconds=>seconds===0)||
  total<=0||total*4>data.max_wav_bytes;
 $("status").textContent=changed&&fades.every(value=>value===0)?
  "All joins select original: use your already-approved original master; no redundant hybrid render is needed.":
  changed?
  changed+" real transition decisions changed; approved full sources must be rechecked before rendering.":
  "Current SHA-verified master kept unchanged; change at least one transition to render a new master.";
}
data.joins.forEach((join,i)=>{
 const card=document.createElement("li");
 const row=document.createElement("div");row.className="row";
 const name=document.createElement("strong");
 name.textContent=(i+1)+". "+join.from+" → "+join.to;
 const prev=document.createElement("small");
 prev.textContent="Current master: "+(join.choice==="original"?"hard join":join.fade_seconds+"s real crossfade");
 const select=document.createElement("select");
 select.setAttribute("aria-label","New approved transition for join "+(i+1));
 for(const [value,label] of [["original","Exact original hard cut"],
  ["blend","Already rendered "+join.fade_seconds+"s crossfade"]]){
  const option=document.createElement("option");option.value=value;option.textContent=label;select.append(option);
 }
 select.addEventListener("change",()=>{choices[i]=select.value;render();});
 row.append(name,prev,select);
 const field=document.createElement("textarea");field.maxLength=300;
 field.value=join.note;field.setAttribute("aria-label","Private operator note for join "+(i+1));
 field.addEventListener("input",()=>{notes[i]=field.value;});
 card.append(row,field);
 if(data.reels_available){
  const controls=document.createElement("div");controls.className="controls";
  for(const version of ["original","blend"]){
   const listen=document.createElement("button");listen.type="button";
   listen.textContent=version==="original"?"Hear actual hard join":"Hear actual rendered crossfade";
   listen.addEventListener("click",()=>{
    clipPlayer.pause();
    clipPlayer.src="./join-"+String(i+1).padStart(2,"0")+"-"+version+".wav";
    clipPlayer.load();
    $("clip-status").textContent="Real previously verified "+version+
     " PCM16 excerpt, not a browser-generated transition.";
    const playback=clipPlayer.play();
    if(playback)playback.catch(()=>{$("clip-status").textContent="Press Play in the player.";});
   });controls.append(listen);
  }card.append(controls);
 }
 $("joins").append(card);
 cards.push(card);selects.push(select);textareas.push(field);
});
function resetChoices(which){
 data.joins.forEach((row,i)=>{
  choices[i]=which||row.choice;notes[i]=row.note;
  textareas[i].value=row.note;
 });render();
}
$("restore").addEventListener("click",()=>resetChoices(null));
$("originals").addEventListener("click",()=>resetChoices("original"));
$("blends").addEventListener("click",()=>resetChoices("blend"));
$("fingerprints").textContent="Actual current hybrid WAV SHA-256: "+data.parent_hybrid_sha256+
 " · Official original SHA-256: "+data.original_sha256+
 " · Approved full blended WAV SHA-256: "+data.blend_sha256;
$("export").addEventListener("click",()=>{
 if($("export").disabled)return;
 const rows=data.joins.map((row,i)=>({
  index:i+1,from:row.from,to:row.to,fade_seconds:row.fade_seconds,
  choice:choices[i],note:notes[i]
 }));
 const plan={schema_version:1,kind:"mixlab-private-join-master-picks-v1",
  original_sha256:data.original_sha256,blend_sha256:data.blend_sha256,
  parent_hybrid_sha256:data.parent_hybrid_sha256,
  private_only:true,blind_study:false,joins:rows};
 const blob=new Blob([JSON.stringify(plan,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),link=document.createElement("a");
 link.href=url;link.download="mixlab-hybrid-revision.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("status").textContent="New private revision downloaded. Real PCM16 remains unchanged until you approve a separate CLI render.";
});
render();
</script></body></html>"""


def _verified_revision_context(previous_wav, original_wav, blend_wav):
    prior = Path(previous_wav).absolute()
    if prior.name != "marathon.wav":
        raise ValueError("Select a completed private hybrid marathon.wav to revise")
    (_, _), (r0, r1), fades, _ = _pair(original_wav, blend_wav)
    prev_duration, n, kind = _marathon_duration(prior.parent, prior)
    choices_path = prior.parent / "master-picks.private.json"
    choices = _read_plan(choices_path)
    receipt = _validate(prior, choices)
    if (kind != "marathon_blend" or n != len(r0["sections"]) or
            receipt["source_marathon_sha256"] != r0["wav_sha256"] or
            choices["source_blend_sha256"] != r1["wav_sha256"] or
            len(choices["joins"]) != len(fades)):
        raise ValueError("The existing human-picked master is not related to these exact original and blended sources")
    for i, (row, fade) in enumerate(zip(choices["joins"], fades)):
        if row["fade_seconds"] != fade or (
                row["fade_seconds"] if row["choice"] == "blend" else 0
            ) != receipt["fade_seconds_by_join"][i]:
            raise ValueError("Existing original-versus-crossfade decisions disagree with the approved real source fade")
    return r0, r1, choices, receipt, prev_duration


def create_revision_desk(previous_wav, original_wav, blend_wav, new_private_html,
                         *, reels_folder=None):
    r0, r1, decisions, receipt, previous_duration = _verified_revision_context(
        previous_wav, original_wav, blend_wav)
    target = _private_html_destination(new_private_html)
    if reels_folder is not None:
        from .marathon_reels_transfer import _inspect
        if Path(reels_folder).absolute() != target.parent:
            raise ValueError("Private revision page and verified real reels must share one folder")
        approved, _ = _inspect(reels_folder)
        if (approved["original_sha256"] != r0["wav_sha256"] or
                approved["blend_sha256"] != r1["wav_sha256"] or
                approved["rate"] != r0["rate"] or
                len(approved["joins"]) != len(decisions["joins"])):
            raise ValueError("Real WAV reels do not belong to these approved masters")
        for i, pair in enumerate(approved["joins"]):
            if (pair["from"] != r0["sections"][i]["label"] or
                    pair["to"] != r0["sections"][i+1]["label"] or
                    pair["fade_seconds"] != decisions["joins"][i]["fade_seconds"]):
                raise ValueError("Verified short original/blend reels have different join labels or fades")
    data = {
        "original_sha256": r0["wav_sha256"],
        "blend_sha256": r1["wav_sha256"],
        "parent_hybrid_sha256": receipt["wav_sha256"],
        "current_duration": previous_duration, "original_frames": r0["frames"],
        "rate": r0["rate"], "max_wav_bytes": 768 * 1024 * 1024,
        "reels_available": reels_folder is not None,
        "joins": decisions["joins"]
    }
    serialized = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    for bad, good in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        serialized = serialized.replace(bad, good)
    payload = _PAGE.replace("__DATA__", serialized).encode("utf-8")
    if not 0 < len(payload) <= MAX_HTML:
        raise ValueError("Private hybrid revision studio exceeds offline size budget")
    with target.open("xb") as out:
        try:
            os.fchmod(out.fileno(), 0o600)
            out.write(payload)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return {"private_revision_studio": str(target),
            "actual_parent_wav_sha256": receipt["wav_sha256"],
            "approved_source_original_sha256": r0["wav_sha256"],
            "approved_source_blend_sha256": r1["wav_sha256"],
            "joins": len(decisions["joins"]), "contains_audio": False,
            "verified_real_reels": reels_folder is not None,
            "has_source_paths": False, "music_rights_proven": False,
            "blind_preference_proven": False}


def main():
    parser = argparse.ArgumentParser(
        description="Make a local operator desk to revise real approved original/blend joins in a finished private hybrid Marathon")
    parser.add_argument("existing_hybrid_marathon_wav")
    parser.add_argument("original_marathon_wav")
    parser.add_argument("approved_blended_marathon_wav")
    parser.add_argument("new_private_mixlab_revision_html")
    parser.add_argument("--reels-folder", help="Existing verified real original-vs-blend Join Reel folder; new revision HTML must be in it")
    args = parser.parse_args()
    try:
        result = create_revision_desk(
            args.existing_hybrid_marathon_wav,
            args.original_marathon_wav, args.approved_blended_marathon_wav,
            args.new_private_mixlab_revision_html,
            reels_folder=args.reels_folder)
    except (ValueError, KeyError, TypeError, OSError, wave.Error, UnicodeError):
        parser.exit(2, "MixLab revision: previous real WAV, source receipts, privacy or new HTML destination unavailable.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
