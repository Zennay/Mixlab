"""Strict, bounded library ingest. No decoding services or source uploads."""
from array import array
import hashlib
import json
import math
import os
import stat
from pathlib import Path
import re
import sys
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
RIGHTS = {"synthetic", "licensed", "user-permitted", "public-domain"}


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and within {low}..{high}")
    return value


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _source_snapshot(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns)


def inspect_wav_and_digest(path):
    """Check PCM and checksum on ONE bounded file descriptor, reject visible races.

    The final identity recheck catches ordinary source replacements/edits
    during validation; this is not a signed or immutable filesystem snapshot.
    """
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Source is not an accessible regular PCM16 WAV") from exc
    try:
        with os.fdopen(fd, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
                raise ValueError("Source missing or exceeds 32 MiB")
            try:
                with wave.open(source, "rb") as audio:
                    channels, width, rate, count, compression, _ = audio.getparams()
                    if channels not in (1, 2) or width != 2 or compression != "NONE":
                        raise ValueError("Only PCM16 mono/stereo WAV is supported")
                    if not 8000 <= rate <= 96000 or not 1 <= count <= MAX_FRAMES:
                        raise ValueError("Sample rate or frame budget exceeded")
                    pcm = hashlib.sha256()
                    pcm.update(f"{rate}:{channels}:".encode())
                    remaining = count
                    while remaining:
                        size = min(8192, remaining)
                        block = audio.readframes(size)
                        if len(block) != size * channels * 2:
                            raise ValueError("Truncated WAV data")
                        pcm.update(block)
                        remaining -= size
            except (wave.Error, EOFError) as exc:
                raise ValueError("Invalid PCM16 WAV") from exc
            source.seek(0)
            content = hashlib.sha256()
            total = 0
            for block in iter(lambda: source.read(65536), b""):
                total += len(block)
                if total > MAX_BYTES:
                    raise ValueError("Source grew beyond 32 MiB during inspection")
                content.update(block)
            after = os.fstat(source.fileno())
    except OSError as exc:
        raise ValueError("Source changed or became unreadable during inspection") from exc
    try:
        final = os.lstat(path)
    except OSError as exc:
        raise ValueError("Source changed during inspection") from exc
    if (_source_snapshot(before) != _source_snapshot(after)
            or _source_snapshot(before) != _source_snapshot(final)
            or not stat.S_ISREG(final.st_mode)):
        raise ValueError("Source changed during inspection")
    return ({"sample_rate": rate, "channels": channels, "frame_count": count,
             "duration_seconds": count / rate, "pcm_sha256": pcm.hexdigest()},
            content.hexdigest())


def inspect_wav(path):
    """Public metadata-only interface backed by the same one-fd verification."""
    info, _checksum = inspect_wav_and_digest(path)
    return info

def pcm_blocks(path, start=0, frames=None, block_frames=4096):
    """Stream bounded PCM16 from one regular descriptor, rejecting visible edits.

    Unlike re-opening a previously validated filename, RIFF validation and
    decoded PCM share the same descriptor. Post-read inode/size/mtime/ctime
    checks detect ordinary concurrent edits and path replacement; they are
    not an atomic snapshot against a hostile same-metadata writer.
    """
    if type(block_frames) is not int or not 1 <= block_frames <= 65536:
        raise ValueError("Invalid block size")
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        initial = os.lstat(path)
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("PCM source must be a regular file")
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("PCM source is not an accessible regular WAV") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or
                    not 0 < before.st_size <= MAX_BYTES or
                    _source_snapshot(initial) != _source_snapshot(before)):
                raise ValueError("PCM source size or identity invalid")
            try:
                with wave.open(stream, "rb") as source:
                    channels, width, rate, count, compression, _ = source.getparams()
                    if (channels not in (1, 2) or width != 2 or compression != "NONE" or
                            not 8000 <= rate <= 96000 or not 1 <= count <= MAX_FRAMES):
                        raise ValueError("Only bounded PCM16 mono/stereo WAV is supported")
                    if type(start) is not int or start < 0 or start > count:
                        raise ValueError("Invalid start frame")
                    remaining = count - start if frames is None else frames
                    if type(remaining) is not int or remaining < 0 or start + remaining > count:
                        raise ValueError("Invalid frame range")
                    source.setpos(start)
                    while remaining:
                        size = min(block_frames, remaining)
                        raw = source.readframes(size)
                        if len(raw) != size * channels * 2:
                            raise ValueError("Truncated WAV data")
                        values = array("h")
                        values.frombytes(raw)
                        if sys.byteorder != "little":
                            values.byteswap()
                        yield values
                        remaining -= size
            except (wave.Error, EOFError) as exc:
                raise ValueError("Invalid PCM16 WAV source") from exc
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ValueError("PCM source changed while reading") from exc
    try:
        final = os.lstat(path)
    except OSError as exc:
        raise ValueError("PCM source changed while reading") from exc
    if (not stat.S_ISREG(final.st_mode) or
            _source_snapshot(before) != _source_snapshot(after) or
            _source_snapshot(before) != _source_snapshot(final)):
        raise ValueError("PCM source changed while reading")


