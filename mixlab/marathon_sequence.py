"""Offline original-event playlist editor; renders through canonical private Marathon.

Plan files bind to exact already-approved event audio receipts, but are not
cryptographically signed. No media is embedded, uploaded or auto-approved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import wave
import zipfile

from .event_marathon import MAX_BYTES, MAX_EVENTS, _admit, _new_folder, create_marathon

PLAN_KIND = "mixlab-private-marathon-sequence-v1"
MAX_PLAN = 65536
MAX_PAGE = 512 * 1024

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; media-src blob:; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / Private Marathon Sequence Studio</title><style>
:root{color-scheme:dark;--bg:#091520;--card:#1a2b3b;--mint:#a5f6d0;--txt:#ecf7ff;--muted:#bbcbda;--edge:#486477}
*{box-sizing:border-box}body{background:radial-gradient(at 80% 0%,#20534c,var(--bg) 60%);color:var(--txt);font:15px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1130px;margin:auto;padding:clamp(20px,5vw,62px)}h1{font-size:clamp(39px,7vw,76px);line-height:1.02;letter-spacing:-.05em;margin:10px 0}h2{font-size:21px;margin:4px 0 16px}
.eyebrow{color:var(--mint);font-weight:850;letter-spacing:.14em;font-size:12px}p,small{color:var(--muted)}
.panel{border:1px solid var(--edge);background:var(--card);border-radius:20px;padding:clamp(18px,4vw,28px);margin:20px 0}
.numbers{display:flex;gap:15px;flex-wrap:wrap;margin:17px 0}.stat{flex:1;min-width:140px;border:1px solid var(--edge);border-radius:14px;padding:16px;background:#112333}
.stat strong{display:block;font-size:32px;font-variant-numeric:tabular-nums;color:var(--mint)}
ol{list-style:none;margin:0;padding:0;display:grid;gap:11px}
li{display:flex;flex-wrap:wrap;gap:12px;align-items:center;border:1px solid var(--edge);border-radius:15px;padding:12px 16px;background:#102537}
li.muted{opacity:.65}li .name{flex:1;min-width:160px;overflow-wrap:anywhere;font-size:18px;font-weight:800}
li small{display:block;font-size:12px;font-weight:500}li .index{font-variant-numeric:tabular-nums;color:var(--mint);font-weight:900}
button,.action{background:#264d5b;border:1px solid #76929a;border-radius:10px;color:var(--txt);padding:11px 14px;font:inherit;font-weight:800;cursor:pointer}
button:hover,.action:hover{background:#396876}button:disabled{opacity:.45;cursor:not-allowed}
button:focus-visible,input:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
.actions{display:flex;gap:11px;flex-wrap:wrap;margin:20px 0}
.join-row{display:flex;align-items:center;flex-wrap:wrap;gap:13px;padding:14px 0}
.join-row label{font-weight:750}
select{background:#102735;color:#f3ffff;padding:9px;border:1px solid #77989e;border-radius:9px;font:inherit}
.join-item{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
.join-item label{font-size:12px;color:#a8ffdc}
.join-item select{min-width:100px}
#audition-panel{background:#102838;border:1px solid #5d8990;border-radius:15px;padding:18px;margin:20px 0}
#audition-panel audio{display:block;width:100%;margin:11px 0}
.preview-pickers{display:flex;flex-wrap:wrap;align-items:center;gap:8px;flex-basis:100%}
.preview-pickers input{max-width:270px;font-size:12px}
.preview-pickers small{flex:1;min-width:130px}
.preview-pickers button{padding:8px 11px;font-size:12px}
.preview-controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.preview-controls label{font-weight:750}
#audition-message{font-size:13px;color:#bdffdd}


.notice{border-left:4px solid var(--mint);padding:11px 16px;background:#0c2530}
code{overflow-wrap:anywhere}.hash{font:11px ui-monospace,monospace;word-break:break-all}
@media(max-width:700px){li button{padding:9px}li .name{flex-basis:100%}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / PRIVATE MARATHON ARRANGEMENT</div>
<h1>Arrange the<br>whole night.</h1>
<p>Build a deliberate sequence from completed receipt-verified MixLab sets. Move entire events up or down,
temporarily exclude one, and export the source-bound render plan. This page contains no audio or source paths.</p>
<section class="panel"><h2>Exact available masters</h2><div class="numbers">
<div class="stat"><strong id="count">—</strong><span>selected events</span></div>
<div class="stat"><strong id="time">—</strong><span>estimated continuous runtime</span></div>
<div class="stat"><strong id="size">—</strong><span>new WAV size</span></div></div>
<ol id="ordered" aria-label="Reorder completed event masters"></ol>
<p id="notice" class="notice" role="status"></p>
<section id="audition-panel"><h2>Audition original local audio — optional</h2>
<p>Select each <em>original permitted completed WAV</em> with its file picker in the list above.
Only the expected filename and byte length are checked here. The canonical render CLI
checks full original SHA-256 and receipt again. The browser never uploads files;
selected media stays in this tab as local blob URLs.</p>
<div class="preview-controls"><label for="preview-join">Adjacent handoff</label><select id="preview-join"></select>
<button id="preview-pair" type="button">Listen to approximate manual fade</button>
<button id="preview-stop" type="button">Stop all local audio</button></div>
<audio id="preview-out" controls preload="none" aria-label="Outgoing approved local WAV"></audio>
<audio id="preview-in" controls preload="none" aria-label="Incoming approved local WAV"></audio>
<p id="audition-message" role="status">Attach WAV files by hand before listening.
Browser overlap is only an approximate cue preview, NOT the actual MixLab PCM renderer.
Always review the final rendered WAV yourself before any event.</p></section>
<div class="join-row"><label for="join-mode">Real output transition style</label>
<select id="join-mode"><option value="hard_cuts">Original sample-exact joins (one output WAV)</option>
<option value="manual_crossfades">Separate manually blended WAV with per-join fades</option></select></div>
<p id="join-info">The default preserves original audio frames. Blended export requires a separate output directory and an extra explicit approval.</p>
<div class="actions"><button type="button" id="reset">Reset original sequence</button>
<button type="button" id="export">Export exact-source render plan</button></div>
</section>
<section class="panel"><h2>How to get the real mix</h2><p>
1. Export the new private <code>mixlab-marathon-sequence.private.json</code> from this page.
2. Run the original command with <code>render</code> and pass the **same SESSION WAV pairs in their original input order**.
3. For manually blended output add <code>--blend-output /private/new-separate-blended-marathon</code>. The app makes the unchanged original WAV first, then renders the chosen real crossfades in the new separate folder. Review the actual names, fade seconds and source permissions in your terminal. MixLab still asks you to type
<code>yes</code> before any new private WAV is created. Optional ZIP, showbook and local mobile formats use
the existing official Marathon production steps.</p>
<p>Changing, deleting or replacing any original master invalidates this plan. The browser only chooses
a track order; it does not encode, resample, crossfade, beatmatch or prove music rights.</p>
<p class="hash" id="fingerprint"></p></section>
</main><script id="data" type="application/json">__DATA__</script><script>
"use strict";
const source=JSON.parse(document.getElementById("data").textContent);
const $=id=>document.getElementById(id);
const all=source.originals;
let order=all.map((_,i)=>i);
let selected=new Set(order);
const fadeByIncoming=new Map(all.map((_,i)=>[i,8]));
const privateMedia=new Map();
let previewAnimation=null;
const previewOut=$("preview-out"),previewIn=$("preview-in");
const previewStatus=message=>{$("audition-message").textContent=message;};
function stopPreview(){
 if(previewAnimation!==null){cancelAnimationFrame(previewAnimation);previewAnimation=null;}
 previewOut.pause();previewIn.pause();
 previewOut.ontimeupdate=null;previewIn.ontimeupdate=null;
 previewOut.volume=1;previewIn.volume=1;
}
function unloadMedia(index){
 const old=privateMedia.get(index);
 if(old){stopPreview();URL.revokeObjectURL(old.url);privateMedia.delete(index);}
}
window.addEventListener("pagehide",()=>{
 stopPreview();for(const item of privateMedia.values())URL.revokeObjectURL(item.url);
 privateMedia.clear();
});

const clock=s=>{
 let t=Math.round(s);const h=Math.floor(t/3600);t%=3600;
 return String(h).padStart(2,"0")+":"+String(Math.floor(t/60)).padStart(2,"0")+":"+String(t%60).padStart(2,"0");
};
function render(){
 const root=$("ordered");root.replaceChildren();
 order.forEach((idx,position)=>{
  const entry=all[idx],active=selected.has(idx);
  const row=document.createElement("li");row.className=active?"":"muted";
  const check=document.createElement("input");check.type="checkbox";check.checked=active;
  check.setAttribute("aria-label","Include event "+(idx+1)+" "+entry.label);
  check.addEventListener("change",()=>{if(check.checked)selected.add(idx);else selected.delete(idx);render();});
  const name=document.createElement("div");name.className="name";
  name.textContent=entry.label;
  const meta=document.createElement("small");
  meta.textContent="Original event "+(idx+1)+" · "+clock(entry.frames/entry.rate)+" · "+entry.rate+" Hz";
  name.append(meta);
  const number=document.createElement("span");number.className="index";
  number.textContent="#"+(position+1);
  const up=document.createElement("button");up.type="button";up.textContent="↑ Up";
  up.disabled=position===0;up.setAttribute("aria-label","Move "+entry.label+" earlier");
  up.addEventListener("click",()=>{[order[position-1],order[position]]=[order[position],order[position-1]];render();});
  const down=document.createElement("button");down.type="button";down.textContent="↓ Down";
  down.disabled=position===order.length-1;down.setAttribute("aria-label","Move "+entry.label+" later");
  down.addEventListener("click",()=>{[order[position+1],order[position]]=[order[position],order[position+1]];render();});
  const chosen=order.filter(id=>selected.has(id));
  if(active&&chosen[0]!==idx&&$("join-mode").value==="manual_crossfades"){
   const wrap=document.createElement("span");wrap.className="join-item";
   const hint=document.createElement("label");hint.textContent="Incoming fade:";
   const select=document.createElement("select");
   select.setAttribute("aria-label","Audio fade into "+entry.label);
   [2,4,8,16].forEach(sec=>{
    const option=document.createElement("option");option.value=String(sec);
    option.textContent=sec+" seconds";select.append(option);
   });
   select.value=String(fadeByIncoming.get(idx)||8);
   select.addEventListener("change",()=>{fadeByIncoming.set(idx,Number(select.value));render();});
   wrap.append(hint,select);row.append(wrap);
  }
  const mediaLine=document.createElement("div");mediaLine.className="preview-pickers";
  const file=document.createElement("input");file.type="file";file.accept=".wav,audio/wav";
  file.setAttribute("aria-label","Attach local source for "+entry.label);
  const attached=document.createElement("small");
  attached.textContent=privateMedia.has(idx)?"Private WAV attached in this tab":"No media loaded";
  const first=document.createElement("button");first.type="button";first.textContent="Listen opening";
  const last=document.createElement("button");last.type="button";last.textContent="Listen closing";
  first.disabled=last.disabled=!privateMedia.has(idx);
  first.addEventListener("click",()=>playClip(idx,false));
  last.addEventListener("click",()=>playClip(idx,true));
  file.addEventListener("change",()=>{
   const incoming=file.files&&file.files[0];
   if(!incoming)return;
   if(incoming.name!==entry.wav_name||incoming.size!==entry.size_bytes){
    unloadMedia(idx);previewStatus("Rejected attachment for "+entry.label+
      ": name or byte size differs. Browser cannot certify a WAV; canonical CLI checks SHA.");
    render();return;
   }
   unloadMedia(idx);
   privateMedia.set(idx,{url:URL.createObjectURL(incoming)});
   previewStatus("Local WAV attached for "+entry.label+". Browser has NOT verified its SHA.");
   render();
  });
  mediaLine.append(file,attached,first,last);
  row.prepend(check,number,name,up,down);row.append(mediaLine);root.append(row);
 });
 const chosen=order.filter(i=>selected.has(i));
 const frames=chosen.reduce((n,i)=>n+all[i].frames,0);
 const seconds=chosen.reduce((n,i)=>n+all[i].frames/all[i].rate,0);
 const select=$("preview-join");
 const previous=Number(select.value)||0;select.replaceChildren();
 for(let i=0;i<chosen.length-1;i++){
  const option=document.createElement("option");option.value=String(i);
  option.textContent=all[chosen[i]].label+" → "+all[chosen[i+1]].label;
  select.append(option);
 }
 select.value=String(Math.min(previous,Math.max(0,chosen.length-2)));
 $("preview-pair").disabled=chosen.length<2||$("join-mode").value!=="manual_crossfades";
 $("count").textContent=String(chosen.length);
 $("time").textContent=clock(seconds);
 $("size").textContent=(frames*4/1048576).toFixed(1)+" MiB";
 const blending=$("join-mode").value==="manual_crossfades";
 const fades=chosen.slice(1).map(i=>fadeByIncoming.get(i)||8);
 const overlapFeasible=!blending||chosen.every((i,j)=>{
  const incoming=j?fades[j-1]:0, outgoing=j<fades.length?fades[j]:0;
  return all[i].frames > (incoming+outgoing)*all[i].rate;
 });
 const valid=chosen.length>=2&&chosen.length<=8&&frames*4<=source.max_pcm_bytes&&overlapFeasible;
 $("export").disabled=!valid;
 $("join-info").textContent=blending?
  "A new original WAV and a separate genuinely blended WAV will be rendered. Both require explicit operator approval. Fade lengths are tied to each incoming set.":
  "Default: one sample-exact original WAV, without additional audio processing.";
 $("notice").textContent=!overlapFeasible?
  "At least one completed set is too short for its incoming and outgoing fades. Choose shorter fades.":
  !valid?"Select 2–8 finished sets within the 768 MiB master WAV budget.":
  "Ready to export "+chosen.length+" source-bound event decisions. Actual renders require human approval.";
}
$("reset").addEventListener("click",()=>{
 order=all.map((_,i)=>i);selected=new Set(order);fadeByIncoming.clear();
 all.forEach((_,i)=>fadeByIncoming.set(i,8));$("join-mode").value="hard_cuts";render();
});
$("join-mode").addEventListener("change",render);
$("export").addEventListener("click",()=>{
 const chosen=order.filter(i=>selected.has(i));
 if(chosen.length<2||chosen.length>8)return;
 const doc={schema_version:1,kind:source.kind,
  source_identity:source.originals.map(({sha256,frames,rate})=>({sha256,frames,rate})),
  selected_indices:chosen,
  blend_mode:$("join-mode").value,
  fade_seconds_by_join:$("join-mode").value==="manual_crossfades"?
   chosen.slice(1).map(i=>fadeByIncoming.get(i)||8):[]};
 const blob=new Blob([JSON.stringify(doc,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;
 a.download="mixlab-marathon-sequence.private.json";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("notice").textContent="Private plan saved. Hand it to the CLI with the original SESSION/WAV pairs.";
});

function safeDuration(media,entry){
 const expected=entry.frames/entry.rate;
 return Number.isFinite(media.duration)&&media.duration>0&&
  Math.abs(media.duration-expected)<0.3;
}
function admitBrowserMedia(element,index){
 return new Promise((resolve,reject)=>{
  const entry=all[index],attached=privateMedia.get(index);
  if(!attached){reject(new Error("Source WAV is not attached"));return;}
  element.onloadedmetadata=()=>{
   if(!safeDuration(element,entry)){reject(new Error("Browser WAV duration differs from original receipt"));return;}
   resolve(element.duration);
  };
  element.onerror=()=>reject(new Error("Browser could not decode the selected local WAV"));
  element.src=attached.url;element.load();
 });
}
async function playClip(index,tail){
 stopPreview();
 try{
  const duration=await admitBrowserMedia(previewOut,index);
  const start=tail?Math.max(0,duration-12):0;
  previewOut.currentTime=start;previewIn.removeAttribute("src");previewIn.load();
  const end=Math.min(duration,start+12);
  previewOut.ontimeupdate=()=>{
   if(previewOut.currentTime>=end-0.05){previewOut.pause();previewOut.ontimeupdate=null;}
  };
  await previewOut.play();
  previewStatus("Rehearsing "+all[index].label+" locally; "+
    (tail?"last":"first")+" 12 seconds. Source SHA is NOT browser-verified.");
 }catch(_){previewStatus("Browser playback unavailable, or the selected WAV duration did not match. Check local media and use a native player.");}
}
async function playJoinedPreview(){
 const chosen=order.filter(i=>selected.has(i));
 const pos=Number($("preview-join").value);
 if($("join-mode").value!=="manual_crossfades"||!Number.isInteger(pos)||
    pos<0||pos>=chosen.length-1)return;
 const from=chosen[pos],to=chosen[pos+1],fade=fadeByIncoming.get(to)||8;
 if(!privateMedia.has(from)||!privateMedia.has(to)){
  previewStatus("Attach both original local WAVs with their row pickers before previewing this handoff.");
  return;
 }
 stopPreview();
 try{
  const durations=await Promise.all([admitBrowserMedia(previewOut,from),
                                     admitBrowserMedia(previewIn,to)]);
  const originalStart=Math.max(0,durations[0]-fade);
  previewOut.currentTime=originalStart;previewIn.currentTime=0;
  previewOut.volume=1;previewIn.volume=0;
  await Promise.all([previewOut.play(),previewIn.play()]);
  const tick=()=>{
   if(previewOut.paused||previewIn.paused){stopPreview();return;}
   const fraction=Math.min(1,Math.max(0,(previewOut.currentTime-originalStart)/fade));
   previewOut.volume=1-fraction;previewIn.volume=fraction;
   if(fraction>=1){stopPreview();previewStatus("Approximate browser handoff ended. The canonical PCM renderer is separate.");return;}
   previewAnimation=requestAnimationFrame(tick);
  };
  tick();
  previewStatus("Local approximately simultaneous "+fade+"s gain-fade prelisten: "+
   all[from].label+" → "+all[to].label+". This is NOT an exact audio render or SHA proof.");
 }catch(_){
  stopPreview();previewStatus("Local overlap preview could not start. Browser codec/playback permissions vary. The canonical CLI still renders offline.");
 }
}
$("preview-pair").addEventListener("click",playJoinedPreview);
$("preview-stop").addEventListener("click",()=>{stopPreview();previewStatus("Local audio stopped.");});
$("fingerprint").textContent="Private original event receipt SHA-256 fingerprints: "+
 all.map(x=>x.sha256.substring(0,16)).join(" / ");
render();
</script></body></html>"""


