"""Bounded 4x windowed-sinc estimate of PCM16 intersample overs.

This is a technical screening proxy, NOT a calibrated BS.1770 true-peak
meter, perceptual loudness measurement or proof of musical preference.
No private audio, filename, path, PCM digest or sample is emitted.
"""
from __future__ import annotations

import argparse
from array import array
from collections import deque
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import stat
import sys
import wave

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_FRAMES_PER_SOURCE = 2_000_000
MAX_TOTAL_FRAMES = 8_000_000
MAX_CANDIDATES = 3
_TAPS = range(-3, 5)


def _sinc(x: float) -> float:
    return 1.0 if abs(x) < 1e-12 else math.sin(math.pi * x) / (math.pi * x)


def _coefficients(fraction: float) -> tuple[float, ...]:
    # Symmetric 8-tap Blackman-windowed sinc; normalize to preserve DC.
    raw = []
    for offset in _TAPS:
        x = offset - fraction
        window = 0.42 + 0.5 * math.cos(math.pi * x / 4) + 0.08 * math.cos(math.pi * x / 2)
        raw.append(_sinc(x) * window)
    scale = sum(raw)
    if scale <= 0:
        raise RuntimeError("Invalid interpolation filter")
    return tuple(x / scale for x in raw)


_PHASES = tuple(_coefficients(k / 4) for k in (1, 2, 3))


class AudioInputError(ValueError):
    """A source cannot safely be screened."""


def _open_pcm(stack: ExitStack, private_path: str):
    # Descriptor-based admission prevents FIFO hangs and final-component
    # symlink traversal. This is not a sandbox against a hostile filesystem.
    fd = os.open(private_path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    stream = stack.enter_context(os.fdopen(fd, "rb", closefd=True))
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode) or not 44 <= info.st_size <= MAX_SOURCE_BYTES:
        raise AudioInputError("Unsupported source")
    reader = stack.enter_context(wave.open(stream, "rb"))
    nch, width, rate, frames, codec, _ = reader.getparams()
    if codec != "NONE" or width != 2 or nch not in (1, 2) or not 8000 <= rate <= 96000:
        raise AudioInputError("Unsupported PCM16 format")
    if not 1 <= frames <= MAX_FRAMES_PER_SOURCE:
        raise AudioInputError("Unsupported duration")
    return reader, stream, info, (rate, nch, frames)


def _scan(reader: wave.Wave_read, channels: int, nframes: int) -> dict:
    """Read <=4096 PCM frames at once with an eight-frame interpolation ring."""
    history = deque(maxlen=8)
    seen = 0
    sample_peak = 0
    interpolated_peak = 0.0
    intersample_over_count = 0
    # Scan every phase, not just areas with sample peaks close to full-scale.
    while seen < nframes:
        want = min(4096, nframes - seen)
        raw = reader.readframes(want)
        if len(raw) != want * channels * 2:
            raise AudioInputError("Truncated PCM")
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        for offset in range(0, len(values), channels):
            frame = tuple(values[offset:offset + channels])
            sample_peak = max(sample_peak, *(abs(v) for v in frame))
            history.append(frame)
            if len(history) == 8:
                # Ring indices 3 and 4 bracket the fractional reconstruction.
                for coeffs in _PHASES:
                    for ch in range(channels):
                        value = abs(sum(coeffs[k] * history[k][ch] for k in range(8)))
                        interpolated_peak = max(interpolated_peak, value)
                        if value > 32768.0:
                            intersample_over_count += 1
        seen += want
    peak = max(sample_peak, interpolated_peak)
    return {
        "sample_peak_dbfs": round(20 * math.log10(sample_peak / 32768), 3) if sample_peak else None,
        "interpolated_peak_dbfs_estimate": round(20 * math.log10(peak / 32768), 3) if peak else None,
        "intersample_overs_estimated": intersample_over_count,
        "screen_evaluable": nframes >= 8,
        "intersample_over_risk": bool(intersample_over_count),
    }


def compare_intersample(baseline: str | Path, candidates: list[str | Path]) -> dict:
    """Shape-match the whole group before PCM processing; leave files intact."""
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise AudioInputError("Invalid number of candidates")
    with ExitStack() as stack:
        sources = [_open_pcm(stack, os.fspath(path)) for path in (baseline, *candidates)]
        shapes = [source[3] for source in sources]
        if any(shape != shapes[0] for shape in shapes[1:]):
            raise AudioInputError("A/B sample format and length mismatch")
        if sum(shape[2] for shape in shapes) > MAX_TOTAL_FRAMES:
            raise AudioInputError("Group frame budget exceeded")
        identities = [(s[2].st_dev, s[2].st_ino) for s in sources]
        if len(set(identities)) != len(identities):
            raise AudioInputError("Repeated source inode")
        results = []
        for reader, stream, before, shape in sources:
            results.append(_scan(reader, shape[1], shape[2]))
            after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise AudioInputError("Source changed during read")
        # Hold all FDs open and detect mutations of earlier sources too.
        for _, stream, before, _ in sources:
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise AudioInputError("Source changed during group read")
    return {
        "schema_version": 1,
        "method": "four_times_eight_tap_windowed_sinc_screen_not_bs1770",
        "sample_rate_hz": shapes[0][0],
        "channels": shapes[0][1],
        "frames_per_source": shapes[0][2],
        "baseline": results[0],
        "candidates": [{"candidate_id": f"candidate-{n}", **result}
                       for n, result in enumerate(results[1:], 1)],
        "human_preference_test_required": True,
    }


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "intersample preflight: invalid arguments (details withheld)\n")


def main(argv=None) -> int:
    parser = _PrivateParser(description="Offline 4x intersample clipping screen; NOT calibrated true peak")
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--fail-on-risk", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = compare_intersample(args.baseline, args.candidates)
    except (OSError, ValueError, EOFError, wave.Error, OverflowError):
        parser.exit(3, "intersample preflight: invalid or unreadable WAV (details withheld)\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    if args.fail_on_risk and (report["baseline"]["intersample_over_risk"] or
                              any(c["intersample_over_risk"] for c in report["candidates"])):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
