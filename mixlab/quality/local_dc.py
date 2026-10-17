"""Read-only PCM16 preflight for persistent *local* DC-offset confounds.

A whole-clip DC mean can hide a +DC section followed by a -DC section.
This technical check abstains on short/ambiguous evidence and never judges
musical quality. It does not modify input or publish source paths or samples.
"""
from __future__ import annotations

from array import array
import argparse
import json
import os
from pathlib import Path
import stat
import struct
import sys
import wave

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FRAMES = 2_000_000
WINDOW_MS = 250
MIN_SUSTAINED_WINDOWS = 4  # 1 second, including on 8 kHz recordings
DC_THRESHOLD = 0.03  # 3% full-scale absolute DC
RELATIVE_THRESHOLD = 0.025  # candidate vs baseline mean change
CHUNK_FRAMES = 4096
MAX_BATCH_CANDIDATES = 8
MAX_BATCH_FRAMES = 8_000_000
MAX_BATCH_BYTES = 128 * 1024 * 1024


def _identity(st: os.stat_result) -> tuple[int, ...]:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _scan_private_pcm(source: str | os.PathLike[str]) -> dict:
    """Retain window means only; fail closed on nonregular/changing input."""
    fd = None
    path = Path(source)
    try:
        original = path.lstat()
        if not stat.S_ISREG(original.st_mode):
            raise ValueError("private input must be a regular WAV")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or _identity(before) != _identity(original):
            raise ValueError("private WAV changed during admission")
        if not 44 <= before.st_size <= MAX_SOURCE_BYTES:
            raise ValueError("private WAV outside byte bounds")
        with os.fdopen(fd, "rb", closefd=True) as handle:
            fd = None
            with wave.open(handle, "rb") as wav:
                channels, width, rate, frames, compression, _ = wav.getparams()
                if channels not in (1, 2) or width != 2 or compression != "NONE":
                    raise ValueError("PCM16 mono/stereo required")
                if not 8000 <= rate <= 96000 or not 1 <= frames <= MAX_SOURCE_FRAMES:
                    raise ValueError("private WAV outside frame/rate bounds")
                window_size = max(1, round(rate * WINDOW_MS / 1000))
                means = []
                sums = [0] * channels
                used_window = processed = 0
                while processed < frames:
                    expected = min(CHUNK_FRAMES, frames - processed)
                    raw = wav.readframes(expected)
                    if len(raw) != expected * channels * 2:
                        raise ValueError("truncated PCM payload")
                    samples = array("h")
                    samples.frombytes(raw)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    for i in range(0, len(samples), channels):
                        for c in range(channels):
                            sums[c] += samples[i + c]
                        used_window += 1
                        if used_window == window_size:
                            means.append(tuple(s / (window_size * 32768.0) for s in sums))
                            sums = [0] * channels
                            used_window = 0
                    processed += expected
            after = os.fstat(handle.fileno())
            if _identity(after) != _identity(before):
                raise ValueError("private WAV changed during scanning")
        final = path.lstat()
        if not stat.S_ISREG(final.st_mode) or _identity(final) != _identity(before):
            raise ValueError("private WAV path changed during scanning")
        return {"_identity": _identity(before), "channels": channels, "sample_rate": rate, "frames": frames,
                "window_count": len(means), "means": means}
    except (OSError, EOFError, wave.Error, struct.error, OverflowError) as exc:
        raise ValueError("private WAV could not be safely inspected") from None
    finally:
        if fd is not None:
            os.close(fd)


def _run_state(flags: list[bool], *, enough_windows: bool) -> bool | None:
    if not enough_windows:
        return None
    run = best = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    if best >= MIN_SUSTAINED_WINDOWS:
        return True
    if best:
        return None  # evidence is too short to call good or bad
    return False


def _verify_pair_source(source: str | os.PathLike[str], expected: tuple[int, ...]) -> None:
    try:
        after = Path(source).lstat()
        if not stat.S_ISREG(after.st_mode) or _identity(after) != expected:
            raise ValueError("private WAV changed during pair inspection")
    except OSError:
        raise ValueError("private WAV changed during pair inspection") from None