def _source_identity(items):
    return [{"sha256": x["wav_sha256"], "frames": x["frames"], "rate": x["rate"]}
            for x in items]


def _admit_pairs(raw):
    if not (4 <= len(raw) <= MAX_EVENTS * 2 and len(raw) % 2 == 0):
        raise ValueError("Provide 2–8 original SESSION WAV argument pairs")
    pairs = list(zip(raw[0::2], raw[1::2]))
    items = [_admit(session, wav) for session, wav in pairs]
    if len({item["wav"] for item in items}) != len(items):
        raise ValueError("The same completed event master may not be supplied twice")
    if len({item["rate"] for item in items}) != 1:
        raise ValueError("Original completed events have differing PCM sample rates")
    return pairs, items


def _private_html_destination(path):
    output = Path(path).absolute()
    if (output.suffix.lower() != ".html" or not output.name.startswith("mixlab-") or
            output.exists() or output.is_symlink() or not output.parent.is_dir()):
        raise ValueError("Choose a NEW private MixLab HTML file outside source repositories")
    if any(part.is_symlink() or (part / ".git").exists() for part in (output.parent, *output.parents)):
        raise ValueError("Source-path symlink and Git publication boundaries are not permitted")
    return output


def _read_plan(path):
    source = Path(path).absolute()
    if (source.suffix.lower() != ".json" or source.is_symlink() or
            any(p.is_symlink() for p in source.parents)):
        raise ValueError("Choose a regular non-symlink local private JSON plan")
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= MAX_PLAN:
            raise ValueError("Private render plan is missing, oversized or not regular")
        body = stream.read(MAX_PLAN + 1)
        after = os.fstat(stream.fileno())
        if (len(body) != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                 after.st_ctime_ns)):
            raise ValueError("Private render plan changed while reading")
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid private render plan JSON") from exc


