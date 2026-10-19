"""Assemble a private, operator-ordered rehearsal session of 2–8 chosen MixLab transitions.

Selected audio and human notes are copied from precise original gallery receipts.
No analysis, music rights, queue admission, or automated publishing takes place.
"""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from .private_transition_selection import (
    _read_json_and_digest, _verified_choice, _copy_and_verify_wav, _valid_sha,
)

MAX_CHAPTERS = 8
MAX_TOTAL_PCM_BYTES = 128 * 1024 * 1024


def _digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _page(receipt, receipt_sha):
    articles = []
    for part in receipt["chapters"]:
        number = part["chapter"]
        family = html.escape(part["family"].replace("_", " ").title())
        note = html.escape(part["private_note"])
        filename = html.escape(part["audio"], quote=True)
        articles.append(
            f'<article class="chapter" data-chapter="{number}" draggable="false">'
            f'<div class="heading"><h2><span class="chapter-number">{number}</span> · {family}</h2>'
            f'<div class="buttons"><button type="button" class="up" aria-label="Move chapter {number} earlier">↑</button>'
            f'<button type="button" class="down" aria-label="Move chapter {number} later">↓</button></div></div>'
            f'<audio controls preload="none" src="{filename}" aria-label="Listen to chapter {number}"></audio>'
            f'<p class="note">DJ cue: {note or "—"}</p>'
            f'<p class="meta">Original render: {part["seconds"]:.2f} seconds · '
            f'Private chapter {number}</p></article>'
        )
    return ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; media-src 'self' file: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>MixLab · Private rehearsal reel</title><style>
