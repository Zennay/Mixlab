"""Version-chain gallery and explicit private release of one finished hybrid WAV.

All media stay local. The HTML shows a real SHA-verified chain but does not
itself hash user-selected browser media; the CLI re-admits full WAV originals.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import wave
import zipfile
import subprocess

from .event_vault import _marathon_duration, _read_small_json
from .marathon_operator_transfer import _validate
from .marathon_sequence import _private_html_destination, _read_plan

KIND="mixlab-private-hybrid-lineage-selection-v1"
MAX_HTML=512*1024

_PAGE=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';media-src blob:;connect-src 'none';img-src 'none';object-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Genuine Hybrid Master Timeline</title>
<style>:root{color-scheme:dark;--bg:#081521;--card:#163344;--line:#426a7a;--mint:#aaffd7;--muted:#bbd6de}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 85% 0,#245846,var(--bg) 65%);color:#f1fcff;font:15px/1.5 system-ui}
main{max-width:1110px;margin:auto;padding:clamp(18px,5vw,60px)}
h1{font-size:clamp(40px,7vw,74px);letter-spacing:-.055em;line-height:1.04}
h2{font-size:24px}p,small{color:var(--muted)}.eyebrow{color:var(--mint);font-size:12px;letter-spacing:.16em;font-weight:900}
section{background:var(--card);border:1px solid var(--line);padding:clamp(17px,3vw,30px);border-radius:22px;margin:20px 0}
ol{padding:0;margin:0;list-style:none;display:grid;gap:13px}li{padding:18px;background:#0d2938;border:1px solid var(--line);border-radius:14px}
li.chosen{border-color:var(--mint);background:#1d4a43}
strong{display:block;color:var(--mint);font-size:19px}
button{background:#2c665c;color:#fff;border:1px solid #8ab1a4;font:inherit;font-weight:850;padding:13px 16px;border-radius:11px;cursor:pointer}
button:disabled{opacity:.4}button:focus-visible,input:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
audio{width:100%;margin:10px 0}.controls{display:flex;flex-wrap:wrap;gap:11px}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere}
label{cursor:pointer}input[type=file]{max-width:90%;margin:12px 0}
</style></head><body><main>
<div class="eyebrow">MIXLAB / SOURCE-VERIFIED REAL WAV HISTORY</div>
<h1>One show.<br>Many real takes.</h1>
<p>These are genuine, already fully rendered and locally SHA-receipt-verified
hybrid WAV masters. Each next version was produced with its predecessor
bound as the exact parent. Hear any private version by attaching its local
WAV manually; choose just one version for a separately approved delivery.
No browser upload, automatic version ranking or quality claim.</p>
<section><h2>1 / Finished master history</h2><ol id="versions"></ol></section>
<section><h2>2 / Preview selected real WAV (optional)</h2>
<p>Select the corresponding completed <code>marathon.wav</code> manually to
play it locally in this tab. Browser checks filename, size and duration,
<strong>not its SHA-256</strong>. The CLI re-verifies the entire actual WAV
and receipts before any packaging or new encoded output.</p>
<audio id="player" controls preload="none"></audio>
<p id="play-status" role="status">Attach a permitted local WAV in the selected version above.</p>
<div class="controls"><button type="button" id="stop">Stop local playback</button></div></section>
<section><h2>3 / Explicitly select the finished master to deliver</h2>
<p>Export a private source-bound selection JSON, then run the CLI
<code>publish</code> with the <strong>same ordered complete WAV paths</strong>.
The release asks for typed <code>yes</code>, checks the entire chain again,
and uses only existing official local delivery/ZIP code. Private operator
notes are never automatically placed in the audio package.</p>
<div class="controls"><button type="button" id="export">Export selected SHA-locked master</button></div>
<p id="status" role="status"></p>
<p class="hash" id="source-hash"></p>
</section></main><script id="data" type="application/json">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("data").textContent);
const $=id=>document.getElementById(id),player=$("player");
let selected=data.versions.length-1;
const localWav=new Map();
let activeUrl=null;
const mins=seconds=>{
 const n=Math.max(0,Math.floor(seconds));
 return [Math.floor(n/3600),Math.floor(n%3600/60),n%60]
  .map(v=>String(v).padStart(2,"0")).join(":");
};
function clearPlayer(){
 player.pause();player.removeAttribute("src");player.load();
 if(activeUrl){URL.revokeObjectURL(activeUrl);activeUrl=null;}
}
window.addEventListener("pagehide",clearPlayer);
const cards=[];
function choose(index){
 selected=index;cards.forEach((card,i)=>card.classList.toggle("chosen",i===selected));
 const source=localWav.get(index);
 clearPlayer();
 if(source){
  activeUrl=URL.createObjectURL(source);player.src=activeUrl;player.load();
  $("play-status").textContent="Local WAV selected. Only filename, size and browser duration checked. SHA must be revalidated by CLI.";
  player.onloadedmetadata=()=>{
   if(!Number.isFinite(player.duration)||
      Math.abs(player.duration-data.versions[index].duration_seconds)>0.3){
    clearPlayer();$("play-status").textContent="Browser WAV duration mismatch; choose the exact completed file.";
   }
  };
 }else $("play-status").textContent="Attach the real local WAV for this selected version.";
 $("status").textContent="Selected completed version "+(index+1)+" / "+data.versions[index].sha256.slice(0,16)+"…";
}
data.versions.forEach((version,index)=>{
 const card=document.createElement("li");
 const title=document.createElement("strong");title.textContent="Version "+(index+1)+
  " · "+mins(version.duration_seconds)+" · "+(version.changed_joins||0)+" changed joins";
 const detail=document.createElement("p");
 detail.textContent=index===0?"Earliest supplied verified finished hybrid master":
  "Parent → this actual WAV · "+version.changed_joins+" changed handoffs";
 const hash=document.createElement("small");hash.className="hash";
 hash.textContent="Actual WAV SHA-256: "+version.sha256+
  (version.parent_sha256?" · Parent "+version.parent_sha256:"");
 const select=document.createElement("button");select.type="button";
 select.textContent="Choose this completed master";
 select.addEventListener("click",()=>choose(index));
 const label=document.createElement("label");
 label.textContent="Optional local WAV for hearing: ";
 const input=document.createElement("input");input.type="file";input.accept=".wav,audio/wav";
 input.setAttribute("aria-label","Attach private actual WAV version "+(index+1));
 input.addEventListener("change",()=>{
  const file=input.files&&input.files[0];
  if(!file)return;
  if(file.name!=="marathon.wav"||file.size!==version.size_bytes){
   localWav.delete(index);
   choose(index);
   $("play-status").textContent="Rejected local WAV: basename or byte length differs from source receipt.";
   return;
  }
  localWav.set(index,file);choose(index);
 });
 label.append(input);
 card.append(title,detail,hash,select,label);
 $("versions").append(card);cards.push(card);
});
$("stop").addEventListener("click",()=>{clearPlayer();$("play-status").textContent="Local private WAV stopped and detached.";});
$("export").addEventListener("click",()=>{
 const obj={schema_version:1,kind:"mixlab-private-hybrid-lineage-selection-v1",
  original_sha256:data.original_sha256,blend_sha256:data.blend_sha256,
  versions:data.versions.map(v=>({sha256:v.sha256,parent_sha256:v.parent_sha256})),
  selected_index:selected,selected_sha256:data.versions[selected].sha256,
  private_only:true,blind_study:false};
 const file=new Blob([JSON.stringify(obj,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(file),link=document.createElement("a");
 link.href=url;link.download="mixlab-selected-hybrid-lineage.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("status").textContent="Private SHA-bound human master selection downloaded. No audio/notes uploaded or shared.";
});
$("source-hash").textContent="Original source full WAV SHA-256: "+data.original_sha256+
 " · Approved compared original blend SHA-256: "+data.blend_sha256;
choose(selected);
</script></body></html>"""


