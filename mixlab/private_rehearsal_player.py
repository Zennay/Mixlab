"""Private offline chapter player for one source-verified MixLab rehearsal WAV.

A user-facing audio reviewer, not a licensing, mastering, or blind-study gate.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import stat
import tempfile
import wave

from .private_transition_selection import _read_json_and_digest, _valid_sha, READ_FLAGS

MAX_WAV_BYTES = 128 * 1024 * 1024
MAX_CHAPTERS = 8


def _admit_source_receipt(data):
    if (type(data.get("schema_version")) is not int or data["schema_version"] != 1
            or data.get("kind") != "mixlab-private-gapped-rehearsal"
            or data.get("status") != "human-rehearsal-preview-only"
            or data.get("rights_status") != "unverified"
            or data.get("seamless_dj_mix") is not False
            or data.get("rights_verified") is not False
            or data.get("blind_preference_verified") is not False):
        raise ValueError("Unsupported private rehearsal mixdown receipt")
    if not _valid_sha(data.get("audio_sha256")) or not _valid_sha(data.get("original_reel_receipt_sha256")):
        raise ValueError("Mixdown receipt lacks canonical audio and original-source hashes")
    if data.get("private_order_sha256") is not None and not _valid_sha(data["private_order_sha256"]):
        raise ValueError("Private running-order digest is invalid")
    rate, channels, frames, gap = (data.get(k) for k in ("sample_rate", "channels", "frames", "gap_ms"))
    if (type(rate) is not int or not 8000 <= rate <= 96000
            or type(channels) is not int or channels not in (1, 2)
            or type(frames) is not int or not 1 <= frames <= 32_000_000
            or type(gap) is not int or not 0 <= gap <= 1000):
        raise ValueError("Mixdown PCM format or duration is invalid")
    chapters = data.get("chapters")
    if type(chapters) is not list or not 2 <= len(chapters) <= MAX_CHAPTERS:
        raise ValueError("Expected 2–8 privately selected rehearsal chapters")
    accepted = []
    seen = set()
    cursor = 0
    gap_frames = round(gap * rate / 1000)
    for n, row in enumerate(chapters, 1):
        if type(row) is not dict:
            raise ValueError("Chapter metadata is invalid")
        chapter = row.get("original_chapter")
        length = row.get("frames")
        family = row.get("family")
        note = row.get("private_note")
        if (type(chapter) is not int or not 1 <= chapter <= MAX_CHAPTERS or chapter in seen
                or type(length) is not int or not 1 <= length <= 2_000_000
                or family not in ("baseline", "bass_swap", "echo_exit", "hard_cut")
                or type(note) is not str or len(note) > 240
                or not _valid_sha(row.get("selected_wav_sha256"))
                or not _valid_sha(row.get("source_gallery_receipt_sha256"))
                or not _valid_sha(row.get("human_choice_sha256"))):
            raise ValueError("A selected chapter contains incomplete human/source evidence")
        try:
            encoded = note.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Chapter cue note contains invalid Unicode") from exc
        if len(encoded) > 1024 or any(ord(ch) < 32 and ch not in "\n\t" for ch in note):
            raise ValueError("Chapter cue note contains unsupported control characters")
        seen.add(chapter)
        accepted.append({
            "position": n, "original_chapter": chapter,
            "start_seconds": cursor / rate,
            "end_seconds": (cursor + length) / rate,
            "family": family, "private_note": note,
        })
        cursor += length
        if n < len(chapters):
            cursor += gap_frames
    if cursor != frames:
        raise ValueError("Chapter boundaries do not match the rendered PCM duration")
    return rate, channels, frames, accepted


def _copy_private_audio(source, destination, expected_sha):
    fd = os.open(source, READ_FLAGS)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 44 <= before.st_size <= MAX_WAV_BYTES:
            raise ValueError("Rehearsal WAV must be one bounded regular file")
        h = hashlib.sha256()
        count = 0
        with open(destination, "wb") as out:
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                count += len(block)
                if count > MAX_WAV_BYTES:
                    raise ValueError("Rehearsal WAV exceeds bounded audio size")
                h.update(block)
                out.write(block)
        after = os.fstat(fd)
        if (count != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("Rehearsal WAV changed during local handoff")
        if h.hexdigest() != expected_sha:
            raise ValueError("Rehearsal audio differs from its original mixdown receipt")
    finally:
        os.close(fd)
    destination.chmod(0o600)


def _timecode(seconds):
    return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"


def _player_html(chapters, audio_sha, receipt_sha, duration):
    cards = []
    for row in chapters:
        n = row["position"]
        family = html.escape(row["family"].replace("_", " ").title())
        original_note = html.escape(row["private_note"])
        cards.append(
            f'<article class="chapter" data-position="{n}" data-start="{row["start_seconds"]:.9f}" '
            f'data-end="{row["end_seconds"]:.9f}">'
            f'<div class="row"><h2>{n}. {family}</h2><button type="button" class="jump" '
            f'aria-label="Jump to chapter {n}">Play chapter</button></div>'
            f'<p class="time">{_timecode(row["start_seconds"])}–{_timecode(row["end_seconds"])} · '
            f'Original chapter {row["original_chapter"]}</p>'
            f'<p class="cue">Original human cue: {original_note or "—"}</p>'
            f'<label>My rehearsal note for chapter {n} (optional)'
            f'<textarea maxlength="300" rows="2" placeholder="Cue, energy or timing observation"></textarea></label>'
            f'</article>'
        )
    markers = [
        {"position": row["position"], "original_chapter": row["original_chapter"],
         "start": row["start_seconds"], "end": row["end_seconds"]}
        for row in chapters
    ]
    return ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>MixLab · Private rehearsal chapter player</title>
<style>
:root{color-scheme:dark}body{font:16px/1.6 system-ui,sans-serif;max-width:920px;margin:auto;padding:28px 18px;background:#111827;color:#f8fafc}
h1{font-size:clamp(28px,5vw,42px);line-height:1.15}p{color:#cbd5e1}.intro{max-width:780px}
small{color:#93c5fd}audio{width:100%;margin:10px 0}
nav,.row{display:flex;align-items:center;justify-content:space-between;gap:12px}nav{justify-content:flex-start;flex-wrap:wrap;margin:18px 0}
button{font:inherit;font-weight:600;background:#93c5fd;color:#111827;border:0;padding:10px 14px;border-radius:8px;cursor:pointer}
button:focus-visible,textarea:focus-visible,input:focus-visible{outline:3px solid #fbbf24}
.bookmarks{background:#1e293b;border:1px solid #64748b;border-radius:14px;padding:16px;margin:20px 0}
.bookmarks .mark{display:flex;align-items:center;flex-wrap:wrap;gap:8px;border-top:1px solid #475569;padding:12px 0}
.bookmarks input{font:inherit;background:#111827;border:1px solid #64748b;color:white;border-radius:8px;padding:8px;min-width:min(220px,65vw);flex:1}
.restore{padding:8px;background:#1e293b;border:1px solid #64748b;border-radius:8px}
.restore input{display:block;max-width:240px;font-size:13px}
.chapter{border:1px solid #475569;background:#1e293b;border-radius:16px;padding:18px;margin:16px 0}
.chapter.active{border-color:#93c5fd}.chapter h2{font-size:19px;margin:0}
.chapter .time{font-size:14px;color:#94a3b8}.cue{white-space:pre-wrap;overflow-wrap:anywhere}
label{display:block;color:#cbd5e1}textarea{display:block;width:100%;box-sizing:border-box;margin:8px 0;border-radius:8px;background:#111827;border:1px solid #64748b;color:#fff;padding:10px;font:inherit}
footer{border-top:1px solid #64748b;margin-top:26px}
@media print{body{color:#111;background:white}nav,audio,button,textarea{display:none}.bookmarks{background:white;color:#111}.bookmarks input{border:none;color:#111;background:white}.chapter{background:white;color:#111;border:1px solid #888;break-inside:avoid}.chapter p,footer p{color:#222}}
</style>
<header><small>LOCAL · SOURCE-CHECKED · HUMAN REHEARSAL</small><h1>Full rehearsal, one audio file</h1>
<p class="intro">Each marker is derived from the original chapter lengths and explicit silence gaps.
Jump through your own transitions, review the exact source-bound playback and capture
private notes. This is a hard-joined rehearsal preview, not a seamless DJ set or a rights approval.</p>
<p><strong>Total duration: """ + html.escape(_timecode(duration)) + """</strong></p></header>
<audio id="master" preload="metadata" controls src="rehearsal.wav"></audio>
<nav><button id="prev">← Previous</button><button id="next">Next →</button>
<button id="start">Play from start</button><button id="stop">Stop</button>
<button id="mark">Bookmark playback cue</button>
<button id="export">Download private debrief</button><button id="print">Print cue notes</button>
<label class="restore">Reopen a debrief <input id="reopen" type="file" accept=".json,application/json"></label></nav>
<p id="status" role="status" aria-live="polite">Your private source-bound rehearsal is ready.</p>
<main id="chapters">""" + "".join(cards) + """</main>
<section class="bookmarks" aria-labelledby="bookmark-heading"><h2 id="bookmark-heading">My rehearsal cue markers</h2>
<p>Bookmark up to 24 playback moments. Markers and observations remain in this browser tab until you explicitly download a debrief.</p>
<div id="bookmarks"></div></section>
<footer><p>No automatic uploads, storage, streaming, loudness normalization, music-rights
verification or blind preference study. The original render receipt remains authoritative.</p></footer>
<script>
const markers = """ + json.dumps(markers) + """;
const audioSha = """ + json.dumps(audio_sha) + """;
const receiptSha = """ + json.dumps(receipt_sha) + """;
const player=document.getElementById('master');
const cards=[...document.querySelectorAll('.chapter')];
const status=document.getElementById('status');
let activeIndex=0;
let privateMarks=[];
const maxSeconds=markers[markers.length-1].end;
const atTime=t=>{
  for(let i=markers.length-1;i>=0;i--)if(t>=markers[i].start)return i;
  return 0;
};
const validNote=(value,cap)=>typeof value==='string' && value.length<=cap &&
  new TextEncoder().encode(value).length<=cap*4 &&
  [...value].every(ch=>ch.codePointAt(0)>=32 || ch==='\\n' || ch==='\\t');
function drawMarks(){
  const list=document.getElementById('bookmarks');
  list.replaceChildren();
  privateMarks.forEach((item,index)=>{
    const row=document.createElement('div');row.className='mark';
    const time=document.createElement('button');time.type='button';
    time.textContent='▶ '+Math.floor(item.second/60)+':'+(item.second%60).toFixed(2).padStart(5,'0');
    time.setAttribute('aria-label','Jump to rehearsal cue '+(index+1));
    time.onclick=()=>{player.currentTime=item.second;player.play().catch(()=>{})};
    const label=document.createElement('span');label.textContent='Chapter '+item.original_chapter;
    const note=document.createElement('input');note.type='text';note.maxLength=200;
    note.value=item.note;note.setAttribute('aria-label','Marker note '+(index+1));
    note.oninput=()=>{item.note=note.value.slice(0,200)};
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';
    remove.onclick=()=>{privateMarks.splice(index,1);drawMarks()};
    row.append(time,label,note,remove);list.appendChild(row);
  });
}
function currentIndex(){
  return atTime(player.currentTime);
}
function highlight(index){
  activeIndex=Math.max(0,Math.min(index,markers.length-1));
  cards.forEach((c,i)=>c.classList.toggle('active',i===activeIndex));
}
function jump(index,play=true){
  highlight(index);player.currentTime=markers[activeIndex].start;
  if(play)player.play().catch(()=>status.textContent='Select Play to start audio on this device.');
}
cards.forEach((c,i)=>c.querySelector('.jump').addEventListener('click',()=>jump(i)));
player.addEventListener('timeupdate',()=>highlight(currentIndex()));
document.getElementById('prev').onclick=()=>jump(Math.max(0,currentIndex()-1));
document.getElementById('next').onclick=()=>jump(Math.min(markers.length-1,currentIndex()+1));
document.getElementById('start').onclick=()=>jump(0);
document.getElementById('stop').onclick=()=>{player.pause();player.currentTime=0;highlight(0)};
document.getElementById('print').onclick=()=>window.print();
document.getElementById('mark').onclick=()=>{
  if(privateMarks.length>=24){status.textContent='24-marker limit reached; remove one to add another.';return}
  const second=Math.round(Math.max(0,Math.min(maxSeconds,player.currentTime))*100)/100;
  privateMarks.push({second,original_chapter:markers[atTime(second)].original_chapter,note:''});
  drawMarks();status.textContent='Private cue bookmarked. Download your debrief to preserve it.';
};
document.getElementById('reopen').addEventListener('change',async event=>{
  const file=event.currentTarget.files?.[0];if(!file)return;
  try{
    if(file.size<4||file.size>16384)throw Error('size');
    const data=JSON.parse(await file.text());
    if(!data||Array.isArray(data)||data.schema_version!==1||
      data.kind!=='mixlab-private-rehearsal-debrief'||
      data.source_receipt_sha256!==receiptSha||data.audio_sha256!==audioSha||
      data.status!=='human-notes-not-blind-study'||data.rights_status!=='unverified'||
      !Array.isArray(data.observations)||data.observations.length!==markers.length)throw Error('identity');
    const checkedNotes=data.observations.map((entry,i)=>{
      if(!entry||Array.isArray(entry)||entry.original_chapter!==markers[i].original_chapter||
        entry.position!==markers[i].position||!validNote(entry.note,300))throw Error('notes');
      return entry.note;
    });
    const rows=data.bookmarks===undefined?[]:data.bookmarks;
    if(!Array.isArray(rows)||rows.length>24)throw Error('markers');
    const checkedMarks=rows.map(entry=>{
      if(!entry||Array.isArray(entry)||typeof entry.second!=='number'||
        !Number.isFinite(entry.second)||entry.second<0||entry.second>maxSeconds||
        !Number.isInteger(entry.original_chapter)||
        entry.original_chapter!==markers[atTime(entry.second)].original_chapter||
        !validNote(entry.note,200))throw Error('marker');
      return {second:entry.second,original_chapter:entry.original_chapter,note:entry.note};
    });
    // Validate every field before changing any local human note.
    cards.forEach((card,i)=>card.querySelector('textarea').value=checkedNotes[i]);
    privateMarks=checkedMarks;drawMarks();
    status.textContent='Exact source-bound private debrief reopened. Review before exporting.';
  }catch{
    status.textContent='Debrief not loaded: invalid, incomplete or from another WAV/receipt.';
  }finally{event.currentTarget.value=''}
});
document.getElementById('export').onclick=()=>{
  const observations=cards.map((c,i)=>({
    original_chapter:markers[i].original_chapter,
    position:markers[i].position,
    note:c.querySelector('textarea').value.slice(0,300)
  }));
  const data={schema_version:1,kind:'mixlab-private-rehearsal-debrief',
    source_receipt_sha256:receiptSha,audio_sha256:audioSha,
    status:'human-notes-not-blind-study',rights_status:'unverified',observations,
    bookmarks:privateMarks.map(m=>({second:m.second,original_chapter:m.original_chapter,note:m.note}))};
  const href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\\n'],{type:'application/json'}));
  const a=document.createElement('a');a.href=href;a.download='mixlab-private-rehearsal-debrief.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(href),1000);
  status.textContent='Your private source-bound rehearsal notes have been downloaded.';
};
highlight(0);
</script></html>
""")


