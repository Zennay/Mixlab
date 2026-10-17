"""Read-only PCM16 A/B resolution-loss preflight (not a perceptual verdict).

This intentionally independent ML-07 module does not modify the renderer, the
existing quality scanner or another worker's active source files.
"""
from __future__ import annotations

import argparse
from array import array
from contextlib import ExitStack
from itertools import islice
import json
import os
from pathlib import Path
import stat
import sys
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
MAX_GROUP_FRAMES = 8_000_000
BLOCK_FRAMES = 4096
MIN_ELIGIBLE = 4096
MIN_ACTIVE_WINDOWS = 4
# Each 100ms evidence window must have >=50% high-level frames; a collection
# of sparse transients or separated islands cannot certify an A/B contrast.
MIN_WINDOW_ACTIVE_PERCENT = 50
ACTIVE_ABS = 2048
BASELINE_MAX_ZERO_FRACTION = 0.35
CANDIDATE_MIN_ZERO_FRACTION = 0.995


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _walk(path):
    """Check every current pathname component, never following a symlink."""
    if ".." in Path(path).parts or "\x00" in os.fspath(path):
        raise ValueError("unsafe source")
    absolute = Path(os.path.abspath(os.fspath(path)))
    if len(os.fspath(absolute)) > 4096 or len(absolute.parts) > 65:
        raise ValueError("invalid path size")
    cursor = Path(absolute.anchor)
    components = absolute.parts[1:]
    for index, part in enumerate(components):
        cursor = cursor / part
        info = os.lstat(cursor)
        if index < len(components) - 1:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("non-directory source parent")
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError("non-regular source")
    return absolute, os.lstat(absolute)


def _open_source(path, stack):
    absolute, initial = _walk(path)
    fd = os.open(absolute, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        handle = os.fdopen(fd, "rb", buffering=0)
    except BaseException:
        os.close(fd)
        raise
    stack.enter_context(handle)
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode) or _identity(info) != _identity(initial):
        raise ValueError("source changed during admission")
    if not 44 <= info.st_size <= MAX_BYTES:
        raise ValueError("source size out of bounds")
    reader = wave.open(handle, "rb")
    stack.callback(reader.close)
    if (reader.getcomptype() != "NONE" or reader.getsampwidth() != 2
            or reader.getnchannels() not in (1, 2)
            or not 8000 <= reader.getframerate() <= 96000
            or not 1 <= reader.getnframes() <= MAX_FRAMES):
        raise ValueError("unsupported source format")
    return {"path": absolute, "handle": handle, "info": info,
            "reader": reader, "shape": (reader.getnchannels(),
                                         reader.getframerate(), reader.getnframes())}


def _scan(source):
    channels, rate, frames = source["shape"]
    reader = source["reader"]
    eligible = [0] * channels
    trailing_zero = [0] * channels
    # Fixed 256-bin per-channel low-byte histograms catch shifted 8-bit
    # amplitude lattices whose bottom byte is e.g. 37 rather than zero.
    low_byte_histogram = [[0] * 256 for _ in range(channels)]
    # A 100 ms bucket with >=32 high-level samples is only a diagnostic;
    # stronger sustained occupancy is required before a conclusive result.
    window_counts = [{} for _ in range(channels)]
    frame_offset = 0
    remaining = frames
    while remaining:
        take = min(BLOCK_FRAMES, remaining)
        raw = reader.readframes(take)
        if len(raw) != take * channels * 2:
            raise ValueError("truncated PCM payload")
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        for position in range(take):
            window_index = (frame_offset + position) * 10 // rate
            for channel in range(channels):
                value = values[position * channels + channel]
                if abs(value) >= ACTIVE_ABS:
                    eligible[channel] += 1
                    residue = value & 255
                    low_byte_histogram[channel][residue] += 1
                    if residue == 0:
                        trailing_zero[channel] += 1
                    counts = window_counts[channel]
                    counts[window_index] = counts.get(window_index, 0) + 1
        frame_offset += take
        remaining -= take
    output = []
    for channel in range(channels):
        present = {w for w, count in window_counts[channel].items() if count >= 32}
        sustained = set()
        for w, count in window_counts[channel].items():
            # Use rational integer PCM frame boundaries at fractional rates.
            # Incomplete trailing windows must not count as 100ms evidence.
            start = (w * rate + 9) // 10
            end = ((w + 1) * rate + 9) // 10
            if (end <= frames and count >= 32
                    and 100 * count >= MIN_WINDOW_ACTIVE_PERCENT * (end - start)):
                sustained.add(w)
        streak = longest_streak = 0
        previous = None
        for w in sorted(sustained):
            streak = streak + 1 if previous is not None and w == previous + 1 else 1
            longest_streak = max(longest_streak, streak)
            previous = w
        evidenced = eligible[channel] >= MIN_ELIGIBLE and longest_streak >= MIN_ACTIVE_WINDOWS
        dominant_count = max(low_byte_histogram[channel])
        output.append({
            "evidenced": evidenced,
            "active_windows": len(present),
            "sustained_windows": len(sustained),
            "longest_sustained_window_run": longest_streak,
            "eligible_samples": eligible[channel],
            "low_byte_zero_samples": trailing_zero[channel],
            "dominant_low_byte_samples": dominant_count,
            "dominant_low_byte_fraction": round(dominant_count / eligible[channel], 6)
            if evidenced else None,
            "low_byte_zero_fraction": round(trailing_zero[channel] / eligible[channel], 6)
            if evidenced else None,
        })
    return output


