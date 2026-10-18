"""Offline full-length DJ set family gallery with position-synced listening.

Renders 2..4 real variations using the existing canonical complete-set
exporter. Never uploads music, uses a fake soundbite or declares blind
listening evidence. Real source/Studio receipts remain immutable.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import wave

from .instant_set import _choose_transitions, render_instant_set
from .set_player import build_chapters
from .studio import FAMILY_NAMES

MAX_VARIANTS = 4
MAX_GALLERY_BYTES = 2 * 1024 * 1024

HTML = """<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; object-src 'none'; connect-src 'none'">
<title>MixLab / Complete Set Gallery</title>
<style>
:root{font:16px system-ui,sans-serif;background:#0d0e16;color:#f6f4ff;color-scheme:dark}
*{box-sizing:border-box}body{margin:0}main{max-width:1030px;margin:auto;padding:40px 18px 80px}
.eyebrow{font-size:.76rem;letter-spacing:.19em;color:#beaaff;font-weight:850}
h1{font-size:clamp(3rem,9vw,6rem);line-height:1;letter-spacing:-.075em;margin:14px 0}
p{color:#afb9d1;line-height:1.6;max-width:790px}.card{background:#1b1e2e;border:1px solid #41435a;
border-radius:19px;padding:23px;margin-top:20px}
.family-options{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}
button{font:inherit;color:#faf8ff;background:#34324b;border:1px solid #707094;
cursor:pointer;border-radius:10px;padding:12px 15px}
button[aria-pressed=true]{background:#7259c0;border-color:#c5baff}
button:hover,button:focus-visible{outline:2px solid #a998ff;outline-offset:3px}
audio{width:100%;margin:15px 0}.timeline{width:100%;accent-color:#b09bfa;margin:12px 0}
.chapter{display:flex;gap:10px;justify-content:space-between;margin:8px 0;
padding:10px 12px;border-radius:9px;border:1px solid #44475d;background:#25283b}
.chapter button{flex:1;text-align:left}.chapter span{color:#b1b8cb;font-size:.8rem;align-self:center}
.muted{font-size:.88rem;color:#a3adc7}#status{min-height:1.4em}
</style></head><body><main>
<div class="eyebrow">MIXLAB / PRIVATE FULL SET GALLERY</div>
<h1>Hear the whole<br>journey.</h1>
<p>Vergelijk dezelfde volledige playlist met verschillende <strong>écht
gerenderde</strong> overgangsstijlen. Schakel tijdens het luisteren van
variant: MixLab houdt je positie op dezelfde tijdlijn vast. Dit is een
creatieve, niet-geblindeerde vergelijking; geen onderzoeksuitslag.</p>
<section class="card"><h2>Welke mix speel je?</h2><div class="family-options" id="families"></div>
<audio controls preload="metadata" id="player"></audio>
<label for="seek">Volledige set · klik om te springen</label>
<input class="timeline" type="range" min="0" step="0.1" id="seek">
<div id="status" role="status" aria-live="polite"></div>
<p class="muted">Alle media staan lokaal naast deze pagina. Geen netwerk, CDN of uploads.</p>
</section><section class="card"><h2>Hoofdstukken en overgangen</h2>
<div id="chapters"></div></section>
<script type="application/json" id="data">__DATA__</script><script>
"use strict";
const metadata=JSON.parse(document.getElementById("data").textContent);
const player=document.getElementById("player");
const buttons=document.getElementById("families");
const seek=document.getElementById("seek");
const chapters=document.getElementById("chapters");
const status=document.getElementById("status");
let active=0;
let wantedSeek=null;
seek.max=String(metadata.duration_seconds);
const fmt=(value)=>{const n=Math.max(0,Math.floor(value));return
 String(Math.floor(n/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0")};
function switchTo(index){
 const at=player.currentTime||0, playing=!player.paused;
 active=index;
 for(const [i,button] of [...buttons.children].entries())
   button.setAttribute("aria-pressed",String(i===index));
 player.pause();
 player.src=encodeURIComponent(metadata.variants[index].wav_name);
 wantedSeek=Math.min(at,metadata.duration_seconds);
 player.load();
 if(playing)player.play().catch(()=>{status.textContent="Druk op afspelen om deze variant te horen.";});
 status.textContent="Variant: "+metadata.variants[index].family+" · positie "+fmt(at);
}
for(const [i,v] of metadata.variants.entries()){
 const button=document.createElement("button");
 button.type="button";button.textContent=v.family.replaceAll("_"," ");
 button.setAttribute("aria-pressed","false");
 button.addEventListener("click",()=>switchTo(i));
 buttons.append(button);
}
player.addEventListener("loadedmetadata",()=>{
 if(wantedSeek!==null){player.currentTime=wantedSeek;wantedSeek=null;}
});
player.addEventListener("timeupdate",()=>{
 seek.value=String(player.currentTime);
});
seek.addEventListener("input",()=>{
 player.currentTime=Number(seek.value);
 status.textContent="Positie "+fmt(Number(seek.value));
});
for(const item of metadata.chapters){
 const row=document.createElement("div");row.className="chapter";
 const button=document.createElement("button");button.type="button";
 button.textContent=(item.kind==="transition"?"↔ Overgang: ":"♪ Nummer: ")+item.label;
 button.addEventListener("click",()=>{
   player.currentTime=item.start_seconds;
   player.play().catch(()=>{status.textContent="Druk op afspelen om het hoofdstuk te horen.";});
 });
 const stamp=document.createElement("span");
 stamp.textContent=fmt(item.start_seconds);
 row.append(button,stamp);chapters.append(row);
}
switchTo(0);
</script></main></body></html>"""


def _destination(directory, session_root):
    dest = Path(directory).absolute()
    if (dest.exists() or dest.is_symlink() or
            not dest.parent.is_dir() or dest.is_relative_to(session_root)
            or session_root.is_relative_to(dest)):
        raise ValueError("Use a new private output folder outside the Studio session")
    for candidate in (dest, *dest.parents):
        if candidate.is_symlink() or (candidate / ".git").exists():
            raise ValueError("Private gallery must not be generated in Git or through symlinks")
    return dest


def create_gallery(session, new_directory, families=("bass_swap", "echo_exit")):
    if (not isinstance(families, (list, tuple))
            or not 2 <= len(families) <= MAX_VARIANTS
            or len(set(families)) != len(families)
            or any(f not in FAMILY_NAMES for f in families)):
        raise ValueError("Choose two to four distinct rendered M1 transition families")
    # Before publishing files, fail closed on missing pair renders, malformed
    # session receipts, mismatched pair graph or unsupported requested styles.
    root = None
    for family in families:
        bound_root, _selection = _choose_transitions(session, family, ())
        if root is None:
            root = bound_root
        elif bound_root != root:
            raise ValueError("Gallery variants must come from the same immutable session")
    target = _destination(new_directory, root)
    target.mkdir(mode=0o700)
    variants = []
    chapter_timeline = None
    duration = None
    # Keep valid completed variants if a later render fails: no deleting
    # original music, session receipts or already finished WAVs.
    for family in families:
        wav = target / (family + ".wav")
        rendered = render_instant_set(root, wav, family=family)
        chapters = build_chapters(root, wav)
        timeline = [(item["kind"], item["label"],
                     item["start_seconds"], item["duration_seconds"])
                    for item in chapters["chapters"]]
        if chapter_timeline is None:
            chapter_timeline = timeline
            duration = chapters["duration_seconds"]
        elif timeline != chapter_timeline or abs(chapters["duration_seconds"]-duration) > .00001:
            raise ValueError("DJ variations have different timelines; saved WAVs remain available")
        variants.append({"family": family, "wav_name": wav.name,
                         "wav_sha256": chapters["wav_sha256"],
                         "receipt": str(wav.name) + ".receipt.private.json",
                         "player": Path(rendered["offline_player"]).name if rendered["offline_player"] else None})
    data = {"schema_version": 1, "kind": "private-continuous-set-family-gallery",
            "duration_seconds": duration, "variants": variants,
            "chapters": chapters["chapters"], "manual_style_selection": True,
            "blind_listening_study": False}
    raw = json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    raw = raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    page = HTML.replace("__DATA__", raw).encode("utf-8")
    if len(page) > MAX_GALLERY_BYTES:
        raise ValueError("Private Set Gallery page too large; WAV exports remain available")
    output = target / "index.html"
    with output.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(page)
    return {"gallery": str(output), "audio_files": [str(target / x["wav_name"]) for x in variants],
            "styles": list(families), "offline": True, "human_preference_proven": False}


def main():
    parser = argparse.ArgumentParser(
        description="Render several full private DJ mixes and compare them at the same position offline")
    parser.add_argument("session", help="Existing private Studio with complete playlist renders")
    parser.add_argument("new_gallery_directory", help="NEW folder outside private Studio and Git")
    parser.add_argument("--family", action="append",
                        help="Render one complete-set family; choose 2..4 distinct families")
    args = parser.parse_args()
    try:
        result = create_gallery(args.session, args.new_gallery_directory,
                                families=tuple(args.family) if args.family else
                                ("bass_swap", "echo_exit"))
    except (OSError, ValueError, KeyError, TypeError, wave.Error) as exc:
        parser.exit(2, "MixLab Set Gallery: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