def admit_history(*wav_names):
    if not 2 <= len(wav_names) <= 8:
        raise ValueError("Select 2–8 consecutive independently completed hybrid Marathon masters")
    wavs=[Path(path).absolute() for path in wav_names]
    if len(set(wavs))!=len(wavs):
        raise ValueError("Duplicate private Marathon master in version chain")
    result=[]
    originals=None
    source_blend=None
    sections=None
    previous_choices=None
    for i,wav in enumerate(wavs):
        if wav.name!="marathon.wav":
            raise ValueError("All sources must be original private marathon.wav files")
        duration,n,kind=_marathon_duration(wav.parent,wav)
        receipt=_read_small_json(wav.parent/"marathon.receipt.private.json")
        decisions=_read_plan(wav.parent/"master-picks.private.json")
        _validate(wav,decisions)
        identity=[(section["source_sha256"],section["label"],section["frames"])
                  for section in receipt["sections"]]
        if (kind!="marathon_blend" or n<2 or
                (originals is not None and originals!=receipt["source_marathon_sha256"]) or
                (source_blend is not None and source_blend!=decisions["source_blend_sha256"]) or
                (sections is not None and identity!=sections)):
            raise ValueError("Version history is not a stable, genuine original-source set")
        parent=decisions.get("parent_hybrid_sha256")
        if i and parent!=result[-1]["sha256"]:
            raise ValueError("Revisions are not an actual adjacent SHA-verified parent-child chain")
        changed=0 if previous_choices is None else sum(
            old["choice"]!=new["choice"]
            for old,new in zip(previous_choices,decisions["joins"]))
        if i and changed==0:
            raise ValueError("A purported consecutive revision did not change actual joined audio")
        result.append({"sha256":receipt["wav_sha256"],"parent_sha256":parent,
                       "duration_seconds":duration,"size_bytes":wav.lstat().st_size,
                       "changed_joins":changed})
        originals=receipt["source_marathon_sha256"]
        source_blend=decisions["source_blend_sha256"]
        sections=identity
        previous_choices=decisions["joins"]
    return wavs, originals, source_blend, result