def _coarse_loss(base, candidate):
    """Compare exact integer counts, never presentation-rounded fractions."""
    baseline_concentrated = base.get("dominant_low_byte_samples", base["low_byte_zero_samples"])
    candidate_concentrated = candidate.get("dominant_low_byte_samples", candidate["low_byte_zero_samples"])
    return (20 * baseline_concentrated <= 7 * base["eligible_samples"]
            and 200 * candidate_concentrated >= 199 * candidate["eligible_samples"])


def inspect_ab(baseline, candidates):
    """Screen high-level PCM low-byte collapse vs baseline, per channel.

    True = candidate-specific likely coarse PCM quantization; False = enough
    comparison evidence without that specific signature; None = abstention.
    Never exposes source paths, PCM, fingerprints or source metadata.
    """
    try:
        if isinstance(candidates, (str, bytes, Path)):
            raise ValueError("candidates must be a sequence")
        # Never materialize an unbounded sequence or exhaust an infinite
        # generator. Reject at the eighth candidate, before opening audio.
        try:
            bounded_candidates = list(islice(iter(candidates), 8))
        except Exception:
            # Custom iterator errors can include private track paths.
            raise ValueError("Invalid candidates (details withheld)") from None
        paths = [baseline, *bounded_candidates]
        if not 2 <= len(paths) <= 8:
            raise ValueError("expected baseline and 1..7 candidates")
        with ExitStack() as stack:
            sources = [_open_source(path, stack) for path in paths]
            if len({(s["info"].st_dev, s["info"].st_ino) for s in sources}) != len(sources):
                raise ValueError("repeated source inode")
            shape = sources[0]["shape"]
            if any(s["shape"] != shape for s in sources[1:]):
                raise ValueError("A/B format or duration mismatch")
            if sum(s["shape"][2] for s in sources) > MAX_GROUP_FRAMES:
                raise ValueError("A/B processing budget exceeded")
            results = [_scan(source) for source in sources]
            # Check every earlier source *after* scanning the last member.
            for source in sources:
                _, path_info = _walk(source["path"])
                descriptor_info = os.fstat(source["handle"].fileno())
                if (_identity(path_info) != _identity(source["info"])
                        or _identity(descriptor_info) != _identity(source["info"])):
                    raise ValueError("source changed during read")
        comparisons = []
        for index, candidate in enumerate(results[1:], start=1):
            per_channel = []
            for base, current in zip(results[0], candidate):
                if (not base["evidenced"] or not current["evidenced"]
                        or 20 * base["dominant_low_byte_samples"] > 7 * base["eligible_samples"]):
                    # An already low-diversity baseline cannot establish
                    # a clean candidate: no trustworthy reference exists.
                    per_channel.append(None)
                else:
                    per_channel.append(_coarse_loss(base, current))
            status = True if True in per_channel else (
                False if all(v is False for v in per_channel) else None
            )
            comparisons.append({
                "candidate_index": index,
                "candidate_channel_metrics": candidate,
                "coarse_resolution_review": status,
                "per_channel_review": per_channel,
            })
        return {
            "metric": "pcm16_low_byte_lattice_vs_baseline_v2",
            "technical_proxy_only": True,
            "channels": shape[0],
            "sample_rate": shape[1],
            "frames_per_source": shape[2],
            "baseline_channel_metrics": results[0],
            "candidates": comparisons,
        }
    except (OSError, ValueError, TypeError, EOFError, wave.Error) as exc:
        raise ValueError("Invalid or unreadable PCM16 source (details withheld)") from None


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "PCM resolution preflight: invalid arguments (details withheld)\n")


def main(argv=None):
    parser = _RedactedArgumentParser(description="Private offline PCM16 resolution proxy, not a musical verdict")
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 3 for a warning OR inconclusive channel evidence")
    args = parser.parse_args(argv)
    try:
        report = inspect_ab(args.baseline, args.candidates)
    except ValueError:
        parser.exit(2, "PCM resolution preflight: invalid sources (details withheld)\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    if args.strict and any(row["coarse_resolution_review"] is not False
                           for row in report["candidates"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
