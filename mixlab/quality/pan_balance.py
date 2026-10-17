"""Read-only, bounded stereo pan-balance comparison for private A/B PCM16.

This detects a *technical listening confound*, not intentional DJ panning,
subjective quality, or a calibrated spatial-audio measurement. Only strict
canonical 44-byte RIFF/PCM16 headers are supported; refuse ambiguous inputs.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
BLOCK_FRAMES = 4096
WINDOW_MS = 250
MIN_ACTIVE_RMS = 10 ** (-45 / 20)
WARN_SHIFT_DB = 6.0
WARN_PERSIST_MS = 1000


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _admit(path, stack):
    """Open a regular file without following the last symlink; no audio copies."""
    p = Path(path)
    before = p.lstat()
    if not stat.S_ISREG(before.st_mode) or not 44 <= before.st_size <= MAX_BYTES:
        raise ValueError("Invalid private PCM source")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(p, flags)
    handle = stack.enter_context(os.fdopen(fd, "rb"))
    actual = os.fstat(handle.fileno())
    if not stat.S_ISREG(actual.st_mode) or _identity(before) != _identity(actual):
        raise ValueError("Private source changed during admission")
    hdr = handle.read(44)
    if (len(hdr) != 44 or hdr[:4] != b"RIFF" or hdr[8:16] != b"WAVEfmt "
            or hdr[16:20] != b"\x10\x00\x00\x00" or hdr[36:40] != b"data"):
        raise ValueError("Only canonical stereo PCM16 WAV is supported")
    tag, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", hdr, 20)
    declared = struct.unpack_from("<I", hdr, 4)[0] + 8
    pcm_bytes = struct.unpack_from("<I", hdr, 40)[0]
    frames = pcm_bytes // 4
    if (tag != 1 or channels != 2 or bits != 16 or
            not 8000 <= rate <= 96000 or byte_rate != 4 * rate or align != 4 or
            pcm_bytes % 4 or not 1 <= frames <= MAX_FRAMES or
            declared != actual.st_size or actual.st_size != 44 + pcm_bytes):
        raise ValueError("Invalid private stereo PCM16 framing")
    return p, handle, _identity(actual), rate, frames


def _unchanged(record):
    p, handle, expected, _, _ = record
    try:
        after_fd = os.fstat(handle.fileno())
        after_path = p.lstat()
    except OSError:
        raise ValueError("Private PCM source changed") from None
    if (_identity(after_fd) != expected or _identity(after_path) != expected or
            not stat.S_ISREG(after_path.st_mode)):
        raise ValueError("Private PCM source changed")


def inspect(baseline, candidate):
    """Return anonymous technical balance diagnostics for equally long stereo WAVs."""
    with ExitStack() as stack:
        a = _admit(baseline, stack)
        b = _admit(candidate, stack)
        if _identity(os.fstat(a[1].fileno()))[:2] == _identity(os.fstat(b[1].fileno()))[:2]:
            raise ValueError("A/B sources must be distinct files")
        if a[3:] != b[3:]:
            raise ValueError("A/B sample rate or duration differs")
        rate, frames = a[3], a[4]
        window_frames = max(1, rate * WINDOW_MS // 1000)
        sum_sq = [[0, 0], [0, 0]]
        count = 0
        active_windows = 0
        active_streak_frames = 0
        longest_active_streak_frames = 0
        consecutive_shift_frames = 0
        longest_shift_frames = 0
        max_shift = 0.0
        warned = False
        remaining = frames
        while remaining:
            take = min(remaining, BLOCK_FRAMES)
            left, right = a[1].read(take * 4), b[1].read(take * 4)
            if len(left) != take * 4 or len(right) != take * 4:
                raise ValueError("Private PCM payload incomplete")
            # Framewise streaming; at most two 4096-frame input buffers.
            for (l0, r0), (l1, r1) in zip(struct.iter_unpack("<hh", left),
                                            struct.iter_unpack("<hh", right)):
                sum_sq[0][0] += l0 * l0
                sum_sq[0][1] += r0 * r0
                sum_sq[1][0] += l1 * l1
                sum_sq[1][1] += r1 * r1
                count += 1
                if count == window_frames:
                    floor = (MIN_ACTIVE_RMS * 32768) ** 2 * count
                    if all(value >= floor for pair in sum_sq for value in pair):
                        active_windows += 1
                        active_streak_frames += count
                        longest_active_streak_frames = max(longest_active_streak_frames, active_streak_frames)
                        db_a = 10 * math.log10(sum_sq[0][0] / sum_sq[0][1])
                        db_b = 10 * math.log10(sum_sq[1][0] / sum_sq[1][1])
                        delta = abs(db_b - db_a)
                        max_shift = max(max_shift, delta)
                        if delta >= WARN_SHIFT_DB:
                            consecutive_shift_frames += count
                            longest_shift_frames = max(longest_shift_frames, consecutive_shift_frames)
                            warned |= consecutive_shift_frames * 1000 >= WARN_PERSIST_MS * rate
                        else:
                            consecutive_shift_frames = 0
                    else:
                        active_streak_frames = 0
                        consecutive_shift_frames = 0
                    sum_sq = [[0, 0], [0, 0]]
                    count = 0
            remaining -= take
        # Remainder <250ms is deliberately non-decisive, never counted as 1 second.
        _unchanged(a)
        _unchanged(b)
        # Distinguish insufficient evidence from a conclusive negative result.
        enough_active_audio = longest_active_streak_frames * 1000 >= WARN_PERSIST_MS * rate
        status = ("insufficient_active_audio" if not enough_active_audio else
                  "review_pan_balance" if warned else "no_sustained_pan_bias_detected")
        return {
            "schema_version": 1,
            "format": {"sample_rate": rate, "frames": frames, "channels": 2},
            "active_windows": active_windows,
            "longest_continuous_active_ms": round(longest_active_streak_frames * 1000 / rate),
            "evidence_status": status,
            "max_pan_balance_delta_db": round(max_shift, 3) if active_windows else None,
            "longest_sustained_shift_ms": round(longest_shift_frames * 1000 / rate),
            "stereo_pan_confound_review": bool(warned) if enough_active_audio else None,
            "interpretation": "technical_screen_only_not_musical_preference",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline anonymous stereo pan A/B screen")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect(args.baseline, args.candidate), sort_keys=True))
        return 0
    except (OSError, ValueError, OverflowError, struct.error, ZeroDivisionError):
        print("Stereo pan preflight rejected private input", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
