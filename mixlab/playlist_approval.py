"""Private offline approvals form and strict bridge to the canonical Playlist Studio.

A browser-entered rights declaration is *not* a license. The existing
source-hash-bound import, cue bounds and user confirmation stay mandatory.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from .ingest import RIGHTS
from .journey import (
    PLAN_KIND, _private_json_path, _read_json, _source_root, load_journey,
)
from .project_wizard import _nonblank

KIND = "mixlab-private-approved-playlist-v1"
MAX_FORM = 1024 * 1024

_PAGE = r"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Approve Your Set</title>
<style>
:root{color-scheme:dark;--ink:#ecf4ff;--dim:#adbbd1;--panel:#192539;--line:#3a526e;--mint:#79f2bc;--bg:#091421}
*{box-sizing:border-box}body{background:radial-gradient(at 85% 0,#1d424c,var(--bg) 62%);color:var(--ink);font:15px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1080px;padding:clamp(16px,4vw,56px);margin:auto}
h1{font-size:clamp(32px,5vw,53px);line-height:1.12;margin:8px 0}h2{font-size:23px}
p,small{color:var(--dim)}.eyebrow{font-size:12px;font-weight:800;letter-spacing:.18em;color:var(--mint)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:21px;padding:clamp(17px,2.5vw,27px);margin:20px 0}
.song{border:1px solid #3c5067;border-radius:13px;padding:17px;margin:12px 0;background:#101e30}
.row{display:grid;grid-template-columns:1fr 1fr;gap:15px}
label{display:grid;gap:5px;font-size:13px;font-weight:700;margin:9px 0}
input,select{background:#101b2b;border:1px solid #66809b;border-radius:10px;color:var(--ink);font:inherit;width:100%;padding:11px 12px}
input:focus-visible,select:focus-visible,button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
strong{overflow-wrap:anywhere}.meta{font-size:12px;color:var(--dim)}
button{border:0;border-radius:11px;background:var(--mint);font:inherit;font-weight:800;padding:14px 20px;cursor:pointer;color:#092519}
button:hover{background:#abffda}button:disabled{opacity:.45;cursor:not-allowed}
.notice{border-left:4px solid #89b6ef;padding:8px 15px;color:var(--dim);margin:20px 0}
.check{display:flex;gap:10px;align-items:start;font-size:14px}.check input{width:auto;margin-top:5px;accent-color:var(--mint)}
.feedback{min-height:24px;font-weight:600}.bad{color:#ffaeac}.good{color:var(--mint)}
@media(max-width:650px){.row{grid-template-columns:1fr}.card{padding:16px}}
</style>
</head>
<body><main>
<div class="eyebrow">MIXLAB / HUMAN CUE APPROVAL</div>
<h1>Approve your set, on one screen.</h1>
<p>Provide the actual usage-rights basis and exact checked audio cue seconds for each transition. This is a private local form, **not** automatic downbeat detection or an online licensing check.</p>
<div class="notice"><strong>Before you begin:</strong> listen to your permitted local recordings with your own player. Enter the precise outgoing and incoming cue start seconds; they are the FIRST samples of the transition. A correct BPM and rights declaration must be based on real information, not a guess.</div>
<section class="card"><h2>Set settings</h2>
<div class="row"><label>Shared manually verified tempo
<span id="bpm" class="meta"></span></label><label for="beats">Transition length, in beats (1–64)
<input id="beats" type="number" min="1" max="64" step="1" value="16" required></label></div>
<p class="meta">Use the same --beats value when starting Playlist Studio. Changing this value changes required cue spacing.</p></section>
<section class="card"><h2>Song rights and human-verified grid</h2><div id="tracks"></div></section>
<section class="card"><h2>Transitions · exact manual start positions</h2><p>The outgoing cue must not backtrack into the previous incoming transition, whose end is B cue + transition duration.</p><div id="pairs"></div></section>
<section class="card"><h2>Consent to create a private source manifest</h2>
<label class="check"><input type="checkbox" id="rights-ack">
<span>I explicitly confirm I have a valid basis to process and use each selected track, and have manually checked the rights, BPM and cues provided above. This is my declaration, not MixLab's legal proof.</span></label>
<label class="check"><input type="checkbox" id="order-ack">
<span>I approve the displayed order and understand that MixLab will ask me to confirm it again before source import and rendering.</span></label>
<p><button id="save" type="button">Export my private approved cues</button></p>
<p id="feedback" role="status" aria-live="polite" class="feedback"></p>
<small>Save the new JSON file beside your original permitted music. The Studio rechecks source SHA-256 and validates rights/cue details again; a form download alone has not rendered, licensed or approved any media.</small>
</section>
</main><script id="seed" type="application/json">__SEED__</script>
<script>
"use strict";
const bundle=JSON.parse(document.getElementById("seed").textContent);
const tracks=bundle.entries;
const el=id=>document.getElementById(id);
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n};
function field(label,kind,attributes){
 const wrap=node("label",""),heading=node("span","",label),input=document.createElement("input");
 input.type=kind;for(const k in attributes)input.setAttribute(k,String(attributes[k]));
 wrap.append(heading,input);return {wrap,input};
}
const rights=["synthetic","licensed","user-permitted","public-domain"];
const inputs=[],pairs=[];
function build(){
 el("bpm").textContent=String(bundle.bpm)+" BPM";
 tracks.forEach((track,index)=>{
  const box=node("article","song");
  box.append(node("h3","",(index+1)+". "+track.path));
  box.append(node("p","meta","Human energy "+track.energy+"/10 · SHA-bound source · "+track.bpm+" BPM"));
  const row=node("div","row");
  const selection=node("label","");
  selection.append(node("span","","Declared source usage rights"));
  const select=document.createElement("select");select.required=true;
  select.append(new Option("Select explicit rights…","",true,true));
  rights.forEach(r=>select.append(new Option(r,r)));
  selection.append(select);row.append(selection);
  const provenance=field("Source provenance / your permission basis","text",{maxlength:300,required:"required",placeholder:"e.g. original recording by me"});
  row.append(provenance.wrap);box.append(row);
  const downbeat=field("Verified first downbeat, seconds (optional)","number",
  {min:0,max:900,step:0.001,placeholder:"Leave blank if unknown"});
  box.append(downbeat.wrap);el("tracks").append(box);
  inputs.push({select,provenance:provenance.input,downbeat:downbeat.input,track});
 });
 tracks.slice(0,-1).forEach((track,index)=>{
  const box=node("article","song");
  box.append(node("h3","",track.path+" → "+tracks[index+1].path));
  const row=node("div","row");
  const a=field("Outgoing A cue: seconds","number",
   {min:0,max:900,step:0.001,required:"required",placeholder:"Exact verified cue"});
  const b=field("Incoming B cue: seconds","number",
   {min:0,max:900,step:0.001,required:"required",placeholder:"Exact verified cue"});
  row.append(a.wrap,b.wrap);box.append(row);el("pairs").append(box);
  pairs.push({a:a.input,b:b.input});
 });
}
function numeric(input,optional=false){
 const raw=input.value.trim();
 if(!raw){if(optional)return null;throw new Error("Enter each required start position.");}
 const n=Number(raw);
 if(!Number.isFinite(n)||n<0||n>900)throw new Error("Cue/downbeat seconds must be finite values 0–900.");
 return n;
}
function show(message,error){
 const target=el("feedback");target.textContent=message;
 target.className="feedback "+(error?"bad":"good");
 target.setAttribute("role",error?"alert":"status");
}
function exportApproval(){
 try{
  const beats=Number(el("beats").value);
  if(!Number.isInteger(beats)||beats<1||beats>64)throw new Error("Transition beats must be 1–64.");
  if(!el("rights-ack").checked||!el("order-ack").checked)
   throw new Error("Confirm both the usage-rights declaration and the exact set order.");
  const declared=inputs.map(x=>{
   if(!rights.includes(x.select.value))throw new Error("Select actual rights for every song.");
   const basis=x.provenance.value.trim();
   if(!basis||basis.length>300||Array.from(basis).some(c=>c.charCodeAt(0)<32))
    throw new Error("Enter a short, printable usage-rights basis for each track.");
   return {path:x.track.path,sha256:x.track.sha256,
    rights:x.select.value,provenance:basis,
    first_downbeat_seconds:numeric(x.downbeat,true)};
  });
  let lastIncomingEnd=0, length=beats*60/bundle.bpm;
  const approvedPairs=pairs.map((p,i)=>{
   const a=numeric(p.a),b=numeric(p.b);
   if(a+1e-8<lastIncomingEnd)throw new Error("Outgoing cue "+(i+1)+" overlaps the previous incoming transition.");
   lastIncomingEnd=b+length;
   return {a_start_seconds:a,b_start_seconds:b};
  });
  const result={kind:"mixlab-private-approved-playlist-v1",plan_sha256:bundle.plan_sha256,
   declared_source_rights:true,approved_order:true,beats:beats,tracks:declared,pairs:approvedPairs};
  const blob=new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob),anchor=document.createElement("a");
  anchor.href=url;anchor.download="mixlab-event-approved.private.json";
  document.body.append(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  show("A NEW private approval file was exported. Move it beside the original music and use --approval-file with --journey-plan in Playlist Studio.",false);
 }catch(err){show(err.message||"Check the supplied manual metadata.",true)}
}
build();el("save").addEventListener("click",exportApproval);
</script>
</body></html>
"""


