"""Private, offline waveform/cue editor for manually aligned MixLab transitions.

Creates an interactive *file://* HTML editor next to a registered PCM16
library. Users listen and choose A/B cue positions visually, export a small
selection JSON, and apply it to a NEW manifest. Never replaces source audio
or original study/manifest data. No server, network, packages or models.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import stat

from .cue_suggest import _rms_envelope
from .cueprep import ID, _inspect_source, _read_spec, _source_path
from .ingest import MAX_BYTES, MAX_FRAMES, RIGHTS, digest
from .playlist_preview_page import local_song_title

MAX_TRACKS = 20
MAX_PAIRS = 10
MAX_EDITOR_BYTES = 2 * 1024 * 1024


def _require_number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid " + name)
    return value


def _admit_library(path, *, calculate_waveforms):
    path = Path(path).absolute()
    spec = _read_spec(path)
    root = path.parent.resolve(strict=True)
    if path.parent != root:
        raise ValueError("Source manifest must reside in a trusted private directory")
    tracks = spec.get("tracks")
    pairs = spec.get("pairs")
    if not isinstance(tracks, list) or not 2 <= len(tracks) <= MAX_TRACKS:
        raise ValueError("Source must register 2..20 tracks")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= MAX_PAIRS:
        raise ValueError("Source must register 1..10 pairs")

    bank = {}
    for record in tracks:
        if not isinstance(record, dict):
            raise ValueError("Invalid track metadata")
        tid = record.get("id")
        if not isinstance(tid, str) or not ID.fullmatch(tid) or tid in bank:
            raise ValueError("Duplicate or unsafe track identifier")
        if record.get("rights") not in RIGHTS or not isinstance(record.get("provenance"), str) or not record["provenance"].strip():
            raise ValueError("Each track needs explicit rights declaration and provenance")
        bpm = _require_number(record.get("bpm"), "manual BPM", 30, 300)
        if "first_downbeat_seconds" in record:
            _require_number(record["first_downbeat_seconds"], "first downbeat", 0, 900)
        wav = _source_path(root, record.get("path"))
        info = _inspect_source(wav, record.get("sha256"))
        if "first_downbeat_seconds" in record and record["first_downbeat_seconds"] >= info["frames"] / info["rate"]:
            raise ValueError("Declared first downbeat is outside its WAV")
        entry = {"id": tid, "path": record["path"],
                 "display_name": local_song_title(record["path"]), "bpm": bpm,
                 "duration": round(info["frames"] / info["rate"], 6),
                 "sample_rate": info["rate"], "channels": info["channels"],
                 "frame_count": info["frames"],
                 "first_downbeat_seconds": record.get("first_downbeat_seconds"),
                 "sha256": info["sha256"]}
        if calculate_waveforms:
            powers, hop = _rms_envelope(wav, info)
            # RMS proxy is meant for visual navigation, not musical judgement.
            entry["waveform_hop_seconds"] = round(hop, 8)
            entry["waveform"] = [
                min(1., round(math.sqrt(max(0., p)), 5)) for p in powers
            ]
        bank[tid] = entry

    selected = []
    used = set()
    for p in pairs:
        if not isinstance(p, dict):
            raise ValueError("Invalid transition pair")
        pid = p.get("id")
        if not isinstance(pid, str) or not ID.fullmatch(pid) or pid in used:
            raise ValueError("Duplicate or unsafe pair identifier")
        used.add(pid)
        a, b = p.get("a"), p.get("b")
        if not isinstance(a, str) or not isinstance(b, str) or a not in bank or b not in bank or a == b:
            raise ValueError("A/B source IDs must reference different registered tracks")
        left, right = bank[a], bank[b]
        if left["bpm"] != right["bpm"] or (left["sample_rate"], left["channels"]) != (
            right["sample_rate"], right["channels"]
        ):
            raise ValueError("Pair must have matching manual BPM and PCM format")
        beats = p.get("beats", 8)
        if type(beats) is not int or not 1 <= beats <= 64:
            raise ValueError("Pair beat count must be 1..64")
        duration = beats * 60 / left["bpm"]
        frames = round(duration * left["sample_rate"])
        if not 2 <= frames <= MAX_FRAMES or 44 + frames * left["channels"] * 2 > MAX_BYTES:
            raise ValueError("Pair cue duration exceeds renderer audio budget")
        cue = {}
        for side, meta in (("a", left), ("b", right)):
            start = _require_number(p.get(side + "_start_seconds", 0),
                                    "manual cue " + side, 0, 900)
            if round(start * meta["sample_rate"]) + frames > meta["frame_count"]:
                raise ValueError("Cue does not fit source track")
            cue[side + "_start_seconds"] = start
        selected.append({"id": pid, "a": a, "b": b, "beats": beats,
                         "seconds": round(duration, 6), **cue})
    return spec, bank, selected


_HTML = r'''<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MixLab | Handmatige overgangs-editor</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; form-action 'none'; object-src 'none'; base-uri 'none'">
<style>
:root{font:16px system-ui,sans-serif;background:#0b0c12;color:#f4f4f9;color-scheme:dark}
*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:42px 24px 100px}
small,.eyebrow{font-size:.75rem;color:#bca6ff;letter-spacing:.16em;text-transform:uppercase;font-weight:700}
h1{font-size:clamp(2.8rem,8vw,5.6rem);letter-spacing:-.07em;line-height:1;margin:16px 0}
.lede{max-width:730px;color:#b4b8ca;line-height:1.65}
.toolbar{display:flex;align-items:end;flex-wrap:wrap;gap:18px;margin:30px 0 26px}
label{font-size:.85rem;color:#c6c9d9;display:grid;gap:7px}
select,input,button{font:inherit;color:#eef0f9;background:#25283a;border:1px solid #51566b;border-radius:10px;padding:11px}
button{cursor:pointer}button:hover{border-color:#bdabff}
button:focus-visible,input:focus-visible,select:focus-visible,canvas:focus-visible{outline:3px solid #bdabff;outline-offset:3px}
.pair-info{margin-left:auto;color:#b4b8ca;padding-bottom:10px}
.cue-history{display:flex;gap:8px;flex-wrap:wrap;align-items:end}
.cue-history button:disabled{opacity:.4;cursor:not-allowed}
#history-status{color:#c3b5e9;margin:0 0 19px}
#cue-import-status{color:#c3b5e9;min-height:1.5em;margin:12px 0 22px}
.problem-navigation{border:1px solid #ba9363;background:#352616;
  padding:12px 16px;border-radius:12px;margin:14px 0}
.problem-navigation[hidden]{display:none}
.problem-navigation p{color:#f9e2b9}
#jump-to-problem{border-color:#edc083;background:#593e21;color:#fff}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.lane{border:1px solid #383e53;background:linear-gradient(135deg,#1e2030,#151720);border-radius:20px;padding:24px}
h2{font-size:1.4rem;margin:10px 0} .summary{color:#adb4c7;font-size:.83rem;margin:0 0 20px}
canvas{width:100%;height:152px;background:#10121b;border:1px solid #454a62;border-radius:12px;cursor:crosshair;touch-action:manipulation}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}
.row .time{font-variant-numeric:tabular-nums;min-width:75px;font-weight:700}
.range{width:100%;accent-color:#bdabff}.buttons{display:flex;gap:8px;flex-wrap:wrap}
audio{width:100%;margin-top:10px} .footer{margin-top:28px;padding:20px;background:#171a27;border:1px solid #3f4358;border-radius:16px}
.timeline-summary{background:#211d35;border:1px solid #6a5d92;padding:14px;
  margin:12px 0;border-radius:12px;font-variant-numeric:tabular-nums}
#mix-timeline{list-style:none;padding:0;margin:14px 0;display:grid;gap:9px}
#mix-timeline li{display:grid;grid-template-columns:125px minmax(0,1fr);
  gap:16px;background:#212536;border:1px solid #3f4358;border-radius:10px;padding:11px 13px}
#mix-timeline strong{display:block;overflow-wrap:anywhere}
#mix-timeline small{color:#c8c2ec;font-variant-numeric:tabular-nums}
@media(max-width:600px){#mix-timeline li{grid-template-columns:1fr;gap:4px}}
.primary{background:#c8b4ff;color:#131020;font-weight:800;border-color:#c8b4ff}
code{font-size:.87em}p{line-height:1.6}.warning{color:#e8c6a6}
@media(max-width:760px){.grid{grid-template-columns:1fr}.pair-info{width:100%;margin-left:0}}
</style></head><body>
<main><small>MIXLAB / PRIVÉ CUE-EDITOR</small><h1>Kies je<br>overgang.</h1>
<p class="lede">Herken je nummers, bekijk hun geluidsgolf en beluister de handmatig gekozen fragmenten. Verplaats zelf de cue waar het ene nummer uitgaat en het andere begint. De golfvorm is geen automatische beat- of muziekkwaliteitsanalyse.</p>
<div class="toolbar"><label>Overgang tussen nummers<select id="pair"></select></label><label style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
<input type="checkbox" id="snap">Afronden op de opgegeven beatgrid (indien bekend)</label>
<div class="pair-info" id="pair-info"></div>
<div class="cue-history" role="group" aria-label="Cuewijzigingen beheren">
<button id="undo" type="button" disabled>↶ Ongedaan maken</button>
<button id="redo" type="button" disabled>↷ Opnieuw</button>
<button id="restore-pair" type="button" disabled>Herstel dit paar</button>
<button id="restore-all" type="button" disabled>Herstel alle cues</button></div></div>
<p id="history-status" role="status" aria-live="polite">Nog geen cuewijzigingen.</p>
<div class="cue-history" role="group" aria-label="Eerder opgeslagen cuekeuzes laden">
<label for="cue-import-file">Eerder gedownloade cuekeuzes (.json, max 64 KiB)
<input id="cue-import-file" type="file" accept=".json,application/json"></label>
<button id="cue-import" type="button">Laad opgeslagen cues</button>
</div>
<p id="cue-import-status" role="status" aria-live="polite">Nog geen cuekeuzes geladen.</p>
<p class="lede">Fijn afstellen: gebruik ± 0,10 s naast elk deck of Shift + ←/→ op de geselecteerde golfvorm. Deze kleine stappen omzeilen bewust het optionele beatgrid; de standaard beatknoppen blijven op je opgegeven BPM werken.</p>
<div class="grid">
<section class="lane"><small>UITGAAND / DECK A</small><h2 id="name-a"></h2>
<p class="summary" id="info-a"></p><canvas id="wave-a" width="950" height="152" tabindex="0" role="button" aria-label="Kies uitgaande cuepositie op de golfvorm"></canvas>
<div class="row"><span>Startcue</span><span class="time" id="time-a"></span>
<input class="range" type="range" min="0" step="0.01" id="range-a" aria-label="Tijdstip uitgaande cue"></div>
<div class="buttons"><button id="prev-a">− beat</button><button id="next-a">+ beat</button><button id="barprev-a">− 4 beats</button><button id="barnext-a">+ 4 beats</button><button id="fineprev-a" title="100 milliseconden terug, zonder beatgrid">− 0,10 s</button><button id="finenext-a" title="100 milliseconden vooruit, zonder beatgrid">+ 0,10 s</button><button id="play-a">▶ Beluister A</button></div>
<audio id="audio-a" controls preload="metadata"></audio></section>
<section class="lane"><small>INKOMEND / DECK B</small><h2 id="name-b"></h2>
<p class="summary" id="info-b"></p><canvas id="wave-b" width="950" height="152" tabindex="0" role="button" aria-label="Kies inkomende cuepositie op de golfvorm"></canvas>
<div class="row"><span>Startcue</span><span class="time" id="time-b"></span>
<input class="range" type="range" min="0" step="0.01" id="range-b" aria-label="Tijdstip inkomende cue"></div>
<div class="buttons"><button id="prev-b">− beat</button><button id="next-b">+ beat</button><button id="barprev-b">− 4 beats</button><button id="barnext-b">+ 4 beats</button><button id="fineprev-b" title="100 milliseconden terug, zonder beatgrid">− 0,10 s</button><button id="finenext-b" title="100 milliseconden vooruit, zonder beatgrid">+ 0,10 s</button><button id="play-b">▶ Beluister B</button></div>
<audio id="audio-b" controls preload="metadata"></audio></section>
</div>
<section class="footer" aria-labelledby="ab-preview-heading">
<h2 id="ab-preview-heading">Voorluisteren: cue A + B tegelijk</h2>
<p>Hoor beide originele WAV-bronnen tegelijk vanaf jouw handmatig gekozen
startcues, op laag volume. Dit is alleen een ruwe timingcontrole;
geen definitieve mix, crossfade, beatmatch of MixLab-DSP-render.</p>
<div class="buttons"><button type="button" class="primary" id="play-ab">▶ Beluister A + B</button>
<button type="button" id="stop-ab" disabled>■ Stop beide decks</button></div>
<p id="ab-status" role="status" aria-live="polite">Nog niet samen beluisterd.</p>
</section>
<section class="footer" aria-labelledby="timeline-title">
<h2 id="timeline-title">Waar vallen je overgangen in de complete mix?</h2>
<p>Deze lokale indicatie wordt bij elke handmatige cuewijziging opnieuw
berekend uit de oorspronkelijke PCM16-frametellingen en jouw BPM en
cueposities. Er is nog geen volledige WAV gerenderd en de weergegeven
tijden bewijzen niets over muzikale kwaliteit of daadwerkelijke rechten.</p>
<p class="timeline-summary" id="mix-timing-summary" role="status" aria-live="polite">
Nog geen geldige complete mixtijd berekend.</p>
<ol id="mix-timeline" aria-label="Verwachte hoofdstukken van de complete set"></ol>
</section>
<div class="footer">
<button class="primary" id="save">Download cuekeuzes (.json)</button>
<p id="message" role="status" aria-live="polite">Je muziek blijft privé. Wijzigingen worden pas bewaard wanneer je de cuekeuzes downloadt.</p>
<div id="cue-problem-navigation" class="problem-navigation" hidden>
<p id="cue-problem-guidance" role="status" aria-live="polite"></p>
<button id="jump-to-problem" type="button">Ga naar probleemovergang</button>
</div>
<p class="warning">Download eerst je cuekeuzes als privé-JSON. Zet dat bestand in je privé muziekmap en gebruik <code>python3 -m mixlab.cue_editor apply OUD_MANIFEST.json CUEKEUZES.json NIEUW_MANIFEST.json --plan-html --plan-verify-wavs</code> om een <strong>nieuw</strong> bronmanifest met die cues te maken. Het oude manifest, de bron-WAVs en rechtenverklaringen blijven ongewijzigd. Die opdracht maakt ook een nieuwe, lokale, gecontroleerde HTML-tijdlijn zonder audio te renderen. Je kunt het nieuwe manifest zo controleren voordat je met <code>--resume --full-set-wav</code> de echte WAV rendert.</p>
</div></main>
<script type="application/json" id="local-data">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById('local-data').textContent);
const bank=Object.fromEntries(data.tracks.map(x=>[x.id,x]));
const pairs=data.pairs;
const $=id=>document.getElementById(id);
const pairSelect=$('pair');
for(const p of pairs){const option=document.createElement('option');option.value=p.id;option.textContent=bank[p.a].display_name+' → '+bank[p.b].display_name+' · '+p.id;pairSelect.append(option);}
let chosen=pairs[0],playing=null,stopAt=0,edited=false;
let duetActive=false,duetSerial=0,duetVolumes=null,duetEnds=null;
function cueProblemDetail(){
 for(let i=1;i<pairs.length;i++){
   const previous=pairs[i-1],current=pairs[i];
   if(previous.b!==current.a)
     return {pairId:current.id,
       message:'De overgangsparen vormen geen doorlopende afspeelvolgorde.',
       guidance:'Overgang '+current.id+' sluit niet aan op het vorige nummer. '+
       'De bronvolgorde moet in een nieuw manifest worden gecorrigeerd.'};
   const rate=bank[current.a].sample_rate;
   const priorEnd=Math.round(previous.b_start_seconds*rate)+
     Math.round(previous.beats*60/bank[previous.a].bpm*rate);
   if(Math.round(current.a_start_seconds*rate)<priorEnd){
     let earliest=Math.ceil(priorEnd/rate*100-1e-8)/100;
     // The displayed hundredth must itself round to a valid PCM frame;
     // do not understate the earliest playable cue due to float rounding.
     if(Math.round(earliest*rate)<priorEnd)
       earliest=Math.round((earliest+.01)*100)/100;
     const max=Math.max(0,bank[current.a].duration-current.seconds);
     const achievable=earliest<=max;
     return {pairId:current.id,
       message:current.id+' begint vóór de vorige inkomende overgang eindigt.',
       guidance:achievable?
         'Ga naar '+current.id+' (Deck A). Vroegste geldige startcue: '+
          format(earliest)+'; kies dit tijdstip zelf en luister naar de overgang.':
         'Ga naar '+current.id+'. Er past geen latere Deck A-cue in dit '+
         'bronnummer; pas de eerdere Deck B-cue aan of maak een nieuw plan.'};
   }
 }
 return null;
}
function cueProblem(){return cueProblemDetail()?.message||null;}
// Reconstruct the planned complete WAV's nonempty chapters using the
// exact local manually selected PCM16 source frames. No audio is rendered.
function plannedSetTimeline(){
 if(cueProblem())return null;
 const connected=[pairs[0].a,...pairs.map(p=>p.b)];
 if(connected.length!==data.tracks.length ||
    new Set(connected).size!==connected.length ||
    data.tracks.some(t=>!connected.includes(t.id)))return null;
 const rate=bank[connected[0]].sample_rate;
 if(data.tracks.some(t=>t.sample_rate!==rate || t.channels<1))return null;
 let total=0,previousEnd=0;const chapters=[];
 function append(kind,id,frames,description){
   if(frames<0)throw Error('Cue valt vóór een vorige overgang');
   if(frames>0)chapters.push({kind,id,from:total,to:total+frames,
     frames,description});
   total+=frames;
 }
 for(const pair of pairs){
   const length=Math.round(pair.beats*60/bank[pair.a].bpm*rate);
   const outgoing=Math.round(pair.a_start_seconds*rate);
   const incoming=Math.round(pair.b_start_seconds*rate);
   if(length<2 || outgoing<previousEnd ||
      outgoing+length>bank[pair.a].frame_count ||
      incoming+length>bank[pair.b].frame_count)return null;
   append('solo',pair.a,outgoing-previousEnd,bank[pair.a].display_name);
   append('transition',pair.id,length,
      bank[pair.a].display_name+' → '+bank[pair.b].display_name);
   previousEnd=incoming+length;
 }
 const last=connected[connected.length-1];
 const tail=bank[last].frame_count-previousEnd;
 if(tail<0)return null;
 append('solo',last,tail,bank[last].display_name);
 if(total<2 || 44+total*4>512*1024*1024)return null;
 return {rate,total,chapters};
}
const originalCueValues=pairs.map(p=>({id:p.id,a:p.a_start_seconds,b:p.b_start_seconds}));
const undoHistory=[],redoHistory=[];
function snapshot(forPair=chosen.id){
 return {pairId:forPair,values:pairs.map(p=>[p.a_start_seconds,p.b_start_seconds])};
}
function rememberCueEdit(){
 undoHistory.push(snapshot());
 if(undoHistory.length>40)undoHistory.shift();
 redoHistory.length=0;
}
function restoreSnapshot(record){
 pairs.forEach((p,i)=>{
  p.a_start_seconds=record.values[i][0];
  p.b_start_seconds=record.values[i][1];
 });
 chosen=pairs.find(p=>p.id===record.pairId);
 pairSelect.value=chosen.id;refresh();
}
function undoCueEdit(){
 if(!undoHistory.length)return;
 const prior=undoHistory.pop();
 redoHistory.push(snapshot(prior.pairId));restoreSnapshot(prior);
}
function redoCueEdit(){
 if(!redoHistory.length)return;
 const next=redoHistory.pop();
 undoHistory.push(snapshot(next.pairId));restoreSnapshot(next);
}
function restoreAllCues(){
 if(!edited)return;
 if(!window.confirm('Alle handmatige cuewijzigingen herstellen? Je kunt dit nog ongedaan maken.'))return;
 rememberCueEdit();
 pairs.forEach((p,i)=>{p.a_start_seconds=originalCueValues[i].a;
   p.b_start_seconds=originalCueValues[i].b;});
 refresh();
}
function restoreCurrentPair(){
 const original=originalCueValues.find(p=>p.id===chosen.id);
 if(chosen.a_start_seconds===original.a&&chosen.b_start_seconds===original.b)return;
 rememberCueEdit();chosen.a_start_seconds=original.a;
 chosen.b_start_seconds=original.b;refresh();
}
function validateLoadedCues(value){
 if(!value || typeof value!=="object" || Array.isArray(value) ||
    value.schema_version!==1 || value.kind!=="manual-cue-overrides" ||
    value.manifest_sha256!==data.manifest_sha256 ||
    !Array.isArray(value.pairs) || value.pairs.length!==pairs.length)
   throw Error("Cuekeuzes horen niet bij dit exacte originele bronmanifest.");
 const byId=new Map(pairs.map(p=>[p.id,p]));
 const seen=new Set(),selected=new Map();
 for(const item of value.pairs){
   if(!item || typeof item!=="object" || Array.isArray(item) ||
      Object.keys(item).sort().join(',')!==
        'a_start_seconds,b_start_seconds,id' ||
      !byId.has(item.id) || seen.has(item.id))
     throw Error("Ongeldige, vreemde of dubbele overgang in cuekeuzes.");
   const pair=byId.get(item.id);
   for(const [side,track] of [['a',bank[pair.a]],['b',bank[pair.b]]]){
     const seconds=item[side+'_start_seconds'];
     if(typeof seconds!=="number" || !Number.isFinite(seconds) ||
       seconds<0 || seconds>900 ||
       Math.round(seconds*track.sample_rate)+
         Math.round(pair.seconds*track.sample_rate)>track.frame_count)
       throw Error("Cue valt buiten de originele SHA-gecontroleerde WAV.");
   }
   seen.add(item.id);selected.set(item.id,item);
 }
 // Validate complete connected route and pair overlaps BEFORE altering
 // any live editor controls, including the last source PCM frame budget.
 const route=[pairs[0].a,...pairs.map(p=>p.b)];
 if(route.length!==data.tracks.length ||
    new Set(route).size!==route.length ||
    data.tracks.some(t=>!route.includes(t.id)))
   throw Error("Cuekeuzes beschrijven geen complete originele playlist.");
 let previous=null,tailStart=0,total=0;
 for(const pair of pairs){
   const cue=selected.get(pair.id),track=bank[pair.a];
   const frames=Math.round(pair.seconds*track.sample_rate);
   const a=Math.round(cue.a_start_seconds*track.sample_rate);
   const b=Math.round(cue.b_start_seconds*track.sample_rate);
   if(previous && (pair.a!==previous.b || a<tailStart))
     throw Error("Nieuwe uitgaande cue overlapt de vorige overgang.");
   total+=a-tailStart+frames;
   tailStart=b+frames;previous=pair;
 }
 const last=bank[route[route.length-1]];
 const tail=last.frame_count-tailStart;
 if(tail<0 || total+tail<2 || 44+(total+tail)*4>512*1024*1024)
   throw Error("De geselecteerde cues passen niet in één complete WAV.");
 return selected;
}
const originalTiming=plannedSetTimeline();
function refreshHistoryStatus(){
 const changed=originalCueValues.filter((c,i)=>
   pairs[i].a_start_seconds!==c.a||pairs[i].b_start_seconds!==c.b).length;
 edited=changed>0;
 const saved=originalCueValues.find(p=>p.id===chosen.id);
 $('undo').disabled=!undoHistory.length;
 $('redo').disabled=!redoHistory.length;
 $('restore-all').disabled=!edited;
 $('restore-pair').disabled=chosen.a_start_seconds===saved.a&&
   chosen.b_start_seconds===saved.b;
 $('history-status').textContent=changed+' van '+pairs.length+
   ' overgangen gewijzigd · '+undoHistory.length+' stappen terug beschikbaar.';
}
function refreshLiveTimeline(){
 const list=$('mix-timeline'),summary=$('mix-timing-summary');
 list.replaceChildren();
 const planned=plannedSetTimeline();
 if(!planned){
   summary.textContent='De complete mixtijd is nog niet berekenbaar. '+
     'Controleer de doorlopende trackvolgorde, alle nummers en cueposities.';
   return;
 }
 const edited=pairs.filter((p,i)=>p.a_start_seconds!==originalCueValues[i].a ||
   p.b_start_seconds!==originalCueValues[i].b).length;
 const diff=originalTiming?(planned.total-originalTiming.total)/planned.rate:null;
 const comparison=diff===null?'geen geldige originele referentie':
   Math.abs(diff)<.000001?'gelijke totale duur als originele cues':
   (diff>0?'+':'')+diff.toFixed(2)+' s t.o.v. opgeslagen cues';
 summary.textContent='Verwachte complete set: '+format(planned.total/planned.rate)+
   ' · '+edited+' handmatig gewijzigde overgangen · '+comparison+
   ' · '+planned.chapters.length+' niet-lege hoofdstukken.';
 for(const chapter of planned.chapters){
   const li=document.createElement('li');
   const timing=document.createElement('small');
   timing.textContent=format(chapter.from/planned.rate)+' – '+
     format(chapter.to/planned.rate);
   const body=document.createElement('div');
   const title=document.createElement('strong');
   title.textContent=chapter.description;
   const detail=document.createElement('small');
   detail.textContent=(chapter.kind==='transition'?'Overgang '+chapter.id:'Nummer '+chapter.id);
   body.append(title,detail);
   if(chapter.kind==='transition'){
     const edit=document.createElement('button');
     edit.textContent='Wijzig deze overgang';
     edit.setAttribute('aria-label','Wijzig overgang: '+chapter.description);
     edit.addEventListener('click',()=>{
       pairSelect.value=chapter.id;
       chosen=pairs.find(p=>p.id===chapter.id);
       refresh();
     });
     body.append(edit);
   }
   li.append(timing,body);list.append(li);
 }
}
function refreshCueStatus(){
 refreshHistoryStatus();
 const issue=cueProblemDetail();
 const problem=(issue&&issue.message) || (!plannedSetTimeline()?
   'De opgegeven nummers vormen geen complete, renderbare mix. '+
   'Verbind alle bronnen precies eenmaal voordat je cuekeuzes bewaart.':null);
 $('save').disabled=!!problem;
 $('message').textContent=problem?'Nog niet opslaan: '+problem:
   edited?'Cues klaar. Download je keuzes voordat je de pagina sluit.':
   'Je muziek blijft privé. Wijzigingen worden pas bewaard wanneer je de cuekeuzes downloadt.';
 $('cue-problem-navigation').hidden=!issue;
 $('jump-to-problem').disabled=!issue;
 $('cue-problem-guidance').textContent=issue?issue.guidance:'';
 refreshLiveTimeline();
}
function format(seconds){const m=Math.floor(seconds/60);const s=(seconds%60).toFixed(2).padStart(5,'0');return String(m)+':'+s;}
function deck(side){return bank[chosen[side]];}
function maxStart(side){return Math.max(0,deck(side).duration-chosen.seconds);}
function snapTime(value,side,fine=false){
 const track=deck(side),beat=60/track.bpm;
 if(!fine&&$('snap').checked&&typeof track.first_downbeat_seconds==='number'){
   value=track.first_downbeat_seconds+Math.round((value-track.first_downbeat_seconds)/beat)*beat;
 }
 return Math.max(0,Math.min(maxStart(side),Math.round(value*100)/100));
}
function setCue(side,value,fine=false){
 const key=side+'_start_seconds',next=snapTime(value,side,fine);
 if(next!==chosen[key]){
   stopPlayback();
   rememberCueEdit();
   chosen[key]=next;
 }
 refreshSide(side);
 refreshCueStatus();
}
function stopPlayback(){
  ++duetSerial;
  if(playing){playing.pause();playing=null;}
  if(duetActive){
    duetActive=false;
    for(const side of ['a','b'])$('audio-'+side).pause();
    if(duetVolumes){
      $('audio-a').volume=duetVolumes[0];
      $('audio-b').volume=duetVolumes[1];
    }
  }
  duetVolumes=null;duetEnds=null;
  $('play-ab').disabled=false;
  $('stop-ab').disabled=true;
}
function draw(side){
 const t=deck(side),canvas=$('wave-'+side),ctx=canvas.getContext('2d');
 const w=canvas.width,h=canvas.height,signal=t.waveform;
 ctx.clearRect(0,0,w,h);
 ctx.fillStyle='#111521';ctx.fillRect(0,0,w,h);
 let max=.01;
 for(const v of signal){if(v>max)max=v;}
 ctx.fillStyle='#8c83dc';
 for(let x=0;x<w;x++){
    const l=Math.floor(x*signal.length/w),r=Math.max(l+1,Math.floor((x+1)*signal.length/w));
    let peak=0;for(let k=l;k<Math.min(r,signal.length);k++)peak=Math.max(peak,signal[k]);
    const height=Math.max(1,Math.min(h-14,peak/max*(h-14)));
    ctx.fillRect(x,(h-height)/2,1,height);
 }
 const start=chosen[side+'_start_seconds'],left=start/t.duration*w;
 const size=chosen.seconds/t.duration*w;
 ctx.fillStyle='rgba(177,240,207,.19)';ctx.fillRect(left,0,size,h);
 ctx.strokeStyle='#b3f5d8';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(left,0);ctx.lineTo(left,h);ctx.stroke();
 ctx.fillStyle='#dae0f3';ctx.font='13px system-ui';
 ctx.fillText(format(0),9,h-9);ctx.fillText(format(t.duration),w-65,h-9);
}
function refreshSide(side){
 const t=deck(side),time=chosen[side+'_start_seconds'];
 $('time-'+side).textContent=format(time);
 $('range-'+side).value=String(time);
 draw(side);
}
function refresh(){
 stopPlayback();
 $('pair-info').textContent=chosen.beats+' beats · '+chosen.seconds.toFixed(2)+' s';
 for(const side of ['a','b']){
  const t=deck(side);
  $('name-'+side).textContent=t.display_name;
  $('info-'+side).textContent='Bron '+t.id+' · '+t.bpm+' BPM (handmatig) · '+format(t.duration)+' · '+t.sample_rate+' Hz';
  const slider=$('range-'+side);slider.max=String(maxStart(side));slider.value=String(chosen[side+'_start_seconds']);
  const audio=$('audio-'+side);audio.pause();audio.removeAttribute('src');audio.src=t.path.split('/').map(encodeURIComponent).join('/');audio.load();
  refreshSide(side);
 }
 refreshCueStatus();
}
pairSelect.addEventListener('change',()=>{
 chosen=pairs.find(p=>p.id===pairSelect.value);refresh();
});
$('jump-to-problem').addEventListener('click',()=>{
 const issue=cueProblemDetail();
 if(!issue)return;
 const target=pairs.find(p=>p.id===issue.pairId);
 if(!target)return;
 chosen=target;pairSelect.value=target.id;refresh();
 $('wave-a').focus();
});
$('undo').addEventListener('click',undoCueEdit);
$('redo').addEventListener('click',redoCueEdit);
$('restore-pair').addEventListener('click',restoreCurrentPair);
$('restore-all').addEventListener('click',restoreAllCues);
let cueImportBusy=false;
$('cue-import').addEventListener('click',async()=>{
 if(cueImportBusy)return;
 const input=$('cue-import-file'),file=input.files && input.files[0];
 const status=$('cue-import-status');
 if(!file){status.textContent='Kies eerst een opgeslagen privé-JSON.';return;}
 if(!Number.isSafeInteger(file.size) || file.size<1 || file.size>65536){
   status.textContent='Cuekeuzes mogen maximaal 64 KiB groot zijn.';return;
 }
 if(edited && !window.confirm('Dit vervangt de huidige onopgeslagen cues. '+
      'Heb je jouw keuzes al gedownload?')){
   status.textContent='Laden geannuleerd; huidige cues zijn behouden.';return;
 }
 const previous=snapshot();
 cueImportBusy=true;input.disabled=true;$('cue-import').disabled=true;
 try{
   const raw=await file.text();
   if(raw.length>65536 || input.files[0]!==file ||
      pairs.some((p,i)=>p.a_start_seconds!==previous.values[i][0] ||
                         p.b_start_seconds!==previous.values[i][1]))
     throw Error('De editor is tijdens het laden gewijzigd.');
   const accepted=validateLoadedCues(JSON.parse(raw));
   // A valid saved revision becomes exactly ONE Undo operation.
   rememberCueEdit();
   for(const pair of pairs){
     const stored=accepted.get(pair.id);
     pair.a_start_seconds=stored.a_start_seconds;
     pair.b_start_seconds=stored.b_start_seconds;
   }
   refresh();
   status.textContent=pairs.length+' cueparen hersteld uit deze originele '+
     'SHA-gebonden playlist. Je kunt dit in één stap ongedaan maken.';
 }catch(error){
   status.textContent='Import geweigerd: '+(error instanceof SyntaxError?
     'geen geldige JSON.':error.message);
 }finally{
   cueImportBusy=false;input.disabled=false;$('cue-import').disabled=false;
 }
});
for(const side of ['a','b']){
 const t=$('range-'+side);t.addEventListener('input',()=>setCue(side,Number(t.value)));
 const canvas=$('wave-'+side);
 function moveFromCanvas(fraction){setCue(side,fraction*deck(side).duration);}
 canvas.addEventListener('click',e=>moveFromCanvas((e.clientX-canvas.getBoundingClientRect().left)/canvas.getBoundingClientRect().width));
 canvas.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();setCue(side,chosen[side+'_start_seconds']+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?.1:60/deck(side).bpm),Boolean(e.shiftKey));}});
 for(const [name,beats] of [['prev',-1],['next',1],['barprev',-4],['barnext',4]]){
  $(name+'-'+side).addEventListener('click',()=>setCue(side,chosen[side+'_start_seconds']+beats*60/deck(side).bpm));
 }
 for(const [name,amount] of [['fineprev',-.1],['finenext',.1]]){
  $(name+'-'+side).addEventListener('click',()=>setCue(side,chosen[side+'_start_seconds']+amount,true));
 }
 $('play-'+side).addEventListener('click',async()=>{
   stopPlayback();const a=$('audio-'+side);
   try{a.currentTime=chosen[side+'_start_seconds'];stopAt=chosen[side+'_start_seconds']+chosen.seconds;playing=a;await a.play();}
   catch(err){$('message').textContent='Browser kan deze privé-WAV niet afspelen. Open de HTML naast je originele muziekbestanden en controleer de bestandsrechten.';}
 });
 const audio=$('audio-'+side);
 audio.addEventListener('timeupdate',()=>{
   if(playing===audio&&audio.currentTime>=stopAt)stopPlayback();
   if(duetActive&&duetEnds&&(
       $('audio-a').currentTime>=duetEnds[0] ||
       $('audio-b').currentTime>=duetEnds[1]))stopPlayback();
 });
 audio.addEventListener('ended',()=>{if(duetActive)stopPlayback();});
 audio.addEventListener('ended',()=>{if(playing===audio)playing=null;});
}
$('play-ab').addEventListener('click',async()=>{
  stopPlayback();
  if(cueProblem() || !plannedSetTimeline()){
    $('ab-status').textContent='Corrigeer eerst de ongeldige complete playlist/cues.';
    return;
  }
  const a=$('audio-a'),b=$('audio-b');
  const token=duetSerial;
  duetVolumes=[a.volume,b.volume];
  duetEnds=[chosen.a_start_seconds+chosen.seconds,
            chosen.b_start_seconds+chosen.seconds];
  a.currentTime=chosen.a_start_seconds;
  b.currentTime=chosen.b_start_seconds;
  a.volume=.3;b.volume=.3;
  duetActive=true;
  $('play-ab').disabled=true;$('stop-ab').disabled=false;
  $('ab-status').textContent='A + B tegelijk: '+chosen.id+' · '+
    chosen.seconds.toFixed(2)+' s. Ruwe timingcontrole, geen DJ-render.';
  try{
    await Promise.all([a.play(),b.play()]);
  }catch(error){
    if(duetActive&&token===duetSerial){
      stopPlayback();
      $('ab-status').textContent='Kan beide lokale WAVs niet tegelijk afspelen.';
    }
  }
});
$('stop-ab').addEventListener('click',()=>{
  if(!duetActive)return;
  stopPlayback();
  $('ab-status').textContent='Beide decks gestopt.';
});
$('snap').addEventListener('change',()=>{for(const side of ['a','b'])refreshSide(side);});
$('save').addEventListener('click',()=>{
 if(cueProblem()){
   refreshCueStatus();return; // Never export a knowingly unrenderable set.
 }
 const record={schema_version:1,kind:'manual-cue-overrides',manifest_sha256:data.manifest_sha256,
   pairs:pairs.map(p=>({id:p.id,a_start_seconds:p.a_start_seconds,b_start_seconds:p.b_start_seconds}))};
 const blob=new Blob([JSON.stringify(record,null,2)+'\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob);const link=document.createElement('a');
 link.href=url;link.download='mixlab-cue-selections.json';link.click();
 setTimeout(()=>URL.revokeObjectURL(url),3000);
 $('message').textContent='Cuekeuzes gedownload. Pas ze toe op een NIEUW bronmanifest; je originele muziek is niet gewijzigd.';
});
refresh();
</script></body></html>
'''


def prepare(source_manifest, output_html):
    """Generate a browser-playable offline editor beside the private WAVs."""
    manifest = Path(source_manifest).absolute()
    output = Path(output_html).absolute()
    if output.parent != manifest.parent or output.suffix.lower() != ".html":
        raise ValueError("Store editor HTML beside its private source manifest")
    if output.exists() or output.is_symlink():
        raise ValueError("Editor file already exists; original artifacts are immutable")
    for ancestor in (output, *output.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Never publish a private local audio editor inside a Git checkout")
    _spec, tracks, pairs = _admit_library(manifest, calculate_waveforms=True)
    payload = {"schema_version": 1, "kind": "manual-cue-editor",
               "manifest_sha256": digest(manifest), "tracks": list(tracks.values()),
               "pairs": pairs}
    serialized = json.dumps(payload, allow_nan=False, ensure_ascii=True,
                            separators=(",", ":")).replace("<", "\\u003c")
    rendered = _HTML.replace("__DATA__", serialized)
    raw = rendered.encode("utf-8")
    if len(raw) > MAX_EDITOR_BYTES:
        raise ValueError("Waveform editor exceeds private 2 MiB HTML limit; prepare fewer tracks")
    try:
        with output.open("xb") as target:
            os.fchmod(target.fileno(), 0o600)
            target.write(raw)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def apply(source_manifest, selection_json, destination):
    """Apply exact-source browser cue choices to a NEW canonical manifest."""
    source_manifest = Path(source_manifest).absolute()
    destination = Path(destination).absolute()
    if destination.parent != source_manifest.parent or destination.suffix.lower() != ".json":
        raise ValueError("Save new cue manifest alongside the source WAV manifest")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Do not overwrite an existing or frozen source manifest")
    original, _tracks, pairs = _admit_library(source_manifest, calculate_waveforms=False)
    choices = _read_spec(Path(selection_json).absolute())
    if (choices.get("kind") != "manual-cue-overrides"
            or choices.get("manifest_sha256") != digest(source_manifest)):
        raise ValueError("Cue choices are not bound to this exact original source manifest")
    entries = choices.get("pairs")
    if not isinstance(entries, list) or len(entries) != len(pairs):
        raise ValueError("Cue selection must include each declared pair exactly once")
    selected = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "a_start_seconds", "b_start_seconds"}:
            raise ValueError("Unexpected cue entry fields")
        pid = entry["id"]
        if not isinstance(pid, str) or pid in selected:
            raise ValueError("Duplicate or invalid selected pair ID")
        selected[pid] = entry
    if set(selected) != {p["id"] for p in pairs}:
        raise ValueError("Cue choices contain missing or foreign pair IDs")
    for item in original["pairs"]:
        original_pair = next(p for p in pairs if p["id"] == item["id"])
        for side in ("a", "b"):
            meta = _tracks[item[side]]
            start = _require_number(selected[item["id"]][side + "_start_seconds"],
                                    "selected cue seconds", 0, 900)
            frames = round(start * meta["sample_rate"]) + round(
                original_pair["seconds"] * meta["sample_rate"])
            if frames > meta["frame_count"]:
                raise ValueError("Selected cue extends past the source audio")
            item[side + "_start_seconds"] = round(start, 6)
    # The cue editor may display a partial library to inspect original
    # waveforms, but an exported cue manifest must be a *complete* set.
    # A valid A->B->C list can otherwise quietly omit song D.
    route = [pairs[0]['a'], *(p['b'] for p in pairs)]
    if (len(route) != len(_tracks) or len(set(route)) != len(route)
            or set(route) != set(_tracks)):
        raise ValueError(
            'Een volledige mix moet elk geregistreerd nummer precies eenmaal bevatten; '
            'vul eerst de ontbrekende overgang in het originele bronmanifest aan')
    # A cue is only useful if the complete saved A->B->C set remains
    # renderable. Prior import checks covered each pair independently,
    # allowing a later outgoing cue to overlap the preceding incoming one.
    # Enforce the same PCM frame boundaries as the full-set exporter BEFORE
    # creating a new source manifest; original audio and choices stay intact.
    previous = None
    for pair in original["pairs"]:
        if previous is not None:
            if pair["a"] != previous["b"]:
                raise ValueError("Overgangsparen vormen geen doorlopende afspeelvolgorde")
            track = _tracks[pair["a"]]
            rate = track["sample_rate"]
            prev_beats = previous.get("beats", 8)
            prev_bpm = _tracks[previous["a"]]["bpm"]
            prior_end = round(previous["b_start_seconds"] * rate) + round(
                prev_beats * 60 / prev_bpm * rate)
            start_frame = round(pair["a_start_seconds"] * rate)
            if start_frame < prior_end:
                raise ValueError(
                    "Uitgaande cue van " + pair["id"] +
                    " overlapt de vorige inkomende overgang; "
                    "schuif de cue later voordat je opslaat")
        previous = pair
    raw = (json.dumps(original, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    try:
        with destination.open("xb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def apply_with_private_plan(source_manifest, selection_json, destination,
                            *, verify_wavs=False):
    """Save manually revised cues AND a separate offline preview, no audio."""
    destination = Path(destination).absolute()
    parent = destination.parent.parent
    planned_wav = parent / (destination.stem + '-planned-set.wav')
    planned_session = parent / (destination.stem + '-plan-only-session')
    html = Path(str(planned_wav) + '.preview.html')
    # Check the optional page's location before committing a new source
    # manifest; never overwrite an existing plan or a real user WAV.
    from .session import _private_project_dir
    from .set_export import _valid_destination
    _private_project_dir(planned_session, Path(source_manifest).absolute())
    _valid_destination(planned_wav, planned_session)
    if html.exists() or html.is_symlink():
        raise ValueError('Private planned-mix HTML already exists; choose a fresh manifest name')
    result = apply(source_manifest, selection_json, destination)
    try:
        from .party_mix import render_party_mix
        new_source = _read_spec(result)
        family = new_source.get('default_family', 'bass_swap')
        preview = render_party_mix(
            result, planned_session, planned_wav, family=family,
            preview=True, verify_wavs=verify_wavs, preview_html=True,
            preview_workflow='guided')
    except (ValueError, TypeError, OSError, KeyError) as exc:
        # An optional HTML failure cannot erase valid manually authored cues.
        raise ValueError('New private cue manifest was preserved, but the '
                         'optional private plan could not be created: '
                         + str(exc)) from exc
    return result, preview


def main():
    parser = argparse.ArgumentParser(description="MixLab visual cue selection on private local WAVs")
    modes = parser.add_subparsers(dest="mode", required=True)
    p = modes.add_parser("prepare", help="Write a static waveform editor beside private WAV manifest")
    p.add_argument("source_manifest")
    p.add_argument("output_html")
    p = modes.add_parser("apply", help="Pin manually chosen cues into a NEW private manifest")
    p.add_argument("source_manifest")
    p.add_argument("selection_json")
    p.add_argument("output_manifest")
    p.add_argument("--plan-html", action="store_true",
                   help="Also create a new private visual full-set plan, without a Studio or WAV")
    p.add_argument("--plan-verify-wavs", action="store_true",
                   help="With --plan-html: verify original PCM16 SHA hashes and exact chapter times")
    args = parser.parse_args()
    try:
        extra = {}
        if args.mode == "prepare":
            result = prepare(args.source_manifest, args.output_html)
        elif args.plan_verify_wavs and not args.plan_html:
            raise ValueError("--plan-verify-wavs requires --plan-html")
        elif args.plan_html:
            result, preview = apply_with_private_plan(
                args.source_manifest, args.selection_json, args.output_manifest,
                verify_wavs=args.plan_verify_wavs)
            extra = {"private_plan_html": preview["preview_html"],
                     "actual_wav_rendered": False,
                     "planned_mix_seconds": (preview["complete_mix_duration"]
                                             if args.plan_verify_wavs else None)}
        else:
            result = apply(args.source_manifest, args.selection_json, args.output_manifest)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, "MixLab cue editor: " + str(exc) + "\n")
    print(json.dumps({"ready": True, "private_file": str(result),
                      "mode": args.mode, "audio_uploaded": False,
                      "cue_source": "manually chosen", **extra}))


if __name__ == "__main__":
    main()
