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

from . import ACTIVE_CHANNEL_RMS, MAX_SOURCE_BYTES, MAX_SOURCE_FRAMES, SILENT_WINDOW_RMS

LOW_PASS_HZ = 180
HIGH_PASS_HZ = 2500
DEFAULT_THRESHOLD_DB = 6.0
# A clean spectral ratio must not silently imply fair A/B loudness:
# detect an independently obvious full-file RMS mismatch first.
RMS_LEVEL_CONFOUND_DB = 1.5
# Risk-only stereo mono-fold proxy. True mono playback and downstream
# mastering are not simulated; this detects obvious polarity cancellation.
MONO_FOLD_LOSS_DB = -10.0
MONO_FOLD_CHANGE_DB = 6.0
MIN_RESOLVABLE_RATIO = 1e-4
READ_FRAMES = 4096
MAX_CANDIDATES = 8
MAX_AGGREGATE_FRAMES = 8_000_000
# Eight equal-duration private spans spot a shift in *when* spectral balance
# changes, even if whole-file band-energy proxies remain very similar.
SPECTRAL_SPANS = 8
TEMPORAL_PROXY_THRESHOLD_DB = 9.0
TEMPORAL_PROXY_MIN_FRACTION = 0.25
TEMPORAL_PROXY_MIN_SPANS = 3


