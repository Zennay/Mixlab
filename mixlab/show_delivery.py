"""Private portable delivery of an already approved, real completed Show WAV.

Encode or package only finished SHA-bound local audio. Never infer copyright
rights, include private source masters or silently publish operator notes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import wave
import zipfile

from .event_vault import _read_small_json
from .media_import import _checked_tools
from .delivery import FORMATS, _probe_encoded
from .show_master import RECEIPT_KIND, MAX_BYTES, _PAGE

MAX_ENCODE = 512*1024*1024
MAX_ZIP_BYTES = MAX_BYTES + MAX_ENCODE + 1024*1024
MAX_PAGE = 512*1024
BLOCK = 65536
BUNDLE_KIND="mixlab-private-complete-show-delivery-v1"
ENCODE_KIND="mixlab-private-complete-show-encoded-v1"


def _sha(path,limit):
    path=Path(path).absolute()
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:
            raise ValueError("Expected regular bounded private delivery file")
        sha=hashlib.sha256()
        for chunk in iter(lambda:stream.read(BLOCK),b""):sha.update(chunk)
        after=os.fstat(stream.fileno())
        fields=("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")
        if tuple(getattr(before,f) for f in fields)!=tuple(getattr(after,f) for f in fields):
            raise ValueError("Private source changed while being verified")
        return sha.hexdigest(),before.st_size


def _source(wav_path):
    wav=Path(wav_path).absolute()
    if wav.name!="show.wav":
        raise ValueError("Only actual already finished private show.wav is eligible")
    for part in (wav,*wav.parents):
        if part.is_symlink() or (part/".git").exists():
            raise ValueError("Keep private show audio away from symlinks and Git")
    doc=_read_small_json(wav.parent/"show.receipt.private.json")
    if (not isinstance(doc,dict) or doc.get("kind")!=RECEIPT_KIND or
            doc.get("schema_version")!=1 or doc.get("private_only") is not True or
            doc.get("automatic_dj_transition") is not False or
            doc.get("blind_study") is not False or
            doc.get("external_music_rights_verified") is not False or
            type(doc.get("sample_rate")) is not int or
            not 8000<=doc["sample_rate"]<=96000 or
            type(doc.get("channels")) is not int or doc["channels"]!=2 or
            type(doc.get("frames")) is not int or doc["frames"]<1 or
            not isinstance(doc.get("wav_sha256"),str) or
            len(doc["wav_sha256"])!=64):
        raise ValueError("Private continuous full show has invalid canonical receipt")
    positions=doc.get("sets")
    if not isinstance(positions,list) or not 2<=len(positions)<=6:
        raise ValueError("Completed show requires 2–6 genuine approved source sets")
    at=0
    for i,row in enumerate(positions):
        if (not isinstance(row,dict) or
                set(row)!={"label","source_sha256","start_frame","frames",
                          "gap_frames","private_note"} or
                not isinstance(row["label"],str) or not 0<len(row["label"])<=60 or
                not isinstance(row["source_sha256"],str) or
                len(row["source_sha256"])!=64 or
                type(row["start_frame"]) is not int or row["start_frame"]!=at or
                type(row["frames"]) is not int or row["frames"]<=0 or
                type(row["gap_frames"]) is not int or row["gap_frames"]<0 or
                (i==len(positions)-1 and row["gap_frames"]!=0) or
                not isinstance(row["private_note"],str) or len(row["private_note"])>300):
            raise ValueError("Finished private show positions are not contiguous and bound")
        at+=row["frames"]+row["gap_frames"]
    if at!=doc["frames"] or doc["frames"]*4+44>MAX_BYTES:
        raise ValueError("Finished private show frames exceed the original bounded receipt")
    actual,size=_sha(wav,MAX_BYTES)
    if actual!=doc["wav_sha256"] or size!=doc["frames"]*4+44:
        raise ValueError("Actual full Show WAV hash or byte count differs from its original receipt")
    with wave.open(str(wav),"rb") as handle:
        if (handle.getnchannels()!=2 or handle.getsampwidth()!=2 or
                handle.getframerate()!=doc["sample_rate"] or
                handle.getnframes()!=doc["frames"] or handle.getcomptype()!="NONE"):
            raise ValueError("Actual private Show WAV PCM16 format differs from its receipt")
    return wav,doc


def _target(folder,name):
    file=folder/name
    if file.exists() or file.is_symlink():
        raise ValueError("Choose a NEW private delivery filename, never overwrite")
    return file


def _player_page(doc,codec,sha):
    payload={"kind":ENCODE_KIND,"audio_name":"show."+codec,
             "source_sha256":doc["wav_sha256"],"output_sha256":sha,
             "duration_seconds":doc["frames"]/doc["sample_rate"],
             "sets":[{"label":x["label"],"start_seconds":x["start_frame"]/doc["sample_rate"],
                      "duration_seconds":x["frames"]/doc["sample_rate"],
                      "gap_seconds":x["gap_frames"]/doc["sample_rate"]}
                     for x in doc["sets"]]}
    serialized=json.dumps(payload,ensure_ascii=True,separators=(",",":"),allow_nan=False)
    serialized=serialized.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    html=r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';media-src 'self' file:;connect-src 'none';base-uri 'none';form-action 'none'">
<title>MixLab · Portable Full Show</title>
<style>body{font:16px/1.5 system-ui;background:#081723;color:#f0fff9;max-width:920px;margin:auto;padding:35px}
h1{font-size:48px}p,small{color:#b5d7dc}section{background:#163447;border-radius:17px;padding:22px;margin:18px 0}
audio{width:100%}button{font:inherit;color:#fff;background:#326c58;border:1px solid #8dccb5;border-radius:9px;padding:11px 15px;cursor:pointer}
li{margin:8px 0}small{display:block;overflow-wrap:anywhere;font:11px ui-monospace,monospace}</style>
<h1>One privately encoded, real complete show.</h1>
<p>Transcoded from an original SHA-verified complete stereo PCM16 WAV, not
automatically remixed. Encoder delay makes compressed seeking approximate.
Offline playback only; independent music licensing and quality not proven.</p>
<section><audio id="player" controls preload="metadata"></audio><p id="status">Local compressed event audio.</p></section>
<section><h2>Real original WAV boundaries</h2><ol id="chapters"></ol></section>
<small id="hashes"></small><script id="metadata" type="application/json">__DATA__</script>
<script>"use strict";
const data=JSON.parse(document.getElementById("metadata").textContent);
const player=document.getElementById("player");
player.src="./"+encodeURIComponent(data.audio_name);
for(const row of data.sets){
 const line=document.createElement("li"),button=document.createElement("button");
 button.type="button";button.textContent=row.label+" · original "+row.start_seconds.toFixed(1)+"s";
 button.addEventListener("click",()=>{player.currentTime=row.start_seconds;});
 line.append(button);document.getElementById("chapters").append(line);
}
player.addEventListener("error",()=>document.getElementById("status").textContent=
 "This browser cannot play this local compressed audio; use a trusted offline player.");
document.getElementById("hashes").textContent="Original WAV SHA-256: "+data.source_sha256+
" · Actual encoded output SHA-256: "+data.output_sha256;
</script></html>"""
    content=html.replace("__DATA__",serialized).encode("utf-8")
    if not 0<len(content)<=MAX_PAGE:
        raise ValueError("Bounded compressed show player too large")
    return content


