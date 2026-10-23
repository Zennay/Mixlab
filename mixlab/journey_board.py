"""Private offline energy curve and manual track ordering board."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .journey import _source_root, _private_json_path, _read_json, load_journey

_PAGE = r"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; object-src 'none'">
<title>MixLab · Energy Journey</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:radial-gradient(at top right,#203e49,#0b111a 65%);color:#f0f7ff;font:16px/1.5 system-ui,sans-serif}
main{max-width:1000px;padding:clamp(18px,5vw,56px);margin:auto}h1{font-size:clamp(29px,5vw,49px);line-height:1.1;margin:8px 0}h2{font-size:19px}
p,small{color:#b0c4d9}.eyebrow{color:#80f1c0;letter-spacing:.2em;text-transform:uppercase;font-size:12px;font-weight:bold}
.panel{background:#172336;border:1px solid #344961;border-radius:20px;padding:22px;margin:20px 0}
svg{display:block;width:100%;height:auto}.axis{stroke:#3d5875;stroke-width:1}
.target{fill:none;stroke:#87bfff;stroke-width:3;stroke-dasharray:8 7}
.actual{fill:none;stroke:#80f1c0;stroke-width:4}
.pill{display:inline-block;margin:6px 8px 6px 0;padding:8px 13px;border:1px solid #405972;border-radius:30px;background:#22374e;font-size:13px}
ol{padding:0;list-style:none;display:grid;gap:10px}.song{display:flex;align-items:center;gap:14px;border:1px solid #405972;border-radius:15px;padding:12px;background:#101c2c}
.order{background:#30435b;padding:10px 13px;border-radius:10px;font-weight:800}.detail{flex:1;min-width:0}
.name{font-weight:700;overflow-wrap:anywhere}.meta{font-size:12px;color:#b0c4d9}
button{border:1px solid #51789a;border-radius:10px;background:#2c4661;color:#fff;padding:10px 15px;cursor:pointer;font:inherit}
button:focus-visible{outline:3px solid #80f1c0}button:disabled{opacity:.25;cursor:not-allowed}
.primary{color:#10251c;background:#80f1c0;border:0;font-weight:800;padding:14px 18px}
@media(max-width:470px){.song{flex-wrap:wrap}.controls{margin-left:auto}}
</style><main>
<div class="eyebrow">MixLab / Offline DJ Set Planner</div>
<h1>Shape your energy journey.</h1>
<p>A creative order from your manually verified BPM and subjective energy. Not automatic song understanding or proof of musical preference.</p>
<div id="stats"></div>
<section class="panel"><h2>Energy across the set</h2>
<svg id="curve" viewBox="0 0 840 270" role="img" aria-label="Solid green: selected track energy; dashed blue: requested journey energy"></svg>
<p>Green: actual annotated energy · Dashed blue: target curve · Scale 1–10</p></section>
<section class="panel"><h2>Track order</h2>
<p>Move any song up or down. All tracks have the same human-confirmed tempo. Nothing is modified until you export a new file.</p>
<ol id="songs"></ol><button id="reset" type="button">Reset order</button></section>
<section class="panel"><h2>Export your approved idea</h2>
<p>Download a new private JSON into your music folder. Then pass it to Playlist Studio with <code>--journey-plan</code>. MixLab rechecks recording hashes and requests final approval, source permissions and transition cue points.</p>
<button id="download" type="button" class="primary">Export my ordered set</button><p id="status" role="status" aria-live="polite"></p>
<small>Local offline page · no uploads · no audio decoding · source rights remain your responsibility.</small></section>
</main><script id="seed" type="application/json">__SEED__</script>
<script>
"use strict";
const source=JSON.parse(document.getElementById("seed").textContent);
const tracks=source.entries,targets=tracks.map(e=>e.target_energy);
const initial=tracks.map((_,i)=>i);let order=initial.slice();
function node(tag,klass,value){const n=document.createElement(tag);if(klass)n.className=klass;if(value!==undefined)n.textContent=value;return n}
function coords(values){return values.map((energy,index)=>String(42+756*index/(values.length-1))+","+String(230-190*(energy-1)/9)).join(" ")}
function render(){
 const stats=document.getElementById("stats");stats.replaceChildren();
 [tracks.length+" tracks",source.bpm+" BPM (manual)",source.shape+" shape","Private / offline"].forEach(s=>stats.append(node("span","pill",s)));
 const svg=document.getElementById("curve");svg.replaceChildren();
 [1,5,10].forEach(e=>{const l=document.createElementNS("http://www.w3.org/2000/svg","line");
 l.setAttribute("x1","42");l.setAttribute("x2","798");
 l.setAttribute("y1",String(230-190*(e-1)/9));l.setAttribute("y2",String(230-190*(e-1)/9));
 l.setAttribute("class","axis");svg.append(l)});
 [["target",targets],["actual",order.map(i=>tracks[i].energy)]].forEach(pair=>{
 const poly=document.createElementNS("http://www.w3.org/2000/svg","polyline");
 poly.setAttribute("points",coords(pair[1]));poly.setAttribute("class",pair[0]);svg.append(poly)});
 const ol=document.getElementById("songs");ol.replaceChildren();
 order.forEach((idx,pos)=>{
 const t=tracks[idx],li=node("li","song");li.append(node("span","order",String(pos+1)));
 const d=node("div","detail");d.append(node("div","name",t.path));
 d.append(node("div","meta","Energy "+t.energy+"/10 · Target "+targets[pos]+"/10 · "+t.bpm+" BPM · "+(t.tags||[]).join(", ")));li.append(d);
 const controls=node("div","controls");
 [[-1,"↑","earlier"],[1,"↓","later"]].forEach(action=>{
 const b=node("button","",action[1]);b.type="button";b.disabled=pos+action[0]<0||pos+action[0]>=order.length;
 b.setAttribute("aria-label",t.path+": move "+action[2]);
 b.onclick=()=>{const swap=pos+action[0];[order[pos],order[swap]]=[order[swap],order[pos]];render()};controls.append(b)});
 li.append(controls);ol.append(li)});
}
document.getElementById("reset").onclick=()=>{order=initial.slice();render()};
document.getElementById("download").onclick=()=>{
 const result={...source,entries:order.map((idx,pos)=>({...tracks[idx],target_energy:targets[pos]})),
 selection_method:"human-adjusted-energy-journey-v1"};delete result.objective_cost;
 const blob=new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;
 a.download="mixlab-journey-curated.private.json";document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById("status").textContent="New private plan exported. Place it beside your music before Playlist Studio.";
};
render();
</script></html>
"""


def create_board(music_folder, private_plan, new_html):
    root = _source_root(music_folder)
    plan = _private_json_path(root, private_plan, existing=True)
    target = Path(new_html).absolute()
    if (target.parent != root or target.suffix.lower() != ".html" or
            target.is_symlink() or target.exists()):
        raise ValueError("Choose a NEW private .html file directly in the music folder")
    load_journey(root, plan)
    payload, _ = _read_json(plan)
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    content = _PAGE.replace("__SEED__", data).encode("utf-8")
    if len(content) > 1024 * 1024:
        raise ValueError("Private board exceeds 1 MiB")
    with target.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(content)
    return target


def main():
    parser = argparse.ArgumentParser(description="Create an offline editable Energy Journey board")
    parser.add_argument("music_directory")
    parser.add_argument("private_plan_json")
    parser.add_argument("new_board_html")
    args = parser.parse_args()
    try:
        path = create_board(args.music_directory, args.private_plan_json, args.new_board_html)
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"MixLab journey board: {exc}\n")
    print(json.dumps({"offline_board": str(path), "published_online": False}))


if __name__ == "__main__":
    main()
