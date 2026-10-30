"""Export one final private reel from a fully decisive human two-take comparison.

Neither the original nor the revision is promoted automatically. The DJ must
select a winner for every original track-pair chapter; undecided explicitly
fails before creating any destination. All media remains PCM16 and SHA-bound.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

from .private_output import write_private_new
import tempfile
import wave

from .models import FAMILY_NAMES
from .private_transition_selection import (
    _copy_and_verify_wav, _read_json_and_digest, _valid_sha,
)
from .private_transition_reel import _page as _reel_page

MAX_OUTPUT_AUDIO_BYTES = 128 * 1024 * 1024


def _sha(path):
    checksum=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            checksum.update(block)
    return checksum.hexdigest()


def _human_choices(comparison, comparison_sha, decision):
    if (type(comparison.get("schema_version")) is not int
            or comparison["schema_version"] != 1
            or comparison.get("kind") != "mixlab-private-original-versus-revision"
            or comparison.get("status") != "prepared-for-visible-human-comparison"
            or comparison.get("rights_status") != "unverified"):
        raise ValueError("Not an original MixLab two-take comparison receipt")
    old_sha=comparison.get("original_reel_receipt_sha256")
    new_sha=comparison.get("revised_reel_receipt_sha256")
    if not _valid_sha(old_sha) or not _valid_sha(new_sha) or old_sha==new_sha:
        raise ValueError("Original and revised sources must be distinct canonical reel hashes")
    entries=comparison.get("chapters")
    if type(entries) is not list or not 2<=len(entries)<=8:
        raise ValueError("Two-take comparison must have 2–8 original chapters")
    if (type(decision.get("schema_version")) is not int
            or decision["schema_version"]!=1
            or decision.get("kind")!="mixlab-private-human-take-comparison"
            or decision.get("status")!="visible-method-human-decision-not-blind-study"
            or decision.get("rights_status")!="unverified"
            or decision.get("comparison_receipt_sha256")!=comparison_sha
            or decision.get("original_reel_receipt_sha256")!=old_sha
            or decision.get("revised_reel_receipt_sha256")!=new_sha):
        raise ValueError("Human decision is not bound to these exact two original reels")
    choices=decision.get("choices")
    if type(choices) is not list or len(choices)!=len(entries):
        raise ValueError("Human decision must cover every track pair exactly once")
    result=[]
    for index,(row,item) in enumerate(zip(entries,choices),1):
        if (type(row) is not dict or type(row.get("chapter")) is not int or row["chapter"]!=index
            or not _valid_sha(row.get("source_gallery_receipt_sha256"))):
            raise ValueError("Comparison has incomplete chapter/source identity")
        if (type(item) is not dict or type(item.get("chapter")) is not int or item["chapter"]!=index):
            raise ValueError("Human decision chapters must be complete and ordered")
        side=item.get("chosen_take")
        if side=="undecided":
            raise ValueError(f"Chapter {index} still needs a human decision; no final reel written")
        if side not in ("original","revised"):
            raise ValueError("Expected an explicit original or revised human choice")
        note=item.get("note")
        if type(note) is not str or len(note)>240:
            raise ValueError("Human comparison note is invalid")
        try:
            encoded=note.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Human comparison note contains unencodable text") from exc
        if len(encoded)>1024 or any(ord(c)<32 and c not in "\n\t" for c in note):
            raise ValueError("Human comparison note has unsupported control characters")
        candidates=[]
        for candidate_side in ("original","revised"):
            candidate=row.get(candidate_side)
            expected=f"{index:02d}-{candidate_side}.wav"
            if (type(candidate) is not dict
                    or candidate.get("audio")!=expected
                    or candidate.get("family") not in FAMILY_NAMES
                    or not _valid_sha(candidate.get("audio_sha256"))
                    or not _valid_sha(candidate.get("human_choice_sha256"))
                    or type(candidate.get("private_note")) is not str
                    or len(candidate["private_note"])>240):
                raise ValueError("Original/revised candidate proof is incomplete")
            candidates.append(candidate)
        result.append((index,side,row[side],row["source_gallery_receipt_sha256"],note))
    return result


def finalize(comparison_workspace, human_decision_json, output_reel):
    """Reassemble one final human-selected, non-overwriting PCM16 reel."""
    studio,target=Path(comparison_workspace),Path(output_reel)
    if not studio.is_dir() or target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("Provide an existing comparison and new private reel folder")
    comparison,comparison_sha=_read_json_and_digest(studio/"receipt.json")
    decision,decision_sha=_read_json_and_digest(human_decision_json)
    selected=_human_choices(comparison,comparison_sha,decision)
    with tempfile.TemporaryDirectory(prefix=".mixlab-human-final-take-",dir=target.parent) as folder:
        stage=Path(folder)
        chapters=[]
        outputs=[]
        total=0
        for index,side,item,original_gallery_sha,choice_note in selected:
            new_name=f"{index:02d}-{item['family']}.wav"
            path=stage/new_name
            total+=_copy_and_verify_wav(
                studio/f"{index:02d}-{side}.wav",path,item["audio_sha256"]
            )
            if total>MAX_OUTPUT_AUDIO_BYTES:
                raise ValueError("Final private reel audio exceeds 128MiB budget")
            path.chmod(0o600)
            outputs.append(new_name)
            try:
                with wave.open(str(path),"rb") as audio:
                    if (audio.getsampwidth()!=2 or audio.getcomptype()!="NONE"
                            or audio.getnchannels() not in (1,2)
                            or not 8000<=audio.getframerate()<=96000
                            or audio.getnframes()<1):
                        raise ValueError("Source-bound take does not contain supported PCM16")
                    seconds=audio.getnframes()/audio.getframerate()
            except (wave.Error,EOFError) as exc:
                raise ValueError("Source-bound take cannot be opened as PCM16") from exc
            chapters.append({
                "chapter":index,"family":item["family"],"audio":new_name,
                "audio_sha256":item["audio_sha256"],"seconds":seconds,
                "private_note":choice_note or item["private_note"],
                "previous_private_note":item["private_note"],
                "comparison_decision_note":choice_note,
                "human_selected_take":side,
                "source_gallery_receipt_sha256":original_gallery_sha,
                "human_choice_sha256":decision_sha,
                "human_choice_source":"explicit-visible-comparison",
            })
        receipt={
            "schema_version":1,"kind":"mixlab-private-rehearsal-reel",
            "status":"human-selected-not-blind-study",
            "rights_status":"unverified","chapter_count":len(chapters),
            "total_audio_bytes":total,"original_order_only":True,
            "human_reordered_in_browser_only":False,
            "human_take_comparison_receipt_sha256":comparison_sha,
            "human_take_decision_sha256":decision_sha,"chapters":chapters,
        }
        receipt_path=stage/"receipt.json"
        write_private_new(receipt_path, (json.dumps(receipt,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8"))
        page=stage/"index.html"
        write_private_new(page, (_reel_page(receipt,_sha(receipt_path))).encode("utf-8"))
        target.mkdir(mode=0o700)
        saved=[]
        try:
            for filename in outputs+["receipt.json","index.html"]:
                os.link(stage/filename,target/filename)
                saved.append(filename)
        except BaseException:
            for filename in saved:
                (target/filename).unlink()
            target.rmdir()
            raise
    return target/"index.html"


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="Apply a complete source-bound human original-vs-revised comparison to a new private reel"
    )
    parser.add_argument("comparison_workspace")
    parser.add_argument("human_comparison_json")
    parser.add_argument("new_output_reel")
    args=parser.parse_args(argv)
    try:
        print(finalize(args.comparison_workspace,args.human_comparison_json,args.new_output_reel))
    except (OSError,ValueError,TypeError) as exc:
        parser.exit(2,f"MixLab human take finalization: {exc}\n")


if __name__=="__main__":
    main()
