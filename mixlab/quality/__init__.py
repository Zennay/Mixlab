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

from .private_source import open_verified_private_pcm16, private_path_identity, private_wav_format
from .pcm_identity import EdgeSilencePcmFingerprint

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FRAMES = 2_000_000
# Aggregate budgets are checked before the first PCM read. Without them a
# 20-candidate comparison can multiply the per-WAV 2M-frame limit by 21.
MAX_COMPARE_TOTAL_SOURCE_BYTES = 128 * 1024 * 1024
MAX_COMPARE_TOTAL_FRAMES = 8_000_000
SILENT_WINDOW_RMS = 10 ** (-55 / 20)
# Investigate gaps of at least 200 ms between audible sections, even if
# the rest of an otherwise valid transition is loud.
INTERIOR_SILENT_GAP_WARNING_MS = 200
# A 50-ms near-digital-silence dropout entirely inside one non-silent RMS
# window can evade the existing >=200ms silent-window gap detector.
# Detect only interior runs across all channels, without sample coordinates.
SHORT_PCM_DROPOUT_WARNING_MS = 50
QUIET_PCM_ABS_SAMPLE = 64
# One channel may drop out for 50ms while the other plays normally,
# without affecting enough RMS windows for the 20% partial-loss check.
SHORT_STEREO_CHANNEL_DROPOUT_MS = 50
# Differing start/end silence in a blind pair can give away the variant or
# make playback timing unequal even with identical frame count.
EDGE_SILENCE_CONFOUND_MS = 200
# Review A/B clips can start noticeably out of sync even when both have
# identical durations and less than 200ms coarse-window silence difference.
# Inspect the first >=5%-FS PCM sample, not a beat/downbeat prediction.
PROMINENT_AUDIO_ABS_SAMPLE = 1638
PROMINENT_ONSET_MISMATCH_MS = 75
# A single stereo channel can arrive >=100ms after the other without
# exceeding the existing 20% partial-channel-loss window threshold.
STEREO_CHANNEL_ONSET_SKEW_MS = 100
# Flag apparent stereo channel loss, not artistic panning: one channel
# below -55 dBFS while the other is clearly active above -35 dBFS.
ACTIVE_CHANNEL_RMS = 10 ** (-35 / 20)
# Flag sustained *partial* channel loss even when whole-file channel RMS
# remains healthy. Short creative pans still require human interpretation.
STEREO_CHANNEL_LOSS_MIN_FRACTION = 0.2
# A >50% full-scale adjacent PCM step is suspicious for a splice pop,
# but percussion and intentional cuts still require human inspection.
SEVERE_SAMPLE_JUMP = 0.5 * 32768
# A one-frame click can have <50%-FS adjacent steps and escape the severe
# jump screen. Inspect a sample >=25% FS surrounded by samples <=6.25% FS
# on the SAME channel. This is a heuristic; short percussion is possible.
ISOLATED_IMPULSE_MIN_SAMPLE = 8192
ISOLATED_IMPULSE_QUIET_NEIGHBOR = 2048
# An isolated playback excerpt starting or ending far from zero may click
# even without a large jump *between* its existing PCM samples.
PLAYBACK_EDGE_STEP_WARNING = 0.25 * 32768
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
# A stereo clip can preserve total and per-window RMS while changing
# channel balance by >9 dB. Such A/B level comparisons need human review.
STEREO_CHANNEL_LEVEL_MISMATCH_DB = 9.0


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

    try:
        # One nonblocking regular-file descriptor is used for RIFF header
        # validation and PCM reads. No pathname re-open between checks.
        with open_verified_private_pcm16(path, max_bytes=MAX_SOURCE_BYTES) as src:
            channels, sample_width, rate, nframes, compression, _ = src.getparams()
            if compression != "NONE" or sample_width != 2 or channels not in (1, 2):
                raise ValueError("Only uncompressed PCM16 mono/stereo WAV is supported")
            if not 8000 <= rate <= 96000:
                raise ValueError("Sample rate must be 8000..96000 Hz")
            if not 1 <= nframes <= MAX_SOURCE_FRAMES:
                raise ValueError("Frames must be between 1 and 2,000,000")
            window_frames = max(1, round(rate * window_ms / 1000))
            pcm_digest = hashlib.sha256()
            # A silence-padded time-shift can preserve all actual PCM audio
            # while changing its full-length digest and blind-trial identity.
            edge_trimmed_pcm = EdgeSilencePcmFingerprint(channels)
            # A signed stereo transform PLUS shifted zero-valued edge
            # padding is otherwise invisible to the independent full-PCM
            # transform and edge-only fingerprints. Reuse the already
            # constructed 4096-frame transform buffers below; never store
            # whole audio or publish the private fingerprints.
            edge_transformed_pcm = [
                EdgeSilencePcmFingerprint(channels)
                for _ in range(7 if channels == 2 else 1)
            ]
            # Stereo L/R exchange changes the interleaved PCM digest even
            # when the audible material is otherwise an exact reuse.
            swapped_stereo_digest = hashlib.sha256() if channels == 2 else None
            # Private polarity-inverted fingerprint: sign inversion is
            # often another PCM-only no-op. -32768 cannot be negated as
            # signed PCM16, so fail closed on that edge rather than clip.
            inverse_digest = hashlib.sha256()
            # Per-channel polarity flips can make reused stereo PCM look
            # like a fresh blind-review option. Digests stay private.
            channel_inverse_digests = [hashlib.sha256(), hashlib.sha256()] if channels == 2 else None
            # A swap combined with sign inversion of either/both channels
            # is another exact PCM reuse disguise. Keep all digests private.
            signed_swap_digests = [hashlib.sha256() for _ in range(3)] if channels == 2 else None
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
            isolated_impulse_count = 0
            high_flat_top_plateau_count = 0
            flat_top_run = [0] * channels
            previous = None
            previous_previous = None
            first_frame = None
            processed_frames = 0
            first_prominent_frame = None
            first_prominent_frame_by_channel = [None] * channels
            window_sum_squares = 0
            window_channel_sum_squares = [0] * channels
            window_mid_sum_squares = 0.0
            window_samples = 0
            window_peaks = []
            # Only small per-window RMS summaries are held privately; no
            # channel audio, source paths or envelopes enter the report.
            channel_window_peaks = []
            silent_windows = 0
            windows = 0
            seen_audible_window = False
            leading_silence_frames = 0
            pending_interior_silence_frames = 0
            longest_interior_silence_frames = 0
            # Per-frame quiet runs operate separately from coarse RMS windows.
            # Ignore leading/trailing silence; flag only audible -> quiet -> audible.
            seen_audible_frame = False
            pending_quiet_frames = 0
            longest_interior_quiet_frames = 0
            stereo_seen_prominent = [False] * channels
            stereo_pending_quiet = [0] * channels
            stereo_pending_other_prominent = [0] * channels
            longest_stereo_channel_gap_frames = 0
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
                    if channels == 2:
                        frames_in_window = window_samples // channels
                        channel_window_peaks.append(tuple(
                            math.sqrt(sumsq / frames_in_window) / 32768
                            for sumsq in window_channel_sum_squares
                        ))
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
                edge_trimmed_pcm.update(raw)
                values = array("h")
                values.frombytes(raw)
                if sys.byteorder != "little":
                    values.byteswap()
                if swapped_stereo_digest is not None:
                    # One extra bounded per-read buffer, not a whole WAV copy.
                    swapped = array("h", values)
                    swapped[::2] = values[1::2]
                    swapped[1::2] = values[::2]
                    if sys.byteorder != "little":
                        swapped.byteswap()
                    swapped_bytes = swapped.tobytes()
                    swapped_stereo_digest.update(swapped_bytes)
                    edge_transformed_pcm[0].update(swapped_bytes)
                if inverse_digest is not None:
                    if -32768 in values:
                        inverse_digest = None
                        edge_transformed_pcm[1 if channels == 2 else 0] = None
                    else:
                        inverted = array("h", (-sample for sample in values))
                        if sys.byteorder != "little":
                            inverted.byteswap()
                        inverted_bytes = inverted.tobytes()
                        inverse_digest.update(inverted_bytes)
                        edge_transformed_pcm[1 if channels == 2 else 0].update(inverted_bytes)
                if channel_inverse_digests is not None:
                    for side in (0, 1):
                        digest = channel_inverse_digests[side]
                        if digest is None:
                            continue
                        channel_samples = values[side::2]
                        # -32768 cannot be negated in PCM16. Never hash an
                        # overflowed/clipped approximation as an exact flip.
                        if -32768 in channel_samples:
                            channel_inverse_digests[side] = None
                            edge_transformed_pcm[2 + side] = None
                            continue
                        channel_flipped = array("h", values)
                        channel_flipped[side::2] = array("h", (-v for v in channel_samples))
                        if sys.byteorder != "little":
                            channel_flipped.byteswap()
                        channel_flipped_bytes = channel_flipped.tobytes()
                        digest.update(channel_flipped_bytes)
                        edge_transformed_pcm[2 + side].update(channel_flipped_bytes)
                if signed_swap_digests is not None:
                    left, right = values[::2], values[1::2]
                    # Transform (L,R) into (-R,L), (R,-L), (-R,-L).
                    # A PCM16 minimum sample cannot be negated exactly;
                    # discard only the transforms that require negating it.
                    for slot, (negate_left, negate_right) in enumerate(
                        ((False, True), (True, False), (True, True))
                    ):
                        digest = signed_swap_digests[slot]
                        if digest is None:
                            continue
                        if ((negate_left and -32768 in left)
                                or (negate_right and -32768 in right)):
                            signed_swap_digests[slot] = None
                            edge_transformed_pcm[4 + slot] = None
                            continue
                        transformed = array("h", values)
                        transformed[::2] = array(
                            "h", (-v if negate_right else v for v in right)
                        )
                        transformed[1::2] = array(
                            "h", (-v if negate_left else v for v in left)
                        )
                        if sys.byteorder != "little":
                            transformed.byteswap()
                        signed_swap_bytes = transformed.tobytes()
                        digest.update(signed_swap_bytes)
                        edge_transformed_pcm[4 + slot].update(signed_swap_bytes)
                for i in range(0, len(values), channels):
                    frame = values[i:i + channels]
                    if first_frame is None:
                        first_frame = frame
                    if (first_prominent_frame is None
                            and any(abs(sample) >= PROMINENT_AUDIO_ABS_SAMPLE for sample in frame)):
                        first_prominent_frame = processed_frames
                    for channel_index, sample in enumerate(frame):
                        if (first_prominent_frame_by_channel[channel_index] is None
                                and abs(sample) >= PROMINENT_AUDIO_ABS_SAMPLE):
                            first_prominent_frame_by_channel[channel_index] = processed_frames
                    processed_frames += 1
                    if channels == 2:
                        for channel_index in (0, 1):
                            value = frame[channel_index]
                            if (stereo_seen_prominent[channel_index]
                                    and abs(value) <= QUIET_PCM_ABS_SAMPLE):
                                stereo_pending_quiet[channel_index] += 1
                                stereo_pending_other_prominent[channel_index] += (
                                    abs(frame[1 - channel_index]) >= PROMINENT_AUDIO_ABS_SAMPLE
                                )
                            else:
                                quiet_frames = stereo_pending_quiet[channel_index]
                                # Only a recovered interior dropout while
                                # the *other* channel remains substantially
                                # active, not a pan into common silence.
                                if (quiet_frames
                                        and 4 * stereo_pending_other_prominent[channel_index]
                                        >= quiet_frames):
                                    longest_stereo_channel_gap_frames = max(
                                        longest_stereo_channel_gap_frames, quiet_frames
                                    )
                                stereo_pending_quiet[channel_index] = 0
                                stereo_pending_other_prominent[channel_index] = 0
                                if abs(value) >= PROMINENT_AUDIO_ABS_SAMPLE:
                                    stereo_seen_prominent[channel_index] = True
                    if all(abs(sample) <= QUIET_PCM_ABS_SAMPLE for sample in frame):
                        if seen_audible_frame:
                            pending_quiet_frames += 1
                    else:
                        if seen_audible_frame:
                            longest_interior_quiet_frames = max(
                                longest_interior_quiet_frames, pending_quiet_frames
                            )
                        seen_audible_frame = True
                        pending_quiet_frames = 0
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
                        if (previous_previous is not None
                                and abs(previous[ch]) >= ISOLATED_IMPULSE_MIN_SAMPLE
                                and abs(previous_previous[ch]) <= ISOLATED_IMPULSE_QUIET_NEIGHBOR
                                and magnitude <= ISOLATED_IMPULSE_QUIET_NEIGHBOR):
                            isolated_impulse_count += 1
                        if (previous is not None and sample == previous[ch]
                                and magnitude >= FLAT_TOP_MIN_ABS_SAMPLE):
                            flat_top_run[ch] += 1
                        else:
                            flat_top_run[ch] = 1
                        if flat_top_run[ch] == FLAT_TOP_MIN_CONSECUTIVE:
                            high_flat_top_plateau_count += 1
                    previous_previous = previous
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
    prominent_onset_ms = (
        round(1000 * first_prominent_frame / rate, 3)
        if first_prominent_frame is not None else None
    )
    stereo_channel_onset_gap_ms = None
    if channels == 2 and all(frame is not None for frame in first_prominent_frame_by_channel):
        stereo_channel_onset_gap_ms = round(
            1000 * abs(first_prominent_frame_by_channel[0] - first_prominent_frame_by_channel[1])
            / rate, 3
        )
    stereo_channel_onset_skew_risk = (
        stereo_channel_onset_gap_ms is not None
        and stereo_channel_onset_gap_ms >= STEREO_CHANNEL_ONSET_SKEW_MS
    )
    stereo_interior_quiet_gap_ms = (
        round(1000 * longest_stereo_channel_gap_frames / rate, 3)
        if channels == 2 else None
    )
    stereo_interior_dropout_risk = (
        channels == 2 and 1000 * longest_stereo_channel_gap_frames
        >= SHORT_STEREO_CHANNEL_DROPOUT_MS * rate
    )
    playback_start_peak = max(abs(sample) for sample in first_frame) / 32768
    playback_end_peak = max(abs(sample) for sample in previous) / 32768
    playback_boundary_pop_risk = (
        max(playback_start_peak, playback_end_peak) >= PLAYBACK_EDGE_STEP_WARNING / 32768
    )
    # The pending trailing gap is intentionally excluded until sound resumes.
    interior_silent_gap_ms = round(1000 * longest_interior_silence_frames / rate, 3)
    short_interior_quiet_gap_ms = round(1000 * longest_interior_quiet_frames / rate, 3)
    # The pending gaps at EOF are trailing silence, not interior dropouts.
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
        "prominent_audio_onset_ms": prominent_onset_ms,
        "stereo_channel_onset_gap_ms": stereo_channel_onset_gap_ms,
        "stereo_channel_onset_skew_risk": stereo_channel_onset_skew_risk,
        "longest_interior_silent_gap_ms": interior_silent_gap_ms,
        "interior_silent_gap_risk": interior_silent_gap_ms >= INTERIOR_SILENT_GAP_WARNING_MS,
        "longest_interior_quiet_pcm_gap_ms": short_interior_quiet_gap_ms,
        "short_interior_pcm_dropout_risk": (
            1000 * longest_interior_quiet_frames >= SHORT_PCM_DROPOUT_WARNING_MS * rate
        ),
        "longest_interior_stereo_channel_quiet_gap_ms": stereo_interior_quiet_gap_ms,
        "short_interior_stereo_channel_dropout_risk": stereo_interior_dropout_risk,
        "window_count": windows,
        "min_window_rms_dbfs": _dbfs(min(window_peaks)),
        "max_window_rms_dbfs": _dbfs(max(window_peaks)),
        "max_adjacent_sample_jump": round(max_jump / 32768, 6),
        "severe_adjacent_jump_count": severe_jump_count,
        "severe_sample_discontinuity_risk": severe_jump_count > 0,
        "isolated_sample_impulse_count": isolated_impulse_count,
        "isolated_sample_impulse_risk": isolated_impulse_count > 0,
        "playback_start_peak": round(playback_start_peak, 6),
        "playback_end_peak": round(playback_end_peak, 6),
        "playback_boundary_pop_risk": playback_boundary_pop_risk,
        "high_flat_top_plateau_count": high_flat_top_plateau_count,
        "high_flat_top_plateau_risk": high_flat_top_plateau_count > 0,
        "stereo_phase_correlation": phase_correlation,
        "mono_fold_down_loss_db": mono_loss_db,
        "mono_fold_down_risky_window_fraction": risky_window_fraction,
        "mono_fold_down_cancellation_risk": phase_risk_windows > 0,
    }
    return metrics, pcm_digest.digest(), window_peaks, (
        swapped_stereo_digest.digest() if swapped_stereo_digest is not None else None
    ), (inverse_digest.digest() if inverse_digest is not None else None), (
        tuple(d.digest() if d is not None else None for d in channel_inverse_digests)
        if channel_inverse_digests is not None else None
    ), (
        tuple(d.digest() if d is not None else None for d in signed_swap_digests)
        if signed_swap_digests is not None else None
    ), edge_trimmed_pcm.digest(), tuple(
        fingerprint.digest() if fingerprint is not None else None
        for fingerprint in edge_transformed_pcm
    ), channel_window_peaks


