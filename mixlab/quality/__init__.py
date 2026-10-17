"""Bounded, streaming audio diagnostics for offline MixLab listening candidates.

Technical screening is not music quality, tempo analysis or perceptual loudness.
The module intentionally does not open or write output audio files.
"""

from __future__ import annotations

from array import array
import hashlib
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
# Differing start/end silence in a blind pair can give away the variant or
# make playback timing unequal even with identical frame count.
EDGE_SILENCE_CONFOUND_MS = 200
# Flag apparent stereo channel loss, not artistic panning: one channel
# below -55 dBFS while the other is clearly active above -35 dBFS.
ACTIVE_CHANNEL_RMS = 10 ** (-35 / 20)
# Flag sustained *partial* channel loss even when whole-file channel RMS
# remains healthy. Short creative pans still require human interpretation.
STEREO_CHANNEL_LOSS_MIN_FRACTION = 0.2
# A >50% full-scale adjacent PCM step is suspicious for a splice pop,
# but percussion and intentional cuts still require human inspection.
SEVERE_SAMPLE_JUMP = 0.5 * 32768
# Earlier digital clipping may have been attenuated: a repeated high-level
# PCM plateau can persist without any sample reaching digital full-scale.
# Warn on >=4 *exactly equal* consecutive samples above 72% full-scale.
# Square waves and intentional sustained signals are possible false positives.
FLAT_TOP_MIN_ABS_SAMPLE = round(0.72 * 32768)
FLAT_TOP_MIN_CONSECUTIVE = 4
# DC >3% full scale can reduce headroom or produce a pop when the file ends.
DC_OFFSET_RISK = 0.03
# Screening heuristic: a loss >= 9 dB during a non-silent stereo window
# means downmixing to mono may suppress an important part of the sound.
MONO_FOLD_DOWN_RISK_DB = 9.0
MONO_FOLD_DOWN_RISK_POWER_RATIO = 10 ** (-MONO_FOLD_DOWN_RISK_DB / 10)
# Short-term RMS is not LUFS: flag only large, persistent relative
# deviations (>=9 dB for >=25% of audible windows) for human inspection.
SHORT_WINDOW_LEVEL_MISMATCH_DB = 9.0
SHORT_WINDOW_LEVEL_MISMATCH_FRACTION = 0.25


def _dbfs(value: float) -> float | None:
    """Numerical RMS/peak in dBFS, not integrated perceptual loudness (LUFS)."""
    return round(20 * math.log10(value), 3) if value > 0 else None


