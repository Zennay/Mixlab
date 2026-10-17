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
READ_BLOCK_FRAMES = 4096
BIN_SECONDS = 0.005
MAX_LAG_SECONDS = 0.200
MIN_LAG_SECONDS = 0.030
MIN_ENVELOPE_BINS = 100
MIN_ENVELOPE_SD = 0.01
MIN_BEST_CORRELATION = 0.85
MIN_CORRELATION_IMPROVEMENT = 0.20
MAX_REGIONS = 8
MIN_REGIONS_FOR_DRIFT = 3
MIN_DRIFT_REGIONS = 2


def _read_envelope(path: str | Path, *, expected: tuple[int, int, int] | None,
                   remaining_frames: int) -> tuple[tuple[int, int, int], list[float], list[list[float]]]:
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
            channel_envelopes: list[list[float]] = [[] for _ in range(channels)]
            channel_squares = [0] * channels
            subtotal = 0
            in_bin = 0
            processed = 0
            while processed < frames:
                count = min(READ_BLOCK_FRAMES, frames - processed)
                data = wav.readframes(count)
                if len(data) != count * channels * 2:
                    raise ValueError("Truncated PCM")
                pcm = array("h")
                pcm.frombytes(data)
                if sys.byteorder != "little":
                    pcm.byteswap()
                for start in range(0, len(pcm), channels):
                    for channel, sample in enumerate(pcm[start:start + channels]):
                        square = sample * sample
                        subtotal += square
                        channel_squares[channel] += square
                    in_bin += 1
                    if in_bin == bin_frames:
                        envelope.append(math.sqrt(subtotal / (in_bin * channels)) / 32768)
                        for channel in range(channels):
                            channel_envelopes[channel].append(
                                math.sqrt(channel_squares[channel] / in_bin) / 32768
                            )
                            channel_squares[channel] = 0
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
    return header, envelope, channel_envelopes


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


def _regional_shift_risk(baseline: list[float], candidate: list[float]) -> bool | None:
    """Flag persistent *within-clip* A/B offset, never expose region/lag.

    Require at least one confidently aligned region as an anchor and two
    independently shifted regions. A uniform global offset is classified by
    _shift_risk instead, not misleadingly labelled a regional timing drift.
    Abstain if most windows are silent, unstructured or strongly re-edited.
    """
    if len(baseline) != len(candidate):
        return None
    count = min(MAX_REGIONS, len(baseline) // MIN_ENVELOPE_BINS)
    if count < MIN_REGIONS_FOR_DRIFT:
        return None
    length = len(baseline)
    lag_max = round(MAX_LAG_SECONDS / BIN_SECONDS)
    lag_min = math.ceil(MIN_LAG_SECONDS / BIN_SECONDS)
    aligned = shifted = informative = 0
    for i in range(count):
        start = i * length // count
        end = (i + 1) * length // count
        target = baseline[start:end]
        zero = _correlation(target, candidate[start:end], 0)
        if zero is None:
            continue
        informative += 1
        if zero >= MIN_BEST_CORRELATION:
            aligned += 1
            continue
        best = zero
        for lag in range(-lag_max, lag_max + 1):
            if abs(lag) < lag_min or start + lag < 0 or end + lag > length:
                continue
            score = _correlation(target, candidate[start + lag:end + lag], 0)
            if score is not None and score > best:
                best = score
        if best >= MIN_BEST_CORRELATION and best - zero >= MIN_CORRELATION_IMPROVEMENT:
            shifted += 1
    if informative < MIN_REGIONS_FOR_DRIFT:
        return None
    if aligned >= 1 and shifted >= MIN_DRIFT_REGIONS:
        return True
    # A negative risk result requires evidence over *every* region. With
    # only two aligned regions, the rest may contain unrelated/uninformative
    # audio (or an undetected edit), so declaring the pair clean is unsound.
    # Preserve null rather than turning partial coverage into false assurance.
    if aligned == count and shifted == 0:
        return False
    return None


def compare_envelopes(baseline: str | Path, candidates: list[str | Path]) -> dict:
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("Candidate count rejected")
    header, reference, reference_channels = _read_envelope(baseline, expected=None,
                                       remaining_frames=MAX_TOTAL_FRAMES)
    remaining = MAX_TOTAL_FRAMES - header[2]
    results = []
    for index, path in enumerate(candidates, 1):
        _, candidate, candidate_channels = _read_envelope(path, expected=header,
                                      remaining_frames=remaining)
        remaining -= header[2]
        risk = _shift_risk(reference, candidate, header[0])
        regional_risk = _regional_shift_risk(reference, candidate)
        stereo_differential_risk = None
        if header[1] == 2:
            left = _shift_risk(reference_channels[0], candidate_channels[0], header[0])
            right = _shift_risk(reference_channels[1], candidate_channels[1], header[0])
            if (left is True and right is False) or (right is True and left is False):
                stereo_differential_risk = True
            elif left is False and right is False:
                stereo_differential_risk = False
        warnings = []
        if risk is True:
            warnings.append("microtiming_envelope_shift_inspect_not_beat_alignment")
        elif risk is None:
            warnings.append("microtiming_alignment_inconclusive_inspect")
        if stereo_differential_risk is True:
            warnings.append("stereo_differential_microtiming_shift_inspect")
        elif (header[1] == 2 and stereo_differential_risk is None
              and risk is False and regional_risk is False):
            # The pooled stereo envelope can be exactly unchanged when L/R
            # content is exchanged. It must not silently hide uncertainty in
            # channel alignment behind a clean whole-clip result.
            warnings.append("stereo_channel_alignment_inconclusive_inspect")
        if regional_risk is True:
            warnings.append("regional_timing_shift_inspect_not_tempo_estimate")
        elif regional_risk is None and risk is not True:
            warnings.append("regional_timing_alignment_inconclusive_inspect")
        results.append({
            "id": f"candidate-{index:02d}",
            "temporal_envelope_shift_risk": risk,
            "regional_timing_shift_risk": regional_risk,
            "stereo_differential_timing_shift_risk": stereo_differential_risk,
            "warnings": warnings,
        })
    return {"screen": "ml07-temporal-envelope-proxy-v1", "candidates": results,
            "human_listening_required": True}


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid arguments (details withheld)\n")


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
