"""Private full-length PCM16 WAV -> bounded MixLab transition excerpts.

This is a *manual cue* compiler, not beat/phrase detection, time stretching,
source separation, or a music licence verifier. Runs entirely on the user's
machine. It does not write audio to git, web services, or standard output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import wave

from mixlab.ingest import MAX_BYTES, MAX_FRAMES, RIGHTS, validate_library

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_TRACK_SECONDS = 15 * 60
MAX_SOURCE_MANIFEST_BYTES = 1024 * 1024


def _fail(message: str):
    raise ValueError(message)


def _number(value, label, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        _fail(f"Invalid {label}: expected finite number in {low}..{high}")
    return value


def _name(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        _fail(f"Invalid {label}")
    return value


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("Duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    _fail("Nonfinite JSON number")


def _read_spec(spec_path):
    if spec_path.is_symlink() or not spec_path.is_file():
        _fail("Source manifest must be a regular, non-link file")
    with spec_path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE_MANIFEST_BYTES:
            _fail("Source manifest exceeds 1 MiB or is empty")
        raw = stream.read(MAX_SOURCE_MANIFEST_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) != before.st_size or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        _fail("Source manifest changed during reading")
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=_constant, object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid source manifest JSON") from exc
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        _fail("Unsupported source manifest schema")
    return value


def _source_path(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        _fail("Source path must be a relative POSIX WAV path")
    parts = PurePosixPath(name)
    if parts.is_absolute() or any(p in ("..", ".") for p in parts.parts) or parts.suffix.lower() != ".wav":
        _fail("Only relative WAV paths under the source manifest directory are supported")
    current = root
    for part in parts.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise ValueError("Source WAV path unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            _fail("Source symlinks are not permitted")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _fail("Source WAV outside local library")
    return resolved


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _inspect_source(path, expected_sha):
    # Explicit sha256 is a prerequisite: editing a track requires a new spec.
    if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha):
        _fail("Full-track SHA-256 declaration is required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Full-track WAV unavailable") from exc
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE_BYTES:
            _fail("Full-track size must be 1..256 MiB")
        try:
            with wave.open(handle, "rb") as audio:
                channels, width, rate, frames, compression, _ = audio.getparams()
                if (channels not in (1, 2) or width != 2 or compression != "NONE" or
                    not 8000 <= rate <= 96000 or frames < 1 or frames > rate * MAX_TRACK_SECONDS):
                    _fail("Only PCM16 mono/stereo WAV up to 15 minutes is supported")
        except (wave.Error, EOFError) as exc:
            raise ValueError("Invalid full-track WAV") from exc
        handle.seek(0)
        digester = hashlib.sha256()
        for part in iter(lambda: handle.read(65536), b""):
            digester.update(part)
        after = os.fstat(handle.fileno())
    if _identity(before) != _identity(after) or _identity(before) != _identity(path.lstat()):
        _fail("Full-track WAV changed during inspection")
    if digester.hexdigest() != expected_sha:
        _fail("Full-track checksum mismatch")
    return {"channels": channels, "rate": rate, "frames": frames, "sha256": expected_sha,
            "identity": _identity(before)}


def _extract(source, target, start_frame, frame_count, info):
    # Exclusive output, one file descriptor, fixed-sized PCM chunks.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(source, flags)
    with os.fdopen(fd, "rb") as handle:
        if _identity(os.fstat(handle.fileno())) != info["identity"]:
            _fail("Full-track WAV changed after initial inspection")
        with wave.open(handle, "rb") as audio:
            if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth(),
                audio.getnframes()) != (info["channels"], info["rate"], 2, info["frames"]):
                _fail("Full-track WAV format changed")
            audio.setpos(start_frame)
            with target.open("xb") as output:
                with wave.open(output, "wb") as excerpt:
                    excerpt.setnchannels(info["channels"])
                    excerpt.setsampwidth(2)
                    excerpt.setframerate(info["rate"])
                    excerpt.setnframes(frame_count)
                    remaining = frame_count
                    while remaining:
                        n = min(4096, remaining)
                        raw = audio.readframes(n)
                        if len(raw) != n * info["channels"] * 2:
                            _fail("Source WAV truncated during excerpt compilation")
                        excerpt.writeframesraw(raw)
                        remaining -= n
        if (_identity(os.fstat(handle.fileno())) != info["identity"]
                or _identity(source.lstat()) != info["identity"]):
            _fail("Full-track WAV changed during excerpt compilation")


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(65536), b""):
            h.update(part)
    return h.hexdigest()


def compile_cues(spec_path, destination):
    """Create a new private, validated MixLab excerpt library; never overwrite."""
    spec_path = Path(spec_path).absolute()
    destination = Path(destination).absolute()
    spec = _read_spec(spec_path)
    root = spec_path.parent.resolve(strict=True)
    tracks = spec.get("tracks")
    pairs = spec.get("pairs")
    if not isinstance(tracks, list) or not 2 <= len(tracks) <= 20:
        _fail("Provide 2..20 permitted source tracks")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 10:
        _fail("Provide 1..10 transition pairs")
    if destination == root or destination == spec_path or destination.exists() or destination.is_symlink():
        _fail("Destination must be a new private directory")
    if destination.is_relative_to(root):
        _fail("Keep private output outside the source library directory")

    catalog = {}
    partitioned = any(isinstance(t, dict) and "partition" in t for t in tracks)
    for record in tracks:
        if not isinstance(record, dict):
            _fail("Track must be an object")
        tid = _name(record.get("id"), "track ID")
        if tid in catalog:
            _fail("Duplicate full-track ID")
        if record.get("rights") not in RIGHTS or not isinstance(record.get("provenance"), str) or not record["provenance"].strip():
            _fail("Explicit rights declaration and provenance are required")
        _number(record.get("bpm"), "manual track BPM", 30, 300)
        if partitioned and record.get("partition") not in ("development", "evaluation"):
            _fail("All full tracks need a partition when any is partitioned")
        recording = _name(record.get("recording_id", tid), "recording ID")
        path = _source_path(root, record.get("path"))
        info = _inspect_source(path, record.get("sha256"))
        catalog[tid] = {"record": record, "path": path, "info": info, "recording": recording}

    jobs = []
    pair_output = []
    for item in pairs:
        if not isinstance(item, dict):
            _fail("Pair must be an object")
        pid = _name(item.get("id"), "pair ID")
        if any(p["id"] == pid for p in pair_output):
            _fail("Duplicate pair ID")
        a, b = item.get("a"), item.get("b")
        if a not in catalog or b not in catalog or a == b:
            _fail("Each pair needs two distinct declared source tracks")
        left, right = catalog[a], catalog[b]
        bpm = left["record"]["bpm"]
        if bpm != right["record"]["bpm"] or (left["info"]["rate"], left["info"]["channels"]) != (
            right["info"]["rate"], right["info"]["channels"]):
            _fail("Equal manually verified BPM, sample rate and channels required")
        if partitioned and left["record"]["partition"] != right["record"]["partition"]:
            _fail("Evaluation/development pairs must not cross partitions")
        beats = item.get("beats", 8)
        if type(beats) is not int or not 1 <= beats <= 64:
            _fail("Pair beats must be 1..64")
        duration = beats * 60. / bpm
        rate = left["info"]["rate"]
        frames = round(duration * rate)
        if not 2 <= frames <= MAX_FRAMES or 44 + frames * left["info"]["channels"] * 2 > MAX_BYTES:
            _fail("Transition exceeds bounded renderer excerpt limits")
        for side, source_id in (("a", a), ("b", b)):
            cue = _number(item.get(side + "_start_seconds"), "manual cue seconds", 0, MAX_TRACK_SECONDS)
            source = catalog[source_id]
            start_frame = round(cue * rate)
            if start_frame + frames > source["info"]["frames"]:
                _fail("Manual cue ends outside full-track WAV")
            clip_id = f"{pid}-{side}"
            jobs.append((clip_id, source_id, start_frame, frames, cue))
        pair_output.append({"id": pid, "a": f"{pid}-a", "b": f"{pid}-b",
                            "bpm": bpm, "beats": beats, "a_start": 0, "b_start": 0})

    destination.mkdir(mode=0o700, parents=False)
    try:
        output_tracks, mappings = [], []
        for clip_id, source_id, start_frame, frames, cue in jobs:
            entry = catalog[source_id]
            rec = entry["record"]
            filename = clip_id + ".wav"
            path = destination / filename
            _extract(entry["path"], path, start_frame, frames, entry["info"])
            out = {"id": clip_id, "path": filename, "sha256": _digest(path),
                   "bpm": rec["bpm"], "rights": rec["rights"],
                   "provenance": rec["provenance"], "recording_id": entry["recording"]}
            if partitioned:
                out["partition"] = rec["partition"]
            output_tracks.append(out)
            mappings.append({"clip_id": clip_id, "source_id": source_id,
                             "source_sha256": entry["info"]["sha256"],
                             "start_seconds_manual": cue,
                             "start_frame": start_frame, "frames": frames})
        output = {"schema_version": 1, "purpose": spec.get("purpose", "development-pilot"),
                  "tracks": output_tracks, "pairs": pair_output}
        (destination / "library.json").write_text(
            json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        private = {"schema_version": 1, "source_manifest_sha256": _digest(spec_path),
                   "cue_source": "manual-unverified", "clips": mappings,
                   "limitations": ["no automatic beatgrid or phrase detection",
                                   "no source rights verification", "no tempo stretching",
                                   "do not publish source or derived WAVs"]}
        (destination / "cue-provenance.private.json").write_text(
            json.dumps(private, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        # Integrate with the canonical reader before declaring the output ready.
        validate_library(destination / "library.json")
        return destination / "library.json"
    except BaseException:
        # Destination did not exist before this call: cleanup cannot erase an old pack.
        shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Compile manual full-track WAV cues into a private bounded MixLab library")
    parser.add_argument("source_manifest", help="Private JSON spec with hashed full tracks")
    parser.add_argument("destination", help="New private output directory, outside source library")
    args = parser.parse_args()
    try:
        manifest = compile_cues(args.source_manifest, args.destination)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab cue compiler: {exc}\n")
    print(json.dumps({"ready": True, "library": str(manifest), "privacy": "local-only"}))


if __name__ == "__main__":
    main()
