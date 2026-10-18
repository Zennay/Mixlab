"""Private mobile MP3/FLAC delivery for an already rendered Marathon master.

Shares MixLab's installed FFmpeg/FFprobe admission and metadata checks.
Never modifies the source WAV or licenses private music for distribution.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from .delivery import FORMATS, _probe_encoded
from .event_marathon import _PAGE, _digest_file, MAX_HTML
from .event_vault import _marathon_duration, _read_small_json
from .media_import import _checked_tools

MAX_ENCODED = 512 * 1024 * 1024
PAGE_LIMIT = MAX_HTML
RECEIPT_LIMIT = 65536


def _target(wav, output):
    dest = Path(output).absolute()
    if (dest.parent != wav.parent or dest.name not in ("marathon.mp3", "marathon.flac") or
            dest.suffix.lower() not in FORMATS):
        raise ValueError("Choose a NEW marathon.mp3 or marathon.flac in the approved WAV folder")
    paths = (dest, dest.with_name(dest.name + ".receipt.private.json"),
             dest.with_name(dest.name + ".player.html"))
    if any(path.is_symlink() or path.exists() for path in paths):
        raise ValueError("Portable audio and its companions must all be NEW")
    for node in (dest, *dest.parents):
        if node.is_symlink() or (node / ".git").exists():
            raise ValueError("Never encode private Marathon audio in Git or symlink directories")
    return paths


def _private_page(wav, receipt, encoded):
    sections = [{"label": section["label"],
                 "start_seconds": section["start_frame"] / receipt["rate"]}
                for section in receipt["sections"]]
    metadata = {"wav_name": encoded.name,
                "wav_sha256": _digest_file(encoded),
                "duration_seconds": receipt["frames"] / receipt["rate"],
                "sections": sections, "showbook": None, "join_studio": None}
    raw = json.dumps(metadata, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = (_PAGE.replace("One long<br>uninterrupted set.", "Your portable<br>private event.")
            .replace("Save original continuous WAV", "Save encoded portable audio")
            .replace("Play the continuous master", "Listen to your private portable encoding")
            .replace("A gapless assembly of real, independently completed private MixLab sets. No artificial remix, automatic harmonic matching, tempo shift or re-encoding.",
                     "This local MP3/FLAC was encoded from the actual finished private Marathon WAV. It is not a new DJ mix or a new music license.")
            .replace("Each joint is an intentional, sample-exact boundary between completed sets. This is not a DJ-quality transition or evidence of listening preference.",
                     "Chapter positions are based on the exact original PCM16 WAV. Encoder delay and browser seeking make compressed-audio cue positions approximate, not frame exact.")
            .replace("Exact continuous WAV SHA-256:", "Portable audio SHA-256:")
            .replace('<button id="cue" type="button">Download chapter CUE</button>',
                     '<button id="cue" type="button" hidden aria-hidden="true">Download chapter CUE</button>')
            .replace("__DATA__", raw)).encode("utf-8")
    if len(page) > PAGE_LIMIT:
        raise ValueError("Private portable event player exceeds its page budget")
    return page


def export_mobile_marathon(original_wav, new_compressed, *,
                           bitrate_kbps=192, timeout_seconds=1200):
    if type(bitrate_kbps) is not int or bitrate_kbps not in (128, 192, 256, 320):
        raise ValueError("MP3 bitrate must be 128/192/256/320 kbps")
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 1800:
        raise ValueError("Local encoder time limit must be 30..1800 seconds")
    wav = Path(original_wav).absolute()
    if wav.name != "marathon.wav" or wav.is_symlink():
        raise ValueError("Only original or manually approved private Marathon WAV can be encoded")
    duration, count, evidence = _marathon_duration(wav.parent, wav)
    if evidence not in ("marathon", "marathon_blend") or not 2 <= count <= 8:
        raise ValueError("Completed private Marathon receipt is required")
    original = _read_small_json(wav.parent / "marathon.receipt.private.json")
    target, output_receipt, player = _target(wav, new_compressed)
    before = wav.lstat()
    codec, muxer, expected_codec = FORMATS[target.suffix.lower()]
    ffprobe, ffmpeg = _checked_tools()
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(wav), "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-map_metadata", "-1", "-c:a", codec, "-threads", "2",
    ]
    if target.suffix == ".mp3":
        command.extend(["-b:a", f"{bitrate_kbps}k"])
    command.extend(["-f", muxer])
    published = []
    with tempfile.TemporaryDirectory(prefix=".mixlab-marathon-mobile-", dir=wav.parent) as temp:
        os.chmod(temp, 0o700)
        tmp = Path(temp)
        encoded = tmp / target.name
        result = subprocess.run(
            command + ["-n", str(encoded)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
        if result.returncode:
            raise ValueError("Installed local FFmpeg could not encode the private Marathon")
        info = encoded.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ENCODED:
            raise ValueError("Portable private audio is empty or too large")
        os.chmod(encoded, 0o600)
        decoded = _probe_encoded(ffprobe, encoded, expected_codec, duration, timeout_seconds)
        after = wav.lstat()
        stamp = lambda m: (m.st_dev, m.st_ino, m.st_size, m.st_mtime_ns, m.st_ctime_ns)
        if stamp(before) != stamp(after) or _digest_file(wav) != original["wav_sha256"]:
            raise ValueError("Original Marathon WAV changed during portable encoding")
        output_sha = _digest_file(encoded)
        receipt = {
            "schema_version": 1, "kind": "mixlab-private-marathon-mobile-v1",
            "source_wav_sha256": original["wav_sha256"],
            "output_sha256": output_sha,
            "format": target.suffix[1:],
            "codec": expected_codec,
            "encoded_duration_seconds": decoded["duration_seconds"],
            "source_duration_seconds": duration,
            "source_events": count,
            "bitrate_kbps": bitrate_kbps if target.suffix == ".mp3" else None,
            "original_pcm16_unchanged": True,
            "private_local_use_only": True,
            "automatic_licensing": False,
            "human_preference_proven": False,
            "media_uploaded": False,
        }
        blob = (json.dumps(receipt, sort_keys=True, indent=2,
                           allow_nan=False) + "\n").encode("utf-8")
        if len(blob) > RECEIPT_LIMIT:
            raise ValueError("Portable receipt exceeds its local metadata budget")
        page = _private_page(wav, original, encoded)
        temporary = [(encoded, target)]
        for name, data, out in (("receipt.json", blob, output_receipt),
                                ("player.html", page, player)):
            file = tmp / name
            with file.open("xb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
            temporary.append((file, out))
        try:
            for source_file, destination in temporary:
                os.link(source_file, destination)
                published.append(destination)
        except BaseException:
            for path in reversed(published):
                path.unlink(missing_ok=True)
            raise
    return {"private_mobile_audio": str(target), "private_receipt": str(output_receipt),
            "offline_player": str(player), "output_sha256": output_sha,
            "source_wav_sha256": original["wav_sha256"], "format": target.suffix[1:],
            "source_pcm16_preserved": True, "private": True,
            "automatic_licensing": False, "media_uploaded": False}


def main():
    parser = argparse.ArgumentParser(
        description="Encode an approved receipt-verified private Marathon into portable MP3/FLAC with local FFmpeg")
    parser.add_argument("original_marathon_wav")
    parser.add_argument("new_private_audio", help="NEW marathon.mp3 or marathon.flac beside source WAV")
    parser.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320), default=192)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    try:
        result = export_mobile_marathon(args.original_marathon_wav, args.new_private_audio,
                                        bitrate_kbps=args.bitrate_kbps,
                                        timeout_seconds=args.timeout_seconds)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        parser.exit(2, "MixLab Marathon portable delivery: no verified private audio export was published.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