:root{color-scheme:dark}body{background:#101624;color:#f5f7fb;font:16px/1.6 system-ui,sans-serif;margin:auto;max-width:920px;padding:30px 18px}
h1{font-size:clamp(28px,6vw,42px);line-height:1.16}h2{font-size:20px;margin:0}p{color:#cbd5e1}
button{font:inherit;cursor:pointer;background:#93c5fd;color:#102035;border:0;border-radius:8px;padding:8px 13px;font-weight:600}
button:focus-visible{outline:3px solid #fbbf24}button[disabled]{opacity:.3;cursor:not-allowed}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0}
.chapter{background:#1e293b;border:1px solid #475569;border-radius:14px;padding:20px;margin:16px 0}
.heading{display:flex;justify-content:space-between;gap:14px;align-items:center}
.buttons{display:flex;gap:7px}.chapter-number{color:#93c5fd}
audio{display:block;width:100%;margin:16px 0}.note{white-space:pre-wrap;overflow-wrap:anywhere}
.meta{font-size:13px;color:#94a3b8}small{color:#93c5fd}
footer{border-top:1px solid #64748b;margin-top:36px;padding-top:18px}
@media print{body{background:white;color:black}.toolbar,.buttons,audio{display:none}.chapter{border:1px solid #777;break-inside:avoid;background:white}.note,.meta,p{color:#222}small{color:#111}}
</style>
<header><small>PRIVATE · HUMAN-SELECTED · OFFLINE</small><h1>Rehearsal running order</h1>
<p>Play a chapter, move it up or down, or play through your rehearsal sequence.
Tracks are separated clips; no seamless DJ set, beatmatching, loudness equalization or listener
study is implied. Nothing is sent to a server. Changes remain in this browser tab until exported.</p></header>
<div class="toolbar"><button id="play-all">▶ Play from start</button><button id="stop">■ Stop</button>
<button id="download">↓ Export private running order</button><button id="print">Print cue sheet</button></div>
<p role="status" id="status" aria-live="polite">Original source order loaded.</p>
<main id="reel">""" + "".join(articles) + """</main>
<footer><p>Rights remain unverified. All chosen WAVs are copied without modifying source audio.
This session documents a human rehearsal decision, not a blind scientific preference or release permission.</p></footer>
<script>
const receiptSha = """ + json.dumps(receipt_sha) + """;
const reel=document.getElementById('reel');
const status=document.getElementById('status');
const cards=()=>[...reel.querySelectorAll('.chapter')];
const stop=()=>cards().forEach(c=>{const a=c.querySelector('audio');a.pause();a.currentTime=0});
const display=()=>{
  cards().forEach((c,i)=>{
    c.querySelector('.up').disabled=i===0;
    c.querySelector('.down').disabled=i===cards().length-1;
    c.querySelector('.chapter-number').textContent=String(i+1);
  });
};
reel.addEventListener('click',e=>{
  const button=e.target.closest('button');
  if(!button)return;
  const card=button.closest('.chapter');if(!card)return;
  stop();
  if(button.classList.contains('up') && card.previousElementSibling)reel.insertBefore(card,card.previousElementSibling);
  if(button.classList.contains('down') && card.nextElementSibling)reel.insertBefore(card.nextElementSibling,card);
  display();status.textContent='Reordered locally. Export your order to retain it.';
});
reel.addEventListener('play',e=>{
  if(e.target.tagName==='AUDIO')cards().forEach(c=>{const audio=c.querySelector('audio');if(audio!==e.target)audio.pause()});
},true);
reel.addEventListener('ended',e=>{
  const ordered=cards();const index=ordered.findIndex(c=>c.querySelector('audio')===e.target);
  if(index>=0&&index+1<ordered.length){
    ordered[index+1].querySelector('audio').play().catch(()=>status.textContent='Select Play to continue.');
  } else status.textContent='Rehearsal sequence finished.';
},true);
document.getElementById('play-all').onclick=()=>{
  stop();const first=cards()[0]?.querySelector('audio');
  if(first)first.play().catch(()=>status.textContent='Choose the first clip to start playback.');
};
document.getElementById('stop').onclick=()=>{stop();status.textContent='Playback stopped.'};
document.getElementById('print').onclick=()=>window.print();
document.getElementById('download').onclick=()=>{
  const order=cards().map((card,index)=>({position:index+1,original_chapter:Number(card.dataset.chapter)}));
  const payload={schema_version:1,kind:'mixlab-private-rehearsal-order',receipt_sha256:receiptSha,
    status:'human-reordered-not-blind-study',order,rights_status:'unverified'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)+'\\n'],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='mixlab-private-running-order.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  status.textContent='Private running order downloaded; original receipt remains unchanged.';
};
display();
</script></html>
""")


def create_reel(pairs, destination):
    """Publish a private offline, source-bound multi-pair listening session.

    pairs is an operator-specified ordered iterable of (gallery, choice) paths.
    """
    if not 2 <= len(pairs) <= MAX_CHAPTERS:
        raise ValueError("Choose between 2 and 8 gallery + human choice pairs")
    output = Path(destination)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("Output must be a new directory under an existing parent")
    chapters = []
    seen = set()
    total_bytes = 0
    with tempfile.TemporaryDirectory(prefix=".mixlab-reel-", dir=output.parent) as stage_name:
        stage = Path(stage_name)
        for index, (gallery_arg, choice_arg) in enumerate(pairs, 1):
            gallery = Path(gallery_arg)
            if not gallery.is_dir():
                raise ValueError("Every gallery must be an existing local directory")
            receipt, receipt_sha = _read_json_and_digest(gallery / "receipt.json")
            choice, choice_sha = _read_json_and_digest(choice_arg)
            family, chosen, note = _verified_choice(receipt, receipt_sha, choice)
            if receipt_sha in seen:
                raise ValueError("The same original gallery cannot be repeated in one reel")
            seen.add(receipt_sha)
            seconds = chosen.get("seconds")
            if type(seconds) not in (float, int) or not math.isfinite(seconds) or not 0 < seconds <= 120:
                raise ValueError("Chosen transition has invalid duration")
            filename = f"{index:02d}-{family}.wav"
            output_file = stage / filename
            size = _copy_and_verify_wav(gallery / filename[3:], output_file, chosen["audio_sha256"])
            total_bytes += size
            if total_bytes > MAX_TOTAL_PCM_BYTES:
                raise ValueError("Rehearsal reel exceeds private audio size budget")
            output_file.chmod(0o600)
            chapters.append({
                "chapter": index, "family": family, "audio": filename,
                "audio_sha256": chosen["audio_sha256"], "seconds": seconds,
                "private_note": note, "source_gallery_receipt_sha256": receipt_sha,
                "human_choice_sha256": choice_sha,
            })
        receipt = {
            "schema_version": 1, "kind": "mixlab-private-rehearsal-reel",
            "status": "human-selected-not-blind-study",
            "rights_status": "unverified", "chapter_count": len(chapters),
            "total_audio_bytes": total_bytes, "original_order_only": True,
            "human_reordered_in_browser_only": False, "chapters": chapters,
        }
        receipt_file = stage / "receipt.json"
        receipt_file.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
                                encoding="utf-8")
        receipt_file.chmod(0o600)
        page_file = stage / "index.html"
        page_file.write_text(_page(receipt, _digest(receipt_file)), encoding="utf-8")
        page_file.chmod(0o600)
        files = [p.name for p in stage.iterdir() if p.is_file()]
        output.mkdir(mode=0o700)
        published = []
        try:
            for filename in files:
                os.link(stage / filename, output / filename)
                published.append(filename)
        except BaseException:
            for filename in published:
                (output / filename).unlink()
            output.rmdir()
            raise
    return output / "index.html"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble 2–8 original-gallery DJ choices into a private offline rehearsal session"
    )
    parser.add_argument("output_dir", help="New private session directory")
    parser.add_argument("--pair", nargs=2, metavar=("GALLERY", "DJ_CHOICE"), action="append",
                        required=True, help="Repeat 2–8 times, in initial running order")
    args = parser.parse_args(argv)
    try:
        print(create_reel(args.pair, args.output_dir))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"MixLab rehearsal reel: {exc}\n")


if __name__ == "__main__":
    main()
