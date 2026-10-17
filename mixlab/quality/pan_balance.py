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
MAX_PATH_COMPONENTS = 64
MAX_PATH_BYTES = 4096


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)



def _open_no_symlink_components(path):
    """Read-only Linux dirfd walk, refusing symlinks anywhere in the path.

    Keep lexical '..': a symlink/../safe.wav path still traverses the
    symlink *before* processing '..'. Resolve() or abspath() would conceal it.
    Bound path length and depth before opening even the root directory.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("Private PCM path traversal protection unavailable")
    p = Path(path)
    absolute = p if p.is_absolute() else Path.cwd() / p
    pieces = absolute.parts
    if (len(pieces) < 2 or len(pieces) > MAX_PATH_COMPONENTS
            or len(os.fspath(absolute)) > MAX_PATH_BYTES
            or len(os.fsencode(absolute)) > MAX_PATH_BYTES):
        raise ValueError("Private PCM path outside bounded admission")
    common = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    dir_flags = common | os.O_DIRECTORY | getattr(os, "O_NONBLOCK", 0)
    file_flags = common | getattr(os, "O_NONBLOCK", 0)
    with ExitStack() as dirs:
        parent = os.open(os.sep, dir_flags)
        dirs.callback(os.close, parent)
        for component in pieces[1:-1]:
            fd = os.open(component, dir_flags, dir_fd=parent)
            dirs.callback(os.close, fd)
            parent = fd
        return os.open(pieces[-1], file_flags, dir_fd=parent)


def _admit(path, stack):
    """Open a regular file without following the last symlink; no audio copies."""
    p = Path(path)
    fd = _open_no_symlink_components(p)
    try:
        actual = os.fstat(fd)
        if not stat.S_ISREG(actual.st_mode) or not 44 <= actual.st_size <= MAX_BYTES:
            raise ValueError("Invalid private PCM source")
        handle = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    stack.enter_context(handle)
    # Independently check that the caller's current name still resolves to
    # this descriptor. The post-read check reopens the entire nofollow path.
    before = p.lstat()
    if not stat.S_ISREG(before.st_mode) or _identity(before) != _identity(actual):
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
        named_fd = _open_no_symlink_components(p)
        try:
            after_path = os.fstat(named_fd)
        finally:
            os.close(named_fd)
    except (OSError, ValueError):
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


class _PrivateArgumentParser(argparse.ArgumentParser):
    """Never repeat a private WAV path from an invalid argv to stderr."""

    def error(self, message):
        print("Stereo pan preflight rejected private arguments", file=sys.stderr)
        raise SystemExit(2)


def main(argv=None):
    parser = _PrivateArgumentParser(description="Offline anonymous stereo pan A/B screen")
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