def prepare_gallery(new_private_html,*wav_paths):
    _,original,blend,versions=admit_history(*wav_paths)
    target=_private_html_destination(new_private_html)
    data={"original_sha256":original,"blend_sha256":blend,"versions":versions}
    payload=json.dumps(data,ensure_ascii=True,allow_nan=False,separators=(",",":"))
    payload=payload.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    html=_PAGE.replace("__DATA__",payload).encode("utf-8")
    if not 0<len(html)<=MAX_HTML:
        raise ValueError("Finished hybrid history browser page exceeds private size bound")
    with target.open("xb") as out:
        try:
            os.fchmod(out.fileno(),0o600);out.write(html)
        except BaseException:
            target.unlink(missing_ok=True);raise
    return {"private_hybrid_history_html":str(target),
            "verified_real_master_versions":len(versions),
            "latest_actual_wav_sha256":versions[-1]["sha256"],
            "source_media_embedded":False,"private":True,
            "automatic_mix_ranking":False,"music_licensing_proven":False}


def publish_selected(choice_json,*wav_paths,bundle=False,delivery=None,
                     bitrate_kbps=192,read=input,write=print):
    if not bundle and delivery is None:
        raise ValueError("Choose an explicit official private --bundle or --delivery format")
    if type(bundle) is not bool or delivery not in (None,"mp3","flac") or (
            type(bitrate_kbps) is not int or bitrate_kbps not in (128,192,256,320)):
        raise ValueError("Unsupported private release option")
    wavs,original,blend,versions=admit_history(*wav_paths)
    plan=_read_plan(choice_json)
    identity=[{"sha256":v["sha256"],"parent_sha256":v["parent_sha256"]} for v in versions]
    if (not isinstance(plan,dict) or set(plan)!={"schema_version","kind",
            "original_sha256","blend_sha256","versions","selected_index",
            "selected_sha256","private_only","blind_study"} or
            type(plan["schema_version"]) is not int or plan["schema_version"]!=1 or
            plan["kind"]!=KIND or plan["original_sha256"]!=original or
            plan["blend_sha256"]!=blend or plan["versions"]!=identity or
            type(plan["selected_index"]) is not int or
            not 0<=plan["selected_index"]<len(wavs) or
            plan["selected_sha256"]!=versions[plan["selected_index"]]["sha256"] or
            plan["private_only"] is not True or plan["blind_study"] is not False):
        raise ValueError("Private selected version differs from exact verified complete source chain")
    selected=wavs[plan["selected_index"]]
    write("MixLab explicit completed local WAV selection, not autonomous DJ preference.")
    write("Selection: version "+str(plan["selected_index"]+1))
    write("Full real selected WAV SHA-256: "+plan["selected_sha256"])
    write("Actual original source SHA-256: "+original)
    write("Release only already finished private source music permitted for this local use.")
    write("Private human notes are NOT silently included in portable audio.")
    if read("Type yes to publish this one verified, existing private hybrid master: ").strip()!="yes":
        raise ValueError("No human approval for selected private version publication")
    result={"actual_selected_master":str(selected),"selected_full_wav_sha256":plan["selected_sha256"],
            "selected_version":plan["selected_index"]+1,
            "source_wav_unchanged":True,"music_rights_proven":False}
    if delivery is not None:
        try:
            from .marathon_delivery import export_mobile_marathon
            result["private_mobile_audio"]=export_mobile_marathon(
                selected,selected.parent/("marathon."+delivery),
                bitrate_kbps=bitrate_kbps)
        except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
            result["private_mobile_warning"]=(
                "Source-selected WAV unchanged; optional installed local encoding unavailable.")
    if bundle:
        try:
            from .marathon_bundle import export_marathon_bundle
            result["private_usb_bundle"]=export_marathon_bundle(
                selected,selected.parent/"marathon.private.zip")
        except (OSError,ValueError,TypeError,KeyError,zipfile.BadZipFile):
            result["private_usb_warning"]=(
                "Source-selected WAV unchanged; optional official private USB ZIP unavailable.")
    return result