def scan_wav(path: str | Path, *, window_ms: int = 100) -> dict:
    """Read at most 32 MiB of PCM16 WAV using bounded chunks.

    Returned diagnostics exclude fingerprints, music samples and private paths.
    Window RMS and silence are signal diagnostics, not a LUFS or DJ score.
    """
    metrics, _, _, _, _, _, _, _, _, _ = _scan_wav_with_digest(path, window_ms=window_ms)
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
    if metrics["short_interior_pcm_dropout_risk"]:
        warnings.append("short_interior_pcm_dropout_inspect")
    if metrics["short_interior_stereo_channel_dropout_risk"]:
        warnings.append("short_interior_stereo_channel_dropout_inspect")
    if metrics["mono_fold_down_cancellation_risk"]:
        warnings.append("stereo_mono_fold_down_cancellation_inspect")
    if metrics["stereo_channel_silence_risk"]:
        warnings.append("stereo_silent_channel_inspect")
    if metrics["partial_stereo_channel_loss_risk"]:
        warnings.append("partial_stereo_channel_loss_inspect")
    if metrics["stereo_channel_onset_skew_risk"]:
        warnings.append("stereo_channel_onset_skew_inspect")
    if metrics["dc_offset_risk"]:
        warnings.append("dc_offset_inspect_for_headroom")
    if metrics["severe_sample_discontinuity_risk"]:
        warnings.append("severe_sample_discontinuity_inspect_for_pops")
    if metrics["isolated_sample_impulse_risk"]:
        warnings.append("isolated_sample_impulse_inspect_for_clicks")
    if metrics["playback_boundary_pop_risk"]:
        warnings.append("playback_boundary_step_inspect_for_clicks")
    if metrics["high_flat_top_plateau_risk"]:
        warnings.append("high_flat_top_plateau_inspect_for_prior_limiting")
    return warnings


