"""Restore a consented private complete-show ZIP without trusting archived HTML.

Streaming stored ZIP with strict flat inventory and SHA-256; regenerate and
compare executable offline pages to code templates. No license is inferred.
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
import zipfile

from .event_marathon import _new_folder
from .show_delivery import (
    BUNDLE_KIND, ENCODE_KIND, MAX_ZIP_BYTES, MAX_ENCODE, BLOCK,
    _source, _safe_delivery_companions, _player_page, _sha
)

MANIFEST = "show.bundle.private.json"
ORIGINAL = {"show.wav", "show.receipt.private.json", "index.html"}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _archive(path):
    source=Path(path).absolute()
    if source.suffix.lower()!=".zip":
        raise ValueError("Choose an official existing private Show .zip")
    for node in (source, *source.parents):
        if node.is_symlink() or (node / ".git").exists():
            raise ValueError("Private Show ZIP cannot be symlinked or live under Git")
    return source


def _manifest_and_members(bundle):
    entries=bundle.infolist()
    indexed={x.filename:x for x in entries}
    if (len(entries)!=len(indexed) or MANIFEST not in indexed or
            len(entries) not in (4,7)):
        raise ValueError("Show ZIP inventory must be a flat official 4/7 member package")
    index=indexed[MANIFEST]
    if not 0<index.file_size<=65536 or index.compress_type!=zipfile.ZIP_STORED:
        raise ValueError("Private Show ZIP manifest exceeds source bounds")
    doc=json.loads(bundle.read(index).decode("utf-8"))
    if (not isinstance(doc,dict) or set(doc)!={"schema_version","kind",
            "source_wav_sha256","private_only","music_rights_proven",
            "operator_notes_included","original_source_songs_included",
            "portable_encoded_included","unsigned_manifest","files"} or
            type(doc["schema_version"]) is not int or doc["schema_version"]!=1 or
            doc["kind"]!=BUNDLE_KIND or doc["private_only"] is not True or
            doc["music_rights_proven"] is not False or
            doc["operator_notes_included"] is not False or
            doc["original_source_songs_included"] is not False or
            doc["unsigned_manifest"] is not True or
            type(doc["portable_encoded_included"]) is not bool or
            not isinstance(doc["source_wav_sha256"],str) or
            not SHA.fullmatch(doc["source_wav_sha256"])):
        raise ValueError("Private archive does not match official unsigned Show bundle schema")
    if not isinstance(doc["files"],list):
        raise ValueError("Private ZIP manifest does not contain finite real member metadata")
    other=[name for name in indexed if name not in ORIGINAL|{MANIFEST}]
    if doc["portable_encoded_included"]:
        codecs=[c for c in ("mp3","flac") if "show."+c in other]
        if len(codecs)!=1:
            raise ValueError("Private ZIP must contain exactly one approved encoded audio codec")
        c=codecs[0]
        expected=ORIGINAL|{MANIFEST,"show."+c,"show."+c+".receipt.private.json",
                          "show."+c+".player.html"}
    else:
        expected=ORIGINAL|{MANIFEST}
    if set(indexed)!=expected or len(doc["files"])!=len(expected)-1:
        raise ValueError("Unexpected ZIP path, private cue file or missing official member")
    records={}
    for row in doc["files"]:
        if (not isinstance(row,dict) or set(row)!={"file","bytes","sha256"} or
                not isinstance(row["file"],str) or row["file"] in records or
                row["file"] not in expected-{MANIFEST} or
                type(row["bytes"]) is not int or row["bytes"]<1 or
                not isinstance(row["sha256"],str) or not SHA.fullmatch(row["sha256"])):
            raise ValueError("Private ZIP manifest lists a malformed media member")
        records[row["file"]]=row
    if set(records)!=expected-{MANIFEST} or records["show.wav"]["sha256"]!=doc["source_wav_sha256"]:
        raise ValueError("Original approved Show WAV identity was replaced inside ZIP")
    total=0
    for name,item in indexed.items():
        limit=(65536 if name==MANIFEST else
               768*1024*1024 if name=="show.wav" else
               MAX_ENCODE if name in ("show.mp3","show.flac") else
               65536 if name.endswith(".json") else
               512*1024)
        if item.file_size>limit:
            raise ValueError("An official media/receipt/player member exceeds its own bound")
        kind=stat.S_IFMT(item.external_attr>>16)
        if (name.startswith("/") or "/" in name or "\\" in name or ".." in name or
                item.is_dir() or item.flag_bits&1 or
                kind not in (0,stat.S_IFREG) or
                item.compress_type!=zipfile.ZIP_STORED or
                item.file_size!=item.compress_size or item.file_size<1):
            raise ValueError("Show package includes a non-flat, compressed or unsafe file")
        if name!=MANIFEST and item.file_size!=records[name]["bytes"]:
            raise ValueError("ZIP file byte count differs from bounded private manifest")
        total+=item.file_size
    if total>MAX_ZIP_BYTES:
        raise ValueError("Full private Show package exceeds bounded local disk budget")
    return doc,indexed,records


def restore_show(private_zip,new_private_folder,*,read=input,write=print):
    archive=_archive(private_zip)
    target=_new_folder(new_private_folder,[])
    fd=os.open(archive,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=MAX_ZIP_BYTES+65536:
            raise ValueError("Original private Show ZIP unavailable or exceeds disk budget")
        with zipfile.ZipFile(stream,"r") as bundle:
            manifest,entries,records=_manifest_and_members(bundle)
            write("MixLab: restore a PRIVATE, unsigned original show WAV bundle.")
            write("Actual full WAV SHA-256 declared: "+manifest["source_wav_sha256"])
            write("All entries will be independently SHA-verified and offline HTML will be regenerated.")
            write("A SHA manifest does NOT authenticate who sent the ZIP or grant music playback rights.")
            if read("Type yes to restore this audio into a NEW private folder: ").strip()!="yes":
                raise ValueError("User did not approve restoring real private music")
            target.mkdir(mode=0o700)
            written=[];complete=False
            try:
                for name in sorted(entries):
                    entry=entries[name]
                    new=target/name
                    written.append(new)
                    digest=hashlib.sha256();length=0
                    with new.open("xb") as out:
                        os.fchmod(out.fileno(),0o600)
                        with bundle.open(entry,"r") as reader:
                            while True:
                                chunk=reader.read(BLOCK)
                                if not chunk:break
                                length+=len(chunk)
                                if length>entry.file_size:
                                    raise ValueError("Archive extraction exceeded its declared byte limit")
                                out.write(chunk);digest.update(chunk)
                    if length!=entry.file_size or (
                            name!=MANIFEST and digest.hexdigest()!=records[name]["sha256"]):
                        raise ValueError("Actual restored private archive member differs from SHA manifest")
                wav,receipt=_source(target/"show.wav")
                if receipt["wav_sha256"]!=manifest["source_wav_sha256"]:
                    raise ValueError("Restored original full WAV SHA-256 did not match handoff identity")
                canonical_receipt,canonical_page,sanitized=_safe_delivery_companions(receipt)
                if ((target/"show.receipt.private.json").read_bytes()!=canonical_receipt or
                        (target/"index.html").read_bytes()!=canonical_page):
                    raise ValueError("Private ZIP contains edited or non-sanitized executable/show notes")
                if manifest["portable_encoded_included"]:
                    encoded=[c for c in ("mp3","flac") if (target/("show."+c)).exists()][0]
                    audio=target/("show."+encoded)
                    descriptor=json.loads((target/(audio.name+".receipt.private.json")).read_text("utf-8"))
                    sha,_=_sha(audio,MAX_ENCODE)
                    if (descriptor.get("kind")!=ENCODE_KIND or
                            descriptor.get("format")!=encoded or
                            descriptor.get("source_wav_sha256")!=receipt["wav_sha256"] or
                            descriptor.get("output_sha256")!=sha or
                            descriptor.get("private_only") is not True or
                            (target/(audio.name+".player.html")).read_bytes()!=
                                _player_page(sanitized,encoded,sha)):
                        raise ValueError("Restored encoded audio/player does not match actual verified Show source")
                after=os.fstat(stream.fileno())
                fields=("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")
                if tuple(getattr(before,f) for f in fields)!=tuple(getattr(after,f) for f in fields):
                    raise ValueError("The private Show ZIP changed during streaming restoration")
                complete=True
            finally:
                if not complete:
                    for entry in reversed(written):entry.unlink(missing_ok=True)
                    target.rmdir()
    return {"restored_private_show_folder":str(target),
            "actual_verified_wav":str(target/"show.wav"),
            "actual_wav_sha256":manifest["source_wav_sha256"],
            "private_offline_player":str(target/"index.html"),
            "restored_encoded_audio":bool(manifest["portable_encoded_included"]),
            "source_music_authenticated_externally":False,
            "operator_notes_in_archive":False}


def main():
    parser=argparse.ArgumentParser(description="Consent-gated offline restore of a SHA-verified, sanitized complete Show WAV USB bundle")
    parser.add_argument("existing_private_show_zip")
    parser.add_argument("new_private_restored_show_folder")
    args=parser.parse_args()
    try:
        result=restore_show(args.existing_private_show_zip,args.new_private_restored_show_folder)
    except (ValueError,TypeError,KeyError,OSError,EOFError,KeyboardInterrupt,
            UnicodeError,zipfile.BadZipFile,wave.Error):
        parser.exit(2,"MixLab private Show restore: source archive, consent or safe NEW destination invalid.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