def create_player(source_wav, dest_dir):
    source = Path(source_wav)
    destination = Path(dest_dir)
    sidecar = source.with_suffix(".rehearsal.json")
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError("Choose a new private player folder under an existing parent")
    receipt, receipt_sha = _read_json_and_digest(sidecar)
    rate, channels, frames, chapters = _admit_source_receipt(receipt)
    with tempfile.TemporaryDirectory(prefix=".mixlab-private-player-", dir=destination.parent) as folder:
        stage = Path(folder)
        audio_path = stage / "rehearsal.wav"
        _copy_private_audio(source, audio_path, receipt["audio_sha256"])
        try:
            with wave.open(str(audio_path), "rb") as clip:
                if (clip.getcomptype() != "NONE" or clip.getsampwidth() != 2
                        or (clip.getframerate(), clip.getnchannels(), clip.getnframes()) !=
                        (rate, channels, frames)):
                    raise ValueError("Actual PCM data format differs from the original receipt")
                remaining = frames
                while remaining:
                    take = min(4096, remaining)
                    if len(clip.readframes(take)) != take * channels * 2:
                        raise ValueError("Rehearsal contains truncated PCM audio")
                    remaining -= take
        except (wave.Error, EOFError) as exc:
            raise ValueError("Invalid original rehearsal WAV") from exc
        page = stage / "index.html"
        page.write_text(_player_html(chapters, receipt["audio_sha256"], receipt_sha, frames/rate),
                        encoding="utf-8")
        page.chmod(0o600)
        # Copy the original private receipt only after a second no-follow
        # descriptor read and exact SHA match; never trust a reopened path.
        receipt_copy = stage / "original-receipt.json"
        fd = os.open(sidecar, READ_FLAGS)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= 65536:
                raise ValueError("Original private receipt is no longer a bounded regular file")
            raw = os.read(fd, 65537)
            after = os.fstat(fd)
            if (len(raw) != before.st_size or
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or
                    hashlib.sha256(raw).hexdigest() != receipt_sha):
                raise ValueError("Original private receipt changed before publication")
        finally:
            os.close(fd)
        receipt_copy.write_bytes(raw)
        receipt_copy.chmod(0o600)
        destination.mkdir(mode=0o700)
        published = []
        try:
            for name in ("rehearsal.wav", "original-receipt.json", "index.html"):
                os.link(stage / name, destination / name)
                published.append(name)
        except BaseException:
            for name in published:
                (destination / name).unlink()
            destination.rmdir()
            raise
    return destination / "index.html"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a private HTML chapter player for one exact source-bound rehearsal mixdown"
    )
    parser.add_argument("rehearsal_wav", help="A previously exported .wav with matching .rehearsal.json receipt")
    parser.add_argument("output_dir", help="New private offline player directory")
    args = parser.parse_args(argv)
    try:
        print(create_player(args.rehearsal_wav, args.output_dir))
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"MixLab private chapter player: {exc}\n")


if __name__ == "__main__":
    main()
