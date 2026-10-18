"""Private offline four-way energy journey comparison before studio rendering.

This is a creative planning UI; no audio inference, network or preference model.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from .journey import (
    NOTE_KIND, PLAN_KIND, SHAPES, _choose, _private_json_path, _read_json,
    _records, _source_root,
)

_PAGE = r"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Four Journeys</title>
<style>
:root{color-scheme:dark;--ink:#eaf4fe;--dim:#a8c1d1;--line:#3c536e;--accent:#78efbf}
*{box-sizing:border-box}body{background:radial-gradient(at top left,#1d3a48,#0c1019 70%);color:var(--ink);font:16px/1.5 system-ui,sans-serif;margin:0}
main{max-width:1360px;margin:auto;padding:clamp(18px,5vw,55px)}
.eyebrow{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.15em;text-transform:uppercase}
h1{font-size:clamp(30px,4vw,54px);line-height:1.1;margin:7px 0 20px}h2{font-size:22px;margin:0 0 10px}
p,small{color:var(--dim)}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.card{border:1px solid var(--line);border-radius:22px;padding:25px;background:#182438;box-shadow:0 16px 34px #04081045}
.card[aria-selected=true]{border:2px solid var(--accent);padding:24px}
svg{display:block;width:100%;height:auto;margin:12px 0}.target{fill:none;stroke:#85b9ff;stroke-width:3;stroke-dasharray:7 6}
.actual{fill:none;stroke:var(--accent);stroke-width:4;stroke-linejoin:round}
ol{padding:0;list-style:none}.song{margin:9px 0;border-bottom:1px solid #314158;padding:6px 0}
.song strong{display:block;overflow-wrap:anywhere}.song span{font-size:12px;color:var(--dim)}
button{display:inline-block;border:1px solid #577594;background:#2c4560;color:#eefcff;padding:12px 16px;border-radius:12px;font:inherit;font-weight:750;cursor:pointer}
button:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
button:hover{background:#385c77}.selected{color:#0b201a;background:var(--accent);border:0}
.footer{margin-top:22px;padding:19px 24px;border:1px solid var(--line);border-radius:17px;background:#172437}
code{overflow-wrap:anywhere}@media(max-width:790px){.cards{grid-template-columns:1fr}}@media(max-width:420px){.card{padding:15px}.card[aria-selected=true]{padding:14px}}
</style>
<main><div class="eyebrow">MixLab / Creative set builder</div>
<h1>Four ways to move the room.</h1>
<p>Compare alternative song orders built from your local, manually annotated collection. All songs in an option share the same human-confirmed tempo. No uploads or automatic musical claims.</p>
<div id="cards" class="cards"></div>
<div class="footer"><h2>Use your favourite route</h2>
<p>Select one journey and export its NEW SHA-pinned private JSON. Place it in your music folder and pass it to Playlist Studio via <code>--journey-plan</code>. Studio will require your explicit approval, rights and manual transition cues.</p>
<button id="download" class="selected" type="button">Export selected journey</button>
<p id="status" role="status" aria-live="polite"></p>
<small>Offline only. These are unvalidated creative ideas, not a blind comparison or listening benchmark. No audio is loaded in this page.</small></div>
</main><script id="seed" type="application/json">__SEED__</script>
<script>
"use strict";
const variants=JSON.parse(document.getElementById("seed").textContent);
const titles={"build":"Slow ignition","peak":"The middle peak","late-peak":"Final-act lift","release":"Gentle landing"};
let chosen=0;
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n}
function points(values){return values.map((v,i)=>String(28+450*i/(values.length-1))+","+String(170-135*(v-1)/9)).join(" ")}
function makeSvg(option){
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
 svg.setAttribute("viewBox","0 0 506 200");svg.setAttribute("role","img");
 svg.setAttribute("aria-label","Solid green: annotated track energy. Dashed blue: target energy.");
 [["target",option.entries.map(t=>t.target_energy)],["actual",option.entries.map(t=>t.energy)]].forEach(pair=>{
 const curve=document.createElementNS("http://www.w3.org/2000/svg","polyline");
 curve.setAttribute("class",pair[0]);curve.setAttribute("points",points(pair[1]));svg.append(curve)});
 return svg
}
function render(){
 const root=document.getElementById("cards");root.replaceChildren();
 variants.forEach((v,i)=>{
 const card=el("section","card");card.setAttribute("aria-selected",String(i===chosen));
 card.append(el("h2","",titles[v.shape]||v.shape));
 card.append(el("p","",v.entries.length+" tracks · "+v.bpm+" BPM (manual) · "+v.shape+" curve"));
 card.append(makeSvg(v));
 const list=el("ol","");
 v.entries.forEach((t,j)=>{
 const li=el("li","song");li.append(el("strong","",(j+1)+". "+t.path));
 li.append(el("span","","Energy "+t.energy+"/10 · Desired "+t.target_energy+"/10 · "+(t.tags||[]).join(", ")));
 list.append(li)});
 card.append(list);
 const pick=el("button",i===chosen?"selected":"","Select this route");
 pick.type="button";pick.setAttribute("aria-pressed",String(i===chosen));
 pick.onclick=()=>{chosen=i;render()};card.append(pick);root.append(card)});
}
document.getElementById("download").onclick=()=>{
 const result=variants[chosen];
 const blob=new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"});
 const link=document.createElement("a"),url=URL.createObjectURL(blob);
 link.href=url;link.download="mixlab-"+result.shape+"-journey.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById("status").textContent="A NEW private "+result.shape+" plan was downloaded. Move it beside your local music; Studio will recheck source hashes.";
};
render();
</script></html>
"""


