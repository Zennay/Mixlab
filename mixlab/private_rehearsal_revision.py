"""Offline human-directed transition revision studio for an existing private reel.

Prepare compares genuine existing PCM16 family renders. Apply accepts only a
human-exported, original-reel-bound decision file. Never promotes a blind study,
changes the DSP engine, licenses audio or acts on zCloud worker claims.
"""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path

from .private_output import write_private_new
import tempfile

from .models import FAMILY_NAMES
from .private_transition_selection import (
    _copy_and_verify_wav, _read_json_and_digest, _verified_choice, _valid_sha,
)
from .private_rehearsal_mixdown import _chapters as _original_chapters
from .private_rehearsal_player import _admit_source_receipt
from .private_transition_reel import _page as _reel_page

MAX_MEDIA_BYTES = 128 * 1024 * 1024


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _private_publish(staged, destination, filenames):
    target = Path(destination)
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Choose a new private output directory under an existing parent")
    target.mkdir(mode=0o700)
    created = []
    try:
        for name in filenames:
            os.link(staged / name, target / name)
            created.append(name)
    except BaseException:
        for name in created:
            (target / name).unlink()
        target.rmdir()
        raise


def _read_original_human_feedback(mixdown_receipt_file, debrief_file, original_reel_sha):
    """Admit only real original WAV-bound human feedback, never synthetic scoring."""
    mixdown, mixdown_sha = _read_json_and_digest(mixdown_receipt_file)
    if mixdown.get("original_reel_receipt_sha256") != original_reel_sha:
        raise ValueError("The original rehearsal mixdown belongs to another reel")
    _, _, _, original_markers = _admit_source_receipt(mixdown)
    debrief, _ = _read_json_and_digest(debrief_file)
    if (type(debrief.get("schema_version")) is not int
            or debrief["schema_version"] != 1
            or debrief.get("kind") != "mixlab-private-rehearsal-debrief"
            or debrief.get("status") != "human-notes-not-blind-study"
            or debrief.get("rights_status") != "unverified"
            or debrief.get("source_receipt_sha256") != mixdown_sha
            or debrief.get("audio_sha256") != mixdown.get("audio_sha256")):
        raise ValueError("Debrief is not from this exact original rehearsal WAV")
    rows = debrief.get("observations")
    if type(rows) is not list or len(rows) != len(original_markers):
        raise ValueError("The original debrief must cover every real audio chapter")
    original_by_id = {p["original_chapter"]:p for p in original_markers}
    result = {}
    for expected, entry in zip(original_markers, rows):
        if (type(entry) is not dict
                or type(entry.get("position")) is not int
                or entry["position"] != expected["position"]
                or type(entry.get("original_chapter")) is not int
                or entry["original_chapter"] != expected["original_chapter"]):
            raise ValueError("Human debrief chapter/source identity is incomplete")
        note = entry.get("note")
        if type(note) is not str or len(note) > 300:
            raise ValueError("Human debrief note length is invalid")
        try:
            encoded = note.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Unencodable human debrief note") from exc
        if len(encoded) > 1200 or any(ord(ch) < 32 and ch not in "\\n\\t" for ch in note):
            raise ValueError("Unsupported human debrief characters")
        result[expected["original_chapter"]] = {"note":note, "bookmarks":[]}
    marks = debrief.get("bookmarks", [])
    if type(marks) is not list or len(marks) > 24:
        raise ValueError("Human bookmarks are incomplete or exceed the supported limit")
    for marker in marks:
        if type(marker) is not dict:
            raise ValueError("Malformed human timestamp marker")
        second = marker.get("second")
        original = marker.get("original_chapter")
        note = marker.get("note")
        if (type(second) not in (int,float) or not math.isfinite(second)
                or second < 0 or second > original_markers[-1]["end_seconds"]
                or type(original) is not int or original not in original_by_id
                or type(note) is not str or len(note) > 200):
            raise ValueError("Human timestamp marker is not source-bound")
        # The original player attributes silence gaps to the preceding chapter.
        marker_owner = original_markers[0]["original_chapter"]
        for point in original_markers:
            if second >= point["start_seconds"]:
                marker_owner = point["original_chapter"]
        if marker_owner != original:
            raise ValueError("Human timestamp references the wrong original audio chapter")
        try:
            data=note.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Unencodable timestamp note") from exc
        if len(data)>800 or any(ord(ch)<32 and ch not in "\\n\\t" for ch in note):
            raise ValueError("Invalid timestamp annotation")
        result[original]["bookmarks"].append({"second":second,"note":note})
    return result, mixdown_sha