def prepare_page(new_private_html, *source_pairs):
    pairs, items = _admit_pairs(source_pairs)
    # All originals may exceed one WAV; the DJ can exclude events in the editor.
    # The exact 768 MiB cap is enforced on the *selected* render plan.
    dest = _private_html_destination(new_private_html)
    data = {"kind": PLAN_KIND, "max_pcm_bytes": MAX_BYTES,
            "originals": [{**identity, "label": x["wav"].parent.name,
                           "wav_name": x["wav"].name, "size_bytes": x["stamp"][2]}
                          for x, identity in zip(items, _source_identity(items))]}
    text = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    payload = _HTML.replace("__DATA__", text).encode("utf-8")
    if len(payload) > MAX_PAGE:
        raise ValueError("Offline set-order editor exceeds its private size budget")
    with dest.open("xb") as stream:
        try:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
    return {"private_sequence_studio": str(dest), "original_event_count": len(pairs),
            "private": True, "music_embedded": False, "auto_approved": False}


def compile_sequence(plan_path, new_private_folder, *source_pairs, start=None,
                     blend_output=None, review_output=None, reels_output=None, reels_usb=False,
                     bundle=False, delivery=None,
                     bitrate_kbps=192, read=input, write=print):
    if type(reels_usb) is not bool or (reels_usb and reels_output is None):
        raise ValueError("Optional short-WAV USB ZIP needs an explicit --reels-output folder")
    pairs, items = _admit_pairs(source_pairs)
    plan = _read_plan(plan_path)
    if (not isinstance(plan, dict) or plan.get("schema_version") != 1 or
            plan.get("kind") != PLAN_KIND or
            plan.get("source_identity") != _source_identity(items)):
        raise ValueError("Private Marathon plan does not match all original verified source masters")
    order = plan.get("selected_indices")
    if (type(order) is not list or not 2 <= len(order) <= len(pairs) or
            any(type(i) is not int or i < 0 or i >= len(pairs) for i in order) or
            len(order) != len(set(order))):
        raise ValueError("Choose 2–8 distinct exact source events in an explicit order")
    if sum(items[i]["frames"] for i in order) * 4 > MAX_BYTES:
        raise ValueError("Planned new continuous master exceeds the WAV size budget")
    mode = plan.get("blend_mode", "hard_cuts")
    fades = plan.get("fade_seconds_by_join", [])
    if mode not in ("hard_cuts", "manual_crossfades") or type(fades) is not list:
        raise ValueError("Unsupported manual transition plan")
    if mode == "hard_cuts":
        if (fades or blend_output is not None or review_output is not None or
                reels_output is not None or reels_usb):
            raise ValueError("Hard-join plans do not accept a separate blended output")
    else:
        if blend_output is None or len(fades) != len(order) - 1 or any(
                type(v) is not int or v not in (2, 4, 8, 16) for v in fades):
            raise ValueError("Manual fades require a separate new blended folder and 2/4/8/16s choices")
        for position, index in enumerate(order):
            incoming = fades[position - 1] if position else 0
            outgoing = fades[position] if position < len(fades) else 0
            if items[index]["frames"] <= (incoming + outgoing) * items[index]["rate"]:
                raise ValueError("At least one completed event is too short for the chosen rendered audio overlaps")
        _new_folder(blend_output, [Path(new_private_folder).absolute()])
    selected = [pairs[i] for i in order]
    write("MixLab exact-source browser arrangement, not a musical compatibility score.")
    write("Chosen event order: " + ", ".join(items[i]["wav"].parent.name for i in order))
    if mode == "manual_crossfades":
        write("Selected actual PCM fades by join: " + ", ".join(str(v) + "s" for v in fades))
        write("First confirm the original source-preserving master; a SECOND human approval is required for the separate rendered blended WAV.")
    original = create_marathon(new_private_folder, *selected, read=read, write=write,
                               start=start, bundle=bundle if mode == "hard_cuts" else False,
                               delivery=delivery if mode == "hard_cuts" else None,
                               bitrate_kbps=bitrate_kbps)
    if mode == "hard_cuts":
        return original
    result = {"original": original, "blended_marathon": None,
              "original_retained": True}
    try:
        from .marathon_blend import publish_blended_marathon
        result["blended_marathon"] = publish_blended_marathon(
            original["continuous_wav"], blend_output, join_fades=tuple(fades),
            read=read, write=write, start=start, bundle=bundle,
            delivery=delivery, bitrate_kbps=bitrate_kbps)
    except (ValueError, TypeError, KeyError, OSError, wave.Error, zipfile.BadZipFile,
            subprocess.SubprocessError, EOFError):
        result["blended_warning"] = (
            "The original verified Marathon remains available; its optional "
            "separate blended master was not published. Inspect local input "
            "format, available resources and explicit approval before retrying.")
    if review_output is not None:
        if result["blended_marathon"] is None:
            result["master_review_warning"] = (
                "No blended master was published. Both original and blended "
                "real WAVs are required to generate a useful A/B listening page.")
        else:
            try:
                from .marathon_master_review import create_review
                result["private_master_review"] = create_review(
                    original["continuous_wav"],
                    result["blended_marathon"]["continuous_wav"], review_output)
            except (ValueError, TypeError, KeyError, OSError, wave.Error):
                result["master_review_warning"] = (
                    "Both original and blended WAVs remain intact; an optional "
                    "private actual-master review page could not be generated. "
                    "Run mixlab.marathon_master_review prepare manually.")
    if reels_output is not None:
        if result["blended_marathon"] is None:
            result["join_reels_warning"] = (
                "No separate approved blended WAV was published; the genuine "
                "original/blend handoff excerpts could not be created.")
        else:
            try:
                from .marathon_join_reels import create_join_reels
                result["actual_join_reels"] = create_join_reels(
                    original["continuous_wav"],
                    result["blended_marathon"]["continuous_wav"],
                    reels_output, read=read, write=write)
                if reels_usb:
                    try:
                        from .marathon_reels_transfer import export_reels
                        result["join_reels_usb"] = export_reels(
                            reels_output,
                            Path(reels_output).absolute() / "join-reels.private.zip")
                    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile):
                        result["join_reels_usb_warning"] = (
                            "The original and blended masters and actual short PCM "
                            "reels were retained. Only the optional compressed-free "
                            "private ZIP failed; run mixlab.marathon_reels_transfer "
                            "pack to retry.")
            except (ValueError, TypeError, KeyError, OSError, wave.Error, EOFError):
                result["join_reels_warning"] = (
                    "Actual original and approved blended WAVs are retained. "
                    "The optional source-bound short WAV listening room was "
                    "not published; retry independently with "
                    "python3 -m mixlab.marathon_join_reels.")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Arrange original approved local MixLab event masters in an offline browser, then render a real new WAV")
    subs = parser.add_subparsers(dest="command", required=True)
    editor = subs.add_parser("prepare", help="Make local reorder/exclude HTML from exact private WAV receipts")
    editor.add_argument("new_private_html")
    editor.add_argument("session_wav_pairs", nargs="+", help="Original SESSION WAV pairs, in fixed input order")
    publish = subs.add_parser("render", help="Compile SHA-bound human order into real separate Marathon WAV")
    publish.add_argument("private_plan_json")
    publish.add_argument("new_private_folder")
    publish.add_argument("session_wav_pairs", nargs="+", help="SAME original SESSION WAV pairs as prepare")
    publish.add_argument("--start", help="Optional planned HH:MM local show start")
    publish.add_argument("--blend-output", help="Mandatory NEW private folder when the exported plan includes actual audio crossfades")
    publish.add_argument("--review-output", help="Optional NEW local mixlab-*.html in an existing private folder; auto-build actual original-versus-blend review after both render approvals")
    publish.add_argument("--reels-output", help="Optional NEW private folder of genuine PCM16 A/B handoff excerpts, after both human-approved real Marathon masters exist")
    publish.add_argument("--reels-usb", action="store_true", help="Also make an explicitly requested portable ZIP containing ONLY the approved short real Join Reels, requires --reels-output")
    publish.add_argument("--bundle", action="store_true", help="Optional separate private ZIP")
    publish.add_argument("--delivery", choices=("mp3", "flac"), help="Optional installed FFmpeg delivery")
    publish.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320), default=192)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare_page(args.new_private_html, *args.session_wav_pairs)
        else:
            result = compile_sequence(args.private_plan_json, args.new_private_folder,
                                      *args.session_wav_pairs, start=args.start,
                                      blend_output=args.blend_output,
                                      review_output=args.review_output,
                                      reels_output=args.reels_output,
                                      reels_usb=args.reels_usb,
                                      bundle=args.bundle, delivery=args.delivery,
                                      bitrate_kbps=args.bitrate_kbps)
    except (ValueError, KeyError, TypeError, OSError, EOFError, KeyboardInterrupt,
            wave.Error, zipfile.BadZipFile, subprocess.SubprocessError):
        parser.exit(2, "MixLab Marathon Sequence: private original sources, operator plan, approval or new output unavailable.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