def compare_journeys(music_folder, private_notes, new_html, *, tracks=5,
                     tempo=None, prefer_tag=None):
    """Compile independent build/peak/late-peak/release suggestions into one page."""
    root = _source_root(music_folder)
    notes = _private_json_path(root, private_notes, existing=True)
    output = Path(new_html).absolute()
    if (output.parent != root or output.suffix.lower() != ".html" or
            output.is_symlink() or output.exists()):
        raise ValueError("Choose a NEW .html in the private music folder")
    if type(tracks) is not int or not 2 <= tracks <= 11:
        raise ValueError("Choose 2..11 tracks")
    if tempo is not None and (type(tempo) not in (int, float) or not
                              math.isfinite(tempo) or not 30 <= tempo <= 300):
        raise ValueError("Tempo filter must be a verified finite BPM")
    if prefer_tag is not None:
        from .journey import _tags
        if _tags(prefer_tag) != [prefer_tag]:
            raise ValueError("Genre/mood preference must be one lowercase tag")
    data, notes_sha = _read_json(notes)
    if data.get("kind") != NOTE_KIND:
        raise ValueError("Expected private human energy notes")
    records = _records(root, data.get("tracks"))
    options = []
    for shape in SHAPES:
        bpm, chosen, targets, score = _choose(records, tracks, shape,
                                             prefer_tag=prefer_tag, tempo=tempo)
        options.append({"kind": PLAN_KIND, "shape": shape,
                        "bpm": bpm, "source_notes_sha256": notes_sha,
                        "preference_proven": False, "automatic_tempo_matching": False,
                        "selection_method": "bounded-human-metadata-heuristic-v1",
                        "objective_cost": score,
                        "entries": [{**row, "target_energy": targets[i]}
                                    for i, row in enumerate(chosen)]})
    embedded = json.dumps(options, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    embedded = embedded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = _PAGE.replace("__SEED__", embedded).encode("utf-8")
    if len(html) > 1024 * 1024:
        raise ValueError("Offline journey comparison exceeds 1 MiB")
    with output.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(html)
    return output


def main():
    parser = argparse.ArgumentParser(description="Compare 4 private song journeys in one offline browser view")
    parser.add_argument("music_directory")
    parser.add_argument("private_notes_json")
    parser.add_argument("new_comparison_html")
    parser.add_argument("--tracks", type=int, default=5)
    parser.add_argument("--tempo", type=float)
    parser.add_argument("--prefer-tag")
    args = parser.parse_args()
    try:
        result = compare_journeys(args.music_directory, args.private_notes_json,
                                  args.new_comparison_html, tracks=args.tracks,
                                  tempo=args.tempo, prefer_tag=args.prefer_tag)
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"MixLab compare: {exc}\n")
    print(json.dumps({"private_comparison": str(result), "offline": True,
                      "human_preference_proven": False}))


if __name__ == "__main__":
    main()
