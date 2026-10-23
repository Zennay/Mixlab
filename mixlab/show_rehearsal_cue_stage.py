"""Offline, human-operated, real-WAV cue stage from a selected private rehearsal.

No browser audio or cue is embedded; live local WAV bytes must match each
original full SHA-256 before an operator can play or jump to chosen cues.
"""
from __future__ import annotations

import argparse
import json
import os
import wave

from .browser_sha256 import SHA256_BROWSER_JS
from .show_rehearsal_cuebook import load_selected, private_destination

MAX_STAGE_BYTES = 768 * 1024


def prepare_stage(new_html: str, selection_path: str, source_pairs: tuple[str, ...],
                  journals: tuple[str, ...]) -> dict:
    sources, take, _selection = load_selected(selection_path, source_pairs, journals)
    out = private_destination(new_html, selection_path, source_pairs, journals)
    content = {
        "sets": [{
            "label": src["label"], "wav_name": src["wav_name"],
            "wav_sha256": src["wav_sha256"],
            "size_bytes": src["size_bytes"], "duration_seconds": src["duration_seconds"],
            "cues": sorted(
                (mark for mark in take["marks"] if mark["set_index"] == i),
                key=lambda mark: (mark["position"], mark["seq"]),
            ),
        } for i, src in enumerate(sources)],
        "take": take["label"], "journal_sha256": take["journal_sha256"],
    }
    serialized = json.dumps(content, ensure_ascii=True, allow_nan=False,
                            separators=(",", ":")).replace("&", "\\u0026").replace(
                                "<", "\\u003c").replace(">", "\\u003e")
    page = _HTML.replace("__DATA__", serialized).replace(
        "__HASH_JS__", SHA256_BROWSER_JS
    ).encode("utf-8")
    if not 0 < len(page) <= MAX_STAGE_BYTES:
        raise ValueError("Private source-verified cue stage exceeded bounded size")
    with out.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(page)
    return {
        "private_selected_cue_stage": str(out),
        "real_original_sets": len(sources), "manually_selected_cues": len(take["marks"]),
        "source_sha256s": [s["wav_sha256"] for s in sources],
        "audio_embedded": False, "automatic_playback": False,
        "rights_or_listening_preference_proven": False,
    }


