"""Optional CPU-only microtiming confound screen for private PCM16 blind A/B.

A coarse RMS time envelope can reveal an otherwise hidden global offset between
two continuous excerpts. It is NOT beat/phrase alignment or a music score.
No source PCM, paths, fingerprints, offsets or envelope coordinates are emitted.
"""
from __future__ import annotations

from array import array
import argparse
import json
import math
import os
from pathlib import Path
import stat
import sys
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
MAX_TOTAL_FRAMES = 8_000_000
MAX_CANDIDATES = 8
BIN_SECONDS = 0.005
MAX_LAG_SECONDS = 0.200
MIN_LAG_SECONDS = 0.030
MIN_ENVELOPE_BINS = 100
MIN_ENVELOPE_SD = 0.01
MIN_BEST_CORRELATION = 0.85
MIN_CORRELATION_IMPROVEMENT = 0.20


def _read_envelope(path: str | Path, *, expected: tuple[int, int, int] | None,
                   remaining_frames: int) -> tuple[tuple[int, int, int], list[float]]:
    """Read only regular, bounded PCM16 from one no-follow descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError("Invalid source")
        with wave.open(source, "rb") as wav:
            channels, width, rate, frames, compression, _ = wav.getparams()
            if compression != "NONE" or width != 2 or channels not in (1, 2):
                raise ValueError("Unsupported PCM")
            if not 8000 <= rate <= 96000 or not 1 <= frames <= MAX_FRAMES:
                raise ValueError("Invalid PCM bounds")
            header = (rate, channels, frames)
            if expected is not None and header != expected:
                raise ValueError("Not comparable")
            if frames > remaining_frames:
                raise ValueError("Aggregate limit")
            bin_frames = max(1, round(rate * BIN_SECONDS))
            envelope: list[float] = []
            subtotal = 0
            in_bin = 0
            processed = 0
            while processed < frames:
                count = min(4096, frames - processed)
                data = wav.readframes(count)
                if len(data) != count * channels * 2:
                    raise ValueError("Truncated PCM")
                pcm = array("h")
                pcm.frombytes(data)
                if sys.byteorder != "little":
                    pcm.byteswap()
                for start in range(0, len(pcm), channels):
                    for sample in pcm[start:start + channels]:
                        subtotal += sample * sample
                    in_bin += 1
                    if in_bin == bin_frames:
                        envelope.append(math.sqrt(subtotal / (in_bin * channels)) / 32768)
                        subtotal = 0
                        in_bin = 0
                processed += count
        after = os.fstat(source.fileno())
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
             before.st_ctime_ns) !=
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
             after.st_ctime_ns)):
            raise ValueError("Source changed")
        # Prevent a replaced path from being mistaken for the checked inode.
        path_stat = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(path_stat.st_mode) or (path_stat.st_dev, path_stat.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("Source replaced")
    return header, envelope


def _correlation(base: list[float], other: list[float], lag: int) -> float | None:
    """Centered Pearson of overlapping 5ms bins, no public lag/score."""
    if lag >= 0:
        a = base[:len(base) - lag] if lag else base
        b = other[lag:]
    else:
        a = base[-lag:]
        b = other[:len(other) + lag]
    if len(a) < MIN_ENVELOPE_BINS:
        return None
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    va = vb = cov = 0.0
    for x, y in zip(a, b):
        dx, dy = x - mean_a, y - mean_b
        va += dx * dx
        vb += dy * dy
        cov += dx * dy
    if va / n < MIN_ENVELOPE_SD ** 2 or vb / n < MIN_ENVELOPE_SD ** 2:
        return None
    return cov / math.sqrt(va * vb)


def _shift_risk(baseline: list[float], candidate: list[float], rate: int) -> bool | None:
    if len(baseline) != len(candidate) or len(baseline) < MIN_ENVELOPE_BINS:
        return None
    zero = _correlation(baseline, candidate, 0)
    if zero is None:
        return None
    max_lag_bins = round(MAX_LAG_SECONDS / BIN_SECONDS)
    min_lag_bins = math.ceil(MIN_LAG_SECONDS / BIN_SECONDS)
    best = zero
    best_lag = 0
    # Prefer zero at ties. An improved high-correlation lag is only an
    # inspection signal for a GLOBAL offset, not a musical timing verdict.
    for lag in range(-max_lag_bins, max_lag_bins + 1):
        if abs(lag) < min_lag_bins:
            continue
        score = _correlation(baseline, candidate, lag)
        if score is not None and score > best:
            best, best_lag = score, lag
    if best >= MIN_BEST_CORRELATION and best - zero >= MIN_CORRELATION_IMPROVEMENT and best_lag:
        return True
    if zero >= MIN_BEST_CORRELATION:
        return False
    return None


def compare_envelopes(baseline: str | Path, candidates: list[str | Path]) -> dict:
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("Candidate count rejected")
    header, reference = _read_envelope(baseline, expected=None,
                                       remaining_frames=MAX_TOTAL_FRAMES)
    remaining = MAX_TOTAL_FRAMES - header[2]
    results = []
    for index, path in enumerate(candidates, 1):
        _, candidate = _read_envelope(path, expected=header,
                                      remaining_frames=remaining)
        remaining -= header[2]
        risk = _shift_risk(reference, candidate, header[0])
        results.append({
            "id": f"candidate-{index:02d}",
            "temporal_envelope_shift_risk": risk,
            "warnings": (["microtiming_envelope_shift_inspect_not_beat_alignment"]
                         if risk is True else
                         ["microtiming_alignment_inconclusive_inspect"]
                         if risk is None else []),
        })
    return {"screen": "ml07-temporal-envelope-proxy-v1", "candidates": results,
            "human_listening_required": True}


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid arguments (details withheld)\\n")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateParser(description=__doc__)
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = compare_envelopes(args.baseline, args.candidates)
    except (OSError, ValueError, EOFError, wave.Error):
        print("Quality alignment input rejected (details withheld)", file=sys.stderr)
        return 3
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return (2 if args.fail_on_warnings and any(x["warnings"] for x in report["candidates"]) else 0)


if __name__ == "__main__":
    raise SystemExit(main())
