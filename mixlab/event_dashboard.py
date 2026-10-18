"""Private offline event landing page for a canonical rendered MixLab WAV.

All statistics come from the actual original session/WAV SHA receipts.
No embedded source music, external scripts, uploads or preference claims.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from .ingest import digest
from .set_composer import _parse_json, _secure_file
from .set_player import build_chapters

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self'; object-src 'none'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab — Your Private DJ Set</title>
<style>
:root{color-scheme:dark;--bg:#080f19;--panel:#162638;--line:#344e65;--muted:#b1c5d5;--ink:#f1f7ff;--mint:#88f7c8;--blue:#99bfff}
*{box-sizing:border-box}
body{font:15px/1.5 system-ui,-apple-system,Arial,sans-serif;background:radial-gradient(at 80% 0%,#204e4a,var(--bg) 61%);color:var(--ink);margin:0}
main{max-width:1240px;margin:0 auto;padding:clamp(18px,4vw,58px)}
.topline{color:var(--mint);font-size:12px;letter-spacing:.19em;font-weight:800;text-transform:uppercase}
h1{font-size:clamp(40px,6vw,78px);letter-spacing:-.055em;line-height:1;margin:12px 0}
h2{font-size:clamp(20px,2.7vw,27px);margin:0 0 10px}h3{font-size:17px;margin:0 0 5px}
p{color:var(--muted)}
.hero{padding:clamp(20px,4vw,48px);border:1px solid #456f68;border-radius:28px;background:linear-gradient(140deg,#1f4943,#101e31 70%);margin:20px 0 26px}
.hero p{max-width:630px}.stats{display:flex;gap:10px;flex-wrap:wrap;margin:30px 0}
.stat{display:grid;gap:2px;background:#0f2d34;border:1px solid #31595b;border-radius:15px;padding:12px 18px;min-width:140px}
.stat strong{font-size:24px}.stat span{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.card{border:1px solid var(--line);background:var(--panel);border-radius:22px;padding:25px;min-width:0}
.large{grid-column:span 2}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}
a.action{display:inline-flex;align-items:center;justify-content:center;min-height:48px;text-align:center;border:1px solid #658ba2;border-radius:12px;padding:10px 18px;color:white;text-decoration:none;background:#2b4d66;font-weight:800}
a.action.primary{background:var(--mint);color:#08261a;border-color:transparent}
a.action:hover,a.action:focus-visible{outline:2px solid var(--mint);outline-offset:2px}
audio{display:block;width:100%;margin:18px 0}
.wave{display:grid;align-items:center;grid-template-columns:repeat(64,minmax(0,1fr));gap:3px;height:100px}
.wave span{background:linear-gradient(#8cfad3,#447e91);border-radius:3px;min-height:2px}
ol{list-style:none;padding:0;margin:0}
li{display:grid;grid-template-columns:105px 1fr auto;gap:14px;border-bottom:1px solid var(--line);padding:12px 0;align-items:center}
li:last-child{border-bottom:none}.timestamp{font-variant-numeric:tabular-nums;color:var(--mint);font-weight:800}
.chapter{overflow-wrap:anywhere}.tag{border-radius:20px;background:#25465b;padding:5px 10px;font-size:11px;color:#d6edff}
.notes{color:var(--muted);font-size:13px}.small{font-size:12px;color:var(--muted)}
.foot{margin:27px 0;max-width:800px;border-left:3px solid var(--mint);padding:4px 18px}
code{font-size:12px;overflow-wrap:anywhere}
@media(max-width:700px){.grid{grid-template-columns:1fr}.large{grid-column:span 1}li{grid-template-columns:74px 1fr}li .tag{grid-column:2;justify-self:start}.card{padding:18px}}
</style></head><body>
<main>
<div class="topline">MIXLAB / PRIVATE OFFLINE DELIVERY</div>
<section class="hero">
<div class="topline">YOUR COMPLETE SET</div>
<h1>Your mix.<br>Your room.</h1>
<p>Your real offline mixed PCM16 WAV and actual rendered chapter timeline are ready. This is a private local event package, created from explicitly approved sources and the canonical MixLab engine.</p>
<div class="stats" id="stats"></div>
<div class="actions" id="hero-actions"></div>
</section>
<div class="grid">
<section class="card"><h2>Play the master here</h2>
<p>The original complete WAV is your sample-exact master. Use the chaptered player for event mode and navigation.</p>
<audio id="master" controls preload="metadata"></audio>
<p id="playback-message" class="small">If your browser cannot play this large local WAV, open the separate offline chapter player or a local audio application.</p>
<div class="actions" id="master-actions"></div>
</section>
<section class="card"><h2>Bring it to the event</h2>
<p>Keep a local backup, check speaker routing and use the printable operator runbook for transitions and stage notes.</p>
<div id="event-links" class="actions"></div>
<p class="notes">No cloud access required. This local landing page is not a high-availability live DJ mixer.</p>
</section>
<section class="card large"><h2>Your real set timeline</h2>
<p>Every offset below is bound to the PCM16 output receipt. Chapters use original private MixLab track/pair identifiers; no track title or audio was inferred.</p>
<div id="wave" class="wave" role="img" aria-label="Sampled waveform of the real completed master; not a loudness score"></div>
<ol id="chapters"></ol>
</section>
</div>
<p class="foot">Private local music delivery only. This page cannot establish independent licensing rights, musical quality, crowd response, beat/key/phrase inference or dependable professional audio hardware. Do not upload music or private receipts to public services.</p>
<p class="small" id="hash"></p>
</main>
<script id="mixlab-data" type="application/json">__DATA__</script>
<script>
"use strict";
const set=JSON.parse(document.getElementById("mixlab-data").textContent);
const byId=id=>document.getElementById(id);
const n=(tag,cls,label)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(label!==undefined)e.textContent=String(label);return e};
function localLink(filename,label,primary=false){
 const a=n("a","action"+(primary?" primary":""),label);
 a.href="./"+encodeURIComponent(filename);
 a.rel="noopener noreferrer";return a;
}
function duration(s){
 const t=Math.max(0,Math.floor(s));
 return String(Math.floor(t/3600)).padStart(2,"0")+":"+String(Math.floor(t%3600/60)).padStart(2,"0")+":"+String(t%60).padStart(2,"0");
}
function render(){
 const transitions=set.chapters.filter(x=>x.kind==="transition");
 const stats=byId("stats");
 [[set.chapters.filter(x=>x.kind==="track").length,"track passages"],
  [transitions.length,"real transitions"],
  [duration(set.duration_seconds),"actual runtime"]].forEach(pair=>{
  const item=n("div","stat");item.append(n("strong","",pair[0]),n("span","",pair[1]));stats.append(item);
 });
 byId("master").src="./"+encodeURIComponent(set.wav_name);
 const mainActions=byId("hero-actions"),master=byId("master-actions");
 if(set.player)mainActions.append(localLink(set.player,"Open chapter player",true));
 mainActions.append(localLink(set.wav_name,"Save the real WAV"));
 master.append(localLink(set.wav_name,"Download WAV master"));
 if(set.compressed){
  mainActions.append(localLink(set.compressed,"Take "+set.compressed.split(".").pop().toUpperCase()));
  master.append(localLink(set.compressed,"Download portable audio"));
 }
 const event=byId("event-links");
 if(set.runbook)event.append(localLink(set.runbook,"Open show runbook",true));
 if(set.rehearsal)event.append(localLink(set.rehearsal,"Rehearse transitions offline"));
 if(set.compressedPlayer)event.append(localLink(set.compressedPlayer,"Portable audio player"));
 if(!set.runbook&&!set.compressedPlayer&&!set.rehearsal)event.append(n("p","","Use your original offline WAV and chapter player; no optional companion was published."));
 const sample=set.waveform;
 const cols=64;
 for(let i=0;i<cols;i++){
  const from=Math.floor(i*sample.length/cols),to=Math.max(from+1,Math.floor((i+1)*sample.length/cols));
  const peak=sample.slice(from,to).reduce((a,b)=>Math.max(a,b),0);
  const bar=n("span");bar.style.height=String(Math.max(3,Math.round(peak*90)))+"px";byId("wave").append(bar);
 }
 for(const ch of set.chapters){
  const item=n("li");
  item.append(n("span","timestamp",duration(ch.start_seconds)));
  const label=n("span","chapter",(ch.kind==="transition"?"Transition ":"Track ")+ch.label);
  item.append(label,n("span","tag",ch.family||"source"));
  byId("chapters").append(item);
 }
 byId("hash").textContent="Exact WAV SHA-256: "+set.wav_sha256;
}
byId("master").addEventListener("error",()=>{
 byId("playback-message").textContent="Local WAV not playable by this browser. Use the offline chapter player or an audio app; the complete original file is still available.";
});
render();
</script></body></html>
"""


