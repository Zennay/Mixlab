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

from .event_marathon import MAX_BYTES, MAX_EVENTS, _admit, create_marathon

PLAN_KIND = "mixlab-private-marathon-sequence-v1"
MAX_PLAN = 65536
MAX_PAGE = 512 * 1024

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; media-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
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
<div class="actions"><button type="button" id="reset">Reset original sequence</button>
<button type="button" id="export">Export exact-source render plan</button></div>
</section>
<section class="panel"><h2>How to get the real mix</h2><p>
1. Export the new private <code>mixlab-marathon-sequence.private.json</code> from this page.
2. Run the original command with <code>render</code> and pass the **same SESSION WAV pairs in their original input order**.
3. Review the actual names, hours and source permissions in your terminal. MixLab still asks you to type
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
  row.append(check,number,name,up,down);root.append(row);
 });
 const chosen=order.filter(i=>selected.has(i));
 const frames=chosen.reduce((n,i)=>n+all[i].frames,0);
 const seconds=chosen.reduce((n,i)=>n+all[i].frames/all[i].rate,0);
 $("count").textContent=String(chosen.length);
 $("time").textContent=clock(seconds);
 $("size").textContent=(frames*4/1048576).toFixed(1)+" MiB";
 const valid=chosen.length>=2&&chosen.length<=8&&frames*4<=source.max_pcm_bytes;
 $("export").disabled=!valid;
 $("notice").textContent=!valid?"Select 2–8 finished sets within the 768 MiB master WAV budget.":
  "Ready to export "+chosen.length+" source-bound event decisions. Final render remains a human-approved local operation.";
}
$("reset").addEventListener("click",()=>{order=all.map((_,i)=>i);selected=new Set(order);render();});
$("export").addEventListener("click",()=>{
 const chosen=order.filter(i=>selected.has(i));
 if(chosen.length<2||chosen.length>8)return;
 const doc={schema_version:1,kind:source.kind,
  source_identity:source.originals.map(({sha256,frames,rate})=>({sha256,frames,rate})),
  selected_indices:chosen};
 const blob=new Blob([JSON.stringify(doc,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;
 a.download="mixlab-marathon-sequence.private.json";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("notice").textContent="Private plan saved. Hand it to the CLI with the original SESSION/WAV pairs.";
});
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
    if sum(x["frames"] for x in items) * 4 > MAX_BYTES:
        raise ValueError("Original set inventory exceeds the maximum Marathon budget")
    dest = _private_html_destination(new_private_html)
    data = {"kind": PLAN_KIND, "max_pcm_bytes": MAX_BYTES,
            "originals": [{**identity, "label": x["wav"].parent.name}
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
                     bundle=False, delivery=None, bitrate_kbps=192, read=input, write=print):
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
    selected = [pairs[i] for i in order]
    write("MixLab exact-source browser arrangement, not a musical compatibility score.")
    write("Chosen event order: " + ", ".join(items[i]["wav"].parent.name for i in order))
    return create_marathon(new_private_folder, *selected, read=read, write=write,
                           start=start, bundle=bundle, delivery=delivery,
                           bitrate_kbps=bitrate_kbps)


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
                                      bundle=args.bundle, delivery=args.delivery,
                                      bitrate_kbps=args.bitrate_kbps)
    except (ValueError, KeyError, TypeError, OSError, EOFError, KeyboardInterrupt,
            wave.Error, zipfile.BadZipFile, subprocess.SubprocessError):
        parser.exit(2, "MixLab Marathon Sequence: private original sources, operator plan, approval or new output unavailable.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
