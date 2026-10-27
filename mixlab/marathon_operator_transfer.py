"""Explicit small, private USB transfer for human hybrid-master cues only.

No full audio, original recordings, source paths or public notes are exported.
The destination's own SHA-receipt-verified real WAV is a mandatory dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import wave
import zipfile

from .event_vault import _marathon_duration, _read_small_json
from .marathon_reel_decisions import KIND, _brief_html, _write_private
from .marathon_hybrid_stage import create_stage
from .marathon_reels_transfer import _read_regular

ZIP_NAME = "master-operator-notes.private.zip"
PICKS_NAME = "master-picks.private.json"
MANIFEST = "master-operator-notes.manifest.json"
MAX_NOTES = 65536
MAX_ARCHIVE = 128 * 1024
PACK_KIND = "mixlab-private-hybrid-operator-cues-usb-v1"


def _no_links(path):
    item = Path(path).absolute()
    if any(part.is_symlink() or (part / ".git").exists()
           for part in (item, *item.parents)):
        raise ValueError("Private music handoff cannot use symlinks or Git folders")
    return item


def _validate(master_wav, note_data):
    """Bind every human decision to the actual final locally verified WAV."""
    wav = _no_links(master_wav)
    if wav.name != "marathon.wav" or not wav.is_file():
        raise ValueError("An existing real private Marathon WAV is required")
    _, count, kind = _marathon_duration(wav.parent, wav)
    receipt = _read_small_json(wav.parent / "marathon.receipt.private.json")
    if (kind != "marathon_blend" or not isinstance(note_data, dict) or
            note_data.get("kind") != KIND or note_data.get("schema_version") != 1 or
            note_data.get("private_only") is not True or
            note_data.get("blind_study") is not False or
            note_data.get("music_rights_proven") is not False or
            note_data.get("source_original_sha256") != receipt.get("source_marathon_sha256") or
            note_data.get("rendered_hybrid_sha256") != receipt.get("wav_sha256") or
            note_data.get("actual_fade_seconds_by_join") != receipt.get("fade_seconds_by_join") or
            not isinstance(note_data.get("source_blend_sha256"), str) or
            re.fullmatch(r"[0-9a-f]{64}", note_data["source_blend_sha256"]) is None):
        raise ValueError("Private operator handoff does not belong to this real rendered hybrid master")
    rows = note_data.get("joins")
    if not isinstance(rows, list) or len(rows) != count - 1:
        raise ValueError("Private cue list differs from rendered source events")
    for idx, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or set(row) != {
                "index", "from", "to", "fade_seconds", "choice", "note"} or
                type(row["index"]) is not int or row["index"] != idx or
                row["from"] != receipt["sections"][idx-1]["label"] or
                row["to"] != receipt["sections"][idx]["label"] or
                row["choice"] not in ("original", "blend") or
                type(row["fade_seconds"]) is not int or
                row["fade_seconds"] not in (0,2,4,8,16) or
                (row["fade_seconds"] if row["choice"] == "blend" else 0) !=
                    receipt["fade_seconds_by_join"][idx-1] or
                not isinstance(row["note"], str) or len(row["note"]) > 300 or
                any(ord(c)<32 and c not in "\n\t" for c in row["note"])):
            raise ValueError("Human cue text or original-versus-rendered fade choice invalid")
    return receipt


def pack(master_wav, new_zip, *, read=input, write=print):
    master = _no_links(master_wav)
    archive_path = _no_links(new_zip)
    notes = master.parent / PICKS_NAME
    if (archive_path.parent != master.parent or archive_path.name != ZIP_NAME or
            archive_path.exists() or archive_path.is_symlink()):
        raise ValueError("New private cue ZIP must be beside the original verified hybrid")
    raw = _read_regular(notes, MAX_NOTES)
    doc = json.loads(raw.decode("utf-8"))
    receipt = _validate(master, doc)
    manifest = {
        "schema_version": 1, "kind": PACK_KIND, "private_only": True,
        "includes_music": False, "includes_operator_notes": True,
        "authenticated_sender": False, "music_rights_proven": False,
        "actual_master_sha256": receipt["wav_sha256"],
        "source_original_sha256": receipt["source_marathon_sha256"],
        "file": PICKS_NAME, "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest()
    }
    write("MixLab: EXPORT PRIVATE human DJ decisions/notes, WITHOUT music bytes.")
    write("Bound to real master SHA-256: "+receipt["wav_sha256"])
    write("The USB archive is unsigned; it does not certify sender identity or music permissions.")
    if read("Type yes to place PRIVATE personal cue notes into a new USB ZIP: ").strip() != "yes":
        raise ValueError("Private note release was not approved")
    complete = False
    try:
        with archive_path.open("xb") as out:
            os.fchmod(out.fileno(), 0o600)
            with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED) as archive:
                for name,payload in (
                    (PICKS_NAME,raw),
                    (MANIFEST,(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode("utf-8"))
                ):
                    entry=zipfile.ZipInfo(name)
                    entry.compress_type=zipfile.ZIP_STORED
                    entry.external_attr=(stat.S_IFREG|0o600)<<16
                    archive.writestr(entry,payload)
        if archive_path.stat().st_size > MAX_ARCHIVE:
            raise ValueError("Private operator notes ZIP is larger than allowed")
        complete=True
    finally:
        if not complete:
            archive_path.unlink(missing_ok=True)
    return {"private_operator_notes_zip":str(archive_path),"actual_master_sha256":receipt["wav_sha256"],
            "music_included":False,"personal_notes_included":True,
            "archive_authenticated":False,"music_rights_proven":False}


def restore(private_zip, existing_actual_master_wav, *, read=input, write=print):
    zip_path = _no_links(private_zip)
    wav = _no_links(existing_actual_master_wav)
    output = wav.parent / PICKS_NAME
    printable = wav.parent / "master-picks.private.html"
    stage = wav.parent / "master-picks.stage.html"
    if (zip_path.suffix.lower() != ".zip" or
            any(path.exists() or path.is_symlink() for path in (output,printable,stage))):
        raise ValueError("Restore only to a verified private master lacking all three operator files")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
    fd=os.open(zip_path,flags)
    with os.fdopen(fd,"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=MAX_ARCHIVE:
            raise ValueError("Private cue ZIP is missing or outside the bounded size")
        with zipfile.ZipFile(stream,"r") as archive:
            info=archive.infolist()
            if (len(info)!=2 or {item.filename for item in info}!={PICKS_NAME,MANIFEST}
                    or len({item.filename for item in info})!=2):
                raise ValueError("Only the official flat private cue inventory is supported")
            for item in info:
                mode=stat.S_IFMT(item.external_attr>>16)
                if (item.is_dir() or item.compress_type!=zipfile.ZIP_STORED or
                        mode not in (0,stat.S_IFREG) or item.file_size!=item.compress_size or
                        item.file_size<=0 or item.file_size>MAX_NOTES):
                    raise ValueError("Private cue ZIP entry is not bounded regular stored data")
            manifest=json.loads(archive.read(MANIFEST).decode("utf-8"))
            payload=archive.read(PICKS_NAME)
        after=os.fstat(stream.fileno())
        fingerprint=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if fingerprint(before)!=fingerprint(after):
            raise ValueError("Private ZIP changed during restoration")
    if (not isinstance(manifest,dict) or manifest.get("schema_version")!=1 or
            manifest.get("kind")!=PACK_KIND or manifest.get("private_only") is not True or
            manifest.get("includes_music") is not False or
            manifest.get("includes_operator_notes") is not True or
            manifest.get("authenticated_sender") is not False or
            manifest.get("music_rights_proven") is not False or
            manifest.get("file")!=PICKS_NAME or
            manifest.get("size_bytes")!=len(payload) or
            manifest.get("sha256")!=hashlib.sha256(payload).hexdigest()):
        raise ValueError("Unsigned operator archive metadata does not match its private notes")
    doc=json.loads(payload.decode("utf-8"))
    receipt=_validate(wav,doc)
    if (manifest.get("actual_master_sha256")!=receipt["wav_sha256"] or
            manifest.get("source_original_sha256")!=receipt["source_marathon_sha256"]):
        raise ValueError("USB notes belong to a DIFFERENT actual restored hybrid WAV")
    write("MixLab: restoring human PRIVATE notes beside SHA-verified existing real Marathon WAV.")
    write("The notes are operator-only; they do not authenticate music rights or a sender.")
    if read("Type yes to restore PRIVATE operator notes beside this master: ").strip() != "yes":
        raise ValueError("Private note restore was not approved")
    written=[]
    try:
        written.append(output)
        _write_private(output,payload)
        written.append(printable)
        _write_private(printable,_brief_html(
            {"wav_sha256":doc["source_original_sha256"]},
            {"wav_sha256":doc["source_blend_sha256"]},
            doc["joins"],receipt["wav_sha256"]))
        written.append(stage)
        create_stage(wav,output,stage)
    except Exception:
        for item in reversed(written):item.unlink(missing_ok=True)
        raise
    return {"private_operator_notes":str(output),"private_printable_cue_sheet":str(printable),
            "private_live_stage":str(stage),"verified_actual_master_sha256":receipt["wav_sha256"],
            "music_included_in_zip":False,"external_sender_authenticated":False}


def main():
    parser=argparse.ArgumentParser(description="Explicit offline transfer of PRIVATE DJ notes to/from an existing verified real hybrid master")
    sub=parser.add_subparsers(dest="command",required=True)
    export=sub.add_parser("pack",help="Create small new private notes-only ZIP, with separate typed approval")
    export.add_argument("existing_hybrid_marathon_wav")
    export.add_argument("new_private_operator_notes_zip")
    incoming=sub.add_parser("restore",help="Restore notes to an existing locally verified full WAV, with explicit approval")
    incoming.add_argument("private_operator_notes_zip")
    incoming.add_argument("existing_hybrid_marathon_wav")
    args=parser.parse_args()
    try:
        result=(pack(args.existing_hybrid_marathon_wav,args.new_private_operator_notes_zip)
                if args.command=="pack" else
                restore(args.private_operator_notes_zip,args.existing_hybrid_marathon_wav))
    except (ValueError,TypeError,KeyError,OSError,UnicodeError,EOFError,
            KeyboardInterrupt,wave.Error,zipfile.BadZipFile):
        parser.exit(2,"MixLab private operator transfer: exact real WAV, notes, consent or safe destination invalid.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