def _local_optional(audio_parent, source, suffixes, *, required=False):
    if source is None:
        if required:
            raise ValueError("Missing required offline event companion")
        return None
    candidate = Path(source).absolute()
    if (candidate.parent != audio_parent or candidate.suffix.lower() not in suffixes
            or candidate.is_symlink() or not candidate.is_file()):
        raise ValueError("Optional event file must be a regular local companion beside the WAV")
    meta = candidate.lstat()
    if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= 512 * 1024 * 1024:
        raise ValueError("Optional event companion is unavailable or oversized")
    return candidate


def create_dashboard(private_session, complete_wav, new_html, *,
                     compressed=None, runbook=None, player=None, rehearsal=None):
    wav = Path(complete_wav).absolute()
    target = Path(new_html).absolute()
    if (target.parent != wav.parent or target.suffix.lower() != ".html" or
            target.exists() or target.is_symlink()):
        raise ValueError("Choose a NEW private dashboard HTML beside the complete WAV")
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or (ancestor / ".git").exists():
            raise ValueError("Offline event page must be outside Git and symlinked paths")
    metadata = build_chapters(private_session, wav)
    parent = wav.parent

    companion = None
    compressed_player = None
    if compressed is not None:
        if not isinstance(compressed, dict) or not isinstance(compressed.get("receipt"), str):
            raise ValueError("Compressed delivery requires official receipt metadata")
        companion = _local_optional(parent, compressed.get("private_delivery"), (".mp3", ".flac"), required=True)
        receipt_path = _local_optional(parent, compressed["receipt"], (".json",), required=True)
        details = _parse_json(_secure_file(receipt_path, 65536))
        if (details.get("kind") != "private-compressed-continuous-set-delivery"
                or details.get("source_set_sha256") != metadata["wav_sha256"]
                or details.get("output_sha256") != digest(companion)
                or details.get("format") != companion.suffix.lower()[1:]):
            raise ValueError("Portable file/receipt does not belong to this exact private WAV")
        compressed_player = _local_optional(parent, compressed.get("offline_player"), (".html",))
    player = _local_optional(parent, player, (".html",))
    runbook = _local_optional(parent, runbook, (".html",))
    rehearsal = _local_optional(parent, rehearsal, (".html",))

    blob = json.dumps({
        "wav_name": metadata["wav_name"],
        "wav_sha256": metadata["wav_sha256"],
        "duration_seconds": metadata["duration_seconds"],
        "waveform": metadata["waveform"],
        "chapters": metadata["chapters"],
        "player": player.name if player else None,
        "runbook": runbook.name if runbook else None,
        "rehearsal": rehearsal.name if rehearsal else None,
        "compressed": companion.name if companion else None,
        "compressedPlayer": compressed_player.name if compressed_player else None,
    }, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _PAGE.replace("__DATA__", blob).encode("utf-8")
    if len(page) > 512 * 1024:
        raise ValueError("Private event dashboard exceeds 512 KiB")
    with target.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(page)
    return target


def main():
    parser = argparse.ArgumentParser(
        description="Create an offline landing page for an existing hash-verified full MixLab WAV event")
    parser.add_argument("private_session")
    parser.add_argument("complete_wav")
    parser.add_argument("new_dashboard_html")
    parser.add_argument("--player")
    parser.add_argument("--runbook")
    parser.add_argument("--rehearsal")
    parser.add_argument("--compressed")
    parser.add_argument("--compressed-receipt")
    parser.add_argument("--compressed-player")
    args = parser.parse_args()
    delivery = None
    if args.compressed or args.compressed_receipt or args.compressed_player:
        if not args.compressed or not args.compressed_receipt:
            parser.exit(2, "Provide both official compressed file and receipt\n")
        delivery = {"private_delivery": args.compressed,
                    "receipt": args.compressed_receipt,
                    "offline_player": args.compressed_player}
    try:
        result = create_dashboard(args.private_session, args.complete_wav,
                                  args.new_dashboard_html, compressed=delivery,
                                  runbook=args.runbook, player=args.player,
                                  rehearsal=args.rehearsal)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, "MixLab Event Dashboard: " + str(exc) + "\n")
    print(json.dumps({"private_dashboard": str(result), "offline": True,
                      "real_receipt_verified": True,
                      "human_preference_proven": False}))


if __name__ == "__main__":
    main()
