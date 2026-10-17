"""Offline, permission-declared music import into MixLab's canonical PCM16 sources.

Source file formats need an *already installed* local FFmpeg and ffprobe.
No downloads, streaming URLs, network uploads, model inference or new dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess

from .cueprep import (
    ID, SHA, MAX_SOURCE_BYTES, MAX_TRACK_SECONDS, _digest,
    _inspect_source, _number, _read_spec,
)
from .ingest import RIGHTS

SOURCE_FORMATS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus",
                  ".aif", ".aiff"}
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_TRACKS = 20
OUTPUT_RATE = 44100
OUTPUT_CHANNELS = 2
MAX_PROBE_BYTES = 65536


def _error(message):
    raise ValueError(message)


def _regular_source(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        _error("Source must be a relative local filename")
    relative = PurePosixPath(name)
    if (relative.is_absolute() or ".." in relative.parts
            or relative.suffix.lower() not in SOURCE_FORMATS):
        _error("Unsupported source format or unsafe relative filename")
    path = root
    for part in relative.parts:
        path = path / part
        try:
            meta = path.lstat()
        except OSError as exc:
            raise ValueError("Declared local source is unavailable") from exc
        if stat.S_ISLNK(meta.st_mode):
            _error("Symlinked source files or directories are not admitted")
    path = path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        _error("Media source must be a regular file within the private library")
    size = path.stat().st_size
    if not 0 < size <= MAX_INPUT_BYTES:
        _error("Source must be 1..512 MiB")
    return path


def _file_identity(meta):
    return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns)


def _fingerprint(path, expected=None):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Local source is unavailable") from exc
    with os.fdopen(fd, "rb") as src:
        before = os.fstat(src.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_INPUT_BYTES:
            _error("Invalid source size or type")
        h = hashlib.sha256()
        for chunk in iter(lambda: src.read(65536), b""):
            h.update(chunk)
        after = os.fstat(src.fileno())
    if (_file_identity(before) != _file_identity(after)
            or _file_identity(before) != _file_identity(path.lstat())):
        _error("Source changed during fingerprinting")
    observed = h.hexdigest()
    if expected is not None and observed != expected:
        _error("Source SHA-256 mismatch or changed during import")
    return observed, _file_identity(before)


def _format_metadata(path, ffprobe):
    # Restrict ffprobe to local file/pipe protocols. Never print private paths.
    cmd = [ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
           "-show_entries", "format=duration:stream=codec_type",
           "-of", "json", str(path)]
    try:
        output = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Local FFprobe could not inspect source") from exc
    if output.returncode != 0 or len(output.stdout) > MAX_PROBE_BYTES:
        _error("Unsupported or unreadable local audio media")
    try:
        info = json.loads(output.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid local media metadata") from exc
    streams = info.get("streams") if isinstance(info, dict) else None
    if not isinstance(streams, list) or not any(
        isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams
    ):
        _error("Media contains no declared audio stream")
    try:
        duration = float(info.get("format", {}).get("duration", "nan"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Media duration is unavailable") from exc
    if not math.isfinite(duration) or not 0 < duration <= MAX_TRACK_SECONDS:
        _error("Media must have an explicit duration of at most 15 minutes")
    return duration


def _transcode(source, target, ffmpeg, timeout_seconds):
    # -n and a newly created private parent protect any existing files.
    # Strip source tags/artwork and decode only the first audio stream. One
    # filter/codec worker avoids accidental server CPU saturation.
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
           "-protocol_whitelist", "file,pipe", "-i", str(source),
           "-map", "0:a:0", "-vn", "-sn", "-dn",
           "-map_metadata", "-1", "-map_chapters", "-1",
           "-threads", "1", "-filter_threads", "1",
           "-ac", str(OUTPUT_CHANNELS), "-ar", str(OUTPUT_RATE),
           "-c:a", "pcm_s16le", "-f", "wav", "-fs", str(MAX_SOURCE_BYTES),
           "-n", str(target)]
    try:
        with subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) as child:
            try:
                child.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                child.kill()
                child.wait()
                raise ValueError("Local audio decoding exceeded its time limit") from exc
            if child.returncode != 0:
                _error("Local FFmpeg could not decode this permitted audio file")
    except OSError as exc:
        raise ValueError("Local FFmpeg executable is unavailable") from exc
    if not target.is_file() or target.is_symlink():
        _error("Local decoding did not produce a WAV")
    target.chmod(0o600)


def _checked_tools():
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        _error("FFmpeg and FFprobe must already be installed locally; no installation performed")
    return ffprobe, ffmpeg


def _validate_spec(spec):
    records, pairs = spec.get("tracks"), spec.get("pairs")
    if not isinstance(records, list) or not 2 <= len(records) <= MAX_TRACKS:
        _error("Import requires 2..20 permitted tracks")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 10:
        _error("Import requires 1..10 declared track pairs")
    by_id, ids, identities = {}, set(), {}
    partitioned = any(isinstance(r, dict) and "partition" in r for r in records)
    for record in records:
        if not isinstance(record, dict):
            _error("Invalid track record")
        tid = record.get("id")
        if not isinstance(tid, str) or not ID.fullmatch(tid) or tid in ids:
            _error("Duplicate or invalid track ID")
        ids.add(tid)
        rights, provenance = record.get("rights"), record.get("provenance")
        if rights not in RIGHTS or not isinstance(provenance, str) or not provenance.strip():
            _error("Every source needs explicit permitted rights and provenance")
        _number(record.get("bpm"), "manually verified BPM", 30, 300)
        sha = record.get("sha256")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            _error("Every source requires a pinned lowercase SHA-256")
        if "first_downbeat_seconds" in record:
            _number(record["first_downbeat_seconds"], "manual first downbeat", 0, MAX_TRACK_SECONDS)
        recording = record.get("recording_id", tid)
        if not isinstance(recording, str) or not ID.fullmatch(recording):
            _error("Invalid recording ID")
        partition = record.get("partition")
        if partitioned and partition not in ("development", "evaluation"):
            _error("All tracks require a development/evaluation partition")
        for identity in ("source:" + sha, "recording:" + recording):
            if identity in identities and identities[identity] != partition:
                _error("Source recording leaks across dataset partitions")
            identities[identity] = partition
        by_id[tid] = record
    seen_pairs = set()
    for pair in pairs:
        if not isinstance(pair, dict):
            _error("Invalid transition pair")
        pid, a, b = pair.get("id"), pair.get("a"), pair.get("b")
        if not isinstance(pid, str) or not ID.fullmatch(pid) or pid in seen_pairs:
            _error("Duplicate or invalid pair ID")
        seen_pairs.add(pid)
        if a not in by_id or b not in by_id or a == b:
            _error("Pair needs two different declared tracks")
        if by_id[a]["bpm"] != by_id[b]["bpm"]:
            _error("Current renderer requires equal manually verified pair BPM")
        if partitioned and by_id[a]["partition"] != by_id[b]["partition"]:
            _error("Pair crosses dataset partitions")
        for label in ("a_start_seconds", "b_start_seconds"):
            if label in pair:
                _number(pair[label], "manual cue time", 0, MAX_TRACK_SECONDS)
        beats = pair.get("beats", 8)
        if type(beats) is not int or not 1 <= beats <= 64:
            _error("Each pair needs 1..64 beats")
    return records, pairs


def import_library(spec_path, destination, *, timeout_seconds=600):
    """Convert one local private source library into a reusable PCM16 workspace.

    The caller owns and supplies every source SHA, licence/provenance and BPM.
    The generated source_manifest.json is suitable for cue_suggest and cueprep.
    """
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 900:
        _error("Decoder timeout must be 30..900 seconds per track")
    spec_path, destination = Path(spec_path).absolute(), Path(destination).absolute()
    spec = _read_spec(spec_path)
    records, pairs = _validate_spec(spec)
    base = spec_path.parent.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        _error("Destination must be a new directory, never an existing music library")
    if (destination == base or destination.is_relative_to(base)
            or base.is_relative_to(destination)):
        _error("Output must remain separate from the private input music library")
    if not destination.parent.is_dir():
        _error("Output parent directory must exist")
    for parent in (destination, *destination.parents):
        if (parent / ".git").exists():
            _error("Never import private audio into a source-code repository")
    ffprobe, ffmpeg = _checked_tools()

    # Cheap admission and hash-pin ALL source tracks before creating output.
    prepared = []
    for record in records:
        path = _regular_source(base, record.get("path"))
        sha, identity = _fingerprint(path, record["sha256"])
        duration = _format_metadata(path, ffprobe)
        prepared.append((record, path, sha, identity, duration))

    destination.mkdir(mode=0o700)
    try:
        audio_dir = destination / "audio"
        audio_dir.mkdir(mode=0o700)
        imported_tracks, receipts = [], []
        for record, source, sha, identity, duration in prepared:
            target = audio_dir / (record["id"] + ".wav")
            _transcode(source, target, ffmpeg, timeout_seconds)
            current_sha, current_identity = _fingerprint(source, sha)
            if current_identity != identity or current_sha != sha:
                _error("Original audio changed during conversion")
            if target.stat().st_size > MAX_SOURCE_BYTES:
                _error("Decoded WAV exceeds bounded full-track capacity")
            wav_sha = _digest(target)
            info = _inspect_source(target, wav_sha)
            if (info["rate"] != OUTPUT_RATE or info["channels"] != OUTPUT_CHANNELS
                    or not 0 < info["frames"] <= OUTPUT_RATE * MAX_TRACK_SECONDS):
                _error("Decoded WAV is outside supported canonical audio format")
            tid = record["id"]
            imported = {"id": tid, "path": f"audio/{tid}.wav",
                        "sha256": wav_sha, "bpm": record["bpm"],
                        "rights": record["rights"], "provenance": record["provenance"],
                        "recording_id": record.get("recording_id", tid)}
            for name in ("partition", "first_downbeat_seconds"):
                if name in record:
                    imported[name] = record[name]
            if (imported.get("first_downbeat_seconds", 0) >=
                    info["frames"] / OUTPUT_RATE):
                _error("Declared first downbeat is outside the imported WAV")
            imported_tracks.append(imported)
            receipts.append({"track_id": tid, "source_sha256": sha,
                             "normalized_sha256": wav_sha, "source_format": source.suffix.lower(),
                             "declared_duration_seconds": duration,
                             "normalized_frames": info["frames"],
                             "transcoding": "ffmpeg PCM16 stereo at 44100 Hz; source metadata stripped"})
        result = {"schema_version": 1, "purpose": spec.get("purpose", "development-pilot"),
                  "tracks": imported_tracks, "pairs": [
                      {**p, "a_start_seconds": p.get("a_start_seconds", 0),
                       "b_start_seconds": p.get("b_start_seconds", 0)} for p in pairs]}
        (destination / "source_manifest.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8")
        private = {"schema_version": 1, "kind": "local-media-import",
                   "original_manifest_sha256": _digest(spec_path),
                   "normalize_rate": OUTPUT_RATE, "normalize_channels": OUTPUT_CHANNELS,
                   "tracks": receipts,
                   "limitations": ["manual BPM and cue alignment required",
                                   "rights declarations are not legally verified",
                                   "not a listening-preference result"]}
        (destination / "import-receipt.private.json").write_text(
            json.dumps(private, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8")
        os.chmod(destination / "source_manifest.json", 0o600)
        os.chmod(destination / "import-receipt.private.json", 0o600)
        return destination / "source_manifest.json"
    except BaseException:
        # Never remove an existing directory: creation was exclusively gated.
        shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Import private permitted MP3/FLAC/M4A/audio into MixLab PCM16 sources")
    parser.add_argument("source_manifest", help="Private source spec JSON with SHA and rights")
    parser.add_argument("destination", help="New private directory outside Git/source music")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        result = import_library(args.source_manifest, args.destination,
                                timeout_seconds=args.timeout_seconds)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab media import: {exc}\n")
    print(json.dumps({"source_manifest": str(result),
                      "status": "imported-local-only", "review_cues_manually": True}))


if __name__ == "__main__":
    main()
