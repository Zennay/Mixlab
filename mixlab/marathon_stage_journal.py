"""Print a source-bound operator playback rehearsal report from a real hybrid WAV.

This does not quantify musical quality or real-world venue clock performance.
The manual journal timestamps are user-entered playback positions only.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
from pathlib import Path
import wave

from .event_vault import _marathon_duration, _read_small_json
from .marathon_sequence import _read_plan
from .marathon_reel_decisions import _write_private

KIND="mixlab-private-hybrid-playback-cue-journal-v1"


def print_journal(master_wav, private_journal_json, new_private_report):
    wav=Path(master_wav).absolute()
    report=Path(new_private_report).absolute()
    if (wav.name!="marathon.wav" or
            report.parent!=wav.parent or
            report.name!="master-playback-journal.private.html" or
            report.exists() or report.is_symlink() or
            any(p.is_symlink() or (p/".git").exists()
                for p in (wav,*wav.parents,report,*report.parents))):
        raise ValueError("Report must be a NEW private HTML beside the existing approved master")
    duration,count,kind=_marathon_duration(wav.parent,wav)
    receipt=_read_small_json(wav.parent/"marathon.receipt.private.json")
    journal=_read_plan(private_journal_json)
    if (kind!="marathon_blend" or not isinstance(journal,dict) or
            set(journal)!={"schema_version","kind","actual_master_sha256",
                "source_original_sha256","duration_seconds","private_only",
                "playback_only","blind_study","joins"} or
            type(journal["schema_version"]) is not int or
            journal["schema_version"]!=1 or journal["kind"]!=KIND or
            journal["actual_master_sha256"]!=receipt["wav_sha256"] or
            journal["source_original_sha256"]!=receipt["source_marathon_sha256"] or
            journal["private_only"] is not True or
            journal["playback_only"] is not True or
            journal["blind_study"] is not False or
            type(journal["duration_seconds"]) not in (int,float) or
            not math.isfinite(journal["duration_seconds"]) or
            abs(journal["duration_seconds"]-duration)>0.001):
        raise ValueError("Private playback journal belongs to another actual finished WAV")
    joins=journal["joins"]
    if not isinstance(joins,list) or len(joins)!=count-1:
        raise ValueError("Private playback journal is missing source boundaries")
    rows=[]
    for i,item in enumerate(joins,1):
        planned=receipt["sections"][i]["start_frame"]/receipt["rate"]
        if (not isinstance(item,dict) or set(item)!={"index","from","to",
                "planned_seconds","fade_seconds","observed_playback_seconds","note"} or
                type(item["index"]) is not int or item["index"]!=i or
                item["from"]!=receipt["sections"][i-1]["label"] or
                item["to"]!=receipt["sections"][i]["label"] or
                type(item["fade_seconds"]) is not int or
                item["fade_seconds"]!=receipt["fade_seconds_by_join"][i-1] or
                type(item["planned_seconds"]) not in (int,float) or
                not math.isfinite(item["planned_seconds"]) or
                abs(item["planned_seconds"]-planned)>0.000001 or
                not isinstance(item["note"],str) or len(item["note"])>300):
            raise ValueError("Journal row is not bound to the actual receipt and private cues")
        value=item["observed_playback_seconds"]
        if value is not None and (type(value) not in (int,float) or
                                  not math.isfinite(value) or
                                  not 0<=value<=duration):
            raise ValueError("Journal observed playback marker outside WAV bounds")
        delta= None if value is None else value-planned
        esc=lambda x:html.escape(str(x),quote=True)
        cue=("Not marked" if value is None else
             f"{value:.3f} s · playback offset {delta:+.3f} s")
        rows.append(f"<tr><td>{i}</td><td>{esc(item['from'])} → {esc(item['to'])}</td>"
                    f"<td>{planned:.3f} s</td><td>{esc(cue)}</td>"
                    f"<td>{item['fade_seconds']} s</td>"
                    f"<td class='note'>{esc(item['note'])}</td></tr>")
    if not any(x["observed_playback_seconds"] is not None for x in joins):
        raise ValueError("Print report needs at least one manually observed playback marker")
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none';form-action 'none'">
<title>MixLab private rehearsal journal</title>
<style>body{font:15px/1.5 system-ui;margin:30px auto;max-width:1150px;padding:16px;color:#172932}
h1{font-size:34px}td,th{border:1px solid #adbcc5;padding:9px;text-align:left;vertical-align:top}
table{border-collapse:collapse;width:100%}.note{white-space:pre-wrap;overflow-wrap:anywhere}
small{display:block;overflow-wrap:anywhere}@media print{body{margin:0;padding:0}}
</style></head><body><h1>Real hybrid · private playback rehearsal</h1>
<p>Manual playback markers against the finished WAV receipt. Pauses, seeks,
device scheduling and arbitrary user marking affect offsets. NOT physical
venue timing, automatic DJ rating, proof of music rights or blind evidence.</p>
<small>Actually rendered WAV SHA-256: '''+html.escape(receipt["wav_sha256"])+'''</small>
<small>Source original WAV SHA-256: '''+html.escape(receipt["source_marathon_sha256"])+'''</small>
<table><thead><tr><th>#</th><th>Real join</th><th>Receipt boundary</th>
<th>Human playback observation</th><th>Real fade</th><th>Private note</th>
</tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></body></html>'''
    encoded=page.encode("utf-8")
    if not 0<len(encoded)<=128*1024:
        raise ValueError("Local private rehearsal report exceeded bounded size")
    _write_private(report,encoded)
    return {"private_rehearsal_report":str(report),
            "actual_master_sha256":receipt["wav_sha256"],
            "marked_joins":sum(x["observed_playback_seconds"] is not None for x in joins),
            "total_joins":len(joins),
            "verified_local_audio":True,"playback_clock_only":True,
            "musical_preference_proven":False}


def main():
    parser=argparse.ArgumentParser(description="Print a source-SHA-bound local manual playback journal for a real hybrid Marathon")
    parser.add_argument("actual_hybrid_marathon_wav")
    parser.add_argument("exported_private_playback_journal_json")
    parser.add_argument("new_private_report_html")
    args=parser.parse_args()
    try:
        result=print_journal(args.actual_hybrid_marathon_wav,
                             args.exported_private_playback_journal_json,
                             args.new_private_report_html)
    except (ValueError,TypeError,KeyError,OSError,UnicodeError,wave.Error):
        parser.exit(2,"MixLab journal: local real master, exact journal or new private report unavailable.\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
