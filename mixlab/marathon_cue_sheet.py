"""Render receipt-locked local Marathon rehearsal cues as an offline printable show sheet.

The imported log is an unsigned operator note, not an audio or rights credential.
All source reading remains local. No new mixer/renderer is involved.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import stat

from .event_vault import _marathon_duration, _read_small_json

MAX_CUES = 200
MAX_JSON = 65536
MAX_HTML = 512 * 1024
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.html\Z")


def _clock(seconds):
    n = max(0, int(seconds))
    return f"{n // 3600:02d}:{(n // 60) % 60:02d}:{n % 60:02d}"


def _ordinary_file(path, maximum):
    if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Only ordinary private files without symlink ancestors are permitted")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= maximum:
        raise ValueError("Private cue file exceeds its local size bound")


def _read_cues(path):
    _ordinary_file(path, MAX_JSON)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as input_file:
        initial = os.fstat(input_file.fileno())
        raw = input_file.read(MAX_JSON + 1)
        final = os.fstat(input_file.fileno())
    if initial != final or len(raw) > MAX_JSON:
        raise ValueError("Private cue log changed during bounded admission")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Private cue log is not valid UTF-8 JSON") from exc


def create_cue_sheet(approved_marathon_wav, private_cue_json, new_private_html):
    wav = Path(approved_marathon_wav).absolute()
    cues_path = Path(private_cue_json).absolute()
    output = Path(new_private_html).absolute()
    if wav.name != "marathon.wav":
        raise ValueError("Expected the completed original or blended Marathon master")
    _ordinary_file(wav, 768 * 1024 * 1024 + 44)
    _, count, kind = _marathon_duration(wav.parent, wav)
    if kind not in ("marathon", "marathon_blend") or not 2 <= count <= 8:
        raise ValueError("Not a validated private Marathon")
    receipt = _read_small_json(wav.parent / "marathon.receipt.private.json")
    sections = receipt["sections"]
    expected = [{"label": s["label"], "start_seconds": s["start_seconds"]} for s in sections]
    duration = receipt["frames"] / receipt["rate"]
    payload = _read_cues(cues_path)
    if (not isinstance(payload, dict) or payload.get("kind") != "mixlab-private-marathon-cues-v1" or
            payload.get("schema_version") != 1 or
            payload.get("source_wav_sha256") != receipt["wav_sha256"] or
            payload.get("source_duration_seconds") != duration or
            payload.get("sections") != expected or
            type(payload.get("cues")) is not list or
            len(payload["cues"]) > MAX_CUES):
        raise ValueError("Cue log belongs to a different master or is not a supported export")
    ordered = []
    for i, cue in enumerate(payload["cues"], 1):
        if not isinstance(cue, dict):
            raise ValueError("Invalid cue record")
        idx, when, label, note = (cue.get("event_index"), cue.get("time_seconds"),
                                  cue.get("event_label"), cue.get("note"))
        if (type(idx) is not int or not 0 <= idx < count or
                type(when) not in (int, float) or not 0 <= when <= duration or
                label != sections[idx]["label"] or
                type(note) is not str or len(note) > 300 or
                when + 0.05 < sections[idx]["start_seconds"] or
                (idx + 1 < count and when > sections[idx + 1]["start_seconds"] + 0.05)):
            raise ValueError("Private cue has an invalid time, section binding or note")
        ordered.append((float(when), i, idx, note))
    ordered.sort()
    if (output.suffix.lower() != ".html" or not NAME.fullmatch(output.name) or
            output == wav or output == cues_path or output.exists() or output.is_symlink() or
            not output.parent.is_dir() or
            any(p.is_symlink() or (p / ".git").exists() for p in (output.parent, *output.parents))):
        raise ValueError("Choose a new private HTML path outside any Git checkout")
    rows = []
    for ix, section in enumerate(sections):
        begin = section["start_seconds"]
        until = sections[ix + 1]["start_seconds"] if ix + 1 < count else duration
        crossfade = section.get("fade_in_seconds", 0)
        rows.append(f'<article class="row"><div class="stamp">{_clock(begin)}</div>'
                    f'<div><b>Event {ix + 1}: {escape(section["label"])}</b>'
                    f'<small>Remaining block {_clock(max(0, until - begin))}'
                    + (f' · {int(crossfade)}s rendered handoff' if crossfade else ' · original hard handoff')
                    + '</small></div></article>')
        for when, number, cue_idx, note in ordered:
            if cue_idx == ix:
                rows.append(f'<article class="row note"><div class="stamp">{_clock(when)}</div>'
                            f'<div><b>Cue {number}</b><p>{escape(note) if note else "Manual marker"}</p>'
                            f'<small>Offset from event start {_clock(max(0, when - begin))}</small></div></article>')
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>MixLab · Private Marathon Cue Sheet</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{background:#09141e;color:#eff9ff;font:16px/1.5 system-ui,sans-serif;margin:0}}
main{{max-width:960px;margin:auto;padding:40px 24px}}
h1{{font-size:clamp(32px,6vw,64px);line-height:1.08;letter-spacing:-.045em}}
p,small{{color:#bfd2dd}}small{{display:block;margin-top:5px;font-size:12px}}
.lead{{padding:20px;border:1px solid #547787;border-radius:14px;margin:20px 0}}
.row{{display:grid;grid-template-columns:115px 1fr;gap:18px;border-bottom:1px solid #526b7b;padding:17px 10px}}
.stamp{{font-variant-numeric:tabular-nums;color:#9cfcce;font-weight:850}}
.note{{padding-left:25px;background:#1b3340;white-space:pre-wrap;overflow-wrap:anywhere}}
.note p{{margin:6px 0 0;color:#f6fcff}}
.hash{{font:12px ui-monospace,monospace;overflow-wrap:anywhere}}
@media print{{:root{{color-scheme:light}}body{{background:#fff;color:#000;font-size:12px}}
main{{padding:6mm}}p,small,.stamp{{color:#222}}.note{{background:#eee}}.note p{{color:#000}}
.row{{border-color:#bbb;break-inside:avoid}}.lead{{border-color:#999}}}}
</style></head><body><main><div>MIXLAB / PRIVATE OFFLINE OPERATOR SHEET</div>
<h1>Marathon stage cues.</h1><p>Real rendered audio positions, derived from the approved master.
Manual annotations are not embedded in the WAV. No upload or source tracks in this document.</p>
<div class="lead"><b>{count} completed events · {_clock(duration)} · {len(ordered)} hand-entered cues</b>
<p>Use the original verified WAV as playback master. This is an offline paper companion, not a live DJ engine,
a rights certificate or evidence that transitions have been auditioned.</p></div>
{"".join(rows)}
<footer><p>Each note is tied to the exact source SHA; an untrusted log is not externally authenticated.
Changes to the original master require a new cue export.</p>
<p class="hash">MASTER SHA-256: {receipt["wav_sha256"]}</p></footer>
</main></body></html>"""
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_HTML:
        raise ValueError("Cue sheet exceeds bounded private HTML limit")
    with output.open("xb") as writer:
        try:
            os.fchmod(writer.fileno(), 0o600)
            writer.write(encoded)
        except Exception:
            output.unlink(missing_ok=True)
            raise
    return {"private_cue_sheet": str(output), "source_wav_sha256": receipt["wav_sha256"],
            "events": count, "manual_cues": len(ordered), "offline": True,
            "rights_proven": False}


def main():
    parser = argparse.ArgumentParser(description="Turn a private Marathon Stage cue export into a printable receipt-verified HTML run sheet")
    parser.add_argument("marathon_wav", help="Original receipt-verified marathon.wav")
    parser.add_argument("cues_json", help="Locally exported SHA-locked cue JSON")
    parser.add_argument("new_html", help="New private offline printable .html")
    args = parser.parse_args()
    try:
        result = create_cue_sheet(args.marathon_wav, args.cues_json, args.new_html)
    except (ValueError, TypeError, KeyError, OSError):
        parser.exit(2, "MixLab cue sheet: source receipt, local cue log or destination admission failed.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