def _prepare_page(document, fingerprint):
    cards = []
    for chapter in document["chapters"]:
        n = chapter["position"]
        players = []
        for family in FAMILY_NAMES:
            family_label = html.escape(family.replace("_", " ").title())
            file_name = html.escape(f"{n:02d}-{family}.wav", quote=True)
            players.append(
                f'<label class="option"><input type="radio" name="chapter-{n}" value="{family}" '
                + ('checked ' if family == chapter["selected_family"] else '')
                + f'><span>{family_label}</span><audio controls preload="none" '
                + f'src="{file_name}" aria-label="Chapter {n} · {family_label}"></audio></label>'
            )
        current = html.escape(chapter["selected_family"].replace("_", " ").title())
        note = html.escape(chapter["private_note"])
        feedback = chapter.get("human_rehearsal_feedback") or {}
        feedback_body = ""
        if feedback:
            written = html.escape(feedback["note"])
            cue_items = "".join(
                '<li>' + html.escape(str(item["second"])) + 's: '
                + html.escape(item["note"]) + '</li>'
                for item in feedback["bookmarks"]
            )
            feedback_body = ('<aside class="feedback"><h3>Original human rehearsal feedback</h3>'
                             + '<p>' + (written or 'No chapter comment') + '</p>'
                             + ('<ul>' + cue_items + '</ul>' if cue_items else '')
                             + '<p>Read-only source-bound notes. Select the next take yourself.</p></aside>')
        cards.append(
            f'<section class="chapter" data-position="{n}"><h2>Chapter {n}: revise or keep</h2>'
            f'<p>Originally human-selected: <strong>{current}</strong>. '
            'Listen to each of the four original renders. All choices refer to one exact permitted '
            'local gallery; nothing is re-rendered or normalized.</p>'
            + feedback_body + '<div class="options">' + "".join(players) + '</div>'
            + '<label class="note">Updated human cue note (optional, max 240 characters)'
            + f'<textarea maxlength="240" rows="3">{note}</textarea></label></section>'
        )
    return ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; media-src 'self' file: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>MixLab · Human Revision Studio</title>