def encode(wav_path,codec,*,bitrate=192,timeout=1200,read=input,write=print):
    if codec not in ("mp3","flac") or type(bitrate) is not int or bitrate not in (128,192,256,320):
        raise ValueError("Only official local MP3/FLAC and permitted bitrate are supported")
    if type(timeout) is not int or not 30<=timeout<=1800:
        raise ValueError("Local audio encoder timeout must be between 30 and 1800 seconds")
    wav,doc=_source(wav_path)
    target=_target(wav.parent,"show."+codec)
    receipt=_target(wav.parent,target.name+".receipt.private.json")
    page=_target(wav.parent,target.name+".player.html")
    write("Encoding actual approved WAV SHA-256 "+doc["wav_sha256"])
    write("Create opt-in private "+codec.upper()+" output only; no music rights or public sharing granted.")
    if read("Type yes to encode a separate private portable Show master: ").strip()!="yes":
        raise ValueError("Private audio encoding not approved")
    tool,ffmpeg=_checked_tools()
    encoder,muxer,expected_codec=FORMATS["."+codec]
    published=[]
    with tempfile.TemporaryDirectory(prefix=".mixlab-show-encode-",dir=wav.parent) as scratch:
        os.chmod(scratch,0o700)
        temporary=Path(scratch)/target.name
        command=[ffmpeg,"-nostdin","-hide_banner","-loglevel","error",
                 "-protocol_whitelist","file,pipe","-i",str(wav),
                 "-map","0:a:0","-vn","-sn","-dn",
                 "-map_metadata","-1","-map_chapters","-1",
                 "-threads","2","-c:a",encoder]
        if codec=="mp3":
            command.extend(["-b:a",str(bitrate)+"k"])
        command.extend(["-f",muxer,"-fs",str(MAX_ENCODE),"-n",str(temporary)])
        process=subprocess.run(command,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
            timeout=timeout,check=False)
        if process.returncode:
            raise ValueError("Installed local FFmpeg could not encode the requested format")
        info=temporary.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=MAX_ENCODE:
            raise ValueError("Compressed full show output is empty or oversized")
        probe=_probe_encoded(tool,temporary,expected_codec,
                            doc["frames"]/doc["sample_rate"],timeout)
        source_sha,_=_sha(wav,MAX_BYTES)
        if source_sha!=doc["wav_sha256"]:
            raise ValueError("Original approved Show WAV changed while encoding")
        sha,_=_sha(temporary,MAX_ENCODE)
        page_bytes=_player_page(doc,codec,sha)
        info_json={"schema_version":1,"kind":ENCODE_KIND,"format":codec,
                   "source_wav_sha256":doc["wav_sha256"],
                   "output_sha256":sha,"private_only":True,
                   "automatic_licensing":False,
                   "bitrate_kbps":bitrate if codec=="mp3" else None,
                   "encoded_duration_seconds":probe["duration_seconds"]}
        try:
            # Exclusive create: never overwrite an already delivered private file.
            os.link(temporary,target,follow_symlinks=False);published.append(target)
            with receipt.open("xb") as sink:
                published.append(receipt)
                os.fchmod(sink.fileno(),0o600)
                sink.write((json.dumps(info_json,indent=2,allow_nan=False)+"\n").encode("utf-8"))
            with page.open("xb") as sink:
                published.append(page)
                os.fchmod(sink.fileno(),0o600)
                sink.write(page_bytes)
            os.chmod(target,0o600)
        except BaseException:
            for output in reversed(published):output.unlink(missing_ok=True)
            raise
    return {"portable_private_audio":str(target),"receipt":str(receipt),
            "offline_player":str(page),"source_wav_sha256":doc["wav_sha256"],
            "encoded_output_sha256":sha,"private_only":True,
            "music_rights_proven":False}


