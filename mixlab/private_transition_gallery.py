"""Offline, private four-family transition gallery using the existing bounded DSP.

This is a product-facing consumer of mixlab.dsp.render, not a replacement for
its clipping policy, rights admission, tempo alignment or listening study.
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

from .dsp import render as render_transition
from .models import FAMILY_NAMES, Recipe


def _sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _level(value):
    if value <= 0:
        return "silence"
    return f"{20 * math.log10(value):.1f} dBFS"


def _gallery_html(receipt, receipt_sha256):
    cards = []
    for entry in receipt["renders"]:
        title = html.escape(entry["family"].replace("_", " ").title())
        filename = html.escape(entry["audio"], quote=True)
        cards.append(
            f'<article><h2>{title}</h2><audio controls preload="none" src="{filename}" '
            f'aria-label="{title} transition"></audio>'
            f'<p>Peak: {_level(entry["pcm_peak"])} · RMS: {_level(entry["pcm_rms"])} '
            f'· {entry["seconds"]:.2f} seconds</p></article>'
        )
    choices = "".join(
        f'<option value="{html.escape(item["family"], quote=True)}">'
        f'{html.escape(item["family"].replace("_", " ").title())}</option>'
        for item in receipt["renders"]
    )
    delta = receipt["requested_gain_db"] - receipt["shared_gain_db"]
    level_text = (f"Common gain: {receipt['shared_gain_db']:.1f} dB"
                  + (f" (reduced by {delta:.1f} dB to prevent clipping)" if delta > 0 else ""))
    return ("""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; media-src 'self' file: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>MixLab · Private transition gallery</title>
