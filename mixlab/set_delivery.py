"""Portable offline DJ set export: official WAV -> private MP3 + CUE + M3U8.

Requires already-installed local FFmpeg with libmp3lame. Admission relies
on the original exact SHA-bound full-set receipt and official chapter plan.
No new music inference, upload, licensing claim, normalization or remixing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import tempfile
import time

from .ingest import digest
from .media_import import _checked_tools
from .set_player import build_chapters

BITRATE_KBPS = 192
MAX_PORTABLE_BYTES = 128 * 1024 * 1024
MAX_TIME_SECONDS = 900
READ_BYTES = 65536


def _destination_paths(wav_path, output):
    wav = Path(wav_path).absolute()
    target = Path(output).absolute()
    if target.suffix.lower() != ".mp3" or not target.name.lower().endswith(".mp3"):
        raise ValueError("Portable mix output must be a new .mp3 file")
    if not target.parent.is_dir():
        raise ValueError("Choose an existing private output directory")
    if target.parent == wav.parent and target.stem == wav.stem:
        # Fine: MP3 is a *new* file, separate from the source WAV.
        pass
    paths = {
        "mp3": target,
        "receipt": Path(str(target) + ".receipt.private.json"),
        "cue": target.with_suffix(".cue"),
        "playlist": target.with_suffix(".m3u8")
    }
    for path in paths.values():
        if path.exists() or path.is_symlink():
            raise ValueError("Never overwrite an existing portable audio or sidecar file")
    for parent in (target, *target.parents):
        if parent.is_symlink() or (parent / ".git").exists():
            raise ValueError("Do not publish private audio into Git or a symlink path")
    if any(part in ("\n", "\r", "\x00") for part in target.name):
        raise ValueError("Unsafe output filename")
    return paths


def _write_new(path, raw, created):
    with path.open("xb") as target:
        created.append(path)
        os.fchmod(target.fileno(), 0o600)
        target.write(raw)


def _cue_text(chapters, mp3_name):
    lines = ['REM COMMENT "MixLab creative private portable set"',
             'FILE "' + mp3_name.replace('"', "'") + '" MP3']
    for index, section in enumerate(chapters, 1):
        # An MP3 encoder may introduce a small delay; use original PCM WAV
        # chapter times as navigational estimates, not exact MP3 sample pins.
        frame = round(section["start_seconds"] * 75)
        minute = frame // (75 * 60)
        second = (frame // 75) % 60
        subframe = frame % 75
        label = section["label"].replace('"', "'").replace("\r", " ").replace("\n", " ")
        if section["kind"] == "transition":
            label = "Transition " + label + " " + section["family"]
        else:
            label = "Track " + label
        lines.extend([
            "  TRACK " + str(index).zfill(2) + " AUDIO",
            '    TITLE "' + label + '"',
            "    INDEX 01 " + str(minute).zfill(2) + ":" +
            str(second).zfill(2) + ":" + str(subframe).zfill(2)
        ])
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def _encode_stream(ffmpeg, original, output, created, *, timeout_seconds):
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(original), "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-map_metadata", "-1", "-c:a", "libmp3lame", "-threads", "1",
        "-b:a", str(BITRATE_KBPS) + "k", "-write_xing", "0",
        "-f", "mp3", "pipe:1"
    ]
    with tempfile.TemporaryFile(mode="w+b") as errors:
        with output.open("xb") as destination:
            created.append(output)
            os.fchmod(destination.fileno(), 0o600)
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=errors, close_fds=True, start_new_session=True)
            total = 0
            sha = hashlib.sha256()
            deadline = time.monotonic() + timeout_seconds
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("Private MP3 rendering exceeded its strict time limit")
                    readable, _, _ = select.select([process.stdout.fileno()], [], [], remaining)
                    if not readable:
                        raise ValueError("Private MP3 rendering exceeded its strict time limit")
                    data = os.read(process.stdout.fileno(), READ_BYTES)
                    if not data:
                        break
                    total += len(data)
                    if total > MAX_PORTABLE_BYTES:
                        raise ValueError("Portable MP3 exceeds the bounded private output budget")
                    destination.write(data)
                    sha.update(data)
                if process.wait(timeout=max(.1, deadline - time.monotonic())) != 0:
                    errors.seek(0)
                    info = errors.read(2048).decode("utf-8", "replace").strip()
                    raise ValueError("Local FFmpeg MP3 encoder failed: " + info[:700])
                if total < 128:
                    raise ValueError("Local MP3 encoder produced no useful audio")
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
    return total, sha.hexdigest()


def export_portable(session_dir, complete_wav, new_mp3, *, timeout_seconds=600):
    """Make a usable portable MP3/CUE/M3U8 from an already admitted true WAV."""
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= MAX_TIME_SECONDS:
        raise ValueError("Set --timeout-seconds to a finite integer from 30..900")
    wav_path = Path(complete_wav).absolute()
    paths = _destination_paths(wav_path, new_mp3)
    # Verify every source receipt and canonical chapter boundary BEFORE any
    # sidecar or destination is created. This also verifies the entire WAV SHA.
    metadata = build_chapters(session_dir, wav_path)
    source_sha = metadata["wav_sha256"]
    wav_before = wav_path.lstat()
    if not stat.S_ISREG(wav_before.st_mode) or wav_path.is_symlink():
        raise ValueError("Full-set input WAV has been redirected")
    ffprobe, ffmpeg = _checked_tools()
    created = []
    try:
        written, portable_sha = _encode_stream(
            ffmpeg, wav_path, paths["mp3"], created,
            timeout_seconds=timeout_seconds)
        # Fail closed on source mutations during transcode, including
        # timestamps/identity changes without different final content.
        wav_after = wav_path.lstat()
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if identity(wav_before) != identity(wav_after) or digest(wav_path) != source_sha:
            raise ValueError("Original approved full WAV changed during portable export")
        cue = _cue_text(metadata["chapters"], paths["mp3"].name)
        playlist = (
            "#EXTM3U\n#EXTINF:" + str(round(metadata["duration_seconds"])) +
            ",MixLab private full DJ set\n" + paths["mp3"].name + "\n"
        ).encode("utf-8")
        receipt = {
            "schema_version": 1, "kind": "mixlab-private-portable-dj-delivery",
            "format": "MP3", "encoder": "installed-local-ffmpeg-libmp3lame",
            "bitrate_kbps": BITRATE_KBPS,
            "source_wav_sha256": source_sha,
            "source_duration_seconds": round(metadata["duration_seconds"], 6),
            "output_sha256": portable_sha, "output_bytes": written,
            "chapter_count": len(metadata["chapters"]),
            "chapters": metadata["chapters"],
            "chapter_note": "MP3 encoder delay means CUE times are approximate; exact frames are in source WAV",
            "private_rights_basis": "declared by source owner; no new license generated",
            "audio_uploaded": False, "model_generated_audio": False
        }
        _write_new(paths["cue"], cue, created)
        _write_new(paths["playlist"], playlist, created)
        _write_new(paths["receipt"], (
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8"), created)
    except BaseException:
        for file in reversed(created):
            file.unlink(missing_ok=True)
        raise
    return {
        "ready": True, "portable_mp3": str(paths["mp3"]),
        "cue": str(paths["cue"]), "playlist": str(paths["playlist"]),
        "private_receipt": str(paths["receipt"]), "source_wav_unchanged": True,
        "bitrate_kbps": BITRATE_KBPS, "source_chapter_count": len(metadata["chapters"]),
        "lossy": True, "automatic_musical_analysis": False,
        "audio_uploaded": False
    }


def main():
    parser = argparse.ArgumentParser(
        description="Produce a local portable MP3/CUE/M3U8 from an exact SHA-bound MixLab full WAV")
    parser.add_argument("session", help="Original private Set Composer session folder")
    parser.add_argument("complete_wav", help="Existing real full mix WAV with private receipt")
    parser.add_argument("new_mp3", help="New exclusive .mp3 output; never overwrites media")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        result = export_portable(args.session, args.complete_wav, args.new_mp3,
                                 timeout_seconds=args.timeout_seconds)
    except (ValueError, TypeError, OSError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(2, "MixLab portable export: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
