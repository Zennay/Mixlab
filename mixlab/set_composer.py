"""Private offline set composer for already rendered manual Studio transitions.

Create an interactive local browser page, export an immutable session-bound
choice plan, and render that plan through the canonical continuous-set exporter.
No model, upload, implicit tempo matching, or alteration of source audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat

from .cueprep import _read_spec
from .ingest import digest
from .set_export import MAX_PAIRS, _unique_pairs, export_set
from .studio import FAMILY_NAMES, ID, SHA, _open_receipt

PLAN_KIND = "private-manual-set-composition"
MAX_PLAN_BYTES = 32768

HTML = """<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark"><title>MixLab / Set Composer</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#f5f5fa;background:#0e0f16}
*{box-sizing:border-box}body{margin:0}main{max-width:1220px;margin:auto;padding:38px 20px 90px}
h1{font-size:clamp(2.8rem,7vw,5.3rem);letter-spacing:-.065em;line-height:1;margin:12px 0}
h2{font-size:1.45rem}h3{font-size:1rem;margin:0 0 10px}p{line-height:1.55}
.eyebrow{color:#bba9ff;text-transform:uppercase;letter-spacing:.17em;font-size:.73rem;font-weight:800}
.muted{color:#a0a9be}.intro{max-width:770px;color:#d0d4e0}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(290px,400px);gap:25px;margin-top:35px}
@media(max-width:850px){.layout{grid-template-columns:1fr}}
.pair,.panel{border:1px solid #383a51;border-radius:17px;background:#1c1e2c;padding:20px;margin-bottom:14px}
.panel{position:sticky;top:15px}.pair header{display:flex;justify-content:space-between;align-items:center;gap:10px}
.route{font-weight:750;font-size:1.1rem}button,.control{font:inherit;color:#f9f7ff;border-radius:10px;padding:10px 13px;
border:1px solid #727094;background:#33324f;cursor:pointer}
button:hover{background:#474367}button:focus-visible,.control:focus-visible{outline:3px solid #bbacff;outline-offset:3px}
button:disabled{opacity:.36;cursor:not-allowed}.primary{background:#6755c0;border-color:#a89dff}
audio{display:block;width:100%;height:39px;margin-top:5px}
.preview{padding:11px 0;border-top:1px solid #32344a}.preview label{display:block;color:#c2bfd5;font-size:.83rem}
.stack{display:flex;flex-wrap:wrap;gap:9px}.stack>*{flex:1}ol{padding-left:24px}
li{margin-bottom:14px}li .control{margin-top:7px;width:100%}
footer{padding-top:40px;font-size:.85rem;color:#aab1c3}
small{color:#aab1c3}#status{min-height:1.4rem}input[type=file]{max-width:100%}
</style></head><body><main>
<p class="eyebrow">MIXLAB / PRIVÉ OFFLINE CREATIEVE SESSIE</p>
<h1>Set Composer.</h1>
<p class="intro">Luister naar reeds gerenderde overgangen, stel zelf een aaneengesloten
trackroute samen en bewaar die als privé keuzeplan. MixLab leest niets van internet.
Cuepunten en BPM zijn <strong>handmatig bevestigd</strong>; dit is geen automatische DJ.</p>
<div class="layout"><section><h2>Beschikbare overgangen</h2>
<p class="muted">Voeg telkens een overgang toe die aansluit op je laatste inkomende nummer.
Per overgang kies je het geluid dat je wilt gebruiken.</p><div id="catalog"></div></section>
<section><div class="panel"><h2>Jouw doorlopende set</h2>
<p id="summary" class="muted">Nog geen overgangen geselecteerd.</p><ol id="route"></ol>
<p id="status" role="status" aria-live="polite" class="muted"></p>
<div class="stack"><button id="clear">Wis selectie</button><button id="save" class="primary">Download keuzeplan</button></div>
<p><label for="restore">Heropen eerder keuzeplan:</label><br>
<input id="restore" type="file" accept="application/json,.json"></p>
<p class="muted">Download het JSON-plan. Maak daarna één volledige WAV met:</p>
<pre style="white-space:pre-wrap;overflow-wrap:anywhere">python3 -m mixlab.set_composer render
  /pad/naar/sessie
  /pad/naar/gekozen-plan.json
  /pad/naar/nieuwe-mix.wav</pre>
<small>De renderer controleert de originele bron- en overgangshashes en de
continuïteit opnieuw. De uiteindelijke mix blijft lokaal. Geen bestandsoverschrijving.</small>
</div></section></div>
<footer>Dit is een creatieve unblinded luisteromgeving, geen menselijke
voorkeursmeting of bewijs dat één overgang muzikaal beter is.</footer>
</main>
<script type="application/json" id="mixlab-bootstrap">__BOOTSTRAP__</script>
<script>
"use strict";
const data = JSON.parse(document.getElementById("mixlab-bootstrap").textContent);
const pairs = new Map(data.pairs.map(p=>[p.id,p]));
let route = [];
const catalog = document.getElementById("catalog");
const routeEl = document.getElementById("route");
const statusEl = document.getElementById("status");
const summary = document.getElementById("summary");
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function checkRoute(choices) {
  if (!Array.isArray(choices) || choices.length < 1 || choices.length > 10) return false;
  const seen = new Set();
  let last = null;
  for (const c of choices) {
    const pair = pairs.get(c.pair);
    if (!pair || !pair.families.includes(c.family) || seen.has(c.pair)) return false;
    if (last !== null && last !== pair.a) return false;
    seen.add(c.pair);
    last = pair.b;
  }
  return true;
}
function redraw() {
  routeEl.replaceChildren();
  catalog.replaceChildren();
  const last = route.length ? pairs.get(route[route.length-1].pair).b : null;
  const seen = new Set(route.map(c=>c.pair));
  summary.textContent = route.length
    ? route.length + " overgang(en) · " + pairs.get(route[0].pair).a + " → " + last
    : "Nog geen overgangen geselecteerd.";
  for (const [idx,c] of route.entries()) {
    const pair = pairs.get(c.pair);
    const li = node("li");
    li.append(node("div",pair.a+" → "+pair.b,"route"));
    const select = node("select",undefined,"control");
    select.setAttribute("aria-label","Overgangstype "+pair.id);
    for (const family of pair.families) {
      const option = node("option",family.replaceAll("_"," "));
      option.value=family; option.selected=c.family===family; select.append(option);
    }
    select.addEventListener("change",()=>{c.family=select.value;statusEl.textContent="Overgang gewijzigd.";});
    li.append(select);
    const remove = node("button","Verwijder laatste");
    remove.disabled=idx!==route.length-1;
    remove.addEventListener("click",()=>{route.pop();redraw();});
    li.append(remove); routeEl.append(li);
  }
  for (const pair of data.pairs) {
    const card=node("article",undefined,"pair");
    const header=node("header");
    header.append(node("span",pair.a+" → "+pair.b,"route"),node("small",pair.beats+" beats / "+pair.bpm+" BPM"));
    card.append(header);
    card.append(node("p","Handmatig uitgelijnde overgang "+pair.id,"muted"));
    for (const family of pair.families) {
      const row=node("div",undefined,"preview");
      row.append(node("label",family.replaceAll("_"," ")));
      const audio=node("audio");
      audio.controls=true;audio.preload="none";
      audio.src="../studio/auditions/"+encodeURIComponent(pair.id)+"/"+family+".wav";
      row.append(audio);card.append(row);
    }
    const button=node("button","Voeg overgang toe","primary");
    button.disabled=seen.has(pair.id) || route.length>=10 || (last!==null && last!==pair.a);
    button.addEventListener("click",()=>{
      route.push({pair:pair.id,family:pair.families.includes("bass_swap")?"bass_swap":pair.families[0]});
      statusEl.textContent="Overgang toegevoegd.";redraw();
    });
    card.append(button);catalog.append(card);
  }
}
document.getElementById("clear").addEventListener("click",()=>{
  route=[];statusEl.textContent="Selectie gewist.";redraw();
});
document.getElementById("save").addEventListener("click",()=>{
  if (!checkRoute(route)){statusEl.textContent="Kies eerst een aansluitende route (1–10 overgangen).";return;}
  const value={schema_version:1,kind:"private-manual-set-composition",
    session_sha256:data.session_sha256,studio_sha256:data.studio_sha256,transitions:route};
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+"\\n"],{type:"application/json"}));
  const anchor=node("a");anchor.href=url;anchor.download="mixlab-set-plan.private.json";
  document.body.append(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  statusEl.textContent="Keuzeplan lokaal gedownload. Gebruik de render-opdracht voor je WAV.";
});
document.getElementById("restore").addEventListener("change",async e=>{
  const file=e.target.files[0];if(!file)return;
  try {
    if(file.size>32768)throw Error("Plan is te groot");
    const value=JSON.parse(await file.text());
    if(value.kind!=="private-manual-set-composition" || value.schema_version!==1 ||
       value.session_sha256!==data.session_sha256 ||
       value.studio_sha256!==data.studio_sha256 ||
       !checkRoute(value.transitions))throw Error("Plan hoort niet bij deze sessie of route");
    route=value.transitions.map(c=>({pair:c.pair,family:c.family}));
    redraw();statusEl.textContent="Opgeslagen keuzes hersteld.";
  } catch(err){statusEl.textContent="Keuzeplan geweigerd: "+err.message;}
  e.target.value="";
});
redraw();
</script></body></html>"""


def _secure_file(path, limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing regular private metadata file")
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode) or initial.st_size > limit:
        raise ValueError("Private metadata exceeds its size limit")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as f:
        opened = os.fstat(f.fileno())
        if not stat.S_ISREG(opened.st_mode) or (initial.st_dev, initial.st_ino,
                initial.st_size, initial.st_mtime_ns) != (opened.st_dev,
                opened.st_ino, opened.st_size, opened.st_mtime_ns):
            raise ValueError("Metadata replaced before reading")
        value = f.read(limit + 1)
        after = os.fstat(f.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Metadata changed while reading")
    if len(value) > limit:
        raise ValueError("Private metadata too large")
    return value


def _object_no_duplicates(items):
    record = {}
    for key, value in items:
        if key in record:
            raise ValueError("Duplicate JSON key")
        record[key] = value
    return record


def _parse_json(data):
    try:
        return json.loads(data, object_pairs_hook=_object_no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JSON") from exc


def _session_catalog(root):
    """Bind the UI to existing immutable receipts; never embed source paths."""
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Private session directory missing or redirected")
    root = root.resolve(strict=True)
    for ancestor in (root, *root.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Private audio sessions cannot be inside Git")
    paths = [root / "session-receipt.private.json",
             root / "sources" / "source_manifest.json",
             root / "excerpts" / "library.json",
             root / "studio" / "studio-receipt.private.json"]
    for path in paths:
        if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("Private session metadata missing or redirected")
    receipt = _parse_json(_secure_file(paths[0], 65536))
    if not isinstance(receipt, dict) or receipt.get("kind") != "offline-manual-transition-session":
        raise ValueError("Expected a completed MixLab private session")
    if (receipt.get("studio_receipt_sha256") != digest(paths[3]) or
            receipt.get("prepared_manifest_sha256") != digest(paths[2])):
        raise ValueError("Session and Studio receipts no longer agree")
    studio = _open_receipt(root / "studio")
    if studio.get("manifest_sha256") != digest(paths[2]):
        raise ValueError("Studio pair manifest changed")
    spec = _read_spec(paths[1])
    tracks = spec.get("tracks")
    source_pairs = spec.get("pairs")
    if not isinstance(tracks, list) or not 2 <= len(tracks) <= 20:
        raise ValueError("Session track list invalid")
    ids = [x.get("id") if isinstance(x, dict) else None for x in tracks]
    if any(not isinstance(x, str) or not ID.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("Unsafe or duplicate session track")
    if not isinstance(source_pairs, list) or not 1 <= len(source_pairs) <= MAX_PAIRS:
        raise ValueError("Session pair list invalid")
    rendered = studio.get("renders")
    if not isinstance(rendered, list) or len(rendered) > MAX_PAIRS * len(FAMILY_NAMES):
        raise ValueError("Studio rendering catalog invalid")
    choices = {}
    for record in rendered:
        if not isinstance(record, dict):
            raise ValueError("Invalid Studio render")
        pair, family = record.get("pair"), record.get("family")
        if (not isinstance(pair, str) or not ID.fullmatch(pair) or family not in FAMILY_NAMES
                or record.get("relative_path") != f"auditions/{pair}/{family}.wav"
                or not isinstance(record.get("sha256"), str) or not SHA.fullmatch(record["sha256"])):
            raise ValueError("Invalid Studio rendered transition")
        if family in choices.setdefault(pair, {}):
            raise ValueError("Duplicate Studio rendered transition")
        src = root / "studio" / record["relative_path"]
        if src.is_symlink() or not src.is_file() or not src.resolve(strict=True).is_relative_to(root / "studio"):
            raise ValueError("Studio WAV missing or redirected")
        if digest(src) != record["sha256"]:
            raise ValueError("Studio WAV changed since rendering")
        choices[pair][family] = record
    pairs, seen = [], set()
    for item in source_pairs:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Invalid session pair")
        pid, a, b = item["id"], item.get("a"), item.get("b")
        if (not ID.fullmatch(pid) or pid in seen or a not in ids or b not in ids or a == b):
            raise ValueError("Unsafe, duplicate or disconnected session pair")
        seen.add(pid)
        if pid not in choices:
            continue  # Studio may have been rendered for a single chosen pair.
        bpm, beats = item.get("bpm"), item.get("beats", 8)
        if (type(bpm) not in (int, float) or not math.isfinite(bpm) or not 30 <= bpm <= 300
                or type(beats) is not int or not 1 <= beats <= 64):
            raise ValueError("Invalid manually verified timing")
        pairs.append({"id": pid, "a": a, "b": b, "bpm": bpm,
                      "beats": beats, "families": [f for f in FAMILY_NAMES if f in choices[pid]]})
    if not pairs:
        raise ValueError("No Studio renders can be selected")
    return root, {"schema_version": 1,
                  "session_sha256": digest(paths[0]), "studio_sha256": digest(paths[3]),
                  "pairs": pairs}


def create_composer(session_dir):
    root, catalog = _session_catalog(session_dir)
    dest = root / "set-composer"
    if dest.exists() or dest.is_symlink():
        raise ValueError("A set composer already exists: use its index.html")
    dest.mkdir(mode=0o700)
    try:
        bootstrap = json.dumps(catalog, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        bootstrap = bootstrap.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
        page = HTML.replace("__BOOTSTRAP__", bootstrap)
        target = dest / "index.html"
        with target.open("x", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(page)
    except BaseException:
        shutil.rmtree(dest)
        raise
    return target


def render_composition(session_dir, choice_file, output_wav):
    root, catalog = _session_catalog(session_dir)
    choice_path = Path(choice_file).absolute()
    if choice_path.resolve(strict=True).is_relative_to(root):
        raise ValueError("Keep the downloaded plan outside the immutable session")
    plan = _parse_json(_secure_file(choice_path, MAX_PLAN_BYTES))
    if not isinstance(plan, dict) or set(plan) != {
            "schema_version", "kind", "session_sha256", "studio_sha256", "transitions"}:
        raise ValueError("Unexpected choice-plan fields")
    if (type(plan["schema_version"]) is not int or plan["schema_version"] != 1
            or plan["kind"] != PLAN_KIND
            or plan["session_sha256"] != catalog["session_sha256"]
            or plan["studio_sha256"] != catalog["studio_sha256"]):
        raise ValueError("Choice plan does not match the original Studio session")
    entries = plan["transitions"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PAIRS:
        raise ValueError("Choose one to ten transitions")
    available = {p["id"]: p for p in catalog["pairs"]}
    choices, previous_b = [], None
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"pair", "family"}:
            raise ValueError("Invalid selected transition")
        pair = available.get(item["pair"]) if isinstance(item["pair"], str) else None
        if pair is None or item["family"] not in pair["families"]:
            raise ValueError("Choice refers to unavailable rendered transition")
        if previous_b is not None and pair["a"] != previous_b:
            raise ValueError("Chosen transitions do not form a continuous set")
        choices.append(item["pair"] + ":" + item["family"])
        previous_b = pair["b"]
    _unique_pairs(choices)
    # Canonical exporter verifies every original song SHA, frame boundary,
    # studio WAV SHA and route timing before atomically publishing the mix.
    return export_set(root, output_wav, choices)


def main():
    parser = argparse.ArgumentParser(
        description="Compose and render a multi-track private MixLab DJ set offline")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("create", help="Create local browser audition and route composer")
    build.add_argument("session", help="Completed private mixlab.session directory")
    finish = sub.add_parser("render", help="Compile saved choices to a new full-length WAV")
    finish.add_argument("session", help="The original private session directory")
    finish.add_argument("choice_file", help="Downloaded private JSON route plan")
    finish.add_argument("output", help="New output .wav path outside the session")
    args = parser.parse_args()
    try:
        if args.command == "create":
            file = create_composer(args.session)
            payload = {"private_composer": str(file),
                       "next": "Open index.html locally, audition and download your choice plan"}
        else:
            file = render_composition(args.session, args.choice_file, args.output)
            payload = {"continuous_set": str(file), "private_receipt": str(file) + ".receipt.private.json"}
            # WAV publication stays successful even if the optional player fails.
            try:
                from .set_player import publish_player
                payload["offline_player"] = str(publish_player(args.session, file))
            except (ValueError, OSError, TypeError, KeyError) as exc:
                payload["player_warning"] = str(exc)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, "MixLab Set Composer: " + str(exc) + "\n")
    payload.update({"mode": "offline-manual-creative", "automatic_beatmatching": False,
                    "human_preference_proven": False})
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