def _source_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _scan_spectral_private(
    path: str | Path, *, max_frames: int = MAX_SOURCE_FRAMES,
    expected_format: tuple[int, int, int] | None = None,
) -> dict:
    """Stream a bounded regular PCM16 WAV over one file descriptor.

    First-order filters are intentionally cheap, deterministic proxies.
    Their energy ratios overlap; do not interpret them as isolated EQ bands.
    """
    if not isinstance(max_frames, int) or isinstance(max_frames, bool) or not 1 <= max_frames <= MAX_SOURCE_FRAMES:
        raise ValueError("max_frames must be within the configured source budget")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_path = os.fspath(path)
    fd = os.open(source_path, flags)
    try:
        with os.fdopen(fd, "rb", buffering=0) as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or not 44 <= before.st_size <= MAX_SOURCE_BYTES:
                raise ValueError("WAV must be a bounded regular file")
            with wave.open(handle, "rb") as source:
                channels, width, rate, frames, compression, _ = source.getparams()
                if compression != "NONE" or width != 2 or channels not in (1, 2):
                    raise ValueError("Only uncompressed PCM16 mono/stereo WAV is supported")
                if not 8000 <= rate <= 96000 or not 1 <= frames <= max_frames:
                    raise ValueError("Unsupported WAV rate or frame count")
                # Check comparability at the bounded header-admission stage:
                # do not spend CPU decoding an obviously mismatched candidate.
                if expected_format is not None and (rate, channels, frames) != expected_format:
                    raise ValueError("A/B WAV format mismatch")
                low_alpha = -math.expm1(-2 * math.pi * LOW_PASS_HZ / rate)
                high_alpha = -math.expm1(-2 * math.pi * HIGH_PASS_HZ / rate)
                low_state = [0.0] * channels
                high_state = [0.0] * channels
                # A second LP at 2500 Hz follows the 180 Hz HP residual:
                # a cheap midrange proxy, not an isolated spectral band.
                mid_state = [0.0] * channels
                total_energy = low_energy = mid_energy = high_energy = 0.0
                # Channel-local aggregates catch A/B left/right spectral
                # migrations hidden by an identical total stereo spectrum.
                channel_energy = [[0.0, 0.0, 0.0, 0.0] for _ in range(channels)]
                stereo_cross_energy = 0.0
                # Constant memory (eight aggregate bins), never samples or
                # per-span envelopes in the public report.
                span_energy = [[0.0, 0.0, 0.0, 0.0, 0] for _ in range(SPECTRAL_SPANS)]
                span_cross_energy = [0.0] * SPECTRAL_SPANS
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
                        mid_input = value - low_state[channel]
                        mid_state[channel] += high_alpha * (mid_input - mid_state[channel])
                        sample_energy = value * value
                        low_sample_energy = low_state[channel] ** 2
                        high_sample_energy = high_residual * high_residual
                        mid_sample_energy = mid_state[channel] ** 2
                        total_energy += sample_energy
                        low_energy += low_sample_energy
                        mid_energy += mid_sample_energy
                        high_energy += high_sample_energy
                        channel_energy[channel][0] += sample_energy
                        channel_energy[channel][1] += low_sample_energy
                        channel_energy[channel][2] += mid_sample_energy
                        channel_energy[channel][3] += high_sample_energy
                        if channels == 2 and channel == 1:
                            # Adjacent samples form one stereo PCM16 frame.
                            stereo_cross_energy += (samples[index - 1] / 32768) * value
                        span = min(SPECTRAL_SPANS - 1, ((frames - remaining + index // channels) * SPECTRAL_SPANS) // frames)
                        span_energy[span][0] += sample_energy
                        span_energy[span][1] += low_sample_energy
                        span_energy[span][2] += mid_sample_energy
                        span_energy[span][3] += high_sample_energy
                        if channels == 2 and channel == 1:
                            span_cross_energy[span] += (samples[index - 1] / 32768) * value
                        if channel == 0:
                            span_energy[span][4] += 1
                    remaining -= count
            if _source_identity(before) != _source_identity(os.fstat(handle.fileno())):
                raise ValueError("WAV changed while being inspected")
            # A stable open descriptor alone is insufficient: a concurrent
            # rename could replace the pathname while we read the old inode.
            # Fail closed if its on-disk identity no longer matches the FD.
            try:
                named_after = os.stat(source_path, follow_symlinks=False)
            except OSError as exc:
                raise ValueError("WAV pathname changed while being inspected") from exc
            if (not stat.S_ISREG(named_after.st_mode)
                    or _source_identity(before) != _source_identity(named_after)):
                raise ValueError("WAV pathname changed while being inspected")
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
        "midpass_180_2500_ratio": math.sqrt(mid_energy / total_energy) if total_energy else None,
        "highpass_2500_ratio": math.sqrt(high_energy / total_energy) if total_energy else None,
        "_rms": rms,
        "_mono_fold_ratio": (
            math.sqrt(max(0.0, min(1.0, (0.5 * total_energy + stereo_cross_energy) / total_energy)))
            if channels == 2 and total_energy else None
        ),
        # Only used privately to flag aliases / hardlinks in a blind pack.
        "_source_key": (before.st_dev, before.st_ino),
        "_source_stat_identity": _source_identity(before),
        "_channels": [
            (
                math.sqrt(low / total) if total else None,
                math.sqrt(mid / total) if total else None,
                math.sqrt(high / total) if total else None,
                math.sqrt(total / frames),
            )
            for total, low, mid, high in channel_energy
        ],
        "_fold_spans": [
            (
                math.sqrt(max(0.0, min(1.0, 0.5 + cross / energy)))
                if channels == 2 and energy > 0
                and math.sqrt(energy / (count * channels)) >= SILENT_WINDOW_RMS
                else None
            )
            for (energy, _, _, _, count), cross in zip(span_energy, span_cross_energy)
        ],
        "_spans": [
            (
                math.sqrt(low / total) if total else None,
                math.sqrt(mid / total) if total else None,
                math.sqrt(high / total) if total else None,
                math.sqrt(total / (count * channels)) if count else 0.0,
            )
            for total, low, mid, high, count in span_energy
        ],
    }


def scan_spectral_proxy(
    path: str | Path, *, max_frames: int = MAX_SOURCE_FRAMES,
    expected_format: tuple[int, int, int] | None = None,
) -> dict:
    """Public, strictly redacted PCM16 spectral metrics only.

    File identities, private per-channel energies and per-span summaries
    remain internal to compare_spectral_balance and never escape via this API.
    """
    return _public_metrics(
        _scan_spectral_private(path, max_frames=max_frames, expected_format=expected_format)
    )


def _severe_stereo_channel_loss(metrics: dict) -> bool:
    """One channel near-silent while the other carries substantial energy."""
    if metrics["channels"] != 2:
        return False
    levels = [channel[3] for channel in metrics["_channels"]]
    return (min(levels) < SILENT_WINDOW_RMS and max(levels) > ACTIVE_CHANNEL_RMS)


def compare_spectral_balance(
    baseline: str | Path, candidates: list[str | Path], *, threshold_db: float = DEFAULT_THRESHOLD_DB
) -> dict:
    """Compare relative low/high energy proxies without outputting source IDs."""
    if not isinstance(threshold_db, (int, float)) or isinstance(threshold_db, bool) or (
        not math.isfinite(threshold_db) or not 0 < threshold_db <= 24
    ):
        raise ValueError("threshold_db must be finite and in (0,24]")
    if not candidates or len(candidates) > MAX_CANDIDATES:
        raise ValueError("Expected 1..8 candidates")

    reference = _scan_spectral_private(baseline)
    rows = []
    # Revalidate every participant *after* the whole comparison, not just
    # each WAV at its own scan end. An early baseline can otherwise change
    # while a later candidate is being decoded, invalidating the A/B report.
    source_snapshots = [(os.fspath(baseline), reference["_source_stat_identity"])]
    seen_sources = {reference["_source_key"]}
    scanned_frames = reference["frames"]
    for index, candidate in enumerate(candidates, 1):
        remaining_budget = MAX_AGGREGATE_FRAMES - scanned_frames
        if remaining_budget <= 0:
            raise ValueError("Aggregate frame budget exceeded")
        current = _scan_spectral_private(
            candidate, max_frames=min(MAX_SOURCE_FRAMES, remaining_budget),
            expected_format=(reference["sample_rate"], reference["channels"], reference["frames"]),
        )
        scanned_frames += current["frames"]
        source_snapshots.append((os.fspath(candidate), current["_source_stat_identity"]))
        if any(current[key] != reference[key] for key in ("sample_rate", "channels", "frames")):
            raise ValueError("A/B sample rate, channel count or frame count differs")
        warnings = []
        if current["_source_key"] in seen_sources:
            warnings.append("same_input_file_inspect_for_blind_noop")
        if _severe_stereo_channel_loss(reference) or _severe_stereo_channel_loss(current):
            warnings.append("stereo_channel_near_silence_inspect")
        seen_sources.add(current["_source_key"])
        deltas = {}
        # Channel-local energy ratios cannot see polarity inversion: squared
        # band energies remain equal even when mono folding cancels content.
        # Use one summed L*R cross-energy to estimate RMS((L+R)/2)
        # relative to the original two-channel RMS, with no PCM retention.
        if reference["channels"] == 2:
            fold_a, fold_b = reference["_mono_fold_ratio"], current["_mono_fold_ratio"]
            if (reference["_rms"] >= SILENT_WINDOW_RMS and
                    current["_rms"] >= SILENT_WINDOW_RMS and
                    fold_a is not None and fold_b is not None):
                if min(fold_a, fold_b) > MIN_RESOLVABLE_RATIO:
                    fold_delta = 20 * math.log10(fold_b / fold_a)
                    deltas["stereo_mono_fold_ratio_delta_db"] = round(fold_delta, 3)
                    if abs(fold_delta) >= MONO_FOLD_CHANGE_DB:
                        warnings.append("stereo_mono_fold_change_inspect")
                else:
                    deltas["stereo_mono_fold_ratio_delta_db"] = None
                if min(fold_a, fold_b) <= 10 ** (MONO_FOLD_LOSS_DB / 20):
                    warnings.append("stereo_mono_fold_cancellation_inspect")
            else:
                deltas["stereo_mono_fold_ratio_delta_db"] = None
                warnings.append("stereo_mono_fold_unresolved_inspect")
        # The ratios below intentionally normalize out overall gain.
        # Report an independent sample-RMS confound, *not* perceptual LUFS.
        if reference["_rms"] >= SILENT_WINDOW_RMS and current["_rms"] >= SILENT_WINDOW_RMS:
            level_delta = 20 * math.log10(current["_rms"] / reference["_rms"])
            deltas["rms_delta_db_vs_baseline"] = round(level_delta, 3)
            if abs(level_delta) > RMS_LEVEL_CONFOUND_DB:
                warnings.append("rms_level_mismatch_inspect_not_lufs")
        else:
            deltas["rms_delta_db_vs_baseline"] = None
        if reference["_rms"] < SILENT_WINDOW_RMS or current["_rms"] < SILENT_WINDOW_RMS:
            warnings.append("insufficient_audible_energy_for_spectral_comparison")
        else:
            for name, key in (
                ("low", "lowpass_180_ratio"),
                ("mid", "midpass_180_2500_ratio"),
                ("high", "highpass_2500_ratio"),
            ):
                a, b = reference[key], current[key]
                if a is None or b is None or min(a, b) < MIN_RESOLVABLE_RATIO:
                    deltas[name + "_proxy_delta_db"] = None
                    warnings.append(name + "_proxy_unresolved_inspect")
                else:
                    delta = 20 * math.log10(b / a)
                    deltas[name + "_proxy_delta_db"] = round(delta, 3)
                    if abs(delta) >= threshold_db:
                        warnings.append(name + "_spectral_balance_shift_inspect")
        for name in ("low", "mid", "high"):
            deltas.setdefault(name + "_proxy_delta_db", None)

        # A/B can have identical whole-file energy yet move silence to
        # different positions. Comparing *only* simultaneously audible
        # segments then skips the evidence and can falsely look clean.
        # Report a coarse fraction, never source-specific time coordinates.
        activity = [
            ((ref_span[3] >= SILENT_WINDOW_RMS), (cur_span[3] >= SILENT_WINDOW_RMS))
            for ref_span, cur_span in zip(reference["_spans"], current["_spans"])
        ]
        activity_mismatches = sum(a != b for a, b in activity)
        comparable_activity = sum(a and b for a, b in activity)
        deltas["temporal_audibility_mismatch_fraction"] = round(
            activity_mismatches / len(activity), 6
        )
        if activity_mismatches:
            warnings.append("temporal_audibility_alignment_inspect")
        if (reference["_rms"] >= SILENT_WINDOW_RMS
                and current["_rms"] >= SILENT_WINDOW_RMS
                and comparable_activity < TEMPORAL_PROXY_MIN_SPANS):
            warnings.append("insufficient_temporal_spectral_coverage_inspect")

        # A/B can have *equal global* low/high ratios even if the bass and
        # treble moments were swapped. Eight private time-aligned summaries
        # expose persistent level-normalized band changes without exporting
        # source time coordinates, band envelopes, or audio. Skip quiet or
        # unresolved spans; never create a false 0dB from missing evidence.
        for name, slot in (("low", 0), ("mid", 1), ("high", 2)):
            eligible = differing = 0
            for ref_span, cur_span in zip(reference["_spans"], current["_spans"]):
                if min(ref_span[3], cur_span[3]) < SILENT_WINDOW_RMS:
                    continue
                a, b = ref_span[slot], cur_span[slot]
                if a is None or b is None or min(a, b) < MIN_RESOLVABLE_RATIO:
                    continue
                eligible += 1
                if abs(20 * math.log10(b / a)) >= TEMPORAL_PROXY_THRESHOLD_DB:
                    differing += 1
            fraction = round(differing / eligible, 6) if eligible >= TEMPORAL_PROXY_MIN_SPANS else None
            deltas["temporal_" + name + "_proxy_mismatch_fraction"] = fraction
            if (eligible >= TEMPORAL_PROXY_MIN_SPANS and differing >= 2
                    and differing / eligible >= TEMPORAL_PROXY_MIN_FRACTION):
                warnings.append(name + "_temporal_spectral_shift_inspect")
        # Half the mix may cancel in mono while the *global* mono-fold
        # ratio is still just -3dB. Two or more strongly cancelling audible
        # time-spans warrant inspection even when no whole-file gate fires.
        if reference["channels"] == 2:
            local_cancellation_spans = sum(
                ((a is not None and a <= 10 ** (MONO_FOLD_LOSS_DB / 20)) or
                 (b is not None and b <= 10 ** (MONO_FOLD_LOSS_DB / 20)))
                for a, b in zip(reference["_fold_spans"], current["_fold_spans"])
            )
            deltas["stereo_temporal_mono_fold_cancellation_risk"] = (
                local_cancellation_spans >= 2
            )
            if local_cancellation_spans >= 2:
                warnings.append("stereo_temporal_mono_fold_cancellation_inspect")
        # Whole-stereo ratios mask shifts in frequency placement between L/R.
        # Compare *each* channel at matched playback positions, but expose
        # just coarse boolean flags, not channel identity or private energies.
        if reference["channels"] == 2:
            for name, slot in (("low", 0), ("mid", 1), ("high", 2)):
                mismatched = False
                for ref_ch, cur_ch in zip(reference["_channels"], current["_channels"]):
                    if min(ref_ch[3], cur_ch[3]) < SILENT_WINDOW_RMS:
                        continue
                    a, b = ref_ch[slot], cur_ch[slot]
                    if a is None or b is None or min(a, b) < MIN_RESOLVABLE_RATIO:
                        continue
                    if abs(20 * math.log10(b / a)) >= threshold_db:
                        mismatched = True
                deltas["stereo_channel_" + name + "_spectral_shift_risk"] = mismatched
                if mismatched:
                    warnings.append("stereo_channel_" + name + "_spectral_shift_inspect")
        rows.append({
            "id": f"candidate-{index:02d}",
            "metrics": _public_metrics(current),
            **deltas,
            "warnings": warnings,
        })
    # Final best-effort all-input stability gate. Reject stale baseline or
    # early-candidate observations; no partial JSON can be emitted on error.
    for source_path, snapshot in source_snapshots:
        try:
            current_stat = os.stat(source_path, follow_symlinks=False)
        except OSError as exc:
            raise ValueError("A/B input changed during comparison") from exc
        if (not stat.S_ISREG(current_stat.st_mode)
                or _source_identity(current_stat) != snapshot):
            raise ValueError("A/B input changed during comparison")

    return {
        "schema_version": 1,
        "method": "first_order_energy_ratio_proxy_not_lufs_or_calibrated_spectrum",
        "threshold_db": float(threshold_db),
        "baseline": _public_metrics(reference),
        "candidates": rows,
        "human_preference_test_required": True,
    }


_PUBLIC_METRIC_FIELDS = (
    "sample_rate", "channels", "frames", "rms_dbfs",
    "lowpass_180_ratio", "midpass_180_2500_ratio",
    "highpass_2500_ratio",
)


def _public_metrics(metrics: dict) -> dict:
    """Closed allowlist: future private metric fields cannot leak by default."""
    return {
        key: round(metrics[key], 6)
        if key.endswith("_ratio") and metrics[key] is not None
        else metrics[key]
        for key in _PUBLIC_METRIC_FIELDS
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