_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';media-src blob:;connect-src 'none';img-src 'none';object-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Selected private rehearsal cue stage</title>
<style>
:root{color-scheme:dark;--base:#061924;--panel:#142e3d;--edge:#6d8794;--highlight:#a6ffda}
*{box-sizing:border-box}body{margin:0;background:var(--base);color:#f2ffff;font:15px/1.5 system-ui}
main{max-width:1200px;margin:auto;padding:clamp(18px,3vw,48px)}
h1{font-size:clamp(36px,5vw,65px);line-height:1.07;margin:10px 0}
h2{font-size:22px}.tag{color:var(--highlight);font-size:12px;font-weight:800;letter-spacing:.15em}
p{color:#c5dbe2}.grid{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1.3fr);gap:18px}
section{border-radius:17px;border:1px solid var(--edge);padding:20px;background:var(--panel);margin-top:20px}
button,input{font:inherit}button{border-radius:10px;background:#286e5f;color:white;padding:10px 14px;border:1px solid #8edabb;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}
button:focus-visible,input:focus-visible{outline:3px solid var(--highlight);outline-offset:2px}
input[type=file]{max-width:100%;padding:10px}audio{width:100%}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
ol{list-style:none;padding:0;margin:0;display:grid;gap:10px}
li{border:1px solid var(--edge);padding:12px;border-radius:9px;overflow-wrap:anywhere}
li.selected{border-color:var(--highlight);background:#1e4c42}
.cue{display:flex;gap:12px;align-items:flex-start}
.cue button{flex:0 0 auto}.cue div{min-width:0}
strong{color:#ecfff7}.note{white-space:pre-wrap;overflow-wrap:anywhere;color:#d6e9ed;font-size:13px}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere;color:#afc8d1}
@media(max-width:850px){.grid{grid-template-columns:1fr}}
@media print{button,input,audio{display:none!important}body{color:black;background:white}
section,li{background:white;color:black}.note,p,.hash{color:#444}}
</style></head><body><main><div class="tag">MIXLAB · PRIVATE OPERATOR CUE STAGE</div>
<h1>Rehearse the take you chose.</h1>
<p id="heading"></p>
<p>Attach only the exact original completed WAVs you have permission to use.
Each local file is verified against its <strong>full original WAV SHA-256</strong>,
in bounded 1 MiB pieces, before controls can play or seek. Changing sets
always stops playback. No network, cookies, upload, autoplay, crossfade or
background persistence. This is not a resilient professional live DJ deck.</p>
<div class="grid"><section><h2>1 · Source-verified completed sets</h2>
<ol id="setlist"></ol></section>
<section><h2>2 · Manual cue player</h2>
<audio id="player" controls preload="metadata"></audio>
<div class="controls"><button id="prev" type="button">← Previous set</button>
<button id="next" type="button">Next set →</button>
<button id="stop" type="button">Stop / detach</button></div>
<p id="state" role="status">Select an original WAV. Playback is locked until verified.</p>
<h2>Selected rehearsal marks</h2>
<p>Press a mark only to <strong>seek</strong> within an already
verified local WAV; Play is always a separate manual action.</p>
<ol id="cue-list"></ol></section></div>
<section><h2>3 · Original source fingerprints</h2><ol id="fingerprints"></ol>
<p>This offline page carries only original WAV names/sizes/SHA-256s,
manually selected cue positions and private DJ cue annotations. Never
treat its browser time, selected take or source hashes as sound quality,
venue delivery, music licence or independent listening evidence.</p></section>
</main><script type="application/json" id="mixlab-cue-stage-data">__DATA__</script>
<script>
__HASH_JS__
"use strict";
const data=JSON.parse(document.getElementById("mixlab-cue-stage-data").textContent);
const $=id=>document.getElementById(id),audio=$("player");
const files=new Map(),epochs=data.sets.map(()=>0),rows=[];
let active=-1,objectURL=null;
function detach(){
 audio.pause();audio.removeAttribute("src");audio.load();
 if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
}
function formatted(s){
 const n=Math.max(0,Math.floor(s));return [Math.floor(n/3600),Math.floor((n%3600)/60),
  n%60].map(x=>String(x).padStart(2,"0")).join(":");
}
function arm(i){
 if(i<0||i>=data.sets.length)return;
 detach();active=i;
 rows.forEach((row,index)=>row.card.classList.toggle("selected",index===i));
 const set=data.sets[i],file=files.get(i);
 $("cue-list").replaceChildren();
 if(file){
  objectURL=URL.createObjectURL(file);
  audio.src=objectURL;audio.load();
  $("state").textContent="Original full SHA-256 verified. Press Play manually for "+set.label+".";
  audio.onloadedmetadata=()=>{
   if(!Number.isFinite(audio.duration)||Math.abs(audio.duration-set.duration_seconds)>.3){
    detach();files.delete(i);
    $("state").textContent="Audio decoded duration does not match original receipt; refused.";
   }
  };
 }else{
  $("state").textContent="No original SHA-verified WAV attached for "+set.label+". Choose file on left.";
 }
 for(const mark of set.cues){
  const li=document.createElement("li"),wrapper=document.createElement("div"),btn=document.createElement("button");
  wrapper.className="cue";btn.type="button";btn.textContent="Seek "+formatted(mark.position);
  btn.addEventListener("click",()=>{
   if(!files.has(active)||!audio.src){
    $("state").textContent="Attach the correct SHA-verified original WAV before seeking.";return;
   }
   audio.currentTime=mark.position;
   $("state").textContent="At selected operator cue WAV position "+formatted(mark.position)+
    ". Playback stays manual.";
  });
  const details=document.createElement("div"),title=document.createElement("strong"),note=document.createElement("p");
  const chapter=mark.chapter===null?"No matching chapter within 60 WAV seconds":
   "Chapter "+mark.chapter+" · "+mark.chapter_kind+" · "+
   (mark.chapter_delta>=0?"+":"")+mark.chapter_delta.toFixed(3)+" s";
  title.textContent=chapter;note.textContent=mark.note||"No private note";note.className="note";
  details.append(title,note);wrapper.append(btn,details);li.append(wrapper);$("cue-list").append(li);
 }
 if(!set.cues.length){const li=document.createElement("li");
 li.textContent="No manual cue marks for this set in the selected take.";
 $("cue-list").append(li);}
 $("prev").disabled=i===0;$("next").disabled=i===data.sets.length-1;
}
data.sets.forEach((set,i)=>{
 const li=document.createElement("li"),label=document.createElement("strong"),choose=document.createElement("input");
 label.textContent=(i+1)+". "+set.label+" · "+formatted(set.duration_seconds);
 const button=document.createElement("button");button.type="button";button.textContent="Arm set";
 const status=document.createElement("p");status.textContent="No file SHA verified.";
 choose.type="file";choose.accept=".wav,audio/wav";
 choose.setAttribute("aria-label","Choose original WAV for "+set.label);
 button.addEventListener("click",()=>arm(i));
 choose.addEventListener("change",async()=>{
  const file=choose.files?.[0];if(!file)return;
  const epoch=++epochs[i];files.delete(i);
  if(active===i)arm(i);
  if(file.name!==set.wav_name||file.size!==set.size_bytes){
   status.textContent="Rejected: original WAV filename or bytes differ.";return;
  }
  choose.disabled=true;
  try{
   const digest=await sha256LocalFile(file,percent=>{
    status.textContent="Verifying full original WAV locally: "+percent+"% (no upload).";
   });
   if(epoch!==epochs[i])return;
   if(digest!==set.wav_sha256){
    status.textContent="Rejected: complete original WAV SHA-256 differs.";return;
   }
   files.set(i,file);status.textContent="Complete original WAV SHA-256 verified.";
   if(active===i)arm(i);
  }catch(_error){status.textContent="Could not verify local WAV; playback remains locked.";}
  finally{choose.disabled=false;}
 });
 li.append(label,document.createElement("br"),button,choose,status);
 $("setlist").append(li);rows.push({card:li});
 const fingerprint=document.createElement("li");fingerprint.className="hash";
 fingerprint.textContent=(i+1)+". "+set.label+" · "+set.wav_sha256;
 $("fingerprints").append(fingerprint);
});
$("heading").textContent="Human-selected "+data.take+" · Canonical private journal "+
 data.journal_sha256.slice(0,16)+"…";
$("prev").addEventListener("click",()=>arm(active-1));
$("next").addEventListener("click",()=>arm(active+1));
$("stop").addEventListener("click",()=>{detach();$("state").textContent="Stopped and detached. Arm a verified WAV to continue.";});
audio.addEventListener("error",()=>{$("state").textContent="Browser could not decode original WAV; use a trusted native player.";});
window.addEventListener("pagehide",detach);
arm(0);
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Open a manual, source-SHA-verified offline player for selected rehearsal cues")
    parser.add_argument("new_private_mixlab_html")
    parser.add_argument("selected_private_take_json")
    parser.add_argument("session_and_wav_pairs", nargs="+")
    parser.add_argument("--journal", action="append", required=True,
                        help="Original rehearsal journal in comparison order; 2–6 required")
    args = parser.parse_args()
    try:
        result = prepare_stage(args.new_private_mixlab_html, args.selected_private_take_json,
                               tuple(args.session_and_wav_pairs), tuple(args.journal))
    except (ValueError, KeyError, OSError, TypeError, UnicodeError, wave.Error):
        parser.exit(2, "MixLab Selected Cue Stage: private WAV, journal, selection or output invalid.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
