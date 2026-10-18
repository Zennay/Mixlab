"""Private ZIP handoff of short, genuine rendered Marathon join WAVs.

Not a music license or a blind study. ZIP is unsigned; it checks internal
content consistency and never authenticates an external sender.
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
from .marathon_join_reels import _PAGE, KIND, MAX_PAGE, MAX_PRIVATE_REELS

CHUNK = 65536
MAX_RECEIPT = 65536
MAX_ARCHIVE = MAX_PRIVATE_REELS + 2 * 1024 * 1024
PACK_MANIFEST = "join-reels.zip-manifest.private.json"
RECEIPT = "join-reels.receipt.private.json"
SHA = re.compile(r"[0-9a-f]{64}\Z")
CLIP = re.compile(r"join-([0-9]{2})-(original|blend)\.wav\Z")


def _read_regular(path, limit):
    path = Path(path).absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Private reel file cannot have symlinked ancestry")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("Private reel file must be a bounded regular file")
        content = file.read(limit + 1)
        after = os.fstat(file.fileno())
        stamp = lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if len(content) != before.st_size or stamp(before) != stamp(after):
            raise ValueError("Local reel file changed during private admission")
    return content


def _sha_file(path, size_limit):
    path = Path(path).absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Private reel source file cannot use a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= size_limit:
            raise ValueError("Invalid private reel source size")
        sha = hashlib.sha256()
        for part in iter(lambda:file.read(CHUNK),b""):
            sha.update(part)
        after = os.fstat(file.fileno())
        stamp = lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if stamp(before) != stamp(after):
            raise ValueError("Private reel source was modified during hash admission")
    return {"sha256": sha.hexdigest(), "size_bytes": before.st_size}


def _expected_page(data):
    encoded=json.dumps(data,ensure_ascii=True,separators=(",",":"),allow_nan=False)
    encoded=encoded.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    page=_PAGE.replace("__DATA__",encoded).encode("utf-8")
    if not 0 < len(page) <= MAX_PAGE:
        raise ValueError("The private offline Join Reel player exceeded its bound")
    return page


def _inspect(folder):
    """Admit the real, source-bound clip folder without trusting the HTML."""
    folder=Path(folder).absolute()
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Choose the actual completed private Join Reels folder")
    receipt=json.loads(_read_regular(folder / RECEIPT,MAX_RECEIPT).decode("utf-8"))
    if (not isinstance(receipt,dict) or receipt.get("schema_version") != 1 or
            receipt.get("kind") != KIND or
            receipt.get("source_media_embedded") is not False or
            receipt.get("private_only") is not True or receipt.get("blind_study") is not False or
            type(receipt.get("rate")) is not int or not 8000 <= receipt["rate"] <= 96000 or
            not isinstance(receipt.get("original_sha256"),str) or
            not SHA.fullmatch(receipt["original_sha256"]) or
            not isinstance(receipt.get("blend_sha256"),str) or
            not SHA.fullmatch(receipt["blend_sha256"])):
        raise ValueError("Invalid original genuine PCM Join Reels receipt")
    joins=receipt.get("joins")
    if not isinstance(joins,list) or not 1 <= len(joins) <= 7:
        raise ValueError("Private offline listening folder must contain 1–7 source-verified joins")
    names={"index.html",RECEIPT}
    for i,row in enumerate(joins,start=1):
        if (not isinstance(row,dict) or
                type(row.get("fade_seconds")) is not int or
                row["fade_seconds"] not in (2,4,8,16) or
                not isinstance(row.get("from"),str) or
                not isinstance(row.get("to"),str) or
                len(row["from"])>60 or len(row["to"])>60):
            raise ValueError("A private Join Reels handoff lacks real original/derivative source context")
        for side in ("original","blend"):
            entry=row.get(side)
            name=f"join-{i:02d}-{side}.wav"
            if (not isinstance(entry,dict) or entry.get("filename")!=name or
                    type(entry.get("start_frame")) is not int or entry["start_frame"] < 0 or
                    type(entry.get("frames")) is not int or entry["frames"] < 1 or
                    entry["frames"] > (row["fade_seconds"]+16)*receipt["rate"] or
                    not isinstance(entry.get("wav_sha256"),str) or
                    not SHA.fullmatch(entry["wav_sha256"])):
                raise ValueError("The Join Reel excerpt is not a bounded actual PCM clip")
            real=folder/name
            size_info=_sha_file(real,MAX_PRIVATE_REELS)
            if size_info["sha256"]!=entry["wav_sha256"] or size_info["size_bytes"] > (entry["frames"]*4+256):
                raise ValueError("Actual local WAV excerpt disagrees with its original private receipt")
            flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
            fd=os.open(real,flags)
            with os.fdopen(fd,"rb") as stream:
                with wave.open(stream,"rb") as reader:
                    if (reader.getnframes()!=entry["frames"] or
                            reader.getframerate()!=receipt["rate"] or
                            reader.getnchannels()!=2 or reader.getsampwidth()!=2 or
                            reader.getcomptype()!="NONE"):
                        raise ValueError("A private reel is not the original stereo PCM16 format")
            names.add(name)
    if _read_regular(folder/"index.html",MAX_PAGE) != _expected_page(receipt):
        raise ValueError("Offline Reel player differs from exact approved private WAV receipt")
    records={}
    for name in sorted(names):
        records[name]=_sha_file(folder/name,MAX_PRIVATE_REELS if name.endswith(".wav") else MAX_PAGE)
    if sum(row["size_bytes"] for row in records.values()) > MAX_ARCHIVE:
        raise ValueError("Join Reels are larger than the allowed private USB size")
    return receipt,records


def export_reels(folder, new_zip):
    """Create an unsigned SHA-manifest ZIP containing only short local PCM clips."""
    folder=Path(folder).absolute()
    target=Path(new_zip).absolute()
    if (target.parent!=folder or target.name!="join-reels.private.zip" or
            target.exists() or target.is_symlink() or
            any(p.is_symlink() or (p/".git").exists() for p in (target,*target.parents))):
        raise ValueError("Create a NEW join-reels.private.zip beside the original private clips, outside Git")
    receipt,records=_inspect(folder)
    info={"schema_version":1,"kind":"mixlab-private-join-reels-usb-v1",
          "original_sha256":receipt["original_sha256"],
          "blend_sha256":receipt["blend_sha256"],
          "private_only":True,"source_media_included":False,
          "archive_authenticated":False,"music_rights_proven":False,
          "files":records}
    complete=False
    try:
        with target.open("xb") as output:
            os.fchmod(output.fileno(),0o600)
            with zipfile.ZipFile(output,mode="w",compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                for name,claim in records.items():
                    path=folder/name
                    with archive.open(name,"w",force_zip64=True) as dest:
                        flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
                        fd=os.open(path,flags)
                        with os.fdopen(fd,"rb") as stream:
                            before=os.fstat(stream.fileno())
                            digest=hashlib.sha256()
                            total=0
                            while True:
                                piece=stream.read(CHUNK)
                                if not piece:break
                                total+=len(piece)
                                digest.update(piece)
                                dest.write(piece)
                            after=os.fstat(stream.fileno())
                            stamp=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
                            if (stamp(before)!=stamp(after) or total!=claim["size_bytes"]
                                    or digest.hexdigest()!=claim["sha256"]):
                                raise ValueError("A private excerpt changed during ZIP publication")
                archive.writestr(PACK_MANIFEST,(json.dumps(info,sort_keys=True,indent=2,allow_nan=False)+"\n"),
                                  compress_type=zipfile.ZIP_STORED)
        complete=True
    finally:
        if not complete:
            target.unlink(missing_ok=True)
    return {"private_zip":str(target),"real_join_count":len(receipt["joins"]),
            "private_source_wavs_unchanged":True,"source_media_included":False,
            "archive_authenticated":False,"music_rights_proven":False}


def restore_reels(private_zip,new_folder):
    """Extract a private short-WAV listening room into one new, bounded directory."""
    source=Path(private_zip).absolute()
    if (source.suffix.lower()!=".zip" or source.is_symlink() or
            any(p.is_symlink() for p in source.parents)):
        raise ValueError("Private reel ZIP source cannot use a symlink")
    raw=os.open(source,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    destination=_new_folder(new_folder,[])
    completed=False;created=False;written=[]
    with os.fdopen(raw,"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_ARCHIVE:
            raise ValueError("Private Join Reels archive exceeds maximum size")
        try:
            with zipfile.ZipFile(stream,"r") as archive:
                infos=archive.infolist()
                if not 4 <= len(infos) <= 17:
                    raise ValueError("Private reel ZIP file inventory is malformed")
                if len({x.filename for x in infos})!=len(infos):
                    raise ValueError("ZIP has conflicting duplicate private file names")
                info_map={item.filename:item for item in infos}
                if PACK_MANIFEST not in info_map:
                    raise ValueError("Unsigned private reel ZIP is missing its file inventory")
                entry=info_map[PACK_MANIFEST]
                if entry.file_size>MAX_RECEIPT:
                    raise ValueError("ZIP manifest is too large")
                record=json.loads(archive.read(PACK_MANIFEST).decode("utf-8"))
                if (not isinstance(record,dict) or record.get("schema_version")!=1 or
                        record.get("kind")!="mixlab-private-join-reels-usb-v1" or
                        record.get("private_only") is not True or
                        record.get("source_media_included") is not False or
                        record.get("archive_authenticated") is not False or
                        record.get("music_rights_proven") is not False or
                        not isinstance(record.get("files"),dict)):
                    raise ValueError("Not an official private short-WAV listening archive")
                allowed={"index.html",RECEIPT}
                for n in range(1,8):
                    for side in ("original","blend"):
                        allowed.add(f"join-{n:02d}-{side}.wav")
                files=record["files"]
                if (not set(files).issubset(allowed) or
                        not {RECEIPT,"index.html"}.issubset(files) or
                        set(info_map)!=set(files)|{PACK_MANIFEST}):
                    raise ValueError("Private reel ZIP contains unexpected paths or missing outputs")
                total=0
                for name,item in info_map.items():
                    mode=stat.S_IFMT(item.external_attr >> 16)
                    if (item.is_dir() or item.compress_type!=zipfile.ZIP_STORED or
                            mode not in (0,stat.S_IFREG) or
                            item.file_size!=item.compress_size):
                        raise ValueError("Reel ZIP must contain flat regular uncompressed files")
                    if name==PACK_MANIFEST:continue
                    claim=files[name]
                    if (not isinstance(claim,dict) or type(claim.get("size_bytes")) is not int or
                            not 0 < claim["size_bytes"] <= MAX_PRIVATE_REELS or
                            claim["size_bytes"]!=item.file_size or
                            not isinstance(claim.get("sha256"),str) or
                            not SHA.fullmatch(claim["sha256"])):
                        raise ValueError("ZIP file inventory differs from private receipt")
                    total+=item.file_size
                if total>MAX_ARCHIVE:
                    raise ValueError("Private listening clips exceed ZIP output budget")
                destination.mkdir(mode=0o700);created=True
                for name,claim in files.items():
                    path=destination/name;written.append(path)
                    with archive.open(name,"r") as src:
                        with path.open("xb") as output:
                            os.fchmod(output.fileno(),0o600)
                            sha=hashlib.sha256();size=0
                            while True:
                                chunk=src.read(CHUNK)
                                if not chunk:break
                                size+=len(chunk)
                                if size>claim["size_bytes"]:
                                    raise ValueError("ZIP entry expanded beyond declared size")
                                sha.update(chunk);output.write(chunk)
                            if size!=claim["size_bytes"] or sha.hexdigest()!=claim["sha256"]:
                                raise ValueError("Private listening clip ZIP SHA-256 mismatch")
                actual=_inspect(destination)
                if (actual[0]["original_sha256"]!=record["original_sha256"] or
                        actual[0]["blend_sha256"]!=record["blend_sha256"] or actual[1]!=files):
                    raise ValueError("Private Join Reels did not match their restored master provenance")
                after=os.fstat(stream.fileno())
                stamp=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
                if stamp(before)!=stamp(after):
                    raise ValueError("Private reel ZIP changed during restoration")
                completed=True
        finally:
            if created and not completed:
                for path in reversed(written):
                    path.unlink(missing_ok=True)
                destination.rmdir()
    return {"restored_reels":str(destination),"offline_player":str(destination/"index.html"),
            "private_receipt":str(destination/RECEIPT),
            "private":True,"media_uploaded":False,"archive_authenticated":False,
            "blind_preference_proven":False}


def main():
    parser=argparse.ArgumentParser(
        description="Pack/restore a compact offline true-PCM DJ handoff reel studio without original full masters")
    sub=parser.add_subparsers(dest="action",required=True)
    p=sub.add_parser("pack",help="Create a SHA-manifest private ZIP from completed short WAV reel folder")
    p.add_argument("existing_private_reels_folder")
    p.add_argument("new_private_zip")
    r=sub.add_parser("restore",help="Safely expand a private reel ZIP into a NEW local folder")
    r.add_argument("private_reels_zip")
    r.add_argument("new_private_folder")
    args=parser.parse_args()
    try:
        result=export_reels(args.existing_private_reels_folder,args.new_private_zip) if args.action=="pack" else restore_reels(args.private_reels_zip,args.new_private_folder)
    except (ValueError,TypeError,KeyError,OSError,UnicodeError,zipfile.BadZipFile,wave.Error):
        parser.exit(2,"MixLab private actual-WAV Reel transfer: source ZIP, original short WAVs or destination invalid.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
