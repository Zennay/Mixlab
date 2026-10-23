"""Private offline comparison of manual, source-pinned MixLab show rehearsals.

DJ-reported browser WAV positions are annotations, not verified acoustic,
timing, listening preference, venue, or rights evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import wave

from .marathon_sequence import _private_html_destination
from .show_conductor import _sources
from .show_rehearsal import _read_journal, _validate

KIND = "mixlab-private-show-rehearsal-review-v1"
MAX_TAKES = 6
MAX_PAGE = 768 * 1024


def canonical_sha(document: dict) -> str:
    """A digest of validated JSON *values* rather than whitespace/byte formatting."""
    encoded = json.dumps(document, ensure_ascii=True, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _admit_sources_and_takes(source_pairs: tuple[str, ...],
                             journals: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    if not 2 <= len(journals) <= MAX_TAKES:
        raise ValueError("Choose 2–6 separate private rehearsal journals")
    source_paths = [Path(raw).absolute() for raw in source_pairs]
    journal_paths = [Path(path).absolute() for path in journals]
    if (len(set(journal_paths)) != len(journal_paths) or
            any(j in source_paths for j in journal_paths)):
        raise ValueError("Each rehearsal must be a distinct private JSON file")
    sources = _sources(source_pairs)  # Canonical original receipts + entire WAV SHA.
    takes = []
    for index, journal in enumerate(journals):
        raw = _read_journal(str(journal))
        events = _validate(raw, sources)
        marks = []
        for item in events:
            if item["kind"] != "mark":
                continue
            src = sources[item["set_index"]]
            closest = min(src["chapters"], key=lambda c: abs(
                c["start_seconds"] - item["wav_position_seconds"])) if src["chapters"] else None
            difference = (item["wav_position_seconds"] - closest["start_seconds"]
                          if closest is not None else None)
            near = closest if difference is not None and abs(difference) <= 60 else None
            marks.append({
                "seq": item["seq"],
                "set_index": item["set_index"],
                "position": item["wav_position_seconds"],
                "elapsed_ms": item["elapsed_ms"],
                "note": item.get("note", ""),
                "chapter": str(near["label"]) if near else None,
                "chapter_kind": str(near["kind"]) if near else None,
                "chapter_seconds": near["start_seconds"] if near else None,
                "chapter_delta": round(difference, 3) if near else None,
            })
        takes.append({
            "index": index, "label": f"Take {index + 1}",
            "journal_sha256": canonical_sha(raw),
            "event_count": len(events), "marks": marks,
            "play_actions": sum(e["kind"] == "play" for e in events),
            "end_events": sum(e["kind"] == "ended" for e in events),
        })
    if len({item["journal_sha256"] for item in takes}) != len(takes):
        raise ValueError("Comparison needs distinct source-bound private rehearsal contents")
    return sources, takes


def prepare_comparison(new_html: str, source_pairs: tuple[str, ...],
                       journals: tuple[str, ...]) -> dict:
    sources, takes = _admit_sources_and_takes(source_pairs, journals)
    out = _private_html_destination(new_html)
    roots = [Path(raw).absolute() for raw in (*source_pairs, *journals)]
    if any(out.is_relative_to(path) or out.is_relative_to(path.parent)
           for path in roots):
        raise ValueError("Output must be outside source WAVs, sessions and private journals")

    payload = {
        "schema_version": 1, "kind": KIND,
        "source_sha256s": [s["wav_sha256"] for s in sources],
        "sets": [{"label": s["label"], "duration": s["duration_seconds"],
                  "sha256": s["wav_sha256"]} for s in sources],
        "takes": takes,
    }
    blob = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    # A script raw-text element must not let user-supplied notes terminate </script>.
    blob = blob.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    page = _HTML.replace("__DATA__", blob).encode("utf-8")
    if not 0 < len(page) <= MAX_PAGE:
        raise ValueError("Private comparison exceeds bounded HTML size")
    with out.open("xb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(page)
    return {
        "private_comparison_html": str(out),
        "actual_source_verified_sets": len(sources),
        "independent_manual_takes": len(takes),
        "source_sha256s": payload["source_sha256s"],
        "no_audio_embedded": True, "musical_quality_proven": False,
    }


_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';img-src 'none';media-src 'none';connect-src 'none';object-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Private rehearsal take comparison</title>
<style>
:root{color-scheme:dark;--bg:#0a1520;--panel:#172b37;--line:#547080;--mint:#aaf7dc}
*{box-sizing:border-box}body{background:var(--bg);color:#f0fbff;margin:0;font:15px/1.5 system-ui}
main{max-width:1240px;margin:auto;padding:clamp(16px,4vw,48px)}
h1{font-size:clamp(32px,5vw,60px);line-height:1.1;margin:8px 0}
h2{font-size:22px}.lead,.quiet{color:#c7dee8}
.panel{background:var(--panel);border:1px solid var(--line);padding:20px;border-radius:15px;margin:18px 0}
.statrow{display:flex;gap:14px;flex-wrap:wrap}.stat{flex:1;min-width:150px}
.stat strong{display:block;color:var(--mint);font-size:30px}
.takegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
article{border:1px solid var(--line);border-radius:12px;padding:16px}
article.selected{border:2px solid var(--mint)}article h3{margin:0}
button{background:#205b4d;color:white;border:1px solid #95ccb7;font:inherit;border-radius:9px;padding:9px 14px;cursor:pointer}
button:focus-visible,input:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
label{display:inline-flex;gap:8px;align-items:center;margin:12px}
select{background:#10242e;color:white;border:1px solid #9ac; padding:8px;border-radius:8px}
table{border-collapse:collapse;width:100%;min-width:730px}
th,td{padding:10px;border-bottom:1px solid #45616f;text-align:left;vertical-align:top}
th{color:var(--mint)}.scroll{overflow-x:auto}.note{white-space:pre-wrap;overflow-wrap:anywhere;max-width:290px}
.hash{font:11px ui-monospace,monospace;overflow-wrap:anywhere;color:#bacad6}
@media print{body{background:white;color:black}.panel,article{border-color:#777;background:white;color:black}
button,select,label{display:none}th{color:black}.lead,.quiet,.hash{color:#444}}
</style></head><body><main><p class="quiet">MIXLAB / OFFLINE / PRIVATE</p>
<h1>Review your manual show rehearsals.</h1>
<p class="lead">Compare 2–6 previously exported, independently reverified
rehearsal journals against exactly the same complete finished WAVs. No audio is
embedded, read, played or uploaded by this page. WAV positions and cue notes
are DJ/browser annotations, NOT verified venue playback, quality rankings,
listener preference, real-time synchronization or music rights.</p>
<section class="panel"><div class="statrow">
<div class="stat"><small>Source-locked sets</small><strong id="set-count">—</strong></div>
<div class="stat"><small>Rehearsal takes</small><strong id="take-count">—</strong></div>
<div class="stat"><small>Manual cue marks</small><strong id="mark-count">—</strong></div>
</div></section>
<section class="panel"><h2>1 · Choose a rehearsal take</h2>
<p class="quiet">A take selection is an <strong>operator choice</strong>,
never an automated quality winner. Export it as a private source-bound
handoff for your own reference.</p>
<div id="takes" class="takegrid"></div>
<div><button type="button" id="export">Download my private take selection</button>
<p id="status" role="status" class="quiet"></p></div></section>
<section class="panel"><h2>2 · Compare exact WAV cue positions</h2>
<label>Approved source set <select id="set-filter"></select></label>
<label>Rehearsal <select id="take-filter"><option value="all">All takes</option></select></label>
<div class="scroll"><table><thead><tr><th>Take</th><th>WAV position</th>
<th>Source chapter</th><th>WAV delta</th><th>Page elapsed</th>
<th>Manual DJ note</th></tr></thead><tbody id="marks"></tbody></table></div>
<p id="empty" class="quiet"></p></section>
<section class="panel"><h2>3 · Source fingerprints</h2><ol id="sources"></ol>
<p class="quiet">Same source SHA-256 in every admitted journal, with source
receipts and complete original WAV checked again by the generator. No
independent authenticity, rights or sound-quality claims.</p></section>
</main><script type="application/json" id="mixlab-data">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-data").textContent),$=id=>document.getElementById(id);
let chosen=0;
const table=$("marks"),filter=$("set-filter"),takeFilter=$("take-filter");
function textCell(row,value,cls){
 const td=document.createElement("td");td.textContent=String(value);
 if(cls)td.className=cls;row.append(td);
}
function render(){
 const selectedSet=Number(filter.value),takeChoice=takeFilter.value;
 table.replaceChildren();let count=0;
 for(const take of data.takes){
  if(takeChoice!=="all"&&takeChoice!==String(take.index))continue;
  for(const mark of take.marks){
   if(mark.set_index!==selectedSet)continue;
   const row=document.createElement("tr");
   textCell(row,take.label);
   textCell(row,mark.position.toFixed(3)+" s");
   textCell(row,mark.chapter===null?"No nearby chapter":mark.chapter+" · "+mark.chapter_kind);
   textCell(row,mark.chapter_delta===null?"—":(mark.chapter_delta>=0?"+":"")+mark.chapter_delta.toFixed(3)+" s");
   textCell(row,(mark.elapsed_ms/1000).toFixed(2)+" s");
   textCell(row,mark.note||"—","note");
   table.append(row);count++;
  }
 }
 $("empty").textContent=count?"":"No manual marks for this selection. This does not imply playback failed.";
 document.querySelectorAll("#takes article").forEach((card,i)=>card.classList.toggle("selected",i===chosen));
}
$("set-count").textContent=String(data.sets.length);
$("take-count").textContent=String(data.takes.length);
$("mark-count").textContent=String(data.takes.reduce((n,t)=>n+t.marks.length,0));
data.sets.forEach((set,i)=>{
 const option=document.createElement("option");option.value=String(i);
 option.textContent=(i+1)+". "+set.label;filter.append(option);
 const li=document.createElement("li");li.className="hash";
 li.textContent="Set "+(i+1)+" · "+set.label+" · "+set.sha256;
 $("sources").append(li);
});
data.takes.forEach((take,i)=>{
 const card=document.createElement("article"),title=document.createElement("h3");
 title.textContent=take.label;
 const stats=document.createElement("p");
 stats.textContent=take.marks.length+" manual cues · "+take.play_actions+
  " browser play actions · "+take.end_events+" ended events";
 const button=document.createElement("button");button.type="button";
 button.textContent="Select "+take.label;
 button.addEventListener("click",()=>{chosen=i;render();$("status").textContent=take.label+" selected manually.";});
 const hash=document.createElement("p");hash.className="hash";
 hash.textContent="Canonical private journal SHA-256: "+take.journal_sha256;
 card.append(title,stats,button,hash);$("takes").append(card);
 const option=document.createElement("option");option.value=String(i);option.textContent=take.label;
 takeFilter.append(option);
});
filter.addEventListener("change",render);takeFilter.addEventListener("change",render);
$("export").addEventListener("click",()=>{
 const take=data.takes[chosen];
 const selection={schema_version:1,kind:"mixlab-private-rehearsal-take-selection-v1",
  source_sha256s:data.source_sha256s.slice(),
  journal_sha256s:data.takes.map(t=>t.journal_sha256),
  selected_take_index:chosen,private_only:true,operator_selected:true,
  automatically_ranked:false,blind_study:false};
 const blob=new Blob([JSON.stringify(selection,null,2)+"\n"],{type:"application/json"});
 const link=document.createElement("a"),url=URL.createObjectURL(blob);
 link.href=url;link.download="mixlab-rehearsal-take-selection.private.json";
 document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("status").textContent=take.label+" selection exported privately. It is not a quality score.";
});
render();
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare real source-locked private manual show rehearsals offline")
    parser.add_argument("new_private_mixlab_html")
    parser.add_argument("session_and_wav_pairs", nargs="+")
    parser.add_argument("--journal", action="append", required=True,
                        help="Private exported rehearsal journal (2–6 required, in display order)")
    args = parser.parse_args()
    try:
        result = prepare_comparison(args.new_private_mixlab_html,
                                    tuple(args.session_and_wav_pairs),
                                    tuple(args.journal))
    except (ValueError, KeyError, OSError, TypeError, UnicodeError, wave.Error):
        parser.exit(2, "MixLab Rehearsal Review: original WAVs, journals or destination invalid.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
