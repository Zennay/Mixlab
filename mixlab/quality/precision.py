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
GRID_STEPS = (256, 128, 64, 32, 16)
REGIONS = 8
MIN_REGION_INFORMATIVE = 512
MIN_REGION_DISTINCT = 16
MIN_PERSISTENT_REGIONS = 2
MAX_CANDIDATES = 8
MAX_BATCH_FRAMES = 8_000_000
MAX_BATCH_BYTES = 128 * 1024 * 1024


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
            # Residue histograms detect arbitrary quantizer phase, not only
            # PCM samples divisible by 64/256. Memory is fixed: at most
            # 8 regions x 2 channels x (16+32+64+128+256) counters.
            grids = [{step: [0] * step for step in GRID_STEPS}
                     for _ in range(channels)]
            distinct = [set() for _ in range(channels)]
            region_grids = [[{step: [0] * step for step in GRID_STEPS}
                             for _ in range(channels)] for _ in range(REGIONS)]
            region_info = [[0] * channels for _ in range(REGIONS)]
            region_distinct = [[set() for _ in range(channels)]
                               for _ in range(REGIONS)]
            remaining = frames
            processed_frames = 0
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
                    region = min(REGIONS - 1,
                                 ((processed_frames + index // channels) * REGIONS) // frames)
                    informative[channel] += 1
                    region_info[region][channel] += 1
                    if len(distinct[channel]) < MIN_DISTINCT_VALUES:
                        distinct[channel].add(sample)
                    if len(region_distinct[region][channel]) < MIN_REGION_DISTINCT:
                        region_distinct[region][channel].add(sample)
                    for step in GRID_STEPS:
                        residue = sample % step
                        grids[channel][step][residue] += 1
                        region_grids[region][channel][step][residue] += 1
                processed_frames += take
                remaining -= take
        after = os.fstat(file.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                      after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("WAV changed during read")
    return {"rate": rate, "channels": channels, "frames": frames,
            "informative": informative, "distinct": [len(x) for x in distinct],
            "grids": grids, "region_grids": region_grids,
            "region_info": region_info,
            "region_distinct": [[len(x) for x in row] for row in region_distinct],
            # Internal-only: never emitted in the anonymous public JSON.
            "_source_identity": _identity(after)}


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    """Bounded metadata receipt; neither PCM nor path is disclosed."""
    return (metadata.st_dev, metadata.st_ino, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns)

def _assert_source_identity(path: str | Path, expected: tuple[int, ...]) -> None:
    """Fail closed if either private source changed/replaced during the pair scan."""
    current = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(current.st_mode) or _identity(current) != expected:
        raise ValueError("private WAV replaced or modified during comparison")


def _precision_grid_loss(reference: dict, candidate: dict, an: int, bn: int) -> bool:
    # Require the reference not to be concentrated on ANY grid offset; a
    # similarly coarse reference shifted by one LSB is not evidence of loss.
    return any(max(candidate[step]) / bn >= CANDIDATE_GRID_FRACTION
               and max(reference[step]) / an < BASELINE_GRID_FRACTION
               for step in GRID_STEPS)


def _evaluate_precision(a: dict, b: dict) -> dict:
    """Evaluate two already-inspected sources without accessing raw audio."""
    if any(a[key] != b[key] for key in ("rate", "channels", "frames")):
        raise ValueError("incomparable WAV format/duration")
    decisions = []
    for ch in range(a["channels"]):
        an, bn = a["informative"][ch], b["informative"][ch]
        global_decision = None
        if (min(an, bn) >= MIN_INFORMATIVE_SAMPLES
                and min(a["distinct"][ch], b["distinct"][ch]) >= MIN_DISTINCT_VALUES):
            global_decision = _precision_grid_loss(a["grids"][ch], b["grids"][ch], an, bn)
        regional = []
        for region in range(REGIONS):
            ra, rb = a["region_info"][region][ch], b["region_info"][region][ch]
            if (min(ra, rb) < MIN_REGION_INFORMATIVE or
                    min(a["region_distinct"][region][ch],
                        b["region_distinct"][region][ch]) < MIN_REGION_DISTINCT):
                regional.append(None)
            else:
                regional.append(_precision_grid_loss(
                    a["region_grids"][region][ch], b["region_grids"][region][ch], ra, rb))
        # A single quantized block might be an artistic effect; require
        # persistence. Insufficient regional evidence is never a false-clean.
        if global_decision is True or regional.count(True) >= MIN_PERSISTENT_REGIONS:
            decisions.append(True)
        elif global_decision is False and all(value is False for value in regional):
            decisions.append(False)
        else:
            decisions.append(None)
    outcome = (True if True in decisions else
               False if all(v is False for v in decisions) else None)
    return {"schema_version": 1, "status": "technical-inspection-only",
            "candidate_precision_loss_inspect": outcome,
            "warnings": (["candidate_low_bit_precision_loss_inspect"]
                         if outcome is True else [])}


def compare_precision(baseline: str | Path, candidate: str | Path,
                      *, chunk_frames: int = 4096) -> dict:
    """Compare one candidate with a private baseline; no input mutation."""
    a = _scan(baseline, chunk_frames=chunk_frames)
    b = _scan(candidate, chunk_frames=chunk_frames)
    _assert_source_identity(baseline, a["_source_identity"])
    _assert_source_identity(candidate, b["_source_identity"])
    return _evaluate_precision(a, b)


def _preadmit_wav(path: str | Path) -> dict:
    """Admit lightweight private WAV metadata before starting any PCM scan."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ValueError("not a bounded regular WAV")
        with wave.open(file, "rb") as source:
            channels, rate, frames = (source.getnchannels(),
                                      source.getframerate(), source.getnframes())
            if (source.getsampwidth() != 2 or source.getcomptype() != "NONE"
                    or channels not in (1, 2) or not 8000 <= rate <= 96000
                    or not 1 <= frames <= MAX_FRAMES):
                raise ValueError("unsupported WAV metadata")
        after = os.fstat(file.fileno())
        if _identity(before) != _identity(after):
            raise ValueError("WAV changed during admission")
    return {"rate": rate, "channels": channels, "frames": frames,
            "identity": _identity(after), "bytes": after.st_size}


def compare_precision_batch(baseline: str | Path,
                            candidates: list[str | Path] | tuple[str | Path, ...],
                            *, chunk_frames: int = 4096) -> dict:
    """Bounded A/B pool, scanning the baseline once and publishing only neutral IDs.

    All sources are metadata-admitted first and rechecked after the final scan.
    No partial results escape if any source fails admission or changes.
    """
    if type(chunk_frames) is not int or not 1 <= chunk_frames <= 4096:
        raise ValueError("invalid chunk size")
    if type(candidates) not in (list, tuple) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("expected 1..8 candidates")
    paths = [baseline, *candidates]
    receipts = [_preadmit_wav(p) for p in paths]
    if sum(x["frames"] for x in receipts) > MAX_BATCH_FRAMES:
        raise ValueError("aggregate PCM frame budget exceeded")
    # Frame caps alone do not stop oversized RIFF ancillary chunks in many
    # small clips. Bound the sum of admitted physical file sizes too.
    if sum(x["bytes"] for x in receipts) > MAX_BATCH_BYTES:
        raise ValueError("aggregate WAV byte budget exceeded")
    if any(any(x[k] != receipts[0][k] for k in ("rate", "channels", "frames"))
           for x in receipts[1:]):
        raise ValueError("incomparable WAV format/duration")
    # A duplicate alias defeats a blind comparison and makes the workload
    # appear larger than its distinct audio set. Reject even hardlink aliases.
    identities = [(x["identity"][0], x["identity"][1]) for x in receipts]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate A/B audio source")
    a = _scan(baseline, chunk_frames=chunk_frames)
    if a["_source_identity"] != receipts[0]["identity"]:
        raise ValueError("baseline modified after admission")
    results = []
    for index, path in enumerate(candidates, 1):
        b = _scan(path, chunk_frames=chunk_frames)
        if b["_source_identity"] != receipts[index]["identity"]:
            raise ValueError("candidate modified after admission")
        outcome = _evaluate_precision(a, b)
        results.append({
            "candidate_id": f"candidate-{index:03d}",
            "candidate_precision_loss_inspect": outcome["candidate_precision_loss_inspect"],
            "warnings": outcome["warnings"],
        })
    for path, receipt in zip(paths, receipts):
        _assert_source_identity(path, receipt["identity"])
    return {"schema_version": 1, "status": "technical-inspection-only",
            "candidates": results}


class _PrivateArgumentParser(argparse.ArgumentParser):
    """Never echo private command-line operands in parser error messages."""

    def error(self, message: str) -> None:
        self.exit(3, "MixLab precision: invalid arguments\n")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateArgumentParser(
        description="Private, bounded PCM16 A/B precision-loss screen")
    parser.add_argument("baseline", metavar="BASELINE.wav")
    parser.add_argument("candidate", metavar="CANDIDATE.wav")
    parser.add_argument("additional_candidates", metavar="MORE.wav", nargs="*")
    parser.add_argument("--batch", action="store_true",
                        help="Compare 1..8 neutral candidates against one baseline")
    parser.add_argument(
        "--fail-on-warnings", action="store_true",
        help="Exit 2 on an inspection warning (not a music-quality judgment)",
    )
    parser.add_argument(
        "--require-conclusive", action="store_true",
        help="Exit 2 if there is insufficient PCM evidence (null result)",
    )
    args, unknown = parser.parse_known_args(argv)
    try:
        if unknown:
            raise ValueError("unexpected argument")
        if args.batch:
            result = compare_precision_batch(
                args.baseline, [args.candidate, *args.additional_candidates])
        else:
            if args.additional_candidates:
                raise ValueError("batch switch required")
            result = compare_precision(args.baseline, args.candidate)
    except (OSError, ValueError, EOFError, wave.Error):
        print("MixLab precision: invalid or incomparable private WAVs", file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    # A strict preflight can distinguish an invalid input (exit 3), a
    # technical inspection gate not met (exit 2), and a reportable check
    # (exit 0). The default mode remains descriptive and backward compatible.
    entries = result["candidates"] if args.batch else [result]
    if ((args.fail_on_warnings and any(row["warnings"] for row in entries))
            or (args.require_conclusive and any(
                row["candidate_precision_loss_inspect"] is None
                for row in entries))):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
