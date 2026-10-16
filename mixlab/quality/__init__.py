"""Bounded, streaming audio diagnostics for offline MixLab listening candidates.

Technical screening is not music quality, tempo analysis or perceptual loudness.
The module intentionally does not open or write output audio files.
"""

from __future__ import annotations

from array import array
import math
from pathlib import Path
import sys
import wave

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FRAMES = 2_000_000
SILENT_WINDOW_RMS = 10 ** (-55 / 20)
# Investigate gaps of at least 200 ms between audible sections, even if
# the rest of an otherwise valid transition is loud.
INTERIOR_SILENT_GAP_WARNING_MS = 200
# Screening heuristic: a loss >= 9 dB during a non-silent stereo window
# means downmixing to mono may suppress an important part of the sound.
MONO_FOLD_DOWN_RISK_DB = 9.0
MONO_FOLD_DOWN_RISK_POWER_RATIO = 10 ** (-MONO_FOLD_DOWN_RISK_DB / 10)


def _dbfs(value: float) -> float | None:
    """Numerical RMS/peak in dBFS, not integrated perceptual loudness (LUFS)."""
    return round(20 * math.log10(value), 3) if value > 0 else None


def scan_wav(path: str | Path, *, window_ms: int = 100) -> dict:
    """Read at most 32 MiB of PCM16 WAV using bounded chunks.

    Window RMS and short-term silence are simplistic signal diagnostics, not
    beat detection, musical quality or a BS.1770/LUFS measurement.
    """
    if not isinstance(window_ms, int) or isinstance(window_ms, bool) or not 20 <= window_ms <= 1000:
        raise ValueError("window_ms must be an integer between 20 and 1000")
    path = Path(path)
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("WAV exceeds the 32 MiB screening limit")

    try:
        with wave.open(str(path), "rb") as src:
            channels, sample_width, rate, nframes, compression, _ = src.getparams()
            if compression != "NONE" or sample_width != 2 or channels not in (1, 2):
                raise ValueError("Only uncompressed PCM16 mono/stereo WAV is supported")
            if not 8000 <= rate <= 96000:
                raise ValueError("Sample rate must be 8000..96000 Hz")
            if not 1 <= nframes <= MAX_SOURCE_FRAMES:
                raise ValueError("Frames must be between 1 and 2,000,000")
            window_frames = max(1, round(rate * window_ms / 1000))
            peak_sample = 0
            near_full_scale = 0
            total_samples = 0
            sum_squares = 0
            sum_samples = [0] * channels
            channel_sum_squares = [0] * channels
            stereo_cross_product = 0
            stereo_mid_sum_squares = 0.0
            max_jump = 0
            previous = None
            window_sum_squares = 0
            window_mid_sum_squares = 0.0
            window_samples = 0
            window_peaks = []
            silent_windows = 0
            windows = 0
            seen_audible_window = False
            pending_interior_silence_frames = 0
            longest_interior_silence_frames = 0
            eligible_stereo_windows = 0
            phase_risk_windows = 0

            def finish_window():
                nonlocal window_sum_squares, window_mid_sum_squares, window_samples
                nonlocal silent_windows, windows, eligible_stereo_windows, phase_risk_windows
                nonlocal seen_audible_window, pending_interior_silence_frames, longest_interior_silence_frames
                if window_samples:
                    wrms = math.sqrt(window_sum_squares / window_samples) / 32768
                    window_peaks.append(wrms)
                    is_silent = wrms < SILENT_WINDOW_RMS
                    silent_windows += is_silent
                    if is_silent:
                        if seen_audible_window:
                            pending_interior_silence_frames += window_samples // channels
                    else:
                        if seen_audible_window:
                            longest_interior_silence_frames = max(
                                longest_interior_silence_frames, pending_interior_silence_frames
                            )
                        seen_audible_window = True
                        pending_interior_silence_frames = 0
                    if channels == 2 and wrms >= SILENT_WINDOW_RMS:
                        eligible_stereo_windows += 1
                        # Compare mono (L+R)/2 power to original per-channel power.
                        # Silent windows must not trigger false cancellation alerts.
                        if 2 * window_mid_sum_squares <= MONO_FOLD_DOWN_RISK_POWER_RATIO * window_sum_squares:
                            phase_risk_windows += 1
                    windows += 1
                    window_sum_squares = 0
                    window_mid_sum_squares = 0.0
                    window_samples = 0

            remaining = nframes
            while remaining:
                count = min(4096, remaining)
                raw = src.readframes(count)
                if len(raw) != count * channels * 2:
                    raise ValueError("Truncated PCM16 WAV")
                values = array("h")
                values.frombytes(raw)
                if sys.byteorder != "little":
                    values.byteswap()
                for i in range(0, len(values), channels):
                    frame = values[i:i + channels]
                    for ch, sample in enumerate(frame):
                        magnitude = abs(sample)
                        peak_sample = max(peak_sample, magnitude)
                        near_full_scale += magnitude >= 32760
                        sum_squares += sample * sample
                        channel_sum_squares[ch] += sample * sample
                        sum_samples[ch] += sample
                        if previous is not None:
                            max_jump = max(max_jump, abs(sample - previous[ch]))
                    previous = frame
                    if channels == 2:
                        left, right = frame
                        stereo_cross_product += left * right
                        mid_squared = ((left + right) / 2) ** 2
                        stereo_mid_sum_squares += mid_squared
                        window_mid_sum_squares += mid_squared
                    window_sum_squares += sum(x * x for x in frame)
                    window_samples += channels
                    total_samples += channels
                    if window_samples == window_frames * channels:
                        finish_window()
                remaining -= count
            finish_window()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid PCM16 WAV: {exc}") from exc

    rms = math.sqrt(sum_squares / total_samples) / 32768
    peak = peak_sample / 32768
    # The pending trailing gap is intentionally excluded until sound resumes.
    interior_silent_gap_ms = round(1000 * longest_interior_silence_frames / rate, 3)
    phase_correlation = None
    mono_loss_db = None
    risky_window_fraction = None
    if channels == 2:
        if channel_sum_squares[0] and channel_sum_squares[1]:
            phase_correlation = round(
                stereo_cross_product / math.sqrt(channel_sum_squares[0] * channel_sum_squares[1]), 6
            )
        if sum_squares and stereo_mid_sum_squares:
            mono_loss_db = round(
                10 * math.log10(sum_squares / (2 * stereo_mid_sum_squares)), 3
            )
        if eligible_stereo_windows:
            risky_window_fraction = round(phase_risk_windows / eligible_stereo_windows, 6)
    return {
        "sample_rate": rate,
        "channels": channels,
        "frames": nframes,
        "duration_seconds": round(nframes / rate, 6),
        "peak": round(peak, 6),
        "peak_dbfs": _dbfs(peak),
        "rms": round(rms, 8),
        "rms_dbfs": _dbfs(rms),
        "dc_per_channel": [round(x / nframes / 32768, 7) for x in sum_samples],
        "near_full_scale_fraction": round(near_full_scale / total_samples, 8),
        "silent_window_fraction": round(silent_windows / windows, 6),
        "longest_interior_silent_gap_ms": interior_silent_gap_ms,
        "interior_silent_gap_risk": interior_silent_gap_ms >= INTERIOR_SILENT_GAP_WARNING_MS,
        "window_count": windows,
        "min_window_rms_dbfs": _dbfs(min(window_peaks)),
        "max_window_rms_dbfs": _dbfs(max(window_peaks)),
        "max_adjacent_sample_jump": round(max_jump / 32768, 6),
        "stereo_phase_correlation": phase_correlation,
        "mono_fold_down_loss_db": mono_loss_db,
        "mono_fold_down_risky_window_fraction": risky_window_fraction,
        "mono_fold_down_cancellation_risk": phase_risk_windows > 0,
    }