def _safe_delivery_companions(doc):
    # The source private receipt and local index.html intentionally carry
    # PRIVATE operator notes. Never include their raw bytes in a music ZIP.
    clean = dict(doc)
    clean["sets"] = [{**row, "label": f"Set {i+1}", "private_note": ""}
                     for i,row in enumerate(doc["sets"])]
    clean["start_local"] = "redacted"
    source_receipt = (json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
    data={"wav_sha256":clean["wav_sha256"],
          "duration_seconds":clean["frames"]/clean["sample_rate"],
          "source_sha256s":[item["source_sha256"] for item in clean["sets"]],
          "sets":[{"label":item["label"],"note":"",
                   "start_seconds":item["start_frame"]/clean["sample_rate"],
                   "duration_seconds":item["frames"]/clean["sample_rate"],
                   "gap_seconds":item["gap_frames"]/clean["sample_rate"]}
                   for item in clean["sets"]]}
    safe=json.dumps(data,ensure_ascii=True,separators=(",",":"),allow_nan=False)
    safe=safe.replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    player=_PAGE.replace("__DATA__",safe).encode("utf-8")
    if not source_receipt or len(source_receipt)>65536 or not 0<len(player)<=MAX_PAGE:
        raise ValueError("Sanitised private show delivery companion exceeds size")
    return source_receipt,player,clean


def _zip_blob(zf,name,payload):
    item=zipfile.ZipInfo(name)
    item.compress_type=zipfile.ZIP_STORED
    item.external_attr=(stat.S_IFREG|0o600)<<16
    zf.writestr(item,payload)
    return {"file":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}


def _zip_entry(zf,path):
    hash_value=hashlib.sha256()
    size=0
    info=zipfile.ZipInfo(path.name)
    info.compress_type=zipfile.ZIP_STORED
    info.external_attr=(stat.S_IFREG|0o600)<<16
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as source:
        before=os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Private source changed into an invalid archive member")
        with zf.open(info,"w") as dest:
            for chunk in iter(lambda:source.read(BLOCK),b""):
                dest.write(chunk);hash_value.update(chunk);size+=len(chunk)
        after=os.fstat(source.fileno())
        stamp=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        if stamp(before)!=stamp(after) or size!=before.st_size:
            raise ValueError("Private archive source changed while streaming")
    return {"file":path.name,"bytes":size,"sha256":hash_value.hexdigest()}


def pack(wav_path,*,include_encoded=False,read=input,write=print):
    wav,doc=_source(wav_path)
    target=_target(wav.parent,"show.private.zip")
    if type(include_encoded) is not bool:
        raise ValueError("Portable inclusion must be an explicit boolean")
    receipt_bytes,player_bytes,clean_doc=_safe_delivery_companions(doc)
    files=[wav]
    extra=[("show.receipt.private.json",receipt_bytes),("index.html",player_bytes)]
    if include_encoded:
        existing=[fmt for fmt in ("mp3","flac") if (wav.parent/("show."+fmt)).exists()]
        if len(existing)!=1:
            raise ValueError("Choose exactly one previously encoded official MP3/FLAC before packaging")
        audio=wav.parent/("show."+existing[0])
        details=wav.parent/(audio.name+".receipt.private.json")
        page=wav.parent/(audio.name+".player.html")
        descriptor=_read_small_json(details)
        actual,_=_sha(audio,MAX_ENCODE)
        if (descriptor.get("kind")!=ENCODE_KIND or
                descriptor.get("format")!=existing[0] or
                descriptor.get("source_wav_sha256")!=doc["wav_sha256"] or
                descriptor.get("output_sha256")!=actual or
                descriptor.get("private_only") is not True):
            raise ValueError("Portable audio receipt does not match actual original Show WAV")
        files.append(audio)
        extra.extend([(details.name,(json.dumps(descriptor,indent=2,allow_nan=False)+"\n").encode("utf-8")),
                      (page.name,_player_page(clean_doc,existing[0],actual))])
    expected={"show.wav":doc["wav_sha256"]}
    if include_encoded:
        expected[audio.name]=actual
    total=0
    for item in files:
        if item.is_symlink() or not item.is_file():
            raise ValueError("Private official Show delivery files missing or symlinked")
        meta=item.lstat()
        if not stat.S_ISREG(meta.st_mode) or not 0<meta.st_size<=MAX_ZIP_BYTES:
            raise ValueError("Invalid official Show bundle member")
        total+=meta.st_size
    if total+sum(len(content) for _,content in extra)>MAX_ZIP_BYTES:
        raise ValueError("Official source-bound private show ZIP exceeds disk bound")
    write("A single PRIVATE WAV-backed show package with official player and receipts.")
    write("Original Show WAV SHA-256: "+doc["wav_sha256"])
    write("Personal operator cue files, standalone source songs and music licenses are NOT included.")
    if read("Type yes to publish a separate offline Show ZIP: ").strip()!="yes":
        raise ValueError("Private music ZIP not approved")
    complete=False
    try:
        with target.open("xb") as sink:
            os.fchmod(sink.fileno(),0o600)
            with zipfile.ZipFile(sink,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                records=[_zip_entry(archive,item) for item in files]
                records.extend(_zip_blob(archive,name,content) for name,content in extra)
                if any(record["sha256"]!=expected.get(record["file"],record["sha256"])
                       for record in records):
                    raise ValueError("Original complete Show WAV changed while being bundled")
                manifest={"schema_version":1,"kind":BUNDLE_KIND,
                          "source_wav_sha256":doc["wav_sha256"],
                          "private_only":True,"music_rights_proven":False,
                          "operator_notes_included":False,"original_source_songs_included":False,
                          "portable_encoded_included":include_encoded,
                          "unsigned_manifest":True,"files":records}
                entry=zipfile.ZipInfo("show.bundle.private.json")
                entry.compress_type=zipfile.ZIP_STORED
                entry.external_attr=(stat.S_IFREG|0o600)<<16
                archive.writestr(entry,(json.dumps(manifest,indent=2,allow_nan=False)+"\n").encode("utf-8"))
        source_sha,_=_sha(wav,MAX_BYTES)
        if source_sha!=doc["wav_sha256"]:
            raise ValueError("Original Show WAV changed before private ZIP publication")
        complete=True
    finally:
        if not complete:target.unlink(missing_ok=True)
    return {"private_show_bundle_zip":str(target),
            "actual_wav_sha256":doc["wav_sha256"],
            "encoded_audio_included":include_encoded,
            "operator_notes_included":False,"original_tracks_included":False,
            "externally_authenticated":False}


def main():
    parser=argparse.ArgumentParser(description="Private MP3/FLAC and bounded offline ZIP delivery of an existing SHA-verified real show.wav")
    sub=parser.add_subparsers(dest="command",required=True)
    conv=sub.add_parser("encode",help="Create separate consented MP3/FLAC from actual finished Show WAV")
    conv.add_argument("real_complete_show_wav")
    conv.add_argument("--format",choices=("mp3","flac"),required=True)
    conv.add_argument("--bitrate-kbps",type=int,choices=(128,192,256,320),default=192)
    conv.add_argument("--timeout-seconds",type=int,default=1200)
    archive=sub.add_parser("pack",help="Create separate opt-in private ZIP of finished WAV and receipts")
    archive.add_argument("real_complete_show_wav")
    archive.add_argument("--include-encoded",action="store_true",help="Include exactly one separately consented, SHA-receipt-verified MP3/FLAC")
    args=parser.parse_args()
    try:
        result=(encode(args.real_complete_show_wav,args.format,
                       bitrate=args.bitrate_kbps,timeout=args.timeout_seconds)
                if args.command=="encode" else
                pack(args.real_complete_show_wav,include_encoded=args.include_encoded))
    except (ValueError,OSError,KeyError,TypeError,EOFError,
            KeyboardInterrupt,UnicodeError,wave.Error,
            zipfile.BadZipFile,subprocess.SubprocessError):
        parser.exit(2,"MixLab private Show delivery: exact original WAV, optional codec, consent or safe new output invalid.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