def _identifier(value, name):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"Invalid {name}")
    return value


def _object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _pairs(pairs, tracks):
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 10:
        raise ValueError("Register 1–10 pairs")
    ids = set()
    for pair in pairs:
        _object(pair, "pair")
        pid = _identifier(pair.get("id"), "pair id")
        if pid in ids:
            raise ValueError("Duplicate pair id")
        ids.add(pid)
        a_id, b_id = pair.get("a"), pair.get("b")
        _identifier(a_id, "pair a")
        _identifier(b_id, "pair b")
        if a_id not in tracks or b_id not in tracks or a_id == b_id:
            raise ValueError("Pair needs distinct registered tracks")
        a, b = tracks[a_id], tracks[b_id]
        bpm = number(pair.get("bpm"), "pair bpm", 30, 300)
        if bpm != a["bpm"] or bpm != b["bpm"]:
            raise ValueError("Prototype requires equal source tempos; time stretching is not implemented")
        beats = pair.get("beats", 8)
        if type(beats) is not int or not 1 <= beats <= 64:
            raise ValueError("beats must be an integer from 1 to 64")
        duration = beats * 60 / bpm
        if duration > 120:
            raise ValueError("Transition exceeds duration budget")
        if (a["sample_rate"], a["channels"]) != (b["sample_rate"], b["channels"]):
            raise ValueError("Pair format mismatch")
        count = round(duration * a["sample_rate"])
        if count > MAX_FRAMES:
            raise ValueError("Transition exceeds frame budget")
        for track, key in ((a, "a_start"), (b, "b_start")):
            start = number(pair.get(key, 0), key, 0, 250)
            if round(start * track["sample_rate"]) + count > track["frame_count"]:
                raise ValueError("Pair excerpt is too short for its recipe")
        if a.get("partition") != b.get("partition"):
            raise ValueError("Pair crosses dataset partitions")


def _reject_excessive_json_nesting(raw, max_depth=64):
    """Bound JSON containers independently of interpreter recursion limits.

    Count only brackets outside quoted strings, respecting JSON escapes.
    Leave full syntax validation to json.loads; this is an early DoS guard.
    """
    depth = 0
    quoted = False
    escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                raise ValueError("Manifest JSON nesting limit exceeded")
        elif char in "]}":
            depth -= 1


MAX_MANIFEST_BYTES = 1024 * 1024


