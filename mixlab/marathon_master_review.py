"""Human-selected, real-WAV master review and private delivery for two Marathons.

Original + blended are separately verified complete outputs with one shared
provenance; the browser never uploads audio or purports to certify preference.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import wave
import zipfile

from .event_vault import _marathon_duration, _read_small_json
from .marathon_sequence import _private_html_destination, _read_plan

KIND = "mixlab-private-marathon-master-review-v1"
MAX_HTML = 512 * 1024
MAX_NOTE = 300

_PAGE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; media-src blob:; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>MixLab · Marathon Master Review</title>
<style>
:root{color-scheme:dark;--bg:#0b1523;--panel:#182b3c;--green:#b4ffdb;--muted:#b4cadc;--line:#456173}
*{box-sizing:border-box}body{background:radial-gradient(at 80% 0%,#244a4d,var(--bg) 60%);margin:0;color:#f4fbff;font:15px/1.5 system-ui,sans-serif}
main{max-width:1130px;margin:auto;padding:clamp(18px,4vw,65px)}
.eyebrow{font-size:12px;letter-spacing:.17em;font-weight:900;color:var(--green)}
h1{font-size:clamp(37px,6vw,73px);letter-spacing:-.06em;line-height:1.04;margin:10px 0}
h2{margin:0 0 14px;font-size:21px}h3{font-size:17px;margin:0 0 7px}
p,small{color:var(--muted)}.card{padding:clamp(17px,3vw,27px);border:1px solid var(--line);border-radius:20px;background:var(--panel);margin:20px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(275px,1fr));gap:17px}
.audio-card{background:#0d2030;border:1px solid #395d6b;border-radius:16px;padding:17px;min-width:0}
.audio-card strong{color:var(--green)}.audio-card audio{width:100%;margin:12px 0}
button{background:#285466;color:white;border:1px solid #76a3a9;border-radius:10px;font:inherit;font-weight:800;padding:11px 14px;cursor:pointer}
button:hover{background:#396e7c}button:disabled{opacity:.45;cursor:not-allowed}
input,textarea{font:inherit;color:white;background:#0b2230;border:1px solid #73929f;border-radius:8px;padding:9px}
input[type=file]{max-width:100%}.selection{display:flex;gap:20px;flex-wrap:wrap;margin:14px 0}
.selection label{cursor:pointer;padding:13px;background:#123740;border-radius:11px;flex:1;min-width:210px}
input:focus-visible,button:focus-visible,textarea:focus-visible{outline:3px solid var(--green);outline-offset:2px}
input[type=radio]{accent-color:var(--green);margin-right:10px}
ul{list-style:none;padding:0;margin:0;display:grid;gap:11px}
li{border:1px solid var(--line);border-radius:13px;padding:16px;background:#11283a}
li .split{display:flex;gap:9px;flex-wrap:wrap;align-items:center;justify-content:space-between}
li .split strong{flex:1;min-width:190px}
li textarea{width:100%;min-height:70px;resize:vertical;margin-top:9px}
.controls{display:flex;gap:11px;flex-wrap:wrap}
.stat{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}.stat span{padding:9px 12px;border:1px solid var(--line);border-radius:11px}
.fingerprint{font-size:11px;word-break:break-all;font-family:ui-monospace,monospace;color:var(--muted)}
.notice{border-left:4px solid var(--green);padding:10px 15px;background:#12343a;color:#eafff0}
code{word-break:break-word} @media(max-width:620px){.grid{grid-template-columns:1fr}}
</style></head><body><main><div class="eyebrow">MIXLAB / PRIVATE DJ MASTER DECISION</div>
<h1>Which version<br>sounds right?</h1>
<p>Listen to the <em>actual separately rendered</em> original and blended WAVs, not browser-generated fades.
Jump to the real event boundaries, make a human decision, and export a source-bound private delivery choice.
This is a personal mastering decision, <strong>not</strong> a blind listening study or statistically proven preference.</p>
<div class="stat"><span id="event-count"></span><span id="original-runtime"></span><span id="blend-runtime"></span></div>
<section class="card"><h2>1 / Attach your already-rendered local WAV masters</h2>
<div class="grid"><div class="audio-card"><h3>Original · sample preserving</h3>
<strong id="original-sha"></strong><p><label>Choose exact private original marathon.wav
<input id="file-original" type="file" accept=".wav,audio/wav"></label></p>
<audio id="audio-original" controls preload="none"></audio><small id="label-original">No local audio selected.</small></div>
<div class="audio-card"><h3>Blend · real PCM16 transitions</h3>
<strong id="blend-sha"></strong><p><label>Choose exact private blended marathon.wav
<input id="file-blend" type="file" accept=".wav,audio/wav"></label></p>
<audio id="audio-blend" controls preload="none"></audio><small id="label-blend">No local audio selected.</small></div></div>
<p>The browser checks expected basename, byte size and decoded length, <strong>not cryptographic SHA</strong>.
The delivery command separately hashes each real WAV against its official private receipt.
Pick source files only from the original folders passed to the preparation command.</p></section>
<section class="card"><h2>2 / Listen to the actual joins</h2>
<p>Each button seeks near the corresponding event boundary <strong>in that version's own verified output timeline</strong>.
Only one deck plays at a time. Browser seeking is approximate; use a local music app for critical listening.</p>
<ul id="joins"></ul><div class="controls"><button type="button" id="stop">Stop playback</button></div></section>
<section class="card"><h2>3 / Choose one final private master</h2>
<div class="selection"><label><input type="radio" name="choice" value="original" checked>
Original hard joins</label><label><input type="radio" name="choice" value="blend">
Real manual crossfade version</label></div>
<label for="reason">Your choice / note (optional, kept in private JSON)</label>
<textarea id="reason" maxlength="300" style="display:block;width:100%;min-height:80px;margin:10px 0" placeholder="Why this version works for my venue…"></textarea>
<div class="controls"><button type="button" id="export">Export binding master choice</button></div>
<p class="notice" id="status" role="status">No audio data is exported; your private decision needs explicit confirmation at the separate command-line delivery step.</p>
<p>Next: <code>python3 -m mixlab.marathon_master_review publish CHOICE.json ORIGINAL/marathon.wav BLEND/marathon.wav --bundle --delivery mp3</code>.
The command verifies the original and blended SHA/provenance again, asks you to type <code>yes</code>,
then packages or encodes <strong>only the selected</strong> original or blended master. Existing separate masters are not overwritten.</p></section>
<p class="fingerprint" id="hash"></p>
</main><script id="master-data" type="application/json">__DATA__</script><script>
"use strict";
const data=JSON.parse(document.getElementById("master-data").textContent);
const $=name=>document.getElementById(name);
const media={original:$("audio-original"),blend:$("audio-blend")},urls={};
const secs=number=>{
 const t=Math.max(0,Math.floor(number));
 return [Math.floor(t/3600),Math.floor(t%3600/60),t%60].map(x=>String(x).padStart(2,"0")).join(":");
};
$("event-count").textContent=data.joins.length+" events · "+(data.joins.length-1)+" real joins";
$("original-runtime").textContent="Original "+secs(data.original.duration);
$("blend-runtime").textContent="Blend "+secs(data.blend.duration);
$("original-sha").textContent="SHA-256 "+data.original.sha256.slice(0,16)+"…";
$("blend-sha").textContent="SHA-256 "+data.blend.sha256.slice(0,16)+"…";
$("hash").textContent="Local original SHA "+data.original.sha256+
 " / local blended SHA "+data.blend.sha256;
let notes=new Array(data.joins.length-1).fill("");
const stop=()=>{Object.values(media).forEach(player=>player.pause());};
$("stop").addEventListener("click",stop);
window.addEventListener("pagehide",()=>{
 stop();Object.entries(urls).forEach(([key,url])=>URL.revokeObjectURL(url));
});
for(const which of ["original","blend"]){
 $("file-"+which).addEventListener("change",()=>{
  stop();
  if(urls[which]){URL.revokeObjectURL(urls[which]);delete urls[which];}
  media[which].removeAttribute("src");media[which].load();
  const file=$("file-"+which).files[0];
  if(!file)return;
  const expected=data[which];
  if(file.name!=="marathon.wav"||file.size!==expected.size){
   $("label-"+which).textContent="Rejected: original WAV basename/byte length mismatch.";
   return;
  }
  urls[which]=URL.createObjectURL(file);media[which].src=urls[which];
  media[which].onloadedmetadata=()=>{
   if(!Number.isFinite(media[which].duration)||
      Math.abs(media[which].duration-expected.duration)>0.3){
    $("label-"+which).textContent="Rejected: decoded WAV duration mismatch.";
    media[which].pause();URL.revokeObjectURL(urls[which]);
    delete urls[which];media[which].removeAttribute("src");media[which].load();
   } else $("label-"+which).textContent="Local file attached for listening. SHA is NOT browser verified.";
  };
  media[which].onerror=()=>{
   $("label-"+which).textContent="Browser cannot decode local WAV; use an offline media app.";
  };
  media[which].load();
 });
}
async function play(which,boundary){
 const player=media[which];
 if(!urls[which]||!Number.isFinite(player.duration)){
  $("status").textContent="Attach the actual "+which+" WAV above before listening.";
  return;
 }
 stop();player.currentTime=Math.max(0,Math.min(player.duration-1,boundary-10));
 try{await player.play();$("status").textContent="Playing the actual "+which+
  " WAV 10s before the receipt-bound event handoff; browser seek accuracy varies.";}
 catch(_){$("status").textContent="Browser blocked local WAV playback. Use your audio player.";}
}
data.joins.slice(1).forEach((join,i)=>{
 const row=document.createElement("li");
 const header=document.createElement("div");header.className="split";
 const label=document.createElement("strong");label.textContent=(i+1)+". "+
   data.joins[i].label+" → "+join.label;
 header.append(label);
 for(const which of ["original","blend"]){
  const button=document.createElement("button");button.type="button";
  button.textContent="Play "+which+" near join";
  button.addEventListener("click",()=>play(which,join[which]));
  header.append(button);
 }
 const hint=document.createElement("small");hint.textContent=
  "Original boundary "+secs(join.original)+" · blended boundary "+secs(join.blend)+
  " · manual "+join.fade_seconds+"s fade";
 const note=document.createElement("textarea");note.maxLength=300;
 note.setAttribute("aria-label","Private review note for join "+(i+1));
 note.placeholder="Handoff note, volume, energy, style…";
 note.addEventListener("input",()=>{notes[i]=note.value;});
 row.append(header,hint,note);$("joins").append(row);
});
$("export").addEventListener("click",()=>{
 const selected=document.querySelector('input[name="choice"]:checked').value;
 const decision={schema_version:1,kind:data.kind,original_sha256:data.original.sha256,
  blend_sha256:data.blend.sha256,selected_master:selected,
  operator_reason:$("reason").value.trim(),join_notes:notes,private_only:true};
 const blob=new Blob([JSON.stringify(decision,null,2)+"\n"],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");
 a.download="mixlab-marathon-master-choice.private.json";a.href=url;
 document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 $("status").textContent="Exported a private source-bound selection; no audio was copied, published, or uploaded.";
});
</script></body></html>"""