<style>
:root{color-scheme:dark}body{background:#111827;color:#f9fafb;font:16px/1.55 system-ui,sans-serif;max-width:1050px;margin:auto;padding:25px 18px}
h1{font-size:clamp(30px,5vw,44px);line-height:1.15}p{color:#cbd5e1}
small{color:#93c5fd}.chapter{background:#1e293b;border:1px solid #475569;border-radius:16px;padding:20px;margin:25px 0}
 .chapter h2{font-size:22px}.feedback{border:1px solid #64748b;background:#283449;padding:12px;border-radius:10px;margin:16px 0}
.feedback p{white-space:pre-wrap;overflow-wrap:anywhere}.feedback li{overflow-wrap:anywhere}
.options{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,225px),1fr));gap:12px}
.option{display:block;background:#111827;border:1px solid #64748b;padding:12px;border-radius:12px}
.option span{display:inline-block;padding-left:6px;font-weight:650}.option:has(input:checked){border-color:#93c5fd;background:#253247}
.option audio{display:block;width:100%;margin-top:14px}.note{display:block;margin-top:16px}
textarea{display:block;width:100%;box-sizing:border-box;font:inherit;background:#111827;color:#fff;border:1px solid #64748b;border-radius:9px;padding:12px;margin-top:7px}
button{font:inherit;background:#93c5fd;color:#0f172a;border:0;border-radius:10px;font-weight:700;padding:14px 18px;cursor:pointer}
button:focus-visible,textarea:focus-visible,input:focus-visible{outline:3px solid #facc15}
footer{padding:18px 0;border-top:1px solid #64748b}
</style>
<header><small>PRIVATE / HUMAN / ORIGINAL SOURCES ONLY</small><h1>Build your next rehearsal take</h1>
<p>Keep or change each chapter's existing transition family. The selected results can be exported
as a private decision file and assembled into a fresh rehearsal with the command documented
alongside this page. No model, source separation, upload, permission grant, study score or
automatic publication is involved.</p></header>
<main id="studio">""" + "".join(cards) + """</main>
<button id="export">Download my source-bound revision plan</button>
<p id="status" role="status" aria-live="polite">Review the audio before exporting.</p>
<footer><p>Human choices are not blinded evaluation findings. Rights status stays unverified;
all original galleries and receipts must remain available to prepare a new iteration.</p></footer>
<script>
const fingerprint = """ + json.dumps(fingerprint) + """;
const original = """ + json.dumps(document["original_reel_receipt_sha256"]) + """;
const chapters = [...document.querySelectorAll('.chapter')];
document.querySelectorAll('audio').forEach(audio=>audio.addEventListener('play',()=>{
  document.querySelectorAll('audio').forEach(other=>{if(other!==audio)other.pause()});
}));
document.getElementById('export').onclick=()=>{
  const choices=chapters.map((section,index)=>{
    const selected=section.querySelector('input[type=radio]:checked');
    const note=section.querySelector('textarea').value.trim().slice(0,240);
    return {position:index+1,selected_family:selected.value,note};
  });
  const data={schema_version:1,kind:'mixlab-private-human-revision',
    studio_receipt_sha256:fingerprint,original_reel_receipt_sha256:original,
    status:'human-decision-not-blind-study',rights_status:'unverified',choices};
  const blob=new Blob([JSON.stringify(data,null,2)+'\\n'],{type:'application/json'});
  const url=URL.createObjectURL(blob),anchor=document.createElement('a');
  anchor.href=url;anchor.download='mixlab-human-revision.json';anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  document.getElementById('status').textContent='Revision plan downloaded. Apply it locally to create a new source-bound reel.';
};
</script></html>
""")


def prepare(original_reel, galleries, destination, *, debrief=None, mixdown_receipt=None):
    """Create a private four-family, human-selectable browser comparison."""
    if not 2 <= len(galleries) <= 8:
        raise ValueError("Specify exactly one original gallery for each of 2–8 chapters")
    original, original_sha = _read_json_and_digest(Path(original_reel) / "receipt.json")
    chapters = _original_chapters(original)
    if (debrief is None) != (mixdown_receipt is None):
        raise ValueError("Supply both the original mixdown receipt and its human debrief")
    feedback = {}
    mixdown_sha = None
    if debrief is not None:
        feedback, mixdown_sha = _read_original_human_feedback(
            mixdown_receipt, debrief, original_sha
        )
        if set(feedback) != {entry["chapter"] for entry in chapters}:
            raise ValueError("Original WAV human-feedback chapters do not match this reel")
    if len(galleries) != len(chapters):
        raise ValueError("Provide original galleries in the exact original chapter order")
    target = Path(destination)
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Choose a new private studio folder under an existing parent")
    with tempfile.TemporaryDirectory(prefix=".mixlab-human-revision-", dir=target.parent) as working:
        stage = Path(working)
        results = []
        total = 0
        used = set()
        outputs = []
        for index, (gallery_arg, prior) in enumerate(zip(galleries, chapters), 1):
            gallery = Path(gallery_arg)
            if not gallery.is_dir():
                raise ValueError("One required local original gallery is unavailable")
            receipt, gallery_sha = _read_json_and_digest(gallery / "receipt.json")
            if gallery_sha != prior["source_gallery_receipt_sha256"] or gallery_sha in used:
                raise ValueError("Gallery identity or original chapter position does not match")
            used.add(gallery_sha)
            sha_by_family = {}
            for family in FAMILY_NAMES:
                dummy = {"schema_version":1,"kind":"mixlab-private-dj-choice",
                         "human_choice_not_blind_study":True,"receipt_sha256":gallery_sha,
                         "selected_family":family,"note":""}
                _, entry, _ = _verified_choice(receipt, gallery_sha, dummy)
                file_name = f"{index:02d}-{family}.wav"
                path = stage / file_name
                size = _copy_and_verify_wav(gallery / f"{family}.wav", path,
                                            entry["audio_sha256"])
                total += size
                if total > MAX_MEDIA_BYTES:
                    raise ValueError("Private revision comparison exceeds 128 MiB audio budget")
                path.chmod(0o600)
                outputs.append(file_name)
                sha_by_family[family] = entry["audio_sha256"]
            if sha_by_family[prior["family"]] != prior["audio_sha256"]:
                raise ValueError("Original chosen audio does not match its gallery source")
            results.append({"position":index,
                            "source_gallery_receipt_sha256":gallery_sha,
                            "original_human_choice_sha256":prior["human_choice_sha256"],
                            "selected_family":prior["family"],
                            "private_note":prior["private_note"],
                            "human_rehearsal_feedback":feedback.get(index),
                            "candidate_audio_sha256":sha_by_family})
        document = {
            "schema_version":1,"kind":"mixlab-private-human-revision-studio",
            "status":"prepared-for-human-choice","rights_status":"unverified",
            "original_reel_receipt_sha256":original_sha,"chapter_count":len(results),
            "source_human_mixdown_receipt_sha256":mixdown_sha,
            "total_audio_bytes":total,"chapters":results,
        }
        receipt_path = stage / "receipt.json"
        write_private_new(receipt_path, (json.dumps(document,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8"))
        page = stage / "index.html"
        write_private_new(page, (_prepare_page(document, _hash(receipt_path))).encode("utf-8"))
        _private_publish(stage,target,outputs+["receipt.json","index.html"])
    return target / "index.html"


def _admit_decisions(document, document_sha, plan):
    if (type(plan.get("schema_version")) is not int or plan["schema_version"] != 1
        or plan.get("kind") != "mixlab-private-human-revision"
        or plan.get("status") != "human-decision-not-blind-study"
        or plan.get("rights_status") != "unverified"
        or plan.get("studio_receipt_sha256") != document_sha
        or plan.get("original_reel_receipt_sha256") != document["original_reel_receipt_sha256"]):
        raise ValueError("Revision decision is not bound to this exact private studio")
    choices=plan.get("choices")
    rows=document.get("chapters")
    if type(choices) is not list or type(rows) is not list or len(choices)!=len(rows):
        raise ValueError("Every original chapter needs one explicit human decision")
    results=[]
    for index,(entry,row) in enumerate(zip(choices,rows),1):
        if type(entry) is not dict or type(entry.get("position")) is not int or entry["position"]!=index:
            raise ValueError("Revision chapter positions are incomplete or out of order")
        family=entry.get("selected_family")
        note=entry.get("note")
        if family not in FAMILY_NAMES or type(note) is not str or len(note)>240:
            raise ValueError("Invalid family or cue note in human decision")
        try:
            data=note.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Invalid human cue note Unicode") from exc
        if len(data)>1024 or any(ord(ch)<32 and ch not in "\n\t" for ch in note):
            raise ValueError("Unsupported control character in human cue note")
        results.append((family,note))
    return results


def apply(studio_dir, decision_file, destination):
    """Make a new original-compatible reel from explicit human-selected variants."""
    studio=Path(studio_dir)
    target=Path(destination)
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Choose a new rehearsal reel folder under an existing parent")
    document, document_sha=_read_json_and_digest(studio / "receipt.json")
    if (type(document.get("schema_version")) is not int or document["schema_version"]!=1
            or document.get("kind")!="mixlab-private-human-revision-studio"
            or document.get("status")!="prepared-for-human-choice"
            or document.get("rights_status")!="unverified"):
        raise ValueError("Unrecognized original revision studio")
    rows=document.get("chapters")
    if type(rows) is not list or not 2<=len(rows)<=8:
        raise ValueError("Original revision studio has invalid chapter count")
    plan,plan_sha=_read_json_and_digest(decision_file)
    choices=_admit_decisions(document,document_sha,plan)
    with tempfile.TemporaryDirectory(prefix=".mixlab-revised-reel-",dir=target.parent) as working:
        stage=Path(working)
        rendered=[]
        files=[]
        total=0
        for index,(row,(family,note)) in enumerate(zip(rows,choices),1):
            if type(row) is not dict or type(row.get("position")) is not int or row["position"]!=index:
                raise ValueError("Revision studio chapter identity is invalid")
            sha_by_family=row.get("candidate_audio_sha256")
            if (type(sha_by_family) is not dict or set(sha_by_family)!=set(FAMILY_NAMES)
                or any(not _valid_sha(v) for v in sha_by_family.values())
                or not _valid_sha(row.get("source_gallery_receipt_sha256"))):
                raise ValueError("Revision candidate evidence is incomplete")
            chosen=f"{index:02d}-{family}.wav"
            path=stage / chosen
            total+=_copy_and_verify_wav(studio/chosen,path,sha_by_family[family])
            if total>MAX_MEDIA_BYTES:
                raise ValueError("Revised rehearsal exceeds private audio budget")
            path.chmod(0o600)
            files.append(chosen)
            # One authentic human-downloaded plan governs all chapters.
            # Keep its real SHA-256 rather than inventing per-chapter receipts.
            # No invented studio listening metrics: duration comes from the
            # actual regular PCM16 WAV header, not untrusted browser JSON.
            import wave
            try:
                with wave.open(str(path),"rb") as clip:
                    if clip.getsampwidth()!=2 or clip.getcomptype()!="NONE":
                        raise ValueError("Candidate is not PCM16")
                    duration=clip.getnframes()/clip.getframerate()
            except (wave.Error,EOFError) as exc:
                raise ValueError("Candidate WAV cannot be read") from exc
            rendered.append({
                "chapter":index,"family":family,"audio":chosen,
                "audio_sha256":sha_by_family[family],"seconds":duration,
                "private_note":note,
                "source_gallery_receipt_sha256":row["source_gallery_receipt_sha256"],
                "human_choice_sha256":plan_sha,
                "human_choice_source":"revision-plan",
            })
        receipt={"schema_version":1,"kind":"mixlab-private-rehearsal-reel",
                 "status":"human-selected-not-blind-study","rights_status":"unverified",
                 "chapter_count":len(rendered),"total_audio_bytes":total,
                 "original_order_only":True,"human_reordered_in_browser_only":False,
                 "revision_source_studio_sha256":document_sha,
                 "human_revision_decision_sha256":plan_sha,"chapters":rendered}
        receipt_path=stage/"receipt.json"
        write_private_new(receipt_path, (json.dumps(receipt,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8"))
        page=stage/"index.html"
        write_private_new(page, (_reel_page(receipt,_hash(receipt_path))).encode("utf-8"))
        _private_publish(stage,target,files+["receipt.json","index.html"])
    return target/"index.html"


def main(argv=None):
    parser=argparse.ArgumentParser(description="Private, original-source-bound human transition revision studio")
    commands=parser.add_subparsers(dest="command",required=True)
    p=commands.add_parser("prepare",help="Create a local four-family human revision UI")
    p.add_argument("original_reel")
    p.add_argument("output_studio")
    p.add_argument("--gallery",action="append",required=True,
                   help="Original gallery in its original reel chapter order (2–8 times)")
    p.add_argument("--mixdown-receipt",help="Optional original .rehearsal.json for human feedback")
    p.add_argument("--debrief",help="Optional original WAV-bound human debrief JSON (requires --mixdown-receipt)")
    a=commands.add_parser("apply",help="Render a fresh reel from a human-downloaded revision")
    a.add_argument("studio")
    a.add_argument("human_revision_json")
    a.add_argument("output_reel")
    args=parser.parse_args(argv)
    try:
        result=(prepare(args.original_reel,args.gallery,args.output_studio,
                        debrief=args.debrief, mixdown_receipt=args.mixdown_receipt)
                if args.command=="prepare" else
                apply(args.studio,args.human_revision_json,args.output_reel))
        print(result)
    except (OSError,ValueError,TypeError) as exc:
        parser.exit(2,f"MixLab human revision studio: {exc}\n")


if __name__=="__main__":
    main()