def _read_bounded_manifest(path):
    """Read at most 1 MiB from one regular descriptor; never open a FIFO blocking.

    The pathname remains local and no input bytes or private path enter errors.
    Metadata checks detect ordinary replacements and edits, not adversarial
    same-metadata rewrites or a transactional filesystem snapshot.
    """
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        initial = os.lstat(path)
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("Manifest must be a regular file, not a link or pipe")
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Manifest file unavailable") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or identity(before) != identity(initial):
                raise ValueError("Manifest changed before reading")
            if not 0 < before.st_size <= MAX_MANIFEST_BYTES:
                raise ValueError("Manifest size must be 1..1048576 bytes")
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise ValueError("Manifest exceeds 1 MiB during reading")
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ValueError("Manifest read failed") from exc
    try:
        final = os.lstat(path)
    except OSError as exc:
        raise ValueError("Manifest changed during reading") from exc
    if (not stat.S_ISREG(final.st_mode) or
            identity(initial) != identity(after) or identity(initial) != identity(final)):
        raise ValueError("Manifest changed during reading")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Manifest is not UTF-8 text") from exc


def validate_library(manifest_path):
    # Preserve the lexical final component so O_NOFOLLOW/lstat can reject
    # a manifest symlink, rather than resolving it before secure admission.
    source = Path(manifest_path).absolute()
    raw = _read_bounded_manifest(source)
    def reject_constant(value):
        raise ValueError("Non-finite JSON constant")
    def unique_keys(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    _reject_excessive_json_nesting(raw)
    try:
        parsed = json.loads(raw, parse_constant=reject_constant,
                            object_pairs_hook=unique_keys)
    except RecursionError as exc:
        # Untrusted, deeply nested JSON is a validation failure, not an
        # uncaught traceback from the CLI or an ambiguous runner crash.
        raise ValueError("Manifest JSON nesting limit exceeded") from exc
    manifest = _object(parsed, "manifest")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unsupported library schema")
    records = manifest.get("tracks")
    if not isinstance(records, list) or not 2 <= len(records) <= 50:
        raise ValueError("Library must contain 2–50 tracks")
    tracks, identities = {}, {}
    partitioned = any(isinstance(t, dict) and "partition" in t for t in records)
    for track in records:
        _object(track, "track")
        tid = _identifier(track.get("id"), "track id")
        if tid in tracks:
            raise ValueError("Duplicate track id")
        rights = track.get("rights")
        if not isinstance(rights, str) or rights not in RIGHTS:
            raise ValueError("Explicit permission required")
        if not isinstance(track.get("provenance"), str) or not track["provenance"].strip():
            raise ValueError("Provenance required")
        raw = track.get("path")
        if not isinstance(raw, str) or not raw or "\\" in raw:
            raise ValueError("Path must be a relative POSIX path")
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source path must remain within the library directory; traversal rejected")
        path = (source.parent / relative).resolve()
        if not path.is_relative_to(source.parent) or path.suffix.lower() != ".wav":
            raise ValueError("Source must be a WAV inside the library")
        partition = track.get("partition")
        if partitioned and (not isinstance(partition, str) or
                            partition not in {"development", "evaluation"}):
            raise ValueError("All tracks need a development/evaluation partition")
        sha = track.get("sha256")
        if not isinstance(sha, str) or not HASH.fullmatch(sha):
            raise ValueError("Invalid source checksum")
        info, observed_sha = inspect_wav_and_digest(path)
        if observed_sha != sha:
            raise ValueError("Source checksum mismatch")
        number(track.get("bpm"), "manual bpm", 30, 300)
        if "downbeat_seconds" in track:
            number(track["downbeat_seconds"], "manual downbeat", 0, info["duration_seconds"])

        recording = track.get("recording_id", tid)
        _identifier(recording, "recording id")
        for identity in ("pcm:" + info["pcm_sha256"], "recording:" + recording):
            if identity in identities and identities[identity] != partition:
                raise ValueError("Recording leaks across partitions")
            identities[identity] = partition
        tracks[tid] = {**track, **info, "resolved_path": path}
    _pairs(manifest.get("pairs"), tracks)
    return manifest, tracks


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate a private MixLab library")
    parser.add_argument("manifest")
    args = parser.parse_args()
    try:
        manifest, tracks = validate_library(args.manifest)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, f"MixLab ingest: {exc}\n")
    print(json.dumps({"valid": True, "tracks": len(tracks), "pairs": len(manifest["pairs"]),
                      "partitioned": all("partition" in t for t in tracks.values())}))


if __name__ == "__main__":
    main()
