"""Optional local, consent-bound compressed delivery of an already verified set.

This is a *distribution* format conversion, never a new DJ mix or automatic
mastering step. Existing private WAVs, audio sources and receipts are immutable.
Requires already installed local FFmpeg/FFprobe; no downloads or uploads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from .ingest import digest
from .media_import import _checked_tools
from .set_player import PAGE, build_chapters
from .set_composer import _session_catalog

FORMATS = {
    ".mp3": ("libmp3lame", "mp3", "mp3"),
    ".flac": ("flac", "flac", "flac"),
}
MAX_ENCODE_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024


def _admit_target(path, source_wav, session_root):
    target = Path(path).absolute()
    if (target.suffix.lower() not in FORMATS or target.exists() or
            target.is_symlink() or not target.parent.is_dir() or
            target.is_relative_to(session_root) or
            target.parent == source_wav.parent and target.name == source_wav.name):
        raise ValueError("Choose a NEW private .mp3 or .flac path outside the Studio session")
    receipt = target.with_name(target.name + ".receipt.private.json")
    page = target.with_name(target.name + ".player.html")
    if receipt.exists() or receipt.is_symlink() or page.exists() or page.is_symlink():
        raise ValueError("Private receipt or chapter-player output already exists")
    for node in (target, *target.parents):
        if node.is_symlink() or (node / ".git").exists():
            raise ValueError("No private audio through symlink directories or Git checkouts")
    return target, receipt, page


def _probe_encoded(ffprobe, path, codec, duration_seconds, timeout_seconds):
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,channels,sample_rate:format=duration",
         "-of", "json", str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=min(60, timeout_seconds), check=False,
    )
    if completed.returncode or len(completed.stdout) > 65536:
        raise ValueError("Encoded file cannot be inspected by local FFprobe")
    try:
        info = json.loads(completed.stdout)
        streams = info["streams"]
        if not isinstance(streams, list) or len(streams) != 1:
            raise ValueError("Expected exactly one encoded audio stream")
        stream = streams[0]
        duration = float(info["format"]["duration"])
        channels = int(stream["channels"])
        rate = int(stream["sample_rate"])
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, json.JSONDecodeError) as exc:
        raise ValueError("Local compressed output contains invalid audio metadata") from exc
    if (stream.get("codec_name") != codec or channels not in (1, 2)
            or not 8000 <= rate <= 96000 or not math.isfinite(duration)
            or abs(duration - duration_seconds) > 1.0):
        raise ValueError("Compressed delivery audio differs unexpectedly from the source timeline")
    return {"duration_seconds": duration, "channels": channels,
            "sample_rate": rate, "codec_name": codec}


def _compressed_page(target, original_chapters, output_sha):
    # The existing self-contained chapter player can play MP3 and FLAC with
    # browser native media support, using the already verified PCM timeline.
    # The waveform is the original PCM WAV's sparse profile, not a fake
    # computed MP3/FLAC profile or a blind listening score.
    data = dict(original_chapters)
    data["wav_name"] = target.name
    data["wav_sha256"] = output_sha
    data["waveform_basis"] = "source PCM WAV sparse amplitude profile before private delivery encoding"
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    raw = raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    page = PAGE.replace("__DATA__", raw).encode("utf-8")
    if len(page) > MAX_JSON_BYTES:
        raise ValueError("Compressed offline chapter player exceeds 2 MiB")
    return page


def export_delivery(session, verified_wav, new_compressed,
                    *, bitrate_kbps=192, timeout_seconds=900):
    """Encode a completed receipt-verified WAV and atomically publish output."""
    if type(bitrate_kbps) is not int or bitrate_kbps not in (128, 192, 256, 320):
        raise ValueError("Use an explicit MP3 bitrate of 128/192/256/320 kbps")
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 1800:
        raise ValueError("Encoding timeout must be 30..1800 seconds")
    root, catalog = _session_catalog(session)
    source = Path(verified_wav).absolute()
    # build_chapters verifies SHA-256, immutable official Studio receipt,
    # source music, actual PCM16 frames and exact transition render provenance.
    chapters = build_chapters(root, source)
    target, receipt_file, player_file = _admit_target(new_compressed, source, root)
    suffix = target.suffix.lower()
    codec, muxer, expected_codec = FORMATS[suffix]
    ffprobe, ffmpeg = _checked_tools()
    ffmpeg_args = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1",
        "-c:a", codec, "-threads", "2"
    ]
    if suffix == ".mp3":
        ffmpeg_args += ["-b:a", f"{bitrate_kbps}k"]
    ffmpeg_args += ["-f", muxer]
    # Temp output lives under a private, 0700 directory in the same
    # filesystem. Hard-link publication fails if somebody claims target.
    with tempfile.TemporaryDirectory(prefix=".mixlab-delivery-", dir=target.parent) as temp_dir:
        os.chmod(temp_dir, 0o700)
        encoded = Path(temp_dir) / ("encoded" + suffix)
        completed = subprocess.run(
            ffmpeg_args + ["-n", str(encoded)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=timeout_seconds, check=False,
        )
        if completed.returncode:
            raise ValueError("Installed FFmpeg could not encode the selected private format")
        info = encoded.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ENCODE_BYTES:
            raise ValueError("Encoded private delivery exceeds 512 MiB or is empty")
        # FFmpeg commonly creates mode 0644 files according to process umask;
        # restrict the inode BEFORE hard-linking into the visible output folder.
        os.chmod(encoded, 0o600)
        format_info = _probe_encoded(
            ffprobe, encoded, expected_codec, chapters["duration_seconds"], timeout_seconds)
        # Refuse publish if the source WAV changed during the external encoder.
        if digest(source) != chapters["wav_sha256"]:
            raise ValueError("Source WAV changed during private delivery encoding")
        output_hash = digest(encoded)
        receipt = {
            "schema_version": 1, "kind": "private-compressed-continuous-set-delivery",
            "source_set_sha256": chapters["wav_sha256"],
            "source_session_sha256": catalog["session_sha256"],
            "studio_receipt_sha256": catalog["studio_sha256"],
            "output_sha256": output_hash, "format": suffix[1:],
            "codec": expected_codec, "audio_metadata": format_info,
            "bitrate_kbps": bitrate_kbps if suffix == ".mp3" else None,
            "original_pcm16_wav_preserved": True,
            "metadata_stripped": True, "human_preference_proven": False,
            "rights": "Local source rights declarations still apply; check sharing/distribution permission",
        }
        receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2,
                                    allow_nan=False) + "\n").encode("utf-8")
        if len(receipt_bytes) > 65536:
            raise ValueError("Encoded output receipt unexpectedly exceeds 64 KiB")
        published = False
        try:
            os.link(encoded, target)
            published = True
            with receipt_file.open("xb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(receipt_bytes)
        except BaseException:
            receipt_file.unlink(missing_ok=True)
            if published:
                target.unlink(missing_ok=True)
            raise
    result = {"private_delivery": str(target), "receipt": str(receipt_file),
              "format": suffix[1:], "source_pcm16_unchanged": True,
              "offline_player": None, "user_distribution_rights_required": True}
    try:
        raw_page = _compressed_page(target, chapters, output_hash)
        with player_file.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw_page)
        result["offline_player"] = str(player_file)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["player_warning"] = "Compressed music and receipt were published; optional player failed: " + str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Encode private receipt-verified DJ WAV to local MP3/FLAC (installed FFmpeg)")
    parser.add_argument("session", help="Original completed private Studio")
    parser.add_argument("completed_wav", help="Existing SHA-verified complete-set PCM16 WAV")
    parser.add_argument("new_output", help="NEW private .mp3 or .flac file outside Git/session")
    parser.add_argument("--bitrate-kbps", type=int, default=192,
                        choices=(128, 192, 256, 320), help="MP3 only; FLAC is lossless")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        result = export_delivery(args.session, args.completed_wav, args.new_output,
                                 bitrate_kbps=args.bitrate_kbps,
                                 timeout_seconds=args.timeout_seconds)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, "MixLab Private Delivery: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