def prepare_form(music_folder, private_plan, new_html):
    root = _source_root(music_folder)
    plan = _private_json_path(root, private_plan, existing=True)
    html = Path(new_html).absolute()
    if (html.parent != root or html.suffix.lower() != ".html" or
            html.is_symlink() or html.exists()):
        raise ValueError("Choose a NEW private .html directly inside your music folder")
    selected = load_journey(root, plan)
    _, sha = _read_json(plan)
    embedded = json.dumps({"entries": selected, "bpm": selected[0]["bpm"],
                           "plan_sha256": sha},
                          ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    embedded = embedded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    data = _PAGE.replace("__SEED__", embedded).encode("utf-8")
    if len(data) > MAX_FORM:
        raise ValueError("Offline approval page is too large")
    with html.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)
    return html


def _seconds(value, name, optional=False):
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 900:
        raise ValueError("Invalid human-verified seconds for "+name)
    return value


def load_approval(music_folder, private_plan, private_approval, *, beats):
    """Require exact plan/file binding and validated human rights/cue fields.

    This does not mutate source media, the notes, source manifest or the plan.
    """
    root = _source_root(music_folder)
    plan = _private_json_path(root, private_plan, existing=True)
    approval = _private_json_path(root, private_approval, existing=True)
    if plan == approval:
        raise ValueError("Approval and plan must be separate private files")
    selected = load_journey(root, plan)
    _, sha = _read_json(plan)
    info, _ = _read_json(approval)
    if (info.get("kind") != KIND or info.get("plan_sha256") != sha or
            info.get("approved_order") is not True or
            info.get("declared_source_rights") is not True or
            type(beats) is not int or not 1 <= beats <= 64 or
            info.get("beats") != beats or type(info.get("beats")) is not int):
        raise ValueError("Approvals must match the exact SHA-bound plan and selected beat count")
    tracks=info.get("tracks")
    pairs=info.get("pairs")
    if (not isinstance(tracks,list) or len(tracks)!=len(selected)
            or not isinstance(pairs,list) or len(pairs)!=len(selected)-1):
        raise ValueError("Approval track and transition counts must match exact selected journey")
    approved_tracks=[]
    for i,(entry,planned) in enumerate(zip(tracks,selected)):
        if (not isinstance(entry,dict) or entry.get("path")!=planned["path"]
                or entry.get("sha256")!=planned["sha256"]
                or entry.get("rights") not in RIGHTS):
            raise ValueError("Approval has foreign track, stale SHA or unsupported rights declaration")
        basis = entry.get("provenance")
        if not isinstance(basis, str) or not basis.strip() or basis != basis.strip():
            raise ValueError("A nonblank, trimmed source permission basis is required")
        source_basis = _nonblank(basis)
        downbeat = _seconds(entry.get("first_downbeat_seconds"), "downbeat", optional=True)
        approved_tracks.append({"path":planned["path"],"sha256":planned["sha256"],
                                "rights":entry["rights"],"provenance":source_basis,
                                "first_downbeat_seconds":downbeat})
    length_seconds=beats*60/selected[0]["bpm"]
    last_incoming=0.
    approved_pairs=[]
    for i,entry in enumerate(pairs):
        if not isinstance(entry,dict):
            raise ValueError("Invalid approved transition record")
        a=_seconds(entry.get("a_start_seconds"),"outgoing cue")
        b=_seconds(entry.get("b_start_seconds"),"incoming cue")
        if a+1e-8<last_incoming:
            raise ValueError("Approved transition backtracks into previous incoming section")
        last_incoming=b+length_seconds
        approved_pairs.append({"a_start_seconds":a,"b_start_seconds":b})
    return {"tracks": approved_tracks, "pairs": approved_pairs}


def main():
    parser=argparse.ArgumentParser(description="Offline private playlist rights-and-cue approval form")
    parser.add_argument("music_directory")
    parser.add_argument("private_journey_plan")
    parser.add_argument("new_form_html")
    args=parser.parse_args()
    try:
        form=prepare_form(args.music_directory,args.private_journey_plan,args.new_form_html)
    except (ValueError,TypeError,OSError) as exc:
        parser.exit(2,"MixLab Playlist Approval: "+str(exc)+"\n")
    print(json.dumps({"offline_approval_form":str(form),"rights_proof":False,
                      "rendered":False,"uploaded":False}))


if __name__=="__main__":
    main()