def compare_wavs(baseline: str | Path, candidates: list[str | Path], *,
                 window_ms: int = 100, loudness_tolerance_db: float = 1.5) -> dict:
    """Diagnose candidate-vs-baseline safety for a neutral human A/B review.

    The baseline and candidates must have identical format and frame count.
    Candidate numbers are opaque. Paths, samples and source hashes are omitted.
    """
    if not candidates:
        raise ValueError("At least one candidate WAV is required")
    if len(candidates) > 20:
        raise ValueError("At most 20 candidates can be screened in one request")
    if not isinstance(loudness_tolerance_db, (float, int)) or isinstance(loudness_tolerance_db, bool) or (
        not math.isfinite(loudness_tolerance_db) or not 0.1 <= loudness_tolerance_db <= 12
    ):
        raise ValueError("loudness_tolerance_db must be finite between 0.1 and 12")
    base = scan_wav(baseline, window_ms=window_ms)
    results = []
    for index, candidate in enumerate(candidates, start=1):
        metrics = scan_wav(candidate, window_ms=window_ms)
        for field in ("sample_rate", "channels", "frames"):
            if metrics[field] != base[field]:
                raise ValueError(f"Candidate {index} {field} differs from baseline")
        level_difference = None
        if base["rms_dbfs"] is not None and metrics["rms_dbfs"] is not None:
            level_difference = round(metrics["rms_dbfs"] - base["rms_dbfs"], 3)
        warnings = []
        if level_difference is None:
            warnings.append("silence_prevents_rms_level_comparison")
        elif abs(level_difference) > loudness_tolerance_db:
            warnings.append("rms_level_mismatch_not_lufs")
        if metrics["near_full_scale_fraction"] > 0:
            warnings.append("near_full_scale_samples_inspect_for_clipping")
        if metrics["silent_window_fraction"] > 0.5:
            warnings.append("many_low_level_windows_inspect_for_silence")
        if metrics["interior_silent_gap_risk"]:
            warnings.append("interior_silent_gap_inspect_for_dropouts")
        if metrics["mono_fold_down_cancellation_risk"]:
            warnings.append("stereo_mono_fold_down_cancellation_inspect")
        results.append({
            "candidate_id": f"candidate-{index:02d}",
            "metrics": metrics,
            "rms_delta_db_vs_baseline": level_difference,
            "warnings": warnings,
            "requires_human_review": True,
            "level_comparable_for_blind_ab": level_difference is not None and abs(level_difference) <= loudness_tolerance_db,
        })
    return {
        "schema_version": 1,
        "purpose": "technical_preflight_not_musical_quality",
        "analysis_method": "streaming_pcm16_rms_not_lufs",
        "window_ms": window_ms,
        "loudness_tolerance_db": loudness_tolerance_db,
        "baseline": base,
        "candidates": results,
        "human_preference_test_required": True,
        "contains_source_paths_or_audio": False,
    }
