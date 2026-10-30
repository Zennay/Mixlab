"""Human-visible, original-source-bound A/B comparison of two private reels.

The two methods are visible, so this is not a blinded research evaluation.
Only already rendered PCM16 families are compared, with no new DSP processing.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path

from .private_output import write_private_new
import tempfile

from .private_transition_selection import _read_json_and_digest, _copy_and_verify_wav
from .private_rehearsal_mixdown import _chapters as _original_chapters

MAX_COMPARE_AUDIO_BYTES = 128 * 1024 * 1024


def _digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _page(receipt, digest):
    cards=[]
    for chapter in receipt["chapters"]:
        n=chapter["chapter"]
        items=[]
        for side in ("original","revised"):
            family=html.escape(chapter[side]["family"].replace("_"," ").title())
            note=html.escape(chapter[side]["private_note"])
            audio=html.escape(chapter[side]["audio"],quote=True)
            items.append(
                f'<article><h3>{side.title()} · {family}</h3>'
                f'<audio controls preload="none" src="{audio}"></audio>'
                f'<p class="note">Human cue note: {note or "—"}</p></article>'
            )
        cards.append(
            f'<section class="chapter" data-chapter="{n}"><h2>Track-pair chapter {n}</h2>'
            '<div class="choices">'+"".join(items)+'</div>'
            '<fieldset><legend>My private take comparison</legend>'
            f'<label><input type="radio" name="winner-{n}" value="original" required> Original works better</label>'
            f'<label><input type="radio" name="winner-{n}" value="revised"> Revision works better</label>'
            f'<label><input type="radio" name="winner-{n}" value="undecided"> Needs another rehearsal</label>'
            '<label class="note">Why? (optional, max 240 characters)'
            '<textarea maxlength="240" rows="2"></textarea></label></fieldset></section>'
        )
    return ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; media-src 'self' file: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>MixLab · Original vs revised rehearsal</title>
<style>
:root{color-scheme:dark}body{font:16px/1.55 system-ui,sans-serif;background:#111827;color:#f8fafc;max-width:1100px;margin:auto;padding:25px 18px}
h1{font-size:clamp(30px,5vw,44px);line-height:1.15}p{color:#cbd5e1}
small{color:#93c5fd}.chapter{background:#1e293b;border:1px solid #475569;border-radius:16px;padding:20px;margin:20px 0}
.choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:15px}
article{background:#111827;border:1px solid #64748b;border-radius:12px;padding:16px}
h3{margin-top:0}audio{display:block;width:100%;margin:16px 0}
.note{white-space:pre-wrap;overflow-wrap:anywhere}fieldset{border:1px solid #64748b;border-radius:9px;margin:16px 0}
fieldset label{display:block;margin:9px 0}.note textarea{display:block;width:100%;box-sizing:border-box;margin-top:8px;padding:10px;background:#111827;color:#fff;border:1px solid #64748b;border-radius:9px;font:inherit}
button{font:inherit;font-weight:700;background:#93c5fd;color:#111827;border:0;border-radius:8px;padding:13px 18px;cursor:pointer}
button:focus-visible,textarea:focus-visible,input:focus-visible{outline:3px solid #facc15}
footer{border-top:1px solid #64748b;padding:18px 0;margin-top:22px}
</style>
<header><small>OFFLINE · IDENTICAL ORIGINAL TRACK PAIRS</small><h1>Did the revision actually improve your rehearsal?</h1>
<p>Listen to both existing PCM16 transitions for each identical original track pair. Choose your
own preferred take or request another rehearsal. Method names are visible; this is not a blind
preference study, statistical quality score, public stream or licensing approval.</p></header>
<form id="review"><main>""" + "".join(cards) + """</main>
<button type="submit">Download my private comparison decision</button>
<p id="status" role="status" aria-live="polite">All chapters need one deliberate human decision.</p></form>
<footer><p>Everything stays local. Selection files are source-bound to both original reel receipts.
No analytics, uploads, cookies or automatic rights claims.</p></footer>
<script>
const receiptSha = """ + json.dumps(digest) + """;
const originalSha = """ + json.dumps(receipt["original_reel_receipt_sha256"]) + """;
const revisedSha = """ + json.dumps(receipt["revised_reel_receipt_sha256"]) + """;
document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>{
  document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()});
}));
document.getElementById('review').addEventListener('submit',event=>{
  event.preventDefault();
  const choices=[...document.querySelectorAll('[data-chapter]')].map((card,i)=>({
    chapter:i+1,
    chosen_take:card.querySelector('input[type=radio]:checked').value,
    note:card.querySelector('textarea').value.trim().slice(0,240)
  }));
  const body={schema_version:1,kind:'mixlab-private-human-take-comparison',
    status:'visible-method-human-decision-not-blind-study',rights_status:'unverified',
    comparison_receipt_sha256:receiptSha,original_reel_receipt_sha256:originalSha,
    revised_reel_receipt_sha256:revisedSha,choices};
  const url=URL.createObjectURL(new Blob([JSON.stringify(body,null,2)+'\\n'],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='mixlab-human-take-comparison.json';
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  document.getElementById('status').textContent='Private comparison saved. Revisit any undecided chapter deliberately.';
});
</script></html>
""")