def main():
    parser=argparse.ArgumentParser(
        description="Browse and publish one human-chosen completed WAV from a verified private parent-SHA revision chain")
    sub=parser.add_subparsers(dest="action",required=True)
    browse=sub.add_parser("prepare",help="Create local HTML history of actual verified source WAV versions")
    browse.add_argument("new_private_mixlab_gallery_html")
    browse.add_argument("ordered_existing_hybrid_marathon_wavs",nargs="+")
    publish=sub.add_parser("publish",help="Human consent to release only one exact SHA-verified already finished version")
    publish.add_argument("exported_private_version_choice_json")
    publish.add_argument("ordered_existing_hybrid_marathon_wavs",nargs="+")
    publish.add_argument("--bundle",action="store_true",help="Opt-in official full private WAV USB ZIP")
    publish.add_argument("--delivery",choices=("mp3","flac"),help="Opt-in installed local portable audio")
    publish.add_argument("--bitrate-kbps",type=int,choices=(128,192,256,320),default=192)
    args=parser.parse_args()
    try:
        result=(prepare_gallery(args.new_private_mixlab_gallery_html,*args.ordered_existing_hybrid_marathon_wavs)
                if args.action=="prepare" else
                publish_selected(args.exported_private_version_choice_json,
                *args.ordered_existing_hybrid_marathon_wavs,bundle=args.bundle,
                delivery=args.delivery,bitrate_kbps=args.bitrate_kbps))
    except (ValueError,TypeError,KeyError,OSError,EOFError,
            UnicodeError,KeyboardInterrupt,wave.Error):
        parser.exit(2,"MixLab lineage: actual source WAVs, private version order, consent or new output invalid.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