<style>
:root{color-scheme:dark}body{max-width:920px;margin:auto;padding:28px 18px;background:#111827;color:#f4f6fb;font:16px/1.55 system-ui,sans-serif}
header{margin:0 0 26px}h1{font-size:clamp(28px,5vw,44px);line-height:1.13}h2{font-size:22px;margin:0 0 14px}
p{color:#c5cee0}strong{color:white}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:18px}
article{background:#1d293b;border:1px solid #43516a;padding:20px;border-radius:16px}audio{width:100%;margin:8px 0}
small{color:#93c5fd}.review{margin-top:24px;padding:24px;border-radius:16px;background:#1d293b;border:1px solid #43516a}
.review label{display:block;margin:16px 0 6px}.review select,.review textarea,.review input[type=file]{display:block;width:100%;box-sizing:border-box;padding:12px;border-radius:8px;background:#111827;color:white;border:1px solid #64748b;font:inherit}
.review button{padding:12px 18px;background:#93c5fd;color:#101827;font:inherit;font-weight:700;border:0;border-radius:8px;cursor:pointer}
footer{margin-top:25px;border-top:1px solid #43516a;padding-top:16px}
</style>
<header><small>PRIVATE / LOCAL · MIXLAB</small><h1>Compare four real transitions</h1>
<p>No source media leaves your computer. Each player uses the same manual BPM, cue points and gain;
playing one pauses the others. These engineering metrics are not musical preference scores.</p>
<p><strong>""" + html.escape(level_text) + """</strong></p></header>
<main class="grid">""" + "".join(cards) + """</main>
<section class="review" aria-labelledby="review-heading"><h2 id="review-heading">Your private DJ choice</h2>
<p>Choose what worked for <em>your</em> set, and optionally add a short note. Export stays on this
device, is bound to the exact original render receipt and is <strong>not</strong> a blinded
music-quality study or rights approval.</p>
<form id="review-form"><label for="preferred">Preferred transition</label>
<select id="preferred" name="preferred" required><option value="">Select a family…</option>""" + choices + """</select>
<label for="dj-note">Your cue note (optional, 240 characters max)</label>
<textarea id="dj-note" name="note" rows="3" maxlength="240" placeholder="What would you change before rehearsal?"></textarea>
<label for="reopen-choice">Reopen a saved choice from this exact gallery (optional)</label>
<input id="reopen-choice" type="file" accept=".json,application/json" aria-describedby="reopen-help">
<p id="reopen-help">Nothing is uploaded or stored automatically. This does not certify a blinded study.</p>
<button type="submit">Download private choice (.json)</button><p id="choice-status" role="status" aria-live="polite"></p></form></section>
<footer><p>All audio was rendered locally with the existing streaming PCM16 renderer.
These variants are not LUFS-matched. No stems, beat detection, tempo stretching, music
rights or listener preference are inferred. Keep originals and receipts private.</p></footer>
<script>
document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})));
const receiptSha = """ + json.dumps(receipt_sha256) + """;
// Explicit, local-only reopening of a browser-exported preference. No storage
// or file-system permissions beyond the one file the operator selects.
document.getElementById('reopen-choice').addEventListener('change', async event => {
  const file = event.currentTarget.files && event.currentTarget.files[0];
  if (!file) return;
  const status = document.getElementById('choice-status');
  try {
    if (file.size < 2 || file.size > 8192) throw new Error('size');
    const data = JSON.parse(await file.text());
    const select = document.getElementById('preferred');
    const families = [...select.options].map(option => option.value).filter(Boolean);
    if (!data || Array.isArray(data) || data.schema_version !== 1 ||
        data.kind !== 'mixlab-private-dj-choice' ||
        data.human_choice_not_blind_study !== true ||
        data.receipt_sha256 !== receiptSha ||
        !families.includes(data.selected_family) ||
        typeof data.note !== 'string' || data.note.length > 240 ||
        new TextEncoder().encode(data.note).length > 1024 ||
        [...data.note].some(ch => ch.codePointAt(0) < 32 && ch !== '\\n' && ch !== '\\t')) {
      throw new Error('invalid');
    }
    // All fields validated before changing the form.
    select.value = data.selected_family;
    document.getElementById('dj-note').value = data.note;
    status.textContent = 'Choice and note reopened from the same original gallery. Review before exporting.';
  } catch {
    status.textContent = 'Choice not loaded: unsupported, altered or from another gallery.';
  } finally {
    event.currentTarget.value = '';
  }
});
document.getElementById('review-form').addEventListener('submit', event => {
  event.preventDefault();
  const form=event.currentTarget;
  const selected=form.elements.namedItem('preferred').value;
  const note=form.elements.namedItem('note').value.trim().slice(0,240);
  const record={schema_version:1,kind:'mixlab-private-dj-choice',receipt_sha256:receiptSha,
    selected_family:selected,note:note,human_choice_not_blind_study:true};
  const blob=new Blob([JSON.stringify(record,null,2)+'\\n'],{type:'application/json'});
  const uri=URL.createObjectURL(blob);const link=document.createElement('a');
  link.href=uri;link.download='mixlab-dj-choice.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(uri),1000);
  document.getElementById('choice-status').textContent='Your private, receipt-bound choice has been downloaded.';
});
</script>
</html>
""")


def _gain_candidates(requested, auto_reduce):
    # Identical gain for all families; never boost one variant to flatter a result.
    if not auto_reduce:
        return [requested]
    values = [requested]
    while values[-1] > -60:
        values.append(max(-60.0, round(values[-1] - 3.0, 6)))
    return values


def create_gallery(source_a, source_b, output_dir, *, bpm, beats=8,
                   a_start=0.0, b_start=0.0, gain_db=-6.0,
                   reduce_common_gain=False):
    """Create four private WAVs plus a source-bound receipt and offline HTML.

    The complete render is staged before an exclusively created destination
    is populated. A failed family never leaves an apparently complete gallery.
    No existing output is replaced, and no original source is modified.
    """
    a, b, destination = Path(source_a), Path(source_b), Path(output_dir)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new gallery folder")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent directory must already exist")
    if not a.is_file() or not b.is_file():
        raise ValueError("Provide two existing local PCM16 WAV files")
    # Recipe validation happens before any output directory is created.
    parameters = dict(bpm=bpm, beats=beats, a_start=a_start,
                      b_start=b_start, gain_db=gain_db)
    Recipe(family="baseline", **parameters)
    original_hashes = [_sha256(a), _sha256(b)]
    with tempfile.TemporaryDirectory(prefix=".mixlab-private-gallery-", dir=destination.parent) as temp:
        stage = Path(temp)
        selected = None
        rendered = []
        for index, candidate_gain in enumerate(_gain_candidates(gain_db, reduce_common_gain)):
            attempt = stage / f"take-{index}"
            attempt.mkdir(mode=0o700)
            receipts = []
            try:
                for family in FAMILY_NAMES:
                    result = render_transition(a, b, attempt / f"{family}.wav",
                                               Recipe(family=family, bpm=bpm, beats=beats,
                                                      a_start=a_start, b_start=b_start,
                                                      gain_db=candidate_gain))
                    if [item["sha256"] for item in result["sources"]] != original_hashes:
                        raise ValueError("A source changed between gallery candidates")
                    pcm = result["post_pcm_metrics"]
                    receipts.append({
                        "family": family, "audio": f"{family}.wav",
                        "audio_sha256": result["output_sha256"],
                        "seconds": result["duration_seconds"],
                        "pcm_peak": pcm["peak"], "pcm_rms": pcm["rms"],
                        "clipping_samples": pcm["clipping_samples"],
                    })
            except ValueError as exc:
                # Only the renderer's explicit PCM clipping rejection qualifies
                # for an optional common-gain retry. Never mask any other error.
                if reduce_common_gain and "PCM16 clipping rejected" in str(exc) and candidate_gain > -60:
                    shutil.rmtree(attempt)
                    continue
                raise
            selected, rendered, complete = candidate_gain, receipts, attempt
            break
        if selected is None:
            raise ValueError("No clipping-free common gain was found")
        if [_sha256(a), _sha256(b)] != original_hashes:
            raise ValueError("Sources changed before publishing gallery")
        receipt = {
            "schema_version": 1,
            "kind": "mixlab-private-manual-transition-gallery",
            "status": "rendered-not-listener-validated",
            "rights_status": "unverified",
            "source_sha256": {"a": original_hashes[0], "b": original_hashes[1]},
            "bpm": bpm, "beats": beats,
            "cue_seconds": {"a": a_start, "b": b_start},
            "requested_gain_db": gain_db, "shared_gain_db": selected,
            "loudness_matched": False, "tempo_source": "manual",
            "gain_policy": "common-attenuation-only; no limiter or per-family gain",
            "renders": rendered,
        }
        (complete / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
        (complete / "index.html").write_text(_gallery_html(receipt, _sha256(complete / "receipt.json")), encoding="utf-8")
        # Exclusive mkdir + hardlinks: no existing gallery or source can be
        # overwritten, even if another operator creates the destination.
        destination.mkdir(mode=0o700)
        created = []
        try:
            for name in [f"{family}.wav" for family in FAMILY_NAMES] + ["receipt.json", "index.html"]:
                os.link(complete / name, destination / name)
                created.append(name)
        except BaseException:
            for name in created:
                (destination / name).unlink()
            destination.rmdir()
            raise
    return destination / "index.html"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render a private offline comparison of four manual MixLab PCM16 transitions"
    )
    parser.add_argument("source_a", help="Permitted local PCM16 WAV of track A")
    parser.add_argument("source_b", help="Permitted local PCM16 WAV of track B")
    parser.add_argument("output_dir", help="New private destination directory (must not already exist)")
    parser.add_argument("--bpm", type=float, required=True, help="Manually verified common BPM")
    parser.add_argument("--beats", type=int, default=8)
    parser.add_argument("--a-start", type=float, default=0)
    parser.add_argument("--b-start", type=float, default=0)
    parser.add_argument("--gain-db", type=float, default=-6.0,
                        help="Shared gain from -60 to 0 dB (default: -6)")
    parser.add_argument("--reduce-common-gain", action="store_true",
                        help="Opt in to common 3 dB reductions if any family clips")
    args = parser.parse_args(argv)
    try:
        print(create_gallery(args.source_a, args.source_b, args.output_dir,
                             bpm=args.bpm, beats=args.beats,
                             a_start=args.a_start, b_start=args.b_start,
                             gain_db=args.gain_db,
                             reduce_common_gain=args.reduce_common_gain))
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"MixLab private gallery: {exc}\n")


if __name__ == "__main__":
    main()
