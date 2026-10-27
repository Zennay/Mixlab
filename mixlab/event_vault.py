"""Private offline library of existing MixLab event folders.

Indexes only user-selected, already-rendered local events. It renders no
audio, accesses no cloud service, and cannot infer rights or authenticity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import wave

from .event_bundle import MAX_FILE
from .set_player import build_chapters

MAX_EVENTS = 16
MAX_MARATHON = 768 * 1024 * 1024 + 256  # PCM payload plus bounded RIFF header
MANIFEST = "mixlab-bundle-manifest.private.json"
MANIFEST_LIMIT = 65536
BLOCK = 65536
SHA = re.compile(r"[0-9a-f]{64}\Z")

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab / My Private Event Vault</title>
<style>
:root{color-scheme:dark;--bg:#0b111e;--panel:#19283e;--line:#40576a;--mint:#a1f8ca;--text:#edf7ff;--muted:#afc2d6}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at 100% 0%,#225255,var(--bg) 60%);color:var(--text);font:15px/1.5 system-ui,sans-serif}
main{max-width:1310px;margin:auto;padding:clamp(18px,4vw,56px)}
.eyebrow{font-size:12px;font-weight:850;color:var(--mint);letter-spacing:.17em}
h1{font-size:clamp(40px,6vw,80px);letter-spacing:-.065em;line-height:1;margin:10px 0 18px}
h2{font-size:22px;margin:0 0 12px}p{color:var(--muted)}
.toolbar{display:flex;flex-wrap:wrap;gap:14px;align-items:end;margin:24px 0}
label{font-weight:700;color:#d3e5f4;font-size:13px;display:grid;gap:6px}
input,select{padding:12px 14px;border-radius:11px;border:1px solid #6d859c;background:#0e2030;color:var(--text);font:inherit;min-width:200px}
input:focus-visible,select:focus-visible,a:focus-visible,button:focus-visible{outline:3px solid var(--mint);outline-offset:2px}
.stats{display:flex;gap:11px;flex-wrap:wrap;margin:25px 0}
.stat{border:1px solid #43615d;background:#133c39;padding:12px 17px;border-radius:14px;min-width:120px}
.stat b{display:block;font-size:25px}.stat small{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(295px,1fr));gap:18px}
.card{border:1px solid var(--line);border-radius:22px;background:var(--panel);padding:23px;min-width:0}
.card h3{font-size:23px;line-height:1.2;letter-spacing:-.02em;overflow-wrap:anywhere;margin:10px 0}
.meta{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}
.badge{display:inline-block;border:1px solid #567388;border-radius:999px;padding:5px 9px;font-size:11px;color:#d6eaff}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
a,button{font:inherit;font-weight:750;border:1px solid #577c94;border-radius:10px;padding:10px 14px;background:#2c5069;color:white;text-decoration:none;cursor:pointer}
a.primary{background:var(--mint);color:#07291b;border:none}
a:hover,button:hover{filter:brightness(1.15)}
audio{width:100%;margin:12px 0}.player{margin:25px 0;padding:20px;border:1px solid #4d8075;background:#17323b;border-radius:20px}
.hash{font:11px ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}
.empty{padding:24px;border:1px dashed var(--line);border-radius:12px}
@media(max-width:650px){.toolbar>*{flex:1}.grid{grid-template-columns:1fr}}
</style></head><body><main>
<div class="eyebrow">MIXLAB / LOCAL PRIVATE EVENT ARCHIVE</div>
<h1>Every mix.<br>One vault.</h1>
<p>Browse your already rendered private events in one offline place, search by folder and listen to the actual exported WAV. Each event keeps its own player, Rehearsal Desk and runbook.</p>
<div id="stats" class="stats"></div>
<div class="toolbar"><label for="search">Find an event<input id="search" type="search" placeholder="Search event name" autocomplete="off"></label>
<label for="sort">Sort sets<select id="sort"><option value="name">Event name</option><option value="duration">Runtime (longest first)</option><option value="chapters">Most chapters</option></select></label></div>
<section class="player"><h2 id="now">Preview your private WAV</h2>
<audio id="audio" controls preload="metadata"></audio>
<p id="play-status">Choose “Play here” on an event card. If local WAV playback is unavailable, open the event's original offline player.</p></section>
<div id="events" class="grid" aria-live="polite"></div>
<p id="empty" class="empty" hidden>No events match this search.</p>
<p>All event audio and pages remain on this computer; nothing is streamed to a service or uploaded. A transferred ZIP manifest is unsigned, so the vault can check internal file integrity but cannot authenticate the original sender, certify music rights or prove professional live reliability.</p>
<p id="hash" class="hash"></p>
</main>
<script id="mixlab-events-data" type="application/json">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("mixlab-events-data").textContent);
const $=id=>document.getElementById(id),audio=$("audio");
let now=null;
const pretty=s=>{
 const v=Math.max(0,Math.floor(s));
 return String(Math.floor(v/3600)).padStart(2,"0")+":"+
 String(Math.floor((v%3600)/60)).padStart(2,"0")+":"+String(v%60).padStart(2,"0");
};
const element=(tag,cls,text)=>{
 const node=document.createElement(tag);if(cls)node.className=cls;
 if(text!==undefined)node.textContent=String(text);return node;
};
const src=item=>"./"+encodeURIComponent(item.folder)+"/"+encodeURIComponent(item.wav_name);
const link=(item)=>"./"+encodeURIComponent(item.folder)+"/"+encodeURIComponent(item.dashboard);
const stats=$("stats");
[[data.events.length,"private events"],
 [data.events.reduce((n,e)=>n+e.duration_seconds,0)/3600,"hours of WAV"],
 [data.events.reduce((n,e)=>n+e.chapters,0),"rendered chapters"]].forEach((record,i)=>{
 const box=element("div","stat"),value=i===1?record[0].toFixed(1):String(record[0]);
 box.append(element("b","",value),element("small","",record[1]));stats.append(box);
});
function play(item){
 now=item.folder;audio.pause();audio.src=src(item);audio.load();
 $("now").textContent="Playing "+item.label;
 const p=audio.play();if(p)p.catch(()=>{$("play-status").textContent="Browser blocked local playback. Open the event dashboard or your offline media player.";});
 $("play-status").textContent="The real local WAV is playing, no remix or server stream.";
}
audio.addEventListener("error",()=>{
 $("play-status").textContent="Local WAV unsupported by this browser; use the original event player or an offline audio app.";
});
function render(){
 const term=$("search").value.toLocaleLowerCase().trim();
 const shown=data.events.filter(item=>item.label.toLocaleLowerCase().includes(term));
 const mode=$("sort").value;
 shown.sort((a,b)=>mode==="duration"?b.duration_seconds-a.duration_seconds:
                    mode==="chapters"?b.chapters-a.chapters:
                    a.label.localeCompare(b.label));
 const root=$("events");root.replaceChildren();
 $("empty").hidden=shown.length>0;
 shown.forEach(item=>{
  const card=element("article","card"),eyebrow=element("div","eyebrow",item.evidence==="canonical"?"ORIGINAL MIXLAB SET":item.evidence==="marathon"?"CONTINUOUS EVENT MARATHON":item.evidence==="marathon_blend"?"RENDERED CROSSFADE MARATHON":"RESTORED PRIVATE PACKAGE");
  card.append(eyebrow,element("h3","",item.label));
  const meta=element("div","meta");
  [pretty(item.duration_seconds)+" runtime",
   item.chapters+" chapters",item.evidence==="canonical"?"Original receipts":item.evidence==="marathon"?"Joined WAV SHA match":item.evidence==="marathon_blend"?"Crossfaded WAV SHA match":"Bundle SHA match"].forEach(label=>meta.append(element("span","badge",label)));
  card.append(meta);
  const actions=element("div","actions");
  const button=element("button","", "Play here");button.type="button";
  button.addEventListener("click",()=>play(item));actions.append(button);
  const a=element("a","primary","Open event dashboard");
  a.href=link(item);a.rel="noopener noreferrer";actions.append(a);card.append(actions);
  root.append(card);
 });
}
$("search").addEventListener("input",render);$("sort").addEventListener("change",render);
$("hash").textContent="Offline gallery metadata only. Original full WAV identity is rechecked during vault compilation.";
render();
</script></body></html>"""