def _short_window_level_confound(baseline_windows: list[float],
                                 candidate_windows: list[float]) -> tuple[float | None, bool, int]:
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
    return (fraction, audible_windows >= 3 and mismatched_windows / audible_windows >= SHORT_WINDOW_LEVEL_MISMATCH_FRACTION,
            audible_windows)


def _stereo_channel_level_confound(baseline: dict, candidate: dict) -> bool:
    """Check whole-recording channel levels without leaking private envelopes.

    For silent channels, only flag mismatches if the active side crosses the
    existing -55 dBFS silence cutoff; dual-quiet audio is handled elsewhere.
    """
    if baseline["channels"] != 2 or candidate["channels"] != 2:
        return False
    for original, changed in zip(baseline["channel_rms_dbfs"], candidate["channel_rms_dbfs"]):
        if original is None or changed is None:
            if max(original if original is not None else float("-inf"),
                   changed if changed is not None else float("-inf")) > -55:
                return True
        elif max(original, changed) > -55 and abs(original - changed) >= STEREO_CHANNEL_LEVEL_MISMATCH_DB:
            return True
    return False


def _stereo_window_channel_level_confound(
    base: list[tuple[float, float]], candidate: list[tuple[float, float]]
) -> tuple[float | None, bool]:
    """Inspect paired stereo channel RMS windows; never return source curves."""
    if len(base) != len(candidate):
        raise ValueError("Candidate stereo window count differs from baseline")
    audible = 0
    mismatched = 0
    for original, changed in zip(base, candidate):
        if max(*original, *changed) < SILENT_WINDOW_RMS:
            continue
        audible += 1
        for before, after in zip(original, changed):
            if max(before, after) < SILENT_WINDOW_RMS:
                continue
            if min(before, after) < SILENT_WINDOW_RMS or (
                abs(20 * math.log10(after / before)) >= STEREO_CHANNEL_LEVEL_MISMATCH_DB
            ):
                mismatched += 1
                break
    fraction = round(mismatched / audible, 6) if audible else None
    return fraction, audible >= 3 and mismatched / audible >= SHORT_WINDOW_LEVEL_MISMATCH_FRACTION


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
    # Validate all operator controls before any lstat/header/PCM work. The
    # low-level scanner also validates this for standalone scan_wav calls.
    if not isinstance(window_ms, int) or isinstance(window_ms, bool) or not 20 <= window_ms <= 1000:
        raise ValueError("window_ms must be an integer between 20 and 1000")
    if not isinstance(loudness_tolerance_db, (float, int)) or isinstance(loudness_tolerance_db, bool) or (
        not math.isfinite(loudness_tolerance_db) or not 0.1 <= loudness_tolerance_db <= 12
    ):
        raise ValueError("loudness_tolerance_db must be finite between 0.1 and 12")
    # Capture all source identities once for the entire comparison. Each
    # individual scan already uses a verified fd; this additional cheap
    # path-level check catches earlier inputs replaced after their scan
    # while later candidates are being processed.
    all_paths = (baseline, *candidates)
    initial_identities = tuple(private_path_identity(p) for p in all_paths)
    # Admission is O(number of inputs + bounded RIFF chunk headers), not O(audio
    # frames). No PCM sample is decoded until both full-batch budgets pass.
    if sum(identity[2] for identity in initial_identities) > MAX_COMPARE_TOTAL_SOURCE_BYTES:
        raise ValueError("Quality comparison exceeds the total input byte budget")
    declared_frames = 0
    reference_header = None
    for index, source_path in enumerate(all_paths):
        channels, rate, frames = private_wav_format(source_path, max_bytes=MAX_SOURCE_BYTES)
        # Reject overlong/empty recordings and incompatible candidates
        # before paying the cost of decoding even the baseline's PCM.
        if not 1 <= frames <= MAX_SOURCE_FRAMES:
            raise ValueError("Frames must be between 1 and 2,000,000")
        header = (channels, rate, frames)
        if reference_header is None:
            reference_header = header
        else:
            for field, value, reference in zip(
                ("channels", "sample_rate", "frames"), header, reference_header
            ):
                if value != reference:
                    raise ValueError(f"Candidate {index} {field} differs from baseline")
        declared_frames += frames
        if declared_frames > MAX_COMPARE_TOTAL_FRAMES:
            raise ValueError("Quality comparison exceeds the total PCM frame budget")
    if tuple(private_path_identity(p) for p in all_paths) != initial_identities:
        raise ValueError("Private WAV input changed during quality comparison")
    base, base_digest, base_windows, _, _, _, _, base_trimmed_digest, _, base_channel_windows = _scan_wav_with_digest(baseline, window_ms=window_ms)
    baseline_warnings = _signal_warnings(base)
    # Digests stay in memory, never in output. PCM-only means a changed WAV
    # container header cannot conceal an identical listening waveform.
    seen_candidate_digests = {}
    seen_trimmed_digests = {}
    results = []
    for index, candidate in enumerate(candidates, start=1):
        metrics, candidate_digest, candidate_windows, swapped_digest, inverse_digest, channel_inverse_digests, signed_swap_digests, trimmed_digest, transformed_trimmed_digests, candidate_channel_windows = (
            _scan_wav_with_digest(candidate, window_ms=window_ms)
        )
        for field in ("sample_rate", "channels", "frames"):
            if metrics[field] != base[field]:
                raise ValueError(f"Candidate {index} {field} differs from baseline")
        level_difference = None
        if base["rms_dbfs"] is not None and metrics["rms_dbfs"] is not None:
            level_difference = round(metrics["rms_dbfs"] - base["rms_dbfs"], 3)
        warnings = _signal_warnings(metrics)
        short_window_level_mismatch_fraction, short_window_level_mismatch_risk, audible_level_windows = _short_window_level_confound(
            base_windows, candidate_windows
        )
        if short_window_level_mismatch_risk:
            warnings.append("short_window_rms_level_confound_inspect_not_lufs")
        stereo_channel_level_confound_risk = _stereo_channel_level_confound(base, metrics)
        if stereo_channel_level_confound_risk:
            warnings.append("stereo_channel_level_mismatch_inspect_not_lufs")
        stereo_window_channel_level_mismatch_fraction = None
        stereo_window_channel_level_confound_risk = False
        if base["channels"] == 2:
            stereo_window_channel_level_mismatch_fraction, stereo_window_channel_level_confound_risk = (
                _stereo_window_channel_level_confound(base_channel_windows, candidate_channel_windows)
            )
            if stereo_window_channel_level_confound_risk:
                warnings.append("stereo_window_channel_level_mismatch_inspect_not_lufs")
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
        # This is only a sample-onset timing heuristic, not a beat-grid,
        # phrase or musical synchronization measurement.
        onset_gap_ms = (
            round(abs(metrics["prominent_audio_onset_ms"] - base["prominent_audio_onset_ms"]), 3)
            if (metrics["prominent_audio_onset_ms"] is not None
                and base["prominent_audio_onset_ms"] is not None) else None
        )
        prominent_onset_mismatch_risk = (
            onset_gap_ms is not None and onset_gap_ms >= PROMINENT_ONSET_MISMATCH_MS
        )
        if prominent_onset_mismatch_risk:
            warnings.append("ab_prominent_audio_onset_mismatch_inspect")
        stereo_swapped_pcm_of = None
        # Only distinguish *different* stereo PCM. Mono and dual-mono
        # equality already have a separate exact duplicate warning.
        if swapped_digest is not None and candidate_digest != base_digest:
            if swapped_digest == base_digest:
                stereo_swapped_pcm_of = "baseline"
            elif swapped_digest in seen_candidate_digests:
                stereo_swapped_pcm_of = seen_candidate_digests[swapped_digest]
            if stereo_swapped_pcm_of is not None:
                warnings.append("stereo_channel_swapped_pcm_inspect_for_reused_audio")
        polarity_inverted_pcm_of = None
        if inverse_digest is not None and candidate_digest != base_digest:
            if inverse_digest == base_digest:
                polarity_inverted_pcm_of = "baseline"
            elif inverse_digest in seen_candidate_digests:
                polarity_inverted_pcm_of = seen_candidate_digests[inverse_digest]
            if polarity_inverted_pcm_of is not None:
                warnings.append("polarity_inverted_pcm_inspect_for_reused_audio")
        single_channel_polarity_inverted_pcm_of = None
        if channel_inverse_digests is not None and candidate_digest != base_digest:
            for channel_digest in channel_inverse_digests:
                if channel_digest is None:
                    continue
                if channel_digest == base_digest:
                    single_channel_polarity_inverted_pcm_of = "baseline"
                    break
                if channel_digest in seen_candidate_digests:
                    single_channel_polarity_inverted_pcm_of = seen_candidate_digests[channel_digest]
                    break
            if single_channel_polarity_inverted_pcm_of is not None:
                warnings.append("single_stereo_channel_polarity_flip_inspect_for_reused_audio")
        signed_stereo_swap_pcm_of = None
        if signed_swap_digests is not None and candidate_digest != base_digest:
            for transformed_digest in signed_swap_digests:
                if transformed_digest is None:
                    continue
                if transformed_digest == base_digest:
                    signed_stereo_swap_pcm_of = "baseline"
                    break
                if transformed_digest in seen_candidate_digests:
                    signed_stereo_swap_pcm_of = seen_candidate_digests[transformed_digest]
                    break
            if signed_stereo_swap_pcm_of is not None:
                warnings.append("signed_stereo_swap_pcm_inspect_for_reused_audio")
        # Only all-zero PCM *frames* at playback edges are discarded
        # for this exact-match check. Interior silence and any nonzero
        # sample mismatch remain part of the private digest.
        edge_silence_shifted_pcm_of = None
        if trimmed_digest is not None and candidate_digest != base_digest:
            if trimmed_digest == base_trimmed_digest:
                edge_silence_shifted_pcm_of = "baseline"
            elif (trimmed_digest in seen_trimmed_digests
                  and candidate_digest not in seen_candidate_digests):
                edge_silence_shifted_pcm_of = seen_trimmed_digests[trimmed_digest]
            if edge_silence_shifted_pcm_of is not None:
                warnings.append("edge_silence_shifted_pcm_inspect_for_reused_audio")
        # Compare privately against original edge-trimmed baseline/earlier
        # candidate PCM. A sign/swap transform and a zero-edge shift may be
        # combined; they must not masquerade as new blind-review audio.
        # Matching is exact PCM16 only, not perceptual equivalence.
        edge_silence_transformed_pcm_of = None
        if candidate_digest != base_digest:
            for transformed_digest in transformed_trimmed_digests:
                if transformed_digest is None or transformed_digest == trimmed_digest:
                    continue
                if base_trimmed_digest is not None and transformed_digest == base_trimmed_digest:
                    edge_silence_transformed_pcm_of = "baseline"
                    break
                if transformed_digest in seen_trimmed_digests:
                    edge_silence_transformed_pcm_of = seen_trimmed_digests[transformed_digest]
                    break
        if edge_silence_transformed_pcm_of is not None:
            warnings.append("edge_silence_transformed_pcm_inspect_for_reused_audio")
        if trimmed_digest is not None and trimmed_digest not in seen_trimmed_digests:
            seen_trimmed_digests[trimmed_digest] = f"candidate-{index:02d}"
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
            "stereo_channel_level_confound_risk": stereo_channel_level_confound_risk,
            "stereo_window_channel_level_mismatch_fraction": stereo_window_channel_level_mismatch_fraction,
            "stereo_window_channel_level_confound_risk": stereo_window_channel_level_confound_risk,
            "edge_silence_mismatch_risk": edge_silence_mismatch_risk,
            "prominent_onset_mismatch_ms": onset_gap_ms,
            "prominent_onset_mismatch_risk": prominent_onset_mismatch_risk,
            "warnings": warnings,
            "duplicate_pcm_of": duplicate_pcm_of,
            "stereo_swapped_pcm_of": stereo_swapped_pcm_of,
            "polarity_inverted_pcm_of": polarity_inverted_pcm_of,
            "single_channel_polarity_inverted_pcm_of": single_channel_polarity_inverted_pcm_of,
            "signed_stereo_swap_pcm_of": signed_stereo_swap_pcm_of,
            "edge_silence_shifted_pcm_of": edge_silence_shifted_pcm_of,
            "edge_silence_transformed_pcm_of": edge_silence_transformed_pcm_of,
            "requires_human_review": True,
            # Backwards-compatible RMS-only diagnostic above. This stricter
            # technical gate also needs >=3 aligned audible RMS windows and
            # no sustained short-window mismatch; it does not imply LUFS
            # equivalence, beat alignment or listener preference.
            "level_comparable_for_blind_ab": level_difference is not None and abs(level_difference) <= loudness_tolerance_db,
            "rms_and_window_level_preflight_pass": (
                level_difference is not None and abs(level_difference) <= loudness_tolerance_db
                and audible_level_windows >= 3 and not short_window_level_mismatch_risk
                and not stereo_channel_level_confound_risk
                and not stereo_window_channel_level_confound_risk
            ),
        })
    # Do not publish a result if any baseline or candidate changed at any
    # point during the multi-input job, even *after* its own PCM scan.
    # These identifiers stay private and are not attached to the report.
    if tuple(private_path_identity(p) for p in all_paths) != initial_identities:
        raise ValueError("Private WAV input changed during quality comparison")
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