def _scan_wav_with_digest(path: str | Path, *, window_ms: int = 100) -> tuple[dict, bytes, list[float]]:
    """Scan bounded PCM16 with private frame fingerprints and RMS windows.

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
            pcm_digest = hashlib.sha256()
            peak_sample = 0
            near_full_scale = 0
            total_samples = 0
            sum_squares = 0
            sum_samples = [0] * channels
            channel_sum_squares = [0] * channels
            stereo_cross_product = 0
            stereo_mid_sum_squares = 0.0
            max_jump = 0
            severe_jump_count = 0
            high_flat_top_plateau_count = 0
            flat_top_run = [0] * channels
            previous = None
            window_sum_squares = 0
            window_channel_sum_squares = [0] * channels
            window_mid_sum_squares = 0.0
            window_samples = 0
            window_peaks = []
            silent_windows = 0
            windows = 0
            seen_audible_window = False
            leading_silence_frames = 0
            pending_interior_silence_frames = 0
            longest_interior_silence_frames = 0
            eligible_stereo_windows = 0
            phase_risk_windows = 0
            partial_channel_loss_windows = 0

            def finish_window():
                nonlocal window_sum_squares, window_channel_sum_squares, window_mid_sum_squares, window_samples
                nonlocal silent_windows, windows, eligible_stereo_windows, phase_risk_windows
                nonlocal partial_channel_loss_windows
                nonlocal seen_audible_window, leading_silence_frames
                nonlocal pending_interior_silence_frames, longest_interior_silence_frames
                if window_samples:
                    wrms = math.sqrt(window_sum_squares / window_samples) / 32768
                    window_peaks.append(wrms)
                    is_silent = wrms < SILENT_WINDOW_RMS
                    silent_windows += is_silent
                    if is_silent:
                        if seen_audible_window:
                            pending_interior_silence_frames += window_samples // channels
                        else:
                            leading_silence_frames += window_samples // channels
                    else:
                        if seen_audible_window:
                            longest_interior_silence_frames = max(
                                longest_interior_silence_frames, pending_interior_silence_frames
                            )
                        seen_audible_window = True
                        pending_interior_silence_frames = 0
                    if channels == 2 and wrms >= SILENT_WINDOW_RMS:
                        eligible_stereo_windows += 1
                        frames_in_window = window_samples // channels
                        left_rms, right_rms = (
                            math.sqrt(s / frames_in_window) / 32768 for s in window_channel_sum_squares
                        )
                        if ((left_rms < SILENT_WINDOW_RMS and right_rms > ACTIVE_CHANNEL_RMS)
                                or (right_rms < SILENT_WINDOW_RMS and left_rms > ACTIVE_CHANNEL_RMS)):
                            partial_channel_loss_windows += 1
                        # Compare mono (L+R)/2 power to original per-channel power.
                        # Silent windows must not trigger false cancellation alerts.
                        if 2 * window_mid_sum_squares <= MONO_FOLD_DOWN_RISK_POWER_RATIO * window_sum_squares:
                            phase_risk_windows += 1
                    windows += 1
                    window_sum_squares = 0
                    window_channel_sum_squares = [0] * channels
                    window_mid_sum_squares = 0.0
                    window_samples = 0

            remaining = nframes
            while remaining:
                count = min(4096, remaining)
                raw = src.readframes(count)
                if len(raw) != count * channels * 2:
                    raise ValueError("Truncated PCM16 WAV")
                pcm_digest.update(raw)
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
                        window_channel_sum_squares[ch] += sample * sample
                        sum_samples[ch] += sample
                        if previous is not None:
                            jump = abs(sample - previous[ch])
                            max_jump = max(max_jump, jump)
                            severe_jump_count += jump >= SEVERE_SAMPLE_JUMP
                        if (previous is not None and sample == previous[ch]
                                and magnitude >= FLAT_TOP_MIN_ABS_SAMPLE):
                            flat_top_run[ch] += 1
                        else:
                            flat_top_run[ch] = 1
                        if flat_top_run[ch] == FLAT_TOP_MIN_CONSECUTIVE:
                            high_flat_top_plateau_count += 1
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
    # The pending gap at EOF is trailing silence, not an interior dropout.
    # Fully silent files are already diagnosed separately: don't fabricate
    # an audible ending at their duration.
    leading_silence_ms = round(1000 * leading_silence_frames / rate, 3)
    trailing_silence_ms = round(
        1000 * pending_interior_silence_frames / rate, 3
    ) if seen_audible_window else 0.0
    channel_rms = [math.sqrt(x / nframes) / 32768 for x in channel_sum_squares]
    dc_per_channel = [x / nframes / 32768 for x in sum_samples]
    dc_offset_risk = any(abs(x) > DC_OFFSET_RISK for x in dc_per_channel)
    stereo_channel_silence_risk = channels == 2 and (
        (channel_rms[0] < SILENT_WINDOW_RMS and channel_rms[1] > ACTIVE_CHANNEL_RMS)
        or (channel_rms[1] < SILENT_WINDOW_RMS and channel_rms[0] > ACTIVE_CHANNEL_RMS)
    )
    phase_correlation = None
    mono_loss_db = None
    risky_window_fraction = None
    partial_channel_loss_fraction = None
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
            partial_channel_loss_fraction = round(
                partial_channel_loss_windows / eligible_stereo_windows, 6
            )
    metrics = {
        "sample_rate": rate,
        "channels": channels,
        "frames": nframes,
        "duration_seconds": round(nframes / rate, 6),
        "peak": round(peak, 6),
        "peak_dbfs": _dbfs(peak),
        "rms": round(rms, 8),
        "rms_dbfs": _dbfs(rms),
        "dc_per_channel": [round(x, 7) for x in dc_per_channel],
        "dc_offset_risk": dc_offset_risk,
        "channel_rms_dbfs": [_dbfs(x) for x in channel_rms],
        "stereo_channel_silence_risk": stereo_channel_silence_risk,
        "partial_stereo_channel_loss_fraction": partial_channel_loss_fraction,
        "partial_stereo_channel_loss_risk": (
            eligible_stereo_windows >= 3 and partial_channel_loss_windows >= 2
            and partial_channel_loss_windows / eligible_stereo_windows >= STEREO_CHANNEL_LOSS_MIN_FRACTION
        ),
        "near_full_scale_fraction": round(near_full_scale / total_samples, 8),
        "silent_window_fraction": round(silent_windows / windows, 6),
        "leading_silence_ms": leading_silence_ms,
        "trailing_silence_ms": trailing_silence_ms,
        "longest_interior_silent_gap_ms": interior_silent_gap_ms,
        "interior_silent_gap_risk": interior_silent_gap_ms >= INTERIOR_SILENT_GAP_WARNING_MS,
        "window_count": windows,
        "min_window_rms_dbfs": _dbfs(min(window_peaks)),
        "max_window_rms_dbfs": _dbfs(max(window_peaks)),
        "max_adjacent_sample_jump": round(max_jump / 32768, 6),
        "severe_adjacent_jump_count": severe_jump_count,
        "severe_sample_discontinuity_risk": severe_jump_count > 0,
        "high_flat_top_plateau_count": high_flat_top_plateau_count,
        "high_flat_top_plateau_risk": high_flat_top_plateau_count > 0,
        "stereo_phase_correlation": phase_correlation,
        "mono_fold_down_loss_db": mono_loss_db,
        "mono_fold_down_risky_window_fraction": risky_window_fraction,
        "mono_fold_down_cancellation_risk": phase_risk_windows > 0,
    }
    return metrics, pcm_digest.digest(), window_peaks


def scan_wav(path: str | Path, *, window_ms: int = 100) -> dict:
    """Read at most 32 MiB of PCM16 WAV using bounded chunks.

    Returned diagnostics exclude fingerprints, music samples and private paths.
    Window RMS and silence are signal diagnostics, not a LUFS or DJ score.
    """
    metrics, _, _ = _scan_wav_with_digest(path, window_ms=window_ms)
    return metrics


def _signal_warnings(metrics: dict) -> list[str]:
    """Apply the same technical artifact checks to baseline and candidates."""
    warnings = []
    if metrics["rms_dbfs"] is None:
        warnings.append("fully_silent_audio_inspect")
    if metrics["near_full_scale_fraction"] > 0:
        warnings.append("near_full_scale_samples_inspect_for_clipping")
    if metrics["silent_window_fraction"] > 0.5:
        warnings.append("many_low_level_windows_inspect_for_silence")
    if metrics["interior_silent_gap_risk"]:
        warnings.append("interior_silent_gap_inspect_for_dropouts")
    if metrics["mono_fold_down_cancellation_risk"]:
        warnings.append("stereo_mono_fold_down_cancellation_inspect")
    if metrics["stereo_channel_silence_risk"]:
        warnings.append("stereo_silent_channel_inspect")
    if metrics["partial_stereo_channel_loss_risk"]:
        warnings.append("partial_stereo_channel_loss_inspect")
    if metrics["dc_offset_risk"]:
        warnings.append("dc_offset_inspect_for_headroom")
    if metrics["severe_sample_discontinuity_risk"]:
        warnings.append("severe_sample_discontinuity_inspect_for_pops")
    if metrics["high_flat_top_plateau_risk"]:
        warnings.append("high_flat_top_plateau_inspect_for_prior_limiting")
    return warnings


def _short_window_level_confound(baseline_windows: list[float],
                                 candidate_windows: list[float]) -> tuple[float | None, bool]:
    """Compare aligned RMS windows without returning any private envelope."""
    if len(baseline_windows) != len(candidate_windows):
        raise ValueError("Candidate window count differs from baseline")
    audible_windows = 0
    mismatched_windows = 0
    for base_rms, candidate_rms in zip(baseline_windows, candidate_windows):
        if max(base_rms, candidate_rms) < SILENT_WINDOW_RMS:
            continue
        audible_windows += 1
        if min(base_rms, candidate_rms) < SILENT_WINDOW_RMS or (
            abs(20 * math.log10(candidate_rms / base_rms)) >= SHORT_WINDOW_LEVEL_MISMATCH_DB
        ):
            mismatched_windows += 1
    fraction = round(mismatched_windows / audible_windows, 6) if audible_windows else None
    return fraction, audible_windows >= 3 and mismatched_windows / audible_windows >= SHORT_WINDOW_LEVEL_MISMATCH_FRACTION


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
    base, base_digest, base_windows = _scan_wav_with_digest(baseline, window_ms=window_ms)
    baseline_warnings = _signal_warnings(base)
    # Digests stay in memory, never in output. PCM-only means a changed WAV
    # container header cannot conceal an identical listening waveform.
    seen_candidate_digests = {}
    results = []
    for index, candidate in enumerate(candidates, start=1):
        metrics, candidate_digest, candidate_windows = _scan_wav_with_digest(candidate, window_ms=window_ms)
        for field in ("sample_rate", "channels", "frames"):
            if metrics[field] != base[field]:
                raise ValueError(f"Candidate {index} {field} differs from baseline")
        level_difference = None
        if base["rms_dbfs"] is not None and metrics["rms_dbfs"] is not None:
            level_difference = round(metrics["rms_dbfs"] - base["rms_dbfs"], 3)
        warnings = _signal_warnings(metrics)
        short_window_level_mismatch_fraction, short_window_level_mismatch_risk = _short_window_level_confound(
            base_windows, candidate_windows
        )
        if short_window_level_mismatch_risk:
            warnings.append("short_window_rms_level_confound_inspect_not_lufs")
        # Aligned durations do not guarantee aligned audible starts/ends.
        # Only inspect non-silent pairs; a completely silent side is handled
        # by the existing silence-specific warning.
        edge_silence_mismatch_risk = (
            base["rms_dbfs"] is not None and metrics["rms_dbfs"] is not None
            and any(abs(metrics[edge] - base[edge]) >= EDGE_SILENCE_CONFOUND_MS
                    for edge in ("leading_silence_ms", "trailing_silence_ms"))
        )
        if edge_silence_mismatch_risk:
            warnings.append("ab_edge_silence_alignment_confound_inspect")
        duplicate_pcm_of = None
        if candidate_digest == base_digest:
            duplicate_pcm_of = "baseline"
            warnings.append("identical_pcm_to_baseline_inspect_for_noop")
        elif candidate_digest in seen_candidate_digests:
            duplicate_pcm_of = seen_candidate_digests[candidate_digest]
            warnings.append("duplicate_candidate_pcm_inspect")
        else:
            seen_candidate_digests[candidate_digest] = f"candidate-{index:02d}"
        if level_difference is None:
            warnings.append("silence_prevents_rms_level_comparison")
        elif abs(level_difference) > loudness_tolerance_db:
            warnings.append("rms_level_mismatch_not_lufs")
        results.append({
            "candidate_id": f"candidate-{index:02d}",
            "metrics": metrics,
            "rms_delta_db_vs_baseline": level_difference,
            "short_window_level_mismatch_fraction": short_window_level_mismatch_fraction,
            "short_window_level_mismatch_risk": short_window_level_mismatch_risk,
            "edge_silence_mismatch_risk": edge_silence_mismatch_risk,
            "warnings": warnings,
            "duplicate_pcm_of": duplicate_pcm_of,
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
        "baseline_warnings": baseline_warnings,
        "candidates": results,
        "human_preference_test_required": True,
        "contains_source_paths_or_audio": False,
    }