def _entry(path, *, size_limit):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError("Event vault requires ordinary existing private files")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= size_limit:
        raise ValueError("Event vault file is missing or exceeds size limits")
    return path, info


def _read_small_json(path):
    path, meta = _entry(path, size_limit=MANIFEST_LIMIT)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as reader:
        if not stat.S_ISREG(os.fstat(reader.fileno()).st_mode):
            raise ValueError("Event manifest is not a regular file")
        content = reader.read(MANIFEST_LIMIT + 1)
        if len(content) > MANIFEST_LIMIT:
            raise ValueError("Private event manifest exceeds its size limit")
    return json.loads(content)


def _digest_regular(path, expected, *, max_bytes=MAX_FILE):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ValueError("Event master WAV is not an ordinary bounded file")
        h = hashlib.sha256()
        while True:
            chunk = handle.read(BLOCK)
            if not chunk:
                break
            h.update(chunk)
        after = os.fstat(handle.fileno())
        if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (
                after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns,
                after.st_ctime_ns):
            raise ValueError("Event master changed while being indexed")
        if h.hexdigest() != expected:
            raise ValueError("Restored WAV does not match its private package hash")


def _marathon_duration(folder, wav):
    """Verify the local joined WAV; its unsigned receipt is not source authentication."""
    data = _read_small_json(folder / "marathon.receipt.private.json")
    blended = isinstance(data, dict) and data.get("kind") == "mixlab-private-blended-event-v1"
    if (not isinstance(data, dict) or data.get("schema_version") != 1 or
            data.get("kind") not in ("mixlab-private-continuous-event-v1",
                                     "mixlab-private-blended-event-v1") or
            data.get("wav_name") != "marathon.wav" or
            data.get("private_local_use_only") is not True or
            data.get("sample_preserving_joins") is not (not blended) or
            data.get("automatic_licensing") is not False or
            data.get("musical_preference_proven") is not False or
            type(data.get("rate")) is not int or
            not 8000 <= data["rate"] <= 96000 or
            data.get("channels") != 2 or data.get("sample_width_bytes") != 2 or
            type(data.get("frames")) is not int or data["frames"] <= 0 or
            data["frames"] * 4 > MAX_MARATHON or
            not isinstance(data.get("wav_sha256"), str) or
            not SHA.fullmatch(data["wav_sha256"])):
        raise ValueError("Not a supported private continuous MixLab event")
    sections = data.get("sections")
    if not isinstance(sections, list) or not 2 <= len(sections) <= 8:
        raise ValueError("Private Marathon receipt has no valid event sequence")
    overlaps = []
    if blended:
        joined = data.get("overlap_frames_by_join")
        if joined is not None:
            if (not isinstance(joined, list) or len(joined) != len(sections) - 1 or
                    any(type(v) is not int or v not in (
                        0, 2 * data["rate"], 4 * data["rate"],
                        8 * data["rate"], 16 * data["rate"]) for v in joined) or
                    data.get("fade_seconds_by_join") !=
                    [v // data["rate"] for v in joined]):
                raise ValueError("Invalid per-event audio crossfade decisions")
            overlaps = joined
        else:
            # Legacy uniform fades produced before per-boundary curation.
            old = data.get("overlap_frames")
            if (type(old) is not int or old not in (
                    2 * data["rate"], 4 * data["rate"],
                    8 * data["rate"], 16 * data["rate"]) or
                    data.get("fade_seconds") != old // data["rate"]):
                raise ValueError("Missing original uniform crossfade decision")
            overlaps = [old] * (len(sections) - 1)
        if (data.get("transition_curve") != "complementary-linear-pcm16-v1" or
                not isinstance(data.get("source_marathon_sha256"), str) or
                not SHA.fullmatch(data["source_marathon_sha256"]) or
                data.get("no_automatic_tempo_matching") is not True):
            raise ValueError("Blended event is missing original SHA or fade provenance")
    running = 0
    total_overlap = 0
    for i, row in enumerate(sections):
        incoming = overlaps[i - 1] if i else 0
        outgoing = overlaps[i] if i < len(overlaps) else 0
        if (not isinstance(row, dict) or row.get("index") != i + 1 or
                type(row.get("start_frame")) is not int or
                row["start_frame"] != running - total_overlap or
                type(row.get("frames")) is not int or
                row["frames"] <= incoming + outgoing or
                not isinstance(row.get("source_sha256"), str) or
                not SHA.fullmatch(row["source_sha256"])):
            raise ValueError("Joined event boundaries are not contiguous or receipt-bound")
        running += row["frames"]
        total_overlap += outgoing
    if running - total_overlap != data["frames"]:
        raise ValueError("Marathon chapter frames do not cover the real master")
    _digest_regular(wav, data["wav_sha256"], max_bytes=MAX_MARATHON)
    fd = os.open(wav, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as source:
        with wave.open(source, "rb") as media:
            if (media.getnchannels() != 2 or media.getsampwidth() != 2 or
                    media.getcomptype() != "NONE" or
                    media.getframerate() != data["rate"] or
                    media.getnframes() != data["frames"]):
                raise ValueError("Private Marathon audio differs from its joined PCM receipt")
    return data["frames"] / data["rate"], len(sections), "marathon_blend" if blended else "marathon"


def _chapter_count_and_duration(folder, wav):
    if wav.name == "marathon.wav":
        return _marathon_duration(folder, wav)
    session = folder / "studio-session"
    if session.is_dir() and not session.is_symlink():
        original = build_chapters(session, wav)
        return original["duration_seconds"], len(original["chapters"]), "canonical"
    manifest = _read_small_json(folder / MANIFEST)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or
            manifest.get("kind") != "mixlab-private-portable-full-set-v1" or
            manifest.get("source_media_included") is not False or
            manifest.get("private_local_use_only") is not True or
            not isinstance(manifest.get("wav_sha256"), str) or
            not SHA.fullmatch(manifest["wav_sha256"]) or
            type(manifest.get("chapters")) is not int or
            not 1 <= manifest["chapters"] <= 200 or
            not isinstance(manifest.get("files"), list)):
        raise ValueError("Restored folder lacks an original private MixLab bundle manifest")
    files = manifest["files"]
    claims = [x for x in files if isinstance(x, dict) and x.get("file") == wav.name]
    if len(claims) != 1 or claims[0].get("sha256") != manifest["wav_sha256"]:
        raise ValueError("Restored event has no exact WAV hash claim")
    if not any(isinstance(x, dict) and x.get("file") == wav.name + ".receipt.private.json" for x in files):
        raise ValueError("Restored event is missing the original WAV receipt claim")
    _entry(folder / (wav.name + ".receipt.private.json"), size_limit=MANIFEST_LIMIT)
    _digest_regular(wav, manifest["wav_sha256"])
    fd = os.open(wav, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd,"rb") as src:
        with wave.open(src, "rb") as media:
            if (media.getsampwidth() != 2 or media.getnchannels() not in (1, 2) or
                    not 8000 <= media.getframerate() <= 96000):
                raise ValueError("Restored event master is not compatible PCM16")
            seconds = media.getnframes() / media.getframerate()
    if not 0 < seconds <= 24 * 3600:
        raise ValueError("Restored event has an invalid duration")
    return seconds, manifest["chapters"], "bundle"


def build_vault(new_private_html, *event_directories):
    """Build a fresh offline index for explicit trusted local event folders."""
    target = Path(new_private_html).absolute()
    if (target.parent.is_symlink() or not target.parent.is_dir() or
            target.exists() or target.is_symlink() or
            target.suffix.lower() != ".html"):
        raise ValueError("Choose a NEW .html library page beside the trusted event folders")
    for part in (target, *target.parents):
        if part.is_symlink() or (part / ".git").exists():
            raise ValueError("Event vault cannot be published inside Git or a symlink")
    if not 1 <= len(event_directories) <= MAX_EVENTS:
        raise ValueError("Choose 1 to 16 trusted private event folders")
    records = []
    used = set()
    for user_folder in event_directories:
        folder = Path(user_folder).absolute()
        if (folder.parent != target.parent or folder.is_symlink() or
                not folder.is_dir() or folder.name in used or
                not folder.name or folder.name in (".", "..")):
            raise ValueError("Events must be unique sibling directories of the private vault")
        used.add(folder.name)
        _entry(folder / "index.html", size_limit=512 * 1024)
        is_marathon = (folder / "marathon.receipt.private.json").exists()
        wav_name = "marathon.wav" if is_marathon else "final-set.wav"
        wav, meta = _entry(folder / wav_name, size_limit=MAX_MARATHON if is_marathon else MAX_FILE)
        duration, chapters, evidence = _chapter_count_and_duration(folder, wav)
        if not isinstance(duration, (float, int)) or not 0 < duration <= 86400:
            raise ValueError("Private event has invalid running time")
        records.append({
            "folder": folder.name, "label": folder.name.replace("-", " ").replace("_", " "),
            "dashboard": "index.html", "wav_name": wav.name,
            "duration_seconds": round(duration, 4),
            "chapters": chapters, "evidence": evidence,
        })
    blob = json.dumps({"schema_version":1, "events":records},
                      ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = _PAGE.replace("__DATA__", blob).encode("utf-8")
    if len(page) > 512 * 1024:
        raise ValueError("Private event library exceeds its page budget")
    with target.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(page)
    return {"private_event_vault":str(target), "events":len(records),
            "original_canonical":sum(x["evidence"]=="canonical" for x in records),
            "restored_private_packages":sum(x["evidence"]=="bundle" for x in records),
            "continuous_marathons":sum(x["evidence"] in ("marathon","marathon_blend") for x in records),
            "crossfaded_marathons":sum(x["evidence"]=="marathon_blend" for x in records),
            "offline":True, "source_media_uploads":False,
            "automatic_licensing":False, "musical_preference_proven":False}


def main():
    parser = argparse.ArgumentParser(
        description="Create a searchable offline vault of your trusted local MixLab events")
    parser.add_argument("new_private_html", help="NEW private vault page beside event folders")
    parser.add_argument("event_directories", nargs="+", help="One to sixteen original or restored private event folders")
    args = parser.parse_args()
    try:
        result = build_vault(args.new_private_html, *args.event_directories)
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError,
            wave.Error) as exc:
        parser.exit(2, "MixLab event vault: event index could not be created; "
                       "provide trusted receipt-bound event folders.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