def _compare_scans(ref: dict, alt: dict) -> dict:
    """Compare already-screened private sources; reusable by bounded batches."""
    if any(ref[k] != alt[k] for k in ("channels", "sample_rate", "frames", "window_count")):
        raise ValueError("private PCM16 sources do not have identical shape")
    n = ref["window_count"]
    baseline_states = []
    excess_states = []
    for c in range(ref["channels"]):
        baseline_states.append(_run_state(
            [abs(row[c]) >= DC_THRESHOLD for row in ref["means"]],
            enough_windows=n >= MIN_SUSTAINED_WINDOWS,
        ))
        excess_states.append(_run_state(
            [abs(new[c]) >= DC_THRESHOLD and
             abs(new[c] - old[c]) >= RELATIVE_THRESHOLD
             for old, new in zip(ref["means"], alt["means"])],
            enough_windows=n >= MIN_SUSTAINED_WINDOWS,
        ))
    all_states = baseline_states + excess_states
    warning = True if True in all_states else (None if None in all_states else False)
    return {
        "check": "local-dc-bias-v1",
        "warning": warning,
        "baseline_bias_warning": baseline_states,
        "candidate_excess_bias_warning": excess_states,
        "channels": ref["channels"],
        "sample_rate": ref["sample_rate"],
        "frames": ref["frames"],
        "window_ms": WINDOW_MS,
        "complete_windows": n,
        "thresholds": {"dc_fraction_full_scale": DC_THRESHOLD,
                       "relative_fraction_full_scale": RELATIVE_THRESHOLD,
                       "min_consecutive_windows": MIN_SUSTAINED_WINDOWS},
        "interpretation": "Technical DC confound only; not LUFS, clipping proof, or musical preference.",
    }


def inspect(baseline: str | os.PathLike[str], candidate: str | os.PathLike[str]) -> dict:
    """Compare distinct equal-shape private PCM16 files, read-only."""
    ref = _scan_private_pcm(baseline)
    alt = _scan_private_pcm(candidate)
    if ref["_identity"][:2] == alt["_identity"][:2]:
        raise ValueError("A/B sources must be distinct regular files")
    result = _compare_scans(ref, alt)
    _verify_pair_source(baseline, ref["_identity"])
    _verify_pair_source(candidate, alt["_identity"])
    return result


def _admit_batch(sources: list[str | os.PathLike[str]]) -> list[dict]:
    """Admit *all* inputs before decoding any PCM or publishing results.

    This initial read is metadata only. Subsequent full scans verify the exact
    admission device/inode/size/timestamps, and all names are checked again
    after the last candidate. The bounds include the baseline exactly once.
    """
    if not 2 <= len(sources) <= MAX_BATCH_CANDIDATES + 1:
        raise ValueError("Batch needs one baseline and 1..8 candidates")
    accepted = []
    seen = set()
    total_bytes = total_frames = 0
    shape = None
    for source in sources:
        path = Path(source)
        fd = None
        try:
            original = path.lstat()
            if not stat.S_ISREG(original.st_mode):
                raise ValueError("Batch input is not a regular WAV")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            fd = os.open(path, flags)
            actual = os.fstat(fd)
            if not stat.S_ISREG(actual.st_mode) or _identity(actual) != _identity(original):
                raise ValueError("Batch source changed during admission")
            if not 44 <= actual.st_size <= MAX_SOURCE_BYTES:
                raise ValueError("Batch input outside per-file byte bounds")
            key = (actual.st_dev, actual.st_ino)
            if key in seen:
                raise ValueError("Batch WAVs must have distinct identities")
            seen.add(key)
            with os.fdopen(fd, "rb", closefd=True) as handle:
                fd = None
                with wave.open(handle, "rb") as wav:
                    channels, width, rate, frames, comp, _ = wav.getparams()
                    if comp != "NONE" or width != 2 or channels not in (1, 2):
                        raise ValueError("Batch requires PCM16 mono/stereo")
                    if not 8000 <= rate <= 96000 or not 1 <= frames <= MAX_SOURCE_FRAMES:
                        raise ValueError("Batch input outside frame/rate bounds")
                    current_shape = (channels, rate, frames)
                    if shape is None:
                        shape = current_shape
                    elif shape != current_shape:
                        raise ValueError("Batch PCM shapes must match")
                    total_bytes += actual.st_size
                    total_frames += frames
                    if total_bytes > MAX_BATCH_BYTES or total_frames > MAX_BATCH_FRAMES:
                        raise ValueError("Batch resource admission limit exceeded")
                if _identity(os.fstat(handle.fileno())) != _identity(actual):
                    raise ValueError("Batch source mutated during metadata admission")
            accepted.append({"source": source, "identity": _identity(actual)})
        except (OSError, EOFError, wave.Error, struct.error, OverflowError):
            raise ValueError("Batch private WAV admission failed") from None
        finally:
            if fd is not None:
                os.close(fd)
    # Recheck every source after final admission to catch path/metadata changes
    # before the first PCM frame is read.
    for entry in accepted:
        _verify_pair_source(entry["source"], entry["identity"])
    return accepted


