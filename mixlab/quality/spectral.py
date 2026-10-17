"""Optional CPU-only spectral-balance proxy for private blind A/B WAV preflight.

This is *not* a calibrated frequency analyzer, LUFS, true-peak, or a music
preference score. No source audio or filenames are included in reports.
"""
from __future__ import annotations

import argparse
from array import array
import json
import math
import os
from pathlib import Path
import stat
import sys
import wave

from . import MAX_SOURCE_BYTES, MAX_SOURCE_FRAMES, SILENT_WINDOW_RMS

LOW_PASS_HZ = 180
HIGH_PASS_HZ = 2500
DEFAULT_THRESHOLD_DB = 6.0
MIN_RESOLVABLE_RATIO = 1e-4
READ_FRAMES = 4096


def _source_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def scan_spectral_proxy(path: str | Path) -> dict:
    """Stream a bounded regular PCM16 WAV over one file descriptor.

    First-order filters are intentionally cheap, deterministic proxies.
    Their energy ratios overlap; do not interpret them as isolated EQ bands.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(os.fspath(path), flags)
    try:
        with os.fdopen(fd, "rb", buffering=0) as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or not 44 <= before.st_size <= MAX_SOURCE_BYTES:
                raise ValueError("WAV must be a bounded regular file")
            with wave.open(handle, "rb") as source:
                channels, width, rate, frames, compression, _ = source.getparams()
                if compression != "NONE" or width != 2 or channels not in (1, 2):
                    raise ValueError("Only uncompressed PCM16 mono/stereo WAV is supported")
                if not 8000 <= rate <= 96000 or not 1 <= frames <= MAX_SOURCE_FRAMES:
                    raise ValueError("Unsupported WAV rate or frame count")
                low_alpha = -math.expm1(-2 * math.pi * LOW_PASS_HZ / rate)
                high_alpha = -math.expm1(-2 * math.pi * HIGH_PASS_HZ / rate)
                low_state = [0.0] * channels
                high_state = [0.0] * channels
                total_energy = low_energy = high_energy = 0.0
                remaining = frames
                while remaining:
                    count = min(READ_FRAMES, remaining)
                    raw = source.readframes(count)
                    if len(raw) != count * channels * 2:
                        raise ValueError("Truncated PCM16 WAV")
                    samples = array("h")
                    samples.frombytes(raw)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    for index, sample in enumerate(samples):
                        channel = index % channels
                        value = sample / 32768
                        low_state[channel] += low_alpha * (value - low_state[channel])
                        high_state[channel] += high_alpha * (value - high_state[channel])
                        high_residual = value - high_state[channel]
                        total_energy += value * value
                        low_energy += low_state[channel] ** 2
                        high_energy += high_residual * high_residual
                    remaining -= count
            if _source_identity(before) != _source_identity(os.fstat(handle.fileno())):
                raise ValueError("WAV changed while being inspected")
    except BaseException:
        # fdopen normally owns fd; if creation failed, avoid leaking it.
        try:
            os.close(fd)
        except OSError:
            pass
        raise

    rms = math.sqrt(total_energy / (frames * channels))
    return {
        "sample_rate": rate,
        "channels": channels,
        "frames": frames,
        "rms_dbfs": round(20 * math.log10(rms), 3) if rms else None,
        "lowpass_180_ratio": math.sqrt(low_energy / total_energy) if total_energy else None,
        "highpass_2500_ratio": math.sqrt(high_energy / total_energy) if total_energy else None,
        "_rms": rms,
    }


def compare_spectral_balance(
    baseline: str | Path, candidates: list[str | Path], *, threshold_db: float = DEFAULT_THRESHOLD_DB
) -> dict:
    """Compare relative low/high energy proxies without outputting source IDs."""
    if not isinstance(threshold_db, (int, float)) or isinstance(threshold_db, bool) or (
        not math.isfinite(threshold_db) or not 0 < threshold_db <= 24
    ):
        raise ValueError("threshold_db must be finite and in (0,24]")
    if not candidates or len(candidates) > 60:
        raise ValueError("Expected 1..60 candidates")

    reference = scan_spectral_proxy(baseline)
    rows = []
    for index, candidate in enumerate(candidates, 1):
        current = scan_spectral_proxy(candidate)
        if any(current[key] != reference[key] for key in ("sample_rate", "channels", "frames")):
            raise ValueError("A/B sample rate, channel count or frame count differs")
        warnings = []
        deltas = {}
        if reference["_rms"] < SILENT_WINDOW_RMS or current["_rms"] < SILENT_WINDOW_RMS:
            warnings.append("insufficient_audible_energy_for_spectral_comparison")
        else:
            for name, key in (("low", "lowpass_180_ratio"), ("high", "highpass_2500_ratio")):
                a, b = reference[key], current[key]
                if a is None or b is None or min(a, b) < MIN_RESOLVABLE_RATIO:
                    deltas[name + "_proxy_delta_db"] = None
                    warnings.append(name + "_proxy_unresolved_inspect")
                else:
                    delta = 20 * math.log10(b / a)
                    deltas[name + "_proxy_delta_db"] = round(delta, 3)
                    if abs(delta) >= threshold_db:
                        warnings.append(name + "_spectral_balance_shift_inspect")
        for name in ("low", "high"):
            deltas.setdefault(name + "_proxy_delta_db", None)
        rows.append({
            "id": f"candidate-{index:02d}",
            "metrics": _public_metrics(current),
            **deltas,
            "warnings": warnings,
        })
    return {
        "schema_version": 1,
        "method": "first_order_energy_ratio_proxy_not_lufs_or_calibrated_spectrum",
        "threshold_db": float(threshold_db),
        "baseline": _public_metrics(reference),
        "candidates": rows,
        "human_preference_test_required": True,
    }


def _public_metrics(metrics: dict) -> dict:
    return {
        k: round(v, 6) if k.endswith("_ratio") and v is not None else v
        for k, v in metrics.items() if not k.startswith("_")
    }


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "spectral preflight: invalid arguments (details withheld)\n")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateArgumentParser(description="CPU-only spectral balance screen, not music quality")
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--threshold-db", type=float, default=DEFAULT_THRESHOLD_DB)
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = compare_spectral_balance(
            args.baseline, args.candidates, threshold_db=args.threshold_db
        )
    except (OSError, ValueError, wave.Error, EOFError, OverflowError):
        parser.exit(3, "spectral preflight: invalid or unreadable WAV (details withheld)\n")
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    if args.fail_on_warnings and any(row["warnings"] for row in report["candidates"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