def _pair(original_wav, blend_wav):
    original, blend = Path(original_wav).absolute(), Path(blend_wav).absolute()
    for wav in (original, blend):
        if (wav.name != "marathon.wav" or wav.is_symlink() or
                any(part.is_symlink() for part in wav.parents) or not wav.is_file()):
            raise ValueError("Use original local non-symlinked completed Marathon WAVs")
    if original.parent == blend.parent:
        raise ValueError("The original and blended complete WAV must be separate master outputs")
    duration0, count0, kind0 = _marathon_duration(original.parent, original)
    duration1, count1, kind1 = _marathon_duration(blend.parent, blend)
    if kind0 != "marathon" or kind1 != "marathon_blend" or count0 != count1:
        raise ValueError("Choose the exact original Marathon and its actually rendered blended derivative")
    r0 = _read_small_json(original.parent / "marathon.receipt.private.json")
    r1 = _read_small_json(blend.parent / "marathon.receipt.private.json")
    if (r1.get("source_marathon_sha256") != r0["wav_sha256"] or
            r0["rate"] != r1["rate"] or
            [(x["source_sha256"], x["frames"], x["label"]) for x in r0["sections"]] !=
            [(x["source_sha256"], x["frames"], x["label"]) for x in r1["sections"]]):
        raise ValueError("Manually blended WAV was not rendered from these exact original events")
    fades = r1.get("fade_seconds_by_join")
    if fades is None:
        fades = [r1["fade_seconds"]] * (count0 - 1)
    return (original, blend), (r0, r1), fades, (duration0, duration1)