def inspect_batch(baseline: str | os.PathLike[str],
                  candidates: list[str | os.PathLike[str]]) -> dict:
    """Read-only one-to-many technical screen; no partial result on any error.

    A baseline is PCM-decoded *once* for at most 8 unique candidates. Refuse
    mismatched sources or any post-admission mutation across the entire batch.
    """
    if not isinstance(candidates, (list, tuple)):
        raise ValueError("Candidate collection must be a list")
    sources = [baseline, *candidates]
    admitted = _admit_batch(sources)
    ref = _scan_private_pcm(baseline)
    if ref["_identity"] != admitted[0]["identity"]:
        raise ValueError("Baseline changed after batch admission")
    details = []
    for index, candidate in enumerate(candidates, 1):
        scan = _scan_private_pcm(candidate)
        if scan["_identity"] != admitted[index]["identity"]:
            raise ValueError("Candidate changed after batch admission")
        result = _compare_scans(ref, scan)
        details.append({"candidate_id": f"candidate-{index:03d}",
                        "warning": result["warning"],
                        "candidate_excess_bias_warning": result["candidate_excess_bias_warning"]})
    for entry in admitted:
        _verify_pair_source(entry["source"], entry["identity"])
    states = [flag for item in details for flag in [item["warning"]]]
    states += _compare_scans(ref, ref)["baseline_bias_warning"]
    overall = True if True in states else (None if None in states else False)
    return {
        "check": "local-dc-bias-batch-v1",
        "warning": overall,
        "baseline_bias_warning": _compare_scans(ref, ref)["baseline_bias_warning"],
        "channels": ref["channels"],
        "sample_rate": ref["sample_rate"],
        "frames": ref["frames"],
        "candidate_count": len(details),
        "candidates": details,
        "window_ms": WINDOW_MS,
        "interpretation": "Technical DC confound only; not musical preference.",
    }


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default error includes unknown option values, possibly
        # absolute private audio paths. Never let it write usage or arguments.
        raise ValueError("Invalid options")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateArgumentParser(description="Offline, private local DC bias preflight")
    parser.add_argument("baseline")
    parser.add_argument("candidate", nargs="+")
    parser.add_argument("--batch", action="store_true", help="screen 1..8 candidates with a shared baseline")
    parser.add_argument("--strict", action="store_true",
                        help="exit 2 for warning or inconclusive result")
    try:
        args = parser.parse_args(argv)
        if args.batch:
            result = inspect_batch(args.baseline, args.candidate)
        elif len(args.candidate) == 1:
            result = inspect(args.baseline, args.candidate[0])
        else:
            raise ValueError("Pass --batch for multiple candidates")
    except (Exception, SystemExit):
        # Protect private paths even in argparse usage errors and OS exceptions.
        print("Invalid private WAV pair or options", file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True))
    return 2 if args.strict and result["warning"] is not False else 0


if __name__ == "__main__":
    raise SystemExit(main())
