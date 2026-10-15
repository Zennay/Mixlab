"""Strict, bounded library ingest. No decoding services or source uploads."""
from array import array
import hashlib
import json
import math
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


def inspect_wav(path):
    """Validate every declared byte in bounded chunks, without float tuples."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Source missing or exceeds 32 MiB")
    try:
        with wave.open(str(path), "rb") as source:
            channels, width, rate, count, compression, _ = source.getparams()
            if channels not in (1, 2) or width != 2 or compression != "NONE":
                raise ValueError("Only PCM16 mono/stereo WAV is supported")
            if not 8000 <= rate <= 96000 or not 1 <= count <= MAX_FRAMES:
                raise ValueError("Sample rate or frame budget exceeded")
            pcm = hashlib.sha256()
            pcm.update(f"{rate}:{channels}:".encode())
            remaining = count
            while remaining:
                size = min(8192, remaining)
                block = source.readframes(size)
                if len(block) != size * channels * 2:
                    raise ValueError("Truncated WAV data")
                pcm.update(block)
                remaining -= size
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid PCM16 WAV") from exc
    return {"sample_rate": rate, "channels": channels, "frame_count": count,
            "duration_seconds": count / rate, "pcm_sha256": pcm.hexdigest()}


def pcm_blocks(path, start=0, frames=None, block_frames=4096):
    """Yield interleaved native int16 arrays; caller validates metadata first."""
    if type(block_frames) is not int or not 1 <= block_frames <= 65536:
        raise ValueError("Invalid block size")
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        if type(start) is not int or start < 0 or start > source.getnframes():
            raise ValueError("Invalid start frame")
        remaining = source.getnframes() - start if frames is None else frames
        if type(remaining) is not int or remaining < 0 or start + remaining > source.getnframes():
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
            raise ValueError("Source tempos must match; time stretching is not implemented")
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
                raise ValueError("Pair exceeds source clip")
        if a.get("partition") != b.get("partition"):
            raise ValueError("Pair crosses dataset partitions")


def validate_library(manifest_path):
    source = Path(manifest_path).resolve()
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("Manifest exceeds 1 MiB")
    def reject_constant(value):
        raise ValueError("Non-finite JSON constant")
    def unique_keys(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    manifest = _object(json.loads(source.read_text(), parse_constant=reject_constant,
                                  object_pairs_hook=unique_keys), "manifest")
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
        if track.get("rights") not in RIGHTS:
            raise ValueError("Explicit permission required")
        if not isinstance(track.get("provenance"), str) or not track["provenance"].strip():
            raise ValueError("Provenance required")
        raw = track.get("path")
        if not isinstance(raw, str) or not raw or "\\" in raw:
            raise ValueError("Path must be a relative POSIX path")
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Path traversal rejected")
        path = (source.parent / relative).resolve()
        if not path.is_relative_to(source.parent) or path.suffix.lower() != ".wav":
            raise ValueError("Source must be a WAV inside the library")
        sha = track.get("sha256")
        if not isinstance(sha, str) or not HASH.fullmatch(sha):
            raise ValueError("Invalid source checksum")
        info = inspect_wav(path)
        if digest(path) != sha:
            raise ValueError("Source checksum mismatch")
        number(track.get("bpm"), "manual bpm", 30, 300)
        if "downbeat_seconds" in track:
            number(track["downbeat_seconds"], "manual downbeat", 0, info["duration_seconds"])
        partition = track.get("partition")
        if partitioned and partition not in {"development", "evaluation"}:
            raise ValueError("All tracks need a development/evaluation partition")
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
