"""Bounded, private PCM16 precision-loss comparison for offline A/B review.

This checks one narrow artifact: low-order PCM bits disappearing from a
candidate relative to a higher-resolution baseline. It is not a perceptual
quality score, bit-depth estimator, or approval to publish private music.
"""
from __future__ import annotations

from array import array
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
MIN_INFORMATIVE_SAMPLES = 2048
MIN_DISTINCT_VALUES = 32
# Nearly every informative candidate sample must land on a coarser grid,
# while fewer than 10% of corresponding baseline samples do.
CANDIDATE_GRID_FRACTION = 0.995
BASELINE_GRID_FRACTION = 0.10
GRID_STEPS = (256, 64)


def _scan(path: str | Path, *, chunk_frames: int = 4096) -> dict:
    """Read only bounded, regular private WAVs; never return audio/paths."""
    if type(chunk_frames) is not int or not 1 <= chunk_frames <= 4096:
        raise ValueError("invalid chunk size")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ValueError("not a bounded regular WAV")
        with wave.open(file, "rb") as source:
            channels = source.getnchannels()
            rate = source.getframerate()
            frames = source.getnframes()
            if (source.getsampwidth() != 2 or source.getcomptype() != "NONE"
                    or channels not in (1, 2) or not 8000 <= rate <= 96000
                    or not 1 <= frames <= MAX_FRAMES):
                raise ValueError("unsupported WAV metadata")
            informative = [0] * channels
            on_grid = [{step: 0 for step in GRID_STEPS} for _ in range(channels)]
            distinct = [set() for _ in range(channels)]
            remaining = frames
            while remaining:
                take = min(remaining, chunk_frames)
                raw = source.readframes(take)
                if len(raw) != take * channels * 2:
                    raise ValueError("truncated WAV frames")
                pcm = array("h")
                pcm.frombytes(raw)
                if sys.byteorder != "little":
                    pcm.byteswap()
                for index, sample in enumerate(pcm):
                    channel = index % channels
                    if abs(sample) < 1024:
                        continue
                    informative[channel] += 1
                    if len(distinct[channel]) < MIN_DISTINCT_VALUES:
                        distinct[channel].add(sample)
                    for step in GRID_STEPS:
                        if sample % step == 0:
                            on_grid[channel][step] += 1
                remaining -= take
        after = os.fstat(file.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                      after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("WAV changed during read")
    return {"rate": rate, "channels": channels, "frames": frames,
            "informative": informative, "distinct": [len(x) for x in distinct],
            "grid_counts": on_grid}


def compare_precision(baseline: str | Path, candidate: str | Path,
                      *, chunk_frames: int = 4096) -> dict:
    """Return a conservative anonymous candidate-vs-baseline inspection flag.

    null = insufficient signal/diversity; false = evaluated without this
    narrow coarse-grid pattern; true = a likely lost-precision artifact.
    """
    a = _scan(baseline, chunk_frames=chunk_frames)
    b = _scan(candidate, chunk_frames=chunk_frames)
    if any(a[key] != b[key] for key in ("rate", "channels", "frames")):
        raise ValueError("incomparable WAV format/duration")
    decisions = []
    for ch in range(a["channels"]):
        an, bn = a["informative"][ch], b["informative"][ch]
        if (min(an, bn) < MIN_INFORMATIVE_SAMPLES
                or min(a["distinct"][ch], b["distinct"][ch]) < MIN_DISTINCT_VALUES):
            decisions.append(None)
            continue
        decisions.append(any(
            b["grid_counts"][ch][step] / bn >= CANDIDATE_GRID_FRACTION
            and a["grid_counts"][ch][step] / an < BASELINE_GRID_FRACTION
            for step in GRID_STEPS
        ))
    outcome = (True if True in decisions else
               False if all(v is False for v in decisions) else None)
    return {"schema_version": 1, "status": "technical-inspection-only",
            "candidate_precision_loss_inspect": outcome,
            "warnings": (["candidate_low_bit_precision_loss_inspect"]
                         if outcome is True else [])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Private, bounded PCM16 A/B precision-loss screen")
    parser.add_argument("baseline", metavar="BASELINE.wav")
    parser.add_argument("candidate", metavar="CANDIDATE.wav")
    args, unknown = parser.parse_known_args(argv)
    try:
        if unknown:
            raise ValueError("unexpected argument")
        result = compare_precision(args.baseline, args.candidate)
    except (OSError, ValueError, EOFError, wave.Error):
        print("MixLab precision: invalid or incomparable private WAVs", file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