def prepare(original_reel_dir,revised_reel_dir,destination):
    """Create a source-exact original/revised comparison workspace (2–8 chapters)."""
    a_root,b_root,target=Path(original_reel_dir),Path(revised_reel_dir),Path(destination)
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Choose a new private folder under an existing parent")
    original,original_sha=_read_json_and_digest(a_root/"receipt.json")
    revised,revised_sha=_read_json_and_digest(b_root/"receipt.json")
    older=_original_chapters(original)
    newer=_original_chapters(revised)
    if len(older)!=len(newer) or original_sha==revised_sha:
        raise ValueError("Select two different source-bound reels with matching chapter counts")
    for a,b in zip(older,newer):
        if (a["chapter"]!=b["chapter"]
                or a["source_gallery_receipt_sha256"]!=b["source_gallery_receipt_sha256"]):
            raise ValueError("Revisions must use the identical original track pair for every chapter")
    with tempfile.TemporaryDirectory(prefix=".mixlab-take-comparison-",dir=target.parent) as temp:
        stage=Path(temp)
        entries=[]
        copied=[]
        total=0
        for i,(a,b) in enumerate(zip(older,newer),1):
            item={"chapter":i,"source_gallery_receipt_sha256":a["source_gallery_receipt_sha256"]}
            for side,root,row in (("original",a_root,a),("revised",b_root,b)):
                out=f"{i:02d}-{side}.wav"
                path=stage/out
                total+=_copy_and_verify_wav(root/row["audio"],path,row["audio_sha256"])
                if total>MAX_COMPARE_AUDIO_BYTES:
                    raise ValueError("Private two-take comparison exceeds 128MiB")
                path.chmod(0o600)
                copied.append(out)
                item[side]={"family":row["family"],"audio":out,
                            "audio_sha256":row["audio_sha256"],"seconds":row["seconds"],
                            "private_note":row["private_note"],
                            "human_choice_sha256":row["human_choice_sha256"]}
            entries.append(item)
        document={"schema_version":1,"kind":"mixlab-private-original-versus-revision",
                  "status":"prepared-for-visible-human-comparison","rights_status":"unverified",
                  "original_reel_receipt_sha256":original_sha,
                  "revised_reel_receipt_sha256":revised_sha,
                  "chapter_count":len(entries),"total_pcm_bytes":total,"chapters":entries}
        receipt_file=stage/"receipt.json"
        write_private_new(receipt_file, (json.dumps(document,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8"))
        html_file=stage/"index.html"
        write_private_new(html_file, (_page(document,_digest(receipt_file))).encode("utf-8"))
        target.mkdir(mode=0o700)
        published=[]
        try:
            for name in copied+["receipt.json","index.html"]:
                os.link(stage/name,target/name)
                published.append(name)
        except BaseException:
            for name in published:(target/name).unlink()
            target.rmdir()
            raise
    return target/"index.html"


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="Privately compare actual original and human-revised rehearsal chapters"
    )
    parser.add_argument("original_reel")
    parser.add_argument("revised_reel")
    parser.add_argument("output_dir")
    args=parser.parse_args(argv)
    try:
        print(prepare(args.original_reel,args.revised_reel,args.output_dir))
    except (OSError,ValueError,TypeError) as exc:
        parser.exit(2,f"MixLab private take comparison: {exc}\n")


if __name__=="__main__":
    main()