def create_review(original_wav, blend_wav, new_private_html):
    (original, blend), (r0, r1), fades, (duration0, duration1) = _pair(original_wav, blend_wav)
    output = _private_html_destination(new_private_html)
    row = lambda wav, r, dur: {"sha256": r["wav_sha256"], "size": wav.lstat().st_size, "duration": dur}
    data = {"kind": KIND, "original": row(original, r0, duration0),
            "blend": row(blend, r1, duration1),
            "joins": [{"label": sec["label"], "original": sec["start_frame"] / r0["rate"],
                       "blend": r1["sections"][i]["start_frame"] / r1["rate"],
                       "fade_seconds": fades[i-1] if i else 0}
                      for i, sec in enumerate(r0["sections"])]}
    contents = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    contents = contents.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    payload = _PAGE.replace("__DATA__", contents).encode("utf-8")
    if len(payload) > MAX_HTML:
        raise ValueError("Private actual-master review page too large")
    with output.open("xb") as handle:
        try:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    return {"private_master_review_html": str(output), "original_wav_sha256": r0["wav_sha256"],
            "blended_wav_sha256": r1["wav_sha256"],
            "real_completed_outputs_compared": True, "browser_quality_proven": False,
            "media_embedded": False, "private": True}


def publish_choice(choice_json, original_wav, blend_wav, *,
                   bundle=False, delivery=None, bitrate_kbps=192, read=input, write=print):
    if type(bundle) is not bool or delivery not in (None, "mp3", "flac") or (
            type(bitrate_kbps) is not int or bitrate_kbps not in (128, 192, 256, 320)):
        raise ValueError("Unsupported private handoff format")
    if not bundle and delivery is None:
        raise ValueError("Select --bundle and/or --delivery for an actual private output")
    (original, blend), (r0, r1), fades, (duration0, duration1) = _pair(original_wav, blend_wav)
    choice = _read_plan(choice_json)
    if (type(choice) is not dict or choice.get("schema_version") != 1 or
            choice.get("kind") != KIND or choice.get("private_only") is not True or
            choice.get("original_sha256") != r0["wav_sha256"] or
            choice.get("blend_sha256") != r1["wav_sha256"] or
            choice.get("selected_master") not in ("original", "blend")):
        raise ValueError("Private selected-master plan is not bound to both real WAV receipts")
    notes = choice.get("join_notes")
    reason = choice.get("operator_reason")
    if (type(reason) is not str or len(reason) > MAX_NOTE or
            type(notes) is not list or len(notes) != len(fades) or
            any(type(note) is not str or len(note) > MAX_NOTE for note in notes)):
        raise ValueError("Private handwritten decision exceeds its bounded local note limits")
    selected = original if choice["selected_master"] == "original" else blend
    write("MixLab PRIVATE master selection: " + choice["selected_master"])
    write("Actual receipt-verified WAV SHA-256: " +
          (r0 if selected == original else r1)["wav_sha256"])
    write("This is a personal non-blind human decision, NOT evidence of blind preference or public music rights.")
    write("Only the selected master receives new output. The two original PCM16 WAVs are retained.")
    if read("Type yes to package/encode ONLY this exact selected master: ").strip() != "yes":
        raise ValueError("Human approval for this exact private master delivery is required")
    # One post-confirmation admission prevents packaging an accidental changed source
    # after the user reviewed the printed SHA. The downstream producer revalidates too.
    _pair(original, blend)
    result = {"chosen_master": choice["selected_master"], "selected_wav": str(selected),
              "selected_sha256": (r0 if selected == original else r1)["wav_sha256"],
              "private": True, "rights_proven": False, "blind_preference_proven": False}
    if delivery:
        from .marathon_delivery import export_mobile_marathon
        try:
            result["portable_audio"] = export_mobile_marathon(
                selected, selected.parent / ("marathon." + delivery), bitrate_kbps=bitrate_kbps)
        except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
            result["portable_warning"] = "Chosen WAV retained; optional portable audio unavailable."
    if bundle:
        from .marathon_bundle import export_marathon_bundle
        try:
            result["private_usb"] = export_marathon_bundle(
                selected, selected.parent / "marathon.selected.private.zip")
        except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile):
            result["bundle_warning"] = "Chosen WAV retained; optional private USB archive unavailable."
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Review two actual private MixLab Marathon WAVs offline, choose one and hand it off safely")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("prepare", help="Create a local actual-master listening and decision board")
    review.add_argument("original_marathon_wav")
    review.add_argument("blended_marathon_wav")
    review.add_argument("new_private_html")
    deliver = sub.add_parser("publish", help="Publish only the receipt-bound human-selected actual master")
    deliver.add_argument("private_choice_json")
    deliver.add_argument("original_marathon_wav")
    deliver.add_argument("blended_marathon_wav")
    deliver.add_argument("--delivery", choices=("mp3", "flac"))
    deliver.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320), default=192)
    deliver.add_argument("--bundle", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = create_review(args.original_marathon_wav, args.blended_marathon_wav,
                                   args.new_private_html)
        else:
            result = publish_choice(args.private_choice_json, args.original_marathon_wav,
                                    args.blended_marathon_wav, bundle=args.bundle,
                                    delivery=args.delivery, bitrate_kbps=args.bitrate_kbps)
    except (ValueError, TypeError, KeyError, OSError, EOFError, KeyboardInterrupt,
            wave.Error, zipfile.BadZipFile, subprocess.SubprocessError):
        parser.exit(2, "MixLab Master Review: private actual WAV, receipt, choice or approved output unavailable.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
