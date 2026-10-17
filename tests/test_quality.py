import array
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import compare_wavs, scan_wav
from mixlab.quality.pack import inspect_review_pack


def wav(path, samples, *, rate=8000, channels=1, width=2):
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(width)
        dst.setframerate(rate)
        values = array.array("h", samples)
        if sys.byteorder != "little":
            values.byteswap()
        dst.writeframes(values.tobytes())


def neutral_review_page(trials):
    return "".join(
        f'<fieldset data-trial="{trial}">'
        f'<audio src="{trial}-A.wav"></audio>'
        f'<audio src="{trial}-B.wav"></audio></fieldset>'
        for trial in trials
    )


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "base.wav"
        self.candidate = self.root / "candidate.wav"
        self.samples = [int(6000 * math.sin(i * 0.15)) for i in range(8000)]
        wav(self.base, self.samples)
        wav(self.candidate, self.samples)

    def test_companion_synthetic_suites_on_exact_quality_pr_head(self):
        # Quality PR CI uses -p test_quality.py to bound the job, but cannot
        # otherwise expose regressions in engine/ingest/DSP/evaluation.
        # Execute all OTHER synthetic test modules on this exact checkout.
        # The pattern excludes test_quality.py itself to avoid recursion.
        # No VPS process, private music, uploaded recordings or downloads.
        project_root = Path(__file__).resolve().parents[1]
        sibling_pattern = "test_[!q]*.py"
        check = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", "tests", "-p", sibling_pattern, "-v"],
            cwd=project_root, capture_output=True, text=True, timeout=150,
        )
        self.assertEqual(
            0, check.returncode,
            "Companion synthetic regression suites failed:\n" + check.stderr[-3500:],
        )
        self.assertRegex(check.stderr, r"Ran [1-9][0-9]* tests? in ")
        self.assertIn("\nOK", check.stderr)
        # Print only the public numeric summary to preserve reproducible
        # CI evidence without echoing synthetic fixture paths or metadata.
        suites = [line for line in check.stderr.splitlines() if line.startswith("Ran ")]
        print("MixLab companion regression: " + suites[-1])

    def test_equal_pcm_is_level_comparable_with_no_path_leak(self):
        before = self.candidate.read_bytes()
        report = compare_wavs(self.base, [self.candidate])
        self.assertEqual(report["baseline"], report["candidates"][0]["metrics"])
        self.assertEqual(0, report["candidates"][0]["rms_delta_db_vs_baseline"])
        self.assertTrue(report["candidates"][0]["level_comparable_for_blind_ab"])
        self.assertEqual(["identical_pcm_to_baseline_inspect_for_noop"],
                         report["candidates"][0]["warnings"])
        self.assertEqual("baseline", report["candidates"][0]["duplicate_pcm_of"])
        self.assertFalse(report["baseline_warnings"])
        self.assertTrue(report["human_preference_test_required"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(before, self.candidate.read_bytes())

    def test_quieter_candidate_reports_rms_confound_not_best_music(self):
        wav(self.candidate, [int(x / 2) for x in self.samples])
        report = compare_wavs(self.base, [self.candidate])
        row = report["candidates"][0]
        self.assertAlmostEqual(-6.02, row["rms_delta_db_vs_baseline"], delta=0.05)
        self.assertIn("rms_level_mismatch_not_lufs", row["warnings"])
        self.assertFalse(row["level_comparable_for_blind_ab"])
        self.assertNotIn("score", json.dumps(report))

    def test_temporal_level_bias_hidden_by_equal_whole_file_rms(self):
        # The halves balance in overall power despite a 20 dB quiet first half.
        candidate = [int(x * 0.1) for x in self.samples[:4000]] + [
            int(x * 1.4) for x in self.samples[4000:]
        ]
        wav(self.candidate, candidate)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertLess(abs(row["rms_delta_db_vs_baseline"]), 1.5)
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertTrue(row["short_window_level_mismatch_risk"])
        self.assertGreaterEqual(row["short_window_level_mismatch_fraction"], 0.4)
        self.assertIn("short_window_rms_level_confound_inspect_not_lufs", row["warnings"])
        self.assertNotIn(str(self.root), json.dumps(row))
        self.assertNotIn("window_envelope", json.dumps(row))

    def test_moderate_level_changes_do_not_trigger_temporal_bias_warning(self):
        candidate = [int(x * 0.98) for x in self.samples[:4000]] + [
            int(x * 1.02) for x in self.samples[4000:]
        ]
        wav(self.candidate, candidate)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertEqual(0.0, row["short_window_level_mismatch_fraction"])
        self.assertNotIn("short_window_rms_level_confound_inspect_not_lufs", row["warnings"])
        wav(self.candidate, [0] * len(self.samples))
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertEqual(1.0, row["short_window_level_mismatch_fraction"])
        self.assertTrue(row["short_window_level_mismatch_risk"])

    def test_blind_ab_flags_unequal_leading_and_trailing_silence(self):
        # Both variants have the same duration/format, but 300 ms of
        # leading or trailing silence can bias an A/B listener's timing.
        reference = self.samples
        original_metrics = scan_wav(self.base)
        self.assertEqual(0.0, original_metrics["leading_silence_ms"])
        self.assertEqual(0.0, original_metrics["trailing_silence_ms"])
        for placement in ("leading", "trailing"):
            with self.subTest(placement=placement):
                shifted = ([0] * 2400 + reference[:5600]
                           if placement == "leading" else reference[:5600] + [0] * 2400)
                wav(self.candidate, shifted)
                report = compare_wavs(self.base, [self.candidate])
                row = report["candidates"][0]
                self.assertEqual(300.0, row["metrics"][placement + "_silence_ms"])
                self.assertTrue(row["edge_silence_mismatch_risk"])
                self.assertIn("ab_edge_silence_alignment_confound_inspect", row["warnings"])
                self.assertFalse(report["baseline_warnings"])
                self.assertNotIn(str(self.root), json.dumps(report))
                self.assertNotIn("winner", json.dumps(report))

    def test_blind_ab_edge_silence_threshold_stereo_and_fully_silent_guard(self):
        left = self.root / "left-right-base.wav"
        other = self.root / "left-right-candidate.wav"
        stereo = [v for x in self.samples for v in (x, x)]
        wav(left, stereo, channels=2)
        # One 100-ms leading silent window is below the 200-ms threshold.
        shifted = [0] * (800 * 2) + stereo[:7200 * 2]
        wav(other, shifted, channels=2)
        row = compare_wavs(left, [other])["candidates"][0]
        self.assertEqual(100.0, row["metrics"]["leading_silence_ms"])
        self.assertFalse(row["edge_silence_mismatch_risk"])
        # Leading silence can cross the 4096-frame source-read boundary.
        shifted = [0] * (4800 * 2) + stereo[:3200 * 2]
        wav(other, shifted, channels=2)
        row = compare_wavs(left, [other])["candidates"][0]
        self.assertEqual(600.0, row["metrics"]["leading_silence_ms"])
        self.assertTrue(row["edge_silence_mismatch_risk"])
        # Silence already has a dedicated warning; avoid inventing an
        # alignment verdict when there are no audible boundaries.
        wav(other, [0] * len(stereo), channels=2)
        row = compare_wavs(left, [other])["candidates"][0]
        self.assertFalse(row["edge_silence_mismatch_risk"])
        self.assertIn("fully_silent_audio_inspect", row["warnings"])

    def test_silent_and_near_full_scale_candidates(self):
        wav(self.candidate, [0] * 8000)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["rms_delta_db_vs_baseline"])
        self.assertEqual(row["metrics"]["silent_window_fraction"], 1)
        self.assertIn("silence_prevents_rms_level_comparison", row["warnings"])
        wav(self.candidate, [32767] * 8000)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIn("near_full_scale_samples_inspect_for_clipping", row["warnings"])

    def test_corrupt_baseline_is_flagged_even_if_candidate_clean(self):
        wav(self.base, [32767] * 8000)
        report = compare_wavs(self.base, [self.candidate])
        self.assertIn("near_full_scale_samples_inspect_for_clipping", report["baseline_warnings"])
        self.assertNotIn("near_full_scale_samples_inspect_for_clipping", report["candidates"][0]["warnings"])
        wav(self.base, [0] * 8000)
        report = compare_wavs(self.base, [self.candidate])
        self.assertIn("fully_silent_audio_inspect", report["baseline_warnings"])
        self.assertIn("silence_prevents_rms_level_comparison", report["candidates"][0]["warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_one_silent_stereo_channel_is_flagged_on_both_sides(self):
        stereo_base = self.root / "stereo_base.wav"
        stereo_candidate = self.root / "stereo_candidate.wav"
        stereo_clean = [value for sample in self.samples for value in (sample, sample)]
        stereo_missing = [value for sample in self.samples for value in (sample, 0)]
        wav(stereo_base, stereo_missing, channels=2)
        wav(stereo_candidate, stereo_clean, channels=2)
        report = compare_wavs(stereo_base, [stereo_candidate])
        self.assertTrue(report["baseline"]["stereo_channel_silence_risk"])
        self.assertIn("stereo_silent_channel_inspect", report["baseline_warnings"])
        self.assertFalse(report["candidates"][0]["metrics"]["stereo_channel_silence_risk"])
        self.assertNotIn("stereo_silent_channel_inspect", report["candidates"][0]["warnings"])
        self.assertIsNone(report["baseline"]["channel_rms_dbfs"][1])
        wav(stereo_base, stereo_clean, channels=2)
        wav(stereo_candidate, stereo_missing, channels=2)
        report = compare_wavs(stereo_base, [stereo_candidate])
        self.assertFalse(report["baseline_warnings"])
        self.assertIn("stereo_silent_channel_inspect", report["candidates"][0]["warnings"])
        wav(stereo_candidate, [0] * (2 * len(self.samples)), channels=2)
        self.assertFalse(scan_wav(stereo_candidate)["stereo_channel_silence_risk"])

    def test_partial_stereo_channel_dropout_detected_with_normal_whole_file_rms(self):
        # Left remains audible; right drops for half the file, but whole-file
        # right RMS is still far above the missing-channel threshold.
        base = self.root / "balanced.wav"
        candidate = self.root / "partial.wav"
        wav(base, [v for x in self.samples for v in (x, x)], channels=2)
        wav(candidate, [v for i, x in enumerate(self.samples)
                        for v in (x, x if i < 4000 else 0)], channels=2)
        metrics = scan_wav(candidate)
        self.assertFalse(metrics["stereo_channel_silence_risk"])
        self.assertTrue(metrics["partial_stereo_channel_loss_risk"])
        self.assertAlmostEqual(.5, metrics["partial_stereo_channel_loss_fraction"], delta=.01)
        report = compare_wavs(base, [candidate])
        self.assertFalse(report["baseline_warnings"])
        self.assertIn("partial_stereo_channel_loss_inspect", report["candidates"][0]["warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_stereo_channel_dropout_ignores_isolated_and_fully_silent_windows(self):
        sample_count = len(self.samples)
        stereo = self.root / "isolated.wav"
        wav(stereo, [v for i, x in enumerate(self.samples)
                     for v in (x, 0 if 3200 <= i < 4000 else x)], channels=2)
        metrics = scan_wav(stereo)
        self.assertEqual(.1, metrics["partial_stereo_channel_loss_fraction"])
        self.assertFalse(metrics["partial_stereo_channel_loss_risk"])
        wav(stereo, [0] * (2 * sample_count), channels=2)
        metrics = scan_wav(stereo)
        self.assertIsNone(metrics["partial_stereo_channel_loss_fraction"])
        self.assertFalse(metrics["partial_stereo_channel_loss_risk"])
        self.assertIsNone(scan_wav(self.base)["partial_stereo_channel_loss_fraction"])

    def test_attenuated_flat_top_detected_across_streaming_boundary(self):
        # A previously clipped signal later turned down to ~-2.2 dBFS
        # escapes near-full-scale checks but retains exact flat tops.
        samples = self.samples.copy()
        samples[4094:4099] = [26000] * 5
        wav(self.candidate, samples)
        report = compare_wavs(self.base, [self.candidate])
        row = report["candidates"][0]
        self.assertEqual(0.0, row["metrics"]["near_full_scale_fraction"])
        self.assertEqual(1, row["metrics"]["high_flat_top_plateau_count"])
        self.assertTrue(row["metrics"]["high_flat_top_plateau_risk"])
        self.assertIn("high_flat_top_plateau_inspect_for_prior_limiting", row["warnings"])
        self.assertNotIn("high_flat_top_plateau_inspect_for_prior_limiting",
                         report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        # An isolated 3-sample percussion peak is below the rule's length.
        samples[4094:4099] = self.samples[4094:4099]
        samples[1100:1103] = [26000] * 3
        wav(self.candidate, samples)
        metrics = scan_wav(self.candidate)
        self.assertEqual(0, metrics["high_flat_top_plateau_count"])
        self.assertFalse(metrics["high_flat_top_plateau_risk"])
        # The reference must be inspected equally, not trusted blindly.
        wav(self.base, [26000] * len(self.samples))
        report = compare_wavs(self.base, [self.candidate])
        self.assertIn("high_flat_top_plateau_inspect_for_prior_limiting",
                      report["baseline_warnings"])
        self.assertEqual(1, report["baseline"]["high_flat_top_plateau_count"])

    def test_playback_boundaries_flag_steps_absent_from_adjacent_jump_checks(self):
        # A smooth waveform can still start at a very high sample value:
        # no internal >50% discontinuity, but playback from zero may click.
        smooth_start = [int(18000 * math.cos(i * 0.01)) for i in range(8000)]
        wav(self.candidate, smooth_start)
        report = compare_wavs(self.base, [self.candidate])
        candidate = report["candidates"][0]
        metrics = candidate["metrics"]
        self.assertFalse(metrics["severe_sample_discontinuity_risk"])
        self.assertEqual(0, metrics["severe_adjacent_jump_count"])
        self.assertGreater(metrics["playback_start_peak"], 0.5)
        self.assertTrue(metrics["playback_boundary_pop_risk"])
        self.assertIn("playback_boundary_step_inspect_for_clicks", candidate["warnings"])
        self.assertNotIn("playback_boundary_step_inspect_for_clicks",
                         report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        # The exact same hazard must also be audited on the reference.
        wav(self.base, smooth_start)
        wav(self.candidate, self.samples)
        report = compare_wavs(self.base, [self.candidate])
        self.assertIn("playback_boundary_step_inspect_for_clicks", report["baseline_warnings"])
        self.assertNotIn("playback_boundary_step_inspect_for_clicks",
                         report["candidates"][0]["warnings"])

    def test_playback_boundary_threshold_and_stereo_single_channel(self):
        stereo = self.root / "boundary-stereo.wav"
        quiet = [0] * (8000 * 2)
        quiet[-1] = 8191
        wav(stereo, quiet, channels=2)
        metrics = scan_wav(stereo)
        self.assertFalse(metrics["playback_boundary_pop_risk"])
        self.assertLess(metrics["playback_end_peak"], 0.25)
        quiet[-1] = 8192
        wav(stereo, quiet, channels=2)
        metrics = scan_wav(stereo)
        self.assertTrue(metrics["playback_boundary_pop_risk"])
        self.assertEqual(0.25, metrics["playback_end_peak"])
        self.assertEqual(0.0, metrics["playback_start_peak"])
        # Entirely silent audio has no artificial boundary click.
        wav(stereo, [0] * len(quiet), channels=2)
        self.assertFalse(scan_wav(stereo)["playback_boundary_pop_risk"])

    def test_sample_splice_click_detected_across_stream_read_boundary(self):
        samples = self.samples.copy()
        samples[4095], samples[4096], samples[4097] = 0, 22000, 0
        wav(self.candidate, samples)
        report = compare_wavs(self.base, [self.candidate])
        row = report["candidates"][0]
        self.assertGreaterEqual(row["metrics"]["severe_adjacent_jump_count"], 2)
        self.assertGreater(row["metrics"]["max_adjacent_sample_jump"], 0.5)
        self.assertIn("severe_sample_discontinuity_inspect_for_pops", row["warnings"])
        self.assertNotIn("severe_sample_discontinuity_inspect_for_pops", report["baseline_warnings"])

    def test_dc_offset_warns_on_both_sides_without_audio_repair(self):
        wav(self.base, [2500] * len(self.samples))
        report = compare_wavs(self.base, [self.candidate])
        self.assertTrue(report["baseline"]["dc_offset_risk"])
        self.assertIn("dc_offset_inspect_for_headroom", report["baseline_warnings"])
        self.assertFalse(report["candidates"][0]["metrics"]["dc_offset_risk"])
        self.assertNotIn("dc_offset_inspect_for_headroom", report["candidates"][0]["warnings"])
        wav(self.base, self.samples)
        wav(self.candidate, [-2500] * len(self.samples))
        report = compare_wavs(self.base, [self.candidate])
        self.assertFalse(report["baseline_warnings"])
        self.assertIn("dc_offset_inspect_for_headroom", report["candidates"][0]["warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_stereo_stream_windows_and_determinism(self):
        stereo = self.root / "stereo.wav"
        interleaved = [sample for x in self.samples for sample in (x, -x)]
        wav(stereo, interleaved, channels=2)
        once, twice = scan_wav(stereo, window_ms=50), scan_wav(stereo, window_ms=50)
        self.assertEqual(once, twice)
        self.assertEqual(2, once["channels"])
        self.assertEqual(20, once["window_count"])
        self.assertAlmostEqual(0, once["dc_per_channel"][0] + once["dc_per_channel"][1])
        with self.assertRaisesRegex(ValueError, "channels"):
            compare_wavs(self.base, [stereo])

    def test_stereo_antiphase_cancels_in_mono_without_false_musical_claim(self):
        stereo = self.root / "antiphase.wav"
        wav(stereo, [v for x in self.samples for v in (x, -x)], channels=2)
        metrics = scan_wav(stereo)
        self.assertEqual(-1.0, metrics["stereo_phase_correlation"])
        self.assertIsNone(metrics["mono_fold_down_loss_db"])  # Exact zero mono energy.
        self.assertEqual(1.0, metrics["mono_fold_down_risky_window_fraction"])
        self.assertTrue(metrics["mono_fold_down_cancellation_risk"])
        row = compare_wavs(stereo, [stereo])["candidates"][0]
        self.assertIn("stereo_mono_fold_down_cancellation_inspect", row["warnings"])
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertNotIn(str(self.root), json.dumps(row))

    def test_stereo_in_phase_or_one_silent_channel_are_not_cancellation(self):
        stereo = self.root / "stereo.wav"
        wav(stereo, [v for x in self.samples for v in (x, x)], channels=2)
        metrics = scan_wav(stereo)
        self.assertEqual(1.0, metrics["stereo_phase_correlation"])
        self.assertEqual(0.0, metrics["mono_fold_down_loss_db"])
        self.assertEqual(0.0, metrics["mono_fold_down_risky_window_fraction"])
        self.assertFalse(metrics["mono_fold_down_cancellation_risk"])
        wav(stereo, [v for x in self.samples for v in (x, 0)], channels=2)
        metrics = scan_wav(stereo)
        self.assertIsNone(metrics["stereo_phase_correlation"])
        self.assertAlmostEqual(3.01, metrics["mono_fold_down_loss_db"], delta=0.02)
        self.assertFalse(metrics["mono_fold_down_cancellation_risk"])
        wav(stereo, [0] * (len(self.samples) * 2), channels=2)
        self.assertFalse(scan_wav(stereo)["mono_fold_down_cancellation_risk"])

    def test_temporary_antiphase_is_detected_even_if_average_loss_is_small(self):
        stereo = self.root / "temporary.wav"
        wav(stereo, [v for i, x in enumerate(self.samples)
                     for v in (x, x if i < 4000 else -x)], channels=2)
        metrics = scan_wav(stereo, window_ms=100)
        self.assertTrue(metrics["mono_fold_down_cancellation_risk"])
        self.assertAlmostEqual(0.5, metrics["mono_fold_down_risky_window_fraction"], delta=0.01)
        self.assertAlmostEqual(3.01, metrics["mono_fold_down_loss_db"], delta=0.1)
        self.assertEqual(metrics, scan_wav(stereo, window_ms=100))

    def test_short_interior_silence_triggers_warning_below_majority_silence(self):
        # A dropped 300 ms section would be missed by the existing >50%-silent rule.
        wav(self.candidate, self.samples[:2400] + [0] * 2400 + self.samples[4800:])
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertLess(row["metrics"]["silent_window_fraction"], 0.5)
        self.assertEqual(300.0, row["metrics"]["longest_interior_silent_gap_ms"])
        self.assertTrue(row["metrics"]["interior_silent_gap_risk"])
        self.assertIn("interior_silent_gap_inspect_for_dropouts", row["warnings"])

    def test_leading_trailing_silence_and_single_short_gap_are_not_interior_dropouts(self):
        wav(self.candidate, [0] * 1600 + self.samples[1600:6400] + [0] * 1600)
        metrics = scan_wav(self.candidate)
        self.assertEqual(0.0, metrics["longest_interior_silent_gap_ms"])
        self.assertFalse(metrics["interior_silent_gap_risk"])
        wav(self.candidate, self.samples[:3200] + [0] * 800 + self.samples[4000:])
        metrics = scan_wav(self.candidate)
        self.assertEqual(100.0, metrics["longest_interior_silent_gap_ms"])
        self.assertFalse(metrics["interior_silent_gap_risk"])
        wav(self.candidate, [0] * len(self.samples))
        metrics = scan_wav(self.candidate)
        self.assertEqual(0.0, metrics["longest_interior_silent_gap_ms"])
        self.assertFalse(metrics["interior_silent_gap_risk"])

    def test_mismatched_duration_rate_and_format_are_fail_closed(self):
        wav(self.candidate, self.samples[:-10])
        with self.assertRaisesRegex(ValueError, "frames"):
            compare_wavs(self.base, [self.candidate])
        wav(self.candidate, self.samples, rate=16000)
        with self.assertRaisesRegex(ValueError, "sample_rate"):
            compare_wavs(self.base, [self.candidate])
        invalid = self.root / "invalid.wav"
        invalid.write_bytes(b"broken audio data")
        with self.assertRaises(ValueError):
            scan_wav(invalid)
        with wave.open(str(invalid), "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(1)
            dst.setframerate(8000)
            dst.writeframes(bytes(800))
        with self.assertRaisesRegex(ValueError, "PCM16"):
            scan_wav(invalid)

    def test_bounds_and_invalid_parameters(self):
        with self.assertRaisesRegex(ValueError, "window_ms"):
            scan_wav(self.base, window_ms=0)
        for value in (float("nan"), float("inf"), -1, 0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "loudness_tolerance_db"):
                compare_wavs(self.base, [self.candidate], loudness_tolerance_db=value)
        with self.assertRaisesRegex(ValueError, "At least one"):
            compare_wavs(self.base, [])
        with self.assertRaisesRegex(ValueError, "At most 20"):
            compare_wavs(self.base, [self.candidate] * 21)
        with patch("mixlab.quality.MAX_SOURCE_FRAMES", 500):
            with self.assertRaisesRegex(ValueError, "Frames"):
                scan_wav(self.base)
        with patch("mixlab.quality.MAX_SOURCE_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                scan_wav(self.base)

    def test_identical_pcm_detection_ignores_wav_container_metadata(self):
        second = self.root / "same-audio-different-container.wav"
        copy = self.root / "same-other-candidate.wav"
        modified = self.samples.copy()
        modified[123] += 1
        wav(self.candidate, modified)
        wav(copy, modified)
        # Exact PCM bytes with different trailing container bytes: still a duplicate.
        with copy.open("ab") as out:
            out.write(b"non_audio_container_metadata")
        wav(second, self.samples)
        report = compare_wavs(self.base, [self.candidate, copy, second])
        first, duplicate, baseline = report["candidates"]
        self.assertIsNone(first["duplicate_pcm_of"])
        self.assertFalse(first["warnings"])
        self.assertEqual("candidate-01", duplicate["duplicate_pcm_of"])
        self.assertIn("duplicate_candidate_pcm_inspect", duplicate["warnings"])
        self.assertEqual("baseline", baseline["duplicate_pcm_of"])
        self.assertIn("identical_pcm_to_baseline_inspect_for_noop", baseline["warnings"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("sha256", serialized)
        self.assertNotIn("non_audio_container_metadata", serialized)
        self.assertNotIn("duplicate_pcm_of", json.dumps(scan_wav(self.base)))
        # No source rewrite during fingerprinting.
        self.assertTrue(copy.read_bytes().endswith(b"non_audio_container_metadata"))

    def test_cli_optional_strict_gate_preserves_json_and_default_exit(self):
        args = [sys.executable, "-m", "mixlab.quality", str(self.base), str(self.candidate)]
        # Exactly identical baseline/candidate PCM is an invalid blind A/B
        # comparison, so make this clean fixture differ by a benign sample.
        modified = self.samples.copy()
        modified[123] += 1
        wav(self.candidate, modified)
        clean = subprocess.run(args + ["--fail-on-warnings"], capture_output=True, text=True)
        self.assertEqual(0, clean.returncode)
        self.assertFalse(json.loads(clean.stdout)["baseline_warnings"])
        wav(self.candidate, [0] * len(self.samples))
        default = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(0, default.returncode)
        strict = subprocess.run(args + ["--fail-on-warnings"], capture_output=True, text=True)
        self.assertEqual(2, strict.returncode)
        self.assertTrue(json.loads(strict.stdout)["candidates"][0]["warnings"])
        self.assertNotIn(str(self.root), strict.stdout + strict.stderr)
        wav(self.candidate, self.samples)
        wav(self.base, [32767] * len(self.samples))
        baseline_strict = subprocess.run(args + ["--fail-on-warnings"], capture_output=True, text=True)
        self.assertEqual(2, baseline_strict.returncode)
        self.assertIn("near_full_scale_samples_inspect_for_clipping",
                      json.loads(baseline_strict.stdout)["baseline_warnings"])

    def test_cli_failed_inputs_never_echo_private_audio_paths(self):
        args = [sys.executable, "-m", "mixlab.quality"]
        missing = self.root / "private-recording-do-not-leak.wav"
        for baseline, candidate in (
            (missing, self.candidate),
            (self.base, missing),
        ):
            with self.subTest(baseline=baseline == missing):
                result = subprocess.run(args + [str(baseline), str(candidate)],
                                        capture_output=True, text=True)
                self.assertEqual(3, result.returncode)
                self.assertFalse(result.stdout)
                self.assertIn("invalid or unreadable WAV", result.stderr)
                self.assertNotIn(str(self.root), result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("FileNotFoundError", result.stderr)
        bad = self.root / "secret-track.wav"
        bad.write_bytes(b"not a WAV")
        result = subprocess.run(args + [str(self.base), str(bad)],
                                capture_output=True, text=True)
        self.assertEqual(3, result.returncode)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_failed_format_and_parameter_checks_do_not_leak_paths(self):
        args = [sys.executable, "-m", "mixlab.quality", str(self.base), str(self.candidate)]
        for option in (["--window-ms", "10"], ["--loudness-tolerance-db", "NaN"]):
            with self.subTest(option=option):
                result = subprocess.run(args + option, capture_output=True, text=True)
                self.assertEqual(3, result.returncode)
                self.assertNotIn(str(self.root), result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        wav(self.candidate, self.samples[:-1])
        mismatch = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(3, mismatch.returncode)
        self.assertNotIn(str(self.root), mismatch.stdout + mismatch.stderr)

    def test_review_pack_pair_integrity_privacy_and_strict_cli(self):
        review = self.root / "review"
        private = self.root / "private"
        review.mkdir()
        private.mkdir()
        (private / "answer-key.json").write_text("secret-should-not-be-read")
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", self.samples)
        other = self.samples.copy()
        other[140] += 1
        wav(review / "trial-002-A.wav", [int(x * .98) for x in self.samples])
        wav(review / "trial-002-B.wav", other)
        (review / "index.html").write_text(neutral_review_page(["trial-001", "trial-002"]))
        report = inspect_review_pack(review)
        self.assertEqual(2, report["trial_count"])
        self.assertEqual(1, report["warning_trial_count"])
        self.assertEqual(["trial-001", "trial-002"], [r["trial_id"] for r in report["trials"]])
        self.assertIn("identical_pcm_between_A_and_B", report["trials"][0]["B"]["warnings"])
        self.assertFalse(report["trials"][1]["technical_warnings_present"])
        self.assertFalse(report["answer_key_opened"])
        self.assertTrue(report["review_page_audio_links_verified"])
        self.assertTrue(report["human_preference_test_required"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("answer-key", serialized)
        self.assertNotIn("secret-should-not-be-read", serialized)
        self.assertNotIn("sha256", serialized)
        args = [sys.executable, "-m", "mixlab.quality.pack", str(review)]
        default = subprocess.run(args, capture_output=True, text=True)
        strict = subprocess.run(args + ["--fail-on-warnings"], capture_output=True, text=True)
        self.assertEqual(0, default.returncode)
        self.assertEqual(2, strict.returncode)
        self.assertEqual(report, json.loads(strict.stdout))
        self.assertNotIn(str(self.root), strict.stdout + strict.stderr)
        (review / "trial-001-B.wav").unlink()
        self.assertEqual(3, subprocess.run(args, capture_output=True, text=True).returncode)

    def test_repeat_pcm_between_trials_unblinds_recognizable_reference(self):
        review = self.root / "review"
        review.mkdir()
        same_audio = self.samples.copy()
        different_a = [int(x * .85) for x in self.samples]
        different_b = [int(x * 1.05) for x in self.samples]
        wav(review / "trial-001-A.wav", same_audio)
        wav(review / "trial-001-B.wav", different_a)
        wav(review / "trial-002-A.wav", different_b)
        wav(review / "trial-002-B.wav", same_audio)
        # Public review containers now reject non-audio trailers, even when
        # decoded PCM is unchanged. Keep the cross-trial audio-repeat test on
        # the neutral published WAVs; separate compare_wavs tests still show
        # that *private* PCM fingerprints ignore container metadata.
        public_audio = review / "trial-002-B.wav"
        unmodified = public_audio.read_bytes()
        with public_audio.open("ab") as output:
            output.write(b"unrelated-non-audio-container-trailer")
        with self.assertRaisesRegex(ValueError, "Review public WAV"):
            inspect_review_pack(review)
        public_audio.write_bytes(unmodified)
        report = inspect_review_pack(review)
        self.assertEqual(2, report["trial_count"])
        self.assertEqual(1, report["cross_trial_repeated_variant_count"])
        self.assertEqual([], report["trials"][0]["trial_warnings"])
        self.assertIn("repeated_pcm_across_trials_inspect_blinding",
                      report["trials"][1]["trial_warnings"])
        # Preserve blinding even in the QA report: do not expose which
        # slot matched or the earlier A/B label.
        self.assertFalse(report["trials"][1]["A"]["warnings"])
        self.assertFalse(report["trials"][1]["B"]["warnings"])
        self.assertFalse(report["trials"][0]["technical_warnings_present"])
        self.assertTrue(report["trials"][1]["technical_warnings_present"])
        self.assertEqual(1, report["warning_trial_count"])
        serialized = json.dumps(report)
        self.assertNotIn("sha256", serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("non-audio-container-trailer", serialized)
        strict = subprocess.run([sys.executable, "-m", "mixlab.quality.pack", str(review),
                                 "--fail-on-warnings"], capture_output=True, text=True)
        self.assertEqual(2, strict.returncode)
        self.assertEqual(report, json.loads(strict.stdout))

    def test_cross_trial_swapped_stereo_reuse_warns_without_unblinding_sides(self):
        # Exact PCM hash differs when the *same stereo signal* is reused in
        # another trial with left and right exchanged. Keep A/B labels secret.
        review = self.root / "swapped-cross-trial"
        review.mkdir()
        stereo = [v for i in range(8000)
                  for v in (int(4500 * math.sin(i * .13)),
                            int(6000 * math.cos(i * .17)))]
        swapped = [v for i in range(0, len(stereo), 2)
                   for v in (stereo[i + 1], stereo[i])]
        unrelated = [v for i in range(8000)
                     for v in (int(4000 * math.sin(i * .21)),
                               int(3200 * math.cos(i * .09)))]
        wav(review / "trial-001-A.wav", stereo, channels=2)
        wav(review / "trial-001-B.wav", [int(v * .8) for v in stereo], channels=2)
        wav(review / "trial-002-A.wav", unrelated, channels=2)
        wav(review / "trial-002-B.wav", swapped, channels=2)
        before = {p.name: p.read_bytes() for p in review.iterdir()}
        report = inspect_review_pack(review)
        self.assertEqual(1, report["cross_trial_repeated_variant_count"])
        self.assertEqual([], report["trials"][0]["trial_warnings"])
        self.assertEqual(
            ["repeated_pcm_across_trials_inspect_blinding"],
            report["trials"][1]["trial_warnings"],
        )
        for side in ("A", "B"):
            self.assertNotIn("repeated_pcm_across_trials_inspect_blinding",
                             report["trials"][1][side]["warnings"])
        self.assertNotIn("trial-001-A.wav", json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("sha256", json.dumps(report))
        self.assertEqual(before, {p.name: p.read_bytes() for p in review.iterdir()})
        cmd = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.pack", str(review),
             "--fail-on-warnings"], capture_output=True, text=True,
        )
        self.assertEqual(2, cmd.returncode)
        self.assertEqual(report, json.loads(cmd.stdout))
        self.assertNotIn(str(self.root), cmd.stdout + cmd.stderr)
        # Full identity includes sample rate; same samples at different
        # playback speed must not be incorrectly matched.
        wav(review / "trial-002-A.wav", unrelated, rate=16000, channels=2)
        wav(review / "trial-002-B.wav", swapped, rate=16000, channels=2)
        report = inspect_review_pack(review)
        self.assertEqual(0, report["cross_trial_repeated_variant_count"])

    def test_cross_trial_swapped_stereo_keeps_one_trial_and_mono_guards(self):
        review = self.root / "only-one-stereo-trial"
        review.mkdir()
        stereo = [v for i in range(8000)
                  for v in (int(5000 * math.sin(i * .07)),
                            int(6000 * math.cos(i * .12)))]
        swapped = [v for i in range(0, len(stereo), 2)
                   for v in (stereo[i + 1], stereo[i])]
        wav(review / "trial-001-A.wav", stereo, channels=2)
        wav(review / "trial-001-B.wav", swapped, channels=2)
        report = inspect_review_pack(review)
        self.assertEqual(0, report["cross_trial_repeated_variant_count"])
        self.assertEqual([], report["trials"][0]["trial_warnings"])
        # Two identical mono PCM clips are not a stereo channel swap.
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", self.samples)
        report = inspect_review_pack(review)
        self.assertEqual(0, report["cross_trial_repeated_variant_count"])
        self.assertFalse(report["trials"][0]["trial_warnings"])

    def test_cross_trial_fingerprint_distinguishes_playback_sample_rate(self):
        review = self.root / "review"
        review.mkdir()
        # Raw PCM can be identical but sound different when replayed at
        # different rates; format is part of the private fingerprint.
        for number, rate in ((1, 8000), (2, 16000)):
            wav(review / f"trial-00{number}-A.wav", self.samples, rate=rate)
            wav(review / f"trial-00{number}-B.wav",
                [int(x * .9) for x in self.samples], rate=rate)
        report = inspect_review_pack(review)
        self.assertEqual(0, report["cross_trial_repeated_variant_count"])
        self.assertFalse(report["trials"][1]["trial_warnings"])

    def test_review_pack_detects_mutated_audio_page_and_receipt_during_scan(self):
        from mixlab.cli import write_review
        pack = self.root / "pack"
        review = pack / "review"
        review.mkdir(parents=True)
        first, second = review / "trial-001-A.wav", review / "trial-001-B.wav"
        wav(first, self.samples)
        wav(second, [int(x / 2) for x in self.samples])
        page = review / "index.html"
        receipt = pack / "receipt.json"
        write_review(page, ["trial-001"], "a" * 64)
        receipt.write_text(json.dumps({"schema_version": 1, "pack_id": "a" * 64,
                                       "trial_count": 1}))
        arguments = {"require_generated_html": True, "require_receipt": True}
        self.assertTrue(inspect_review_pack(review, **arguments)[
            "public_receipt_pack_id_verified"])
        # Wrap the *actual* PCM scan and change a watched asset only after
        # its metrics have been computed, as another process could do.
        for modified in (first, page, receipt):
            original_bytes = modified.read_bytes()

            def modify_while_scanning(base, candidates, **kwargs):
                result = compare_wavs(base, candidates, **kwargs)
                if modified == first:
                    replacement = self.root / "replacement.wav"
                    replacement.write_bytes(modified.read_bytes())
                    replacement.replace(modified)  # same bytes; different inode
                else:
                    with modified.open("ab") as output:
                        output.write(b" ")  # no effect on WAV metadata
                return result

            with self.subTest(asset=modified.name), patch(
                "mixlab.quality.pack.compare_wavs", side_effect=modify_while_scanning
            ):
                with self.assertRaisesRegex(ValueError, "changed during quality preflight"):
                    inspect_review_pack(review, **arguments)
            modified.write_bytes(original_bytes)
        self.assertTrue(inspect_review_pack(review, **arguments)[
            "public_receipt_pack_id_verified"])

    def test_review_pack_fails_if_public_inventory_grows_during_pcm_scan(self):
        # A private answer key introduced *after* initial enumeration must
        # never be accepted in a listener-facing review pack.
        review = self.root / "growing-review"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x / 2) for x in self.samples])
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])
        for extra_name in ("answer-key.json", "trial-002-A.wav", "notes.txt"):
            injected = review / extra_name

            def add_after_pcm_read(base, candidates, **kwargs):
                result = compare_wavs(base, candidates, **kwargs)
                injected.write_bytes(b"private-data-must-never-be-exposed")
                return result

            with self.subTest(asset=extra_name), patch(
                "mixlab.quality.pack.compare_wavs", side_effect=add_after_pcm_read
            ):
                with self.assertRaisesRegex(ValueError, "changed during quality preflight"):
                    inspect_review_pack(review)
            self.assertTrue(injected.exists())
            injected.unlink()
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])

    def test_review_pack_guards_public_page_and_receipt_during_initial_validation(self):
        from mixlab.cli import write_review
        from mixlab.quality import pack as pack_module
        root = self.root / "early-mutating-pack"
        review = root / "review"
        review.mkdir(parents=True)
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x / 2) for x in self.samples])
        page = review / "index.html"
        receipt = root / "receipt.json"
        write_review(page, ["trial-001"], "b" * 64)
        receipt.write_text(json.dumps({"schema_version": 1, "pack_id": "b" * 64,
                                       "trial_count": 1}))
        opts = {"require_generated_html": False, "require_receipt": True}
        self.assertTrue(inspect_review_pack(review, **opts)["public_receipt_pack_id_verified"])
        original_receipt = receipt.read_bytes()
        read_receipt = pack_module._read_public_receipt_id

        def change_receipt_while_validating(*args):
            result = read_receipt(*args)
            # The JSON still validates; only the file's identity changes.
            receipt.write_bytes(original_receipt + b" ")
            return result

        with patch("mixlab.quality.pack._read_public_receipt_id",
                   side_effect=change_receipt_while_validating):
            with self.assertRaisesRegex(ValueError, "changed during quality preflight"):
                inspect_review_pack(review, **opts)
        receipt.write_bytes(original_receipt)
        original_page = page.read_bytes()
        verify_page = pack_module._verify_public_review_page

        def change_page_while_validating(*args, **kwargs):
            result = verify_page(*args, **kwargs)
            page.write_bytes(original_page + b"\n")
            return result

        with patch("mixlab.quality.pack._verify_public_review_page",
                   side_effect=change_page_while_validating):
            with self.assertRaisesRegex(ValueError, "changed during quality preflight"):
                inspect_review_pack(review, **opts)
        page.write_bytes(original_page)
        self.assertTrue(inspect_review_pack(review, **opts)["review_page_audio_links_verified"])

    def test_review_pack_rejects_missing_trial_numbers_before_audio_or_receipt(self):
        review = self.root / "review"
        review.mkdir()
        for trial in ("trial-001", "trial-003"):
            wav(review / f"{trial}-A.wav", self.samples)
            wav(review / f"{trial}-B.wav", [int(x / 2) for x in self.samples])
        # Previous validation accepted two complete pairs and a two-trial
        # receipt, despite skipping trial-002. Reject the gap early.
        with patch("mixlab.quality.pack.compare_wavs", side_effect=AssertionError("PCM scan")):
            with self.assertRaisesRegex(ValueError, "contiguous sequence"):
                inspect_review_pack(review)
        failed = subprocess.run([sys.executable, "-m", "mixlab.quality.pack", str(review)],
                                capture_output=True, text=True)
        self.assertEqual(3, failed.returncode)
        self.assertFalse(failed.stdout)
        self.assertNotIn(str(self.root), failed.stderr)
        for old in review.glob("trial-003-*.wav"):
            old.rename(review / old.name.replace("trial-003", "trial-002"))
        report = inspect_review_pack(review)
        self.assertEqual(["trial-001", "trial-002"], [row["trial_id"] for row in report["trials"]])

    def test_review_pack_total_resource_budget_is_checked_before_pcm_scan(self):
        review = self.root / "review"
        review.mkdir()
        first, second = review / "trial-001-A.wav", review / "trial-001-B.wav"
        wav(first, self.samples)
        wav(second, [int(x / 2) for x in self.samples])
        total_bytes = first.stat().st_size + second.stat().st_size
        # No sample-domain scan should happen if *either* aggregate limit
        # already rules out the pack from header/metadata inspection.
        with patch("mixlab.quality.pack.MAX_REVIEW_PACK_BYTES", total_bytes - 1), \
             patch("mixlab.quality.pack.compare_wavs", side_effect=AssertionError("PCM read")):
            with self.assertRaisesRegex(ValueError, "total byte budget"):
                inspect_review_pack(review)
        with patch("mixlab.quality.pack.MAX_REVIEW_PACK_FRAMES", 15999), \
             patch("mixlab.quality.pack.compare_wavs", side_effect=AssertionError("PCM read")):
            with self.assertRaisesRegex(ValueError, "total frame budget"):
                inspect_review_pack(review)
        # Exact thresholds remain accepted and the normal diagnostic still
        # runs, so one-trial valid packs are not accidentally disabled.
        with patch("mixlab.quality.pack.MAX_REVIEW_PACK_BYTES", total_bytes), \
             patch("mixlab.quality.pack.MAX_REVIEW_PACK_FRAMES", 16000):
            report = inspect_review_pack(review)
        self.assertEqual(1, report["trial_count"])
        self.assertEqual(1, len(report["trials"]))
        second.write_bytes(b"corrupt header data")
        with patch("mixlab.quality.pack.compare_wavs", side_effect=AssertionError("PCM read")):
            with self.assertRaisesRegex(ValueError, "Invalid review WAV header"):
                inspect_review_pack(review)

    def test_review_pack_rejects_untrusted_incomplete_or_oversized_inventories(self):
        review = self.root / "review"
        review.mkdir()
        a = review / "trial-001-A.wav"
        b = review / "trial-001-B.wav"
        wav(a, self.samples)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            inspect_review_pack(review)
        wav(b, self.samples)
        unexpected = review / "secret-source.wav"
        wav(unexpected, self.samples)
        with self.assertRaisesRegex(ValueError, "unexpected WAV"):
            inspect_review_pack(review)
        unexpected.unlink()
        b.unlink()
        b.symlink_to(self.candidate)
        with self.assertRaisesRegex(ValueError, "symlink"):
            inspect_review_pack(review)
        b.unlink()
        wav(b, self.samples)
        with patch("mixlab.quality.pack.MAX_TRIALS", 0):
            with self.assertRaisesRegex(ValueError, "trial limit"):
                inspect_review_pack(review)
        with self.assertRaisesRegex(ValueError, "real directory"):
            inspect_review_pack(self.candidate)
        linked = self.root / "review-link"
        linked.symlink_to(review, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            inspect_review_pack(linked)
        (review / "trial-000-A.wav").write_bytes(b"invalid")
        with self.assertRaisesRegex(ValueError, "unexpected WAV"):
            inspect_review_pack(review)

    def test_review_pack_rejects_accidentally_published_answer_keys(self):
        review = self.root / "review"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x / 2) for x in self.samples])
        (review / "index.html").write_text(neutral_review_page(["trial-001"]))
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])
        secret = review / "answer-key.json"
        secret.write_text('{"trial-001": "baseline-A"}')
        with self.assertRaisesRegex(ValueError, "unexpected public asset"):
            inspect_review_pack(review)
        args = [sys.executable, "-m", "mixlab.quality.pack", str(review)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(3, result.returncode)
        self.assertFalse(result.stdout)
        self.assertNotIn("baseline-A", result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        secret.unlink()
        index = review / "index.html"
        index.unlink()
        index.symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "Review index"):
            inspect_review_pack(review)

    def test_public_review_wav_rejects_metadata_chunks_and_hidden_trailing_bytes(self):
        review = self.root / "metadata-review"
        review.mkdir()
        a = review / "trial-001-A.wav"
        b = review / "trial-001-B.wav"
        wav(a, self.samples)
        wav(b, [int(sample * .9) for sample in self.samples])
        original = a.read_bytes()
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])

        def riff_with_extra(extra, *, before_data=False, update_size=True):
            payload = (original[:36] + extra + original[36:] if before_data
                       else original + extra)
            modified = bytearray(payload)
            if update_size:
                modified[4:8] = (len(modified) - 8).to_bytes(4, "little")
            return bytes(modified)

        label = b"source-label"
        metadata = b"LIST" + len(label).to_bytes(4, "little") + label
        if len(label) % 2:
            metadata += bytes([0])
        junk = b"JUNK" + (4).to_bytes(4, "little") + b"ABCD"
        variants = (
            riff_with_extra(metadata),
            riff_with_extra(junk, before_data=True),
            riff_with_extra(b"hidden-answer", update_size=False),
        )
        for index, contents in enumerate(variants):
            with self.subTest(case=index):
                a.write_bytes(contents)
                # Wave/PCM reading accepts metadata and trailing bytes, which
                # is why this must be a separate public-container guard.
                with wave.open(str(a), "rb") as source:
                    self.assertEqual(len(self.samples), source.getnframes())
                with patch("mixlab.quality.pack.compare_wavs",
                           side_effect=AssertionError("PCM scanned too early")):
                    with self.assertRaisesRegex(ValueError, "Review public WAV"):
                        inspect_review_pack(review)
                process = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review)],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, process.returncode)
                self.assertNotIn(str(self.root), process.stdout + process.stderr)
                self.assertNotIn("source-label", process.stdout + process.stderr)
                self.assertFalse(process.stdout)
                a.write_bytes(original)
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])

    def test_review_page_links_reject_wrong_swapped_or_external_audio(self):
        review = self.root / "review"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x / 2) for x in self.samples])
        page = review / "index.html"
        valid = neutral_review_page(["trial-001"])
        page.write_text(valid)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])
        with self.assertRaisesRegex(ValueError, "canonical public pack"):
            inspect_review_pack(review, require_generated_html=True)
        for wrong in (
            valid.replace("trial-001-B.wav", "https://example.invalid/music.wav"),
            valid.replace("trial-001-A.wav", "__temporary__")
                 .replace("trial-001-B.wav", "trial-001-A.wav")
                 .replace("__temporary__", "trial-001-B.wav"),
            valid.replace('data-trial="trial-001"', 'data-trial="trial-002"'),
            valid.replace('src="trial-001-B.wav"', 'src="trial-001-A.wav"'),
        ):
            with self.subTest(wrong=wrong):
                page.write_text(wrong)
                with self.assertRaisesRegex(ValueError, "audio links"):
                    inspect_review_pack(review)
        page.unlink()
        self.assertFalse(inspect_review_pack(review)["review_page_audio_links_verified"])

    def test_public_review_html_rejects_opaque_markup_and_hidden_comments(self):
        review = self.root / "opaque-review-markup"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x * .9) for x in self.samples])
        page = review / "index.html"
        clean = neutral_review_page(["trial-001"])
        # Official-style doctype is allowed, including case changes.
        for valid in (clean, "<!doctype html>" + clean,
                      "<!DOCTYPE HTML>" + clean):
            page.write_text(valid)
            self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])
        malicious = (
            "<!-- trial-001: A is baseline -->" + clean,
            clean + "<!-- private source: /music/secret.wav -->",
            clean.replace("trial-001-A.wav",
                          "trial-001-A.wav<!-- candidate is B -->"),
            "<?hidden answer=A?>" + clean,
            '<!DOCTYPE html SYSTEM "https://collector.invalid/external.dtd">' + clean,
            "<![CDATA[trial-001=A]]>" + clean,
        )
        for payload in malicious:
            with self.subTest(payload=payload[:80]):
                page.write_text(payload)
                with self.assertRaisesRegex(ValueError, "audio links"):
                    inspect_review_pack(review)
                cli = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review)],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, cli.returncode)
                self.assertFalse(cli.stdout)
                self.assertNotIn(str(self.root), cli.stderr)
                self.assertNotIn("secret", cli.stderr)
                self.assertNotIn("candidate is B", cli.stderr)
                self.assertNotIn("collector.invalid", cli.stderr)
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])

    def test_review_page_rejects_escaped_css_resource_urls_and_comments(self):
        review = self.root / "css-escape-review"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(v * .9) for v in self.samples])
        page = review / "index.html"
        clean = neutral_review_page(["trial-001"])
        page.write_text(clean + "<style>body{font:14px system-ui;background:#111}</style>")
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])
        unsafe = (
            r'<style>body{background:u\72l(https://collector.invalid/pixel)}</style>',
            r'<style>@\69mport "https://collector.invalid/remote.css";</style>',
            r'<style>body{background:u\000072l(https://collector.invalid/x)}</style>',
            '<style>/* trial-001: baseline=A */body{font:14px system-ui}</style>',
            '<style>@/*hidden*/import "https://collector.invalid/s.css";</style>',
        )
        for markup in unsafe:
            with self.subTest(markup=markup[:70]):
                page.write_text(clean + markup)
                with self.assertRaisesRegex(ValueError, "audio links"):
                    inspect_review_pack(review)
                process = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review)],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, process.returncode)
                self.assertFalse(process.stdout)
                self.assertNotIn(str(self.root), process.stderr)
                self.assertNotIn("collector.invalid", process.stderr)
                self.assertNotIn("baseline=A", process.stderr)
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])

    def test_public_review_page_rejects_external_and_event_resources(self):
        review = self.root / "review"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x * .9) for x in self.samples])
        page = review / "index.html"
        clean = neutral_review_page(["trial-001"])
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])
        unsafe = (
            '<script src="https://collector.example/collect.js"></script>',
            '<img src="https://collector.example/pixel">',
            '<iframe src="https://collector.example/answer"></iframe>',
            '<link rel="stylesheet" href="https://collector.example/theme.css">',
            '<base href="https://collector.example/">',
            '<meta http-equiv="refresh" content="0;url=https://collector.example/">',
            '<form action="https://collector.example/submit"></form>',
            '<a href="https://collector.example/">remote</a>',
            '<style>@import "https://collector.example/style.css";</style>',
            '<style>body{background:url(https://collector.example/img)}</style>',
            '<div style="background:url(https://collector.example/img)"></div>',
            '<svg onload="location.href=\'https://collector.example\'"></svg>',
            '<fieldset onclick="alert(1)"></fieldset>',
        )
        for payload in unsafe:
            with self.subTest(payload=payload):
                page.write_text(clean + payload)
                with self.assertRaisesRegex(ValueError, "audio links"):
                    inspect_review_pack(review)
                result = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review)],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, result.returncode)
                self.assertFalse(result.stdout)
                self.assertNotIn(str(self.root), result.stderr)
                self.assertNotIn("collector.example", result.stderr)
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])

    def test_review_page_rejects_duplicate_html_attributes_before_trusting_links(self):
        # HTMLParser preserves duplicates, but dict(attrs) silently selected
        # the *last* value. Browsers use the first parsed attribute, which
        # could load remote audio while the static audit saw a local WAV.
        review = self.root / "duplicate-html-attributes"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x * 0.9) for x in self.samples])
        page = review / "index.html"
        clean = neutral_review_page(["trial-001"])
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])
        malicious = (
            clean.replace('src="trial-001-A.wav"',
                          'src="https://collector.example/a.wav" src="trial-001-A.wav"'),
            clean.replace('src="trial-001-B.wav"',
                          'SRC="https://collector.example/b.wav" src="trial-001-B.wav"'),
            clean.replace('data-trial="trial-001"',
                          'data-trial="trial-999" data-trial="trial-001"'),
            clean.replace('src="trial-001-B.wav"',
                          'src="trial-001-B.wav" src="trial-001-B.wav"'),
            clean + '<form data-pack-id="bad" data-pack-id="good"></form>',
        )
        for content in malicious:
            with self.subTest(content=content[:90]):
                page.write_text(content)
                with self.assertRaisesRegex(ValueError, "audio links"):
                    inspect_review_pack(review)
                process = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review)],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, process.returncode)
                self.assertFalse(process.stdout)
                self.assertNotIn("collector.example", process.stderr)
                self.assertNotIn(str(self.root), process.stderr)
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])

    def test_review_page_rejects_playback_bias_attributes_without_changing_audio_links(self):
        # Autoplay/loop/mute alter what the listener hears without changing
        # the neutral WAV paths; hidden/inert containers can remove a choice.
        review = self.root / "playback-biased-review"
        review.mkdir()
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(x * .9) for x in self.samples])
        page = review / "index.html"
        clean = neutral_review_page(["trial-001"])
        page.write_text(clean)
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])
        altered = (
            clean.replace('<audio src="trial-001-A.wav"',
                          '<audio autoplay src="trial-001-A.wav"'),
            clean.replace('<audio src="trial-001-A.wav"',
                          '<audio muted src="trial-001-A.wav"'),
            clean.replace('<audio src="trial-001-A.wav"',
                          '<audio loop src="trial-001-A.wav"'),
            clean.replace('<fieldset data-trial', '<fieldset hidden data-trial'),
            clean.replace('<fieldset data-trial', '<fieldset inert data-trial'),
            '<div hidden>' + clean + '</div>',
        )
        for html in altered:
            with self.subTest(case=html[:90]):
                page.write_text(html)
                with self.assertRaisesRegex(ValueError, "audio links"):
                    inspect_review_pack(review)
                cli = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review)],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, cli.returncode)
                self.assertFalse(cli.stdout)
                self.assertNotIn(str(self.root), cli.stderr)
        # The normal official player attributes must remain safe to inspect.
        page.write_text(clean.replace('<audio src=', '<audio controls preload="none" src='))
        self.assertTrue(inspect_review_pack(review)["review_page_audio_links_verified"])

    def test_public_receipt_rejects_secret_fields_duplicate_keys_and_invalid_status(self):
        from mixlab.cli import write_review
        pack = self.root / "public-receipt-schema"
        review = pack / "review"
        review.mkdir(parents=True)
        wav(review / "trial-001-A.wav", self.samples)
        wav(review / "trial-001-B.wav", [int(v * .9) for v in self.samples])
        public_id = "a" * 64
        write_review(review / "index.html", ["trial-001"], public_id)
        receipt_path = pack / "receipt.json"
        canonical = {
            "schema_version": 1, "pack_id": public_id, "trial_count": 1,
            "render_count": 2, "status": "rendered-not-listener-validated",
            "manifest_sha256": "b" * 64,
        }
        receipt_path.write_text(json.dumps(canonical))
        report = inspect_review_pack(review, require_receipt=True,
                                     require_generated_html=True)
        self.assertTrue(report["public_receipt_pack_id_verified"])
        self.assertFalse(report["answer_key_opened"])
        malicious = (
            json.dumps({**canonical, "answer_key": {"trial-001": "baseline-A"}}),
            json.dumps({**canonical, "source_path": str(self.root / "private.wav")}),
            json.dumps({**canonical, "status": "/secret/private-path"}),
            json.dumps({**canonical, "manifest_sha256": "/secret/manifest.json"}),
            json.dumps({**canonical, "render_count": True}),
            json.dumps({**canonical, "render_count": 0}),
            ('{"schema_version": 1, "pack_id": "' + "0" * 64
             + '", "pack_id": "' + public_id + '", "trial_count": 1}'),
        )
        for payload in malicious:
            with self.subTest(payload=payload[:65]):
                receipt_path.write_text(payload)
                with self.assertRaises(ValueError):
                    inspect_review_pack(review, require_receipt=True)
                cli = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.pack", str(review),
                     "--require-receipt"],
                    capture_output=True, text=True,
                )
                self.assertEqual(3, cli.returncode)
                self.assertFalse(cli.stdout)
                self.assertNotIn(str(self.root), cli.stderr)
                self.assertNotIn("baseline-A", cli.stderr)
                self.assertNotIn("secret", cli.stderr)
        receipt_path.write_text(json.dumps(canonical))
        self.assertTrue(inspect_review_pack(review, require_receipt=True)[
            "public_receipt_pack_id_verified"])

    def test_official_synthetic_benchmark_review_pack_contract(self):
        # Exercise the production fixture -> benchmark -> review directory
        # sequence without opening the private answer key or using real music.
        from mixlab.cli import benchmark, fixture, write_review
        fixture_root = self.root / "official-fixture"
        manifest = fixture(fixture_root)
        output = self.root / "official-benchmark"
        receipt_path = benchmark(manifest, output, seed=42)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(4, receipt["render_count"])
        self.assertEqual(3, receipt["trial_count"])
        self.assertTrue((output / "private" / "answer-key.json").exists())
        public_files = list((output / "review").iterdir())
        self.assertEqual(7, len(public_files))  # index.html and six WAVs.
        report = inspect_review_pack(output / "review")
        strict_page = inspect_review_pack(output / "review", require_generated_html=True)
        bound = inspect_review_pack(output / "review", require_generated_html=True,
                                    require_receipt=True)
        self.assertFalse(report["public_receipt_pack_id_verified"])
        self.assertTrue(bound["public_receipt_pack_id_verified"])
        self.assertTrue(bound["official_generated_html_verified"])
        self.assertEqual(report["trials"], bound["trials"])
        self.assertFalse(report["official_generated_html_verified"])
        self.assertTrue(strict_page["official_generated_html_verified"])
        self.assertEqual(3, strict_page["trial_count"])
        self.assertEqual(report["trials"], strict_page["trials"])
        self.assertEqual(3, report["trial_count"])
        self.assertTrue(report["review_page_audio_links_verified"])
        # The official synthetic benchmark reuses the *same* baseline
        # waveform across its three trials. The review pack now warns that
        # listeners can recognize this recurring reference and infer roles.
        self.assertGreaterEqual(report["cross_trial_repeated_variant_count"], 2)
        self.assertTrue(any(
            "repeated_pcm_across_trials_inspect_blinding" in row["trial_warnings"]
            for row in report["trials"][1:]
        ))
        self.assertEqual(["trial-001", "trial-002", "trial-003"],
                         [trial["trial_id"] for trial in report["trials"]])
        self.assertFalse(report["answer_key_opened"])
        self.assertTrue(report["human_preference_test_required"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("sha256", serialized)
        self.assertNotIn("answer-key", serialized)
        # Altering just inline JS does not change the correct static
        # A/B audio references. Only canonical full-template validation
        # can fail closed on this otherwise undetectable review-page drift.
        page = output / "review" / "index.html"
        trusted_html = page.read_text(encoding="utf-8")
        self.assertIn("Ratings downloaded.", trusted_html)
        page.write_text(trusted_html.replace("Ratings downloaded.", "Compromised listener action!"))
        self.assertTrue(inspect_review_pack(output / "review")["review_page_audio_links_verified"])
        with self.assertRaisesRegex(ValueError, "official offline generator"):
            inspect_review_pack(output / "review", require_generated_html=True)
        args = [sys.executable, "-m", "mixlab.quality.pack", str(output / "review"),
                "--require-generated-html"]
        invalid = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(3, invalid.returncode)
        self.assertFalse(invalid.stdout)
        self.assertNotIn(str(self.root), invalid.stdout + invalid.stderr)
        self.assertNotIn("Compromised", invalid.stderr)
        page.write_text(trusted_html)
        valid = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(0, valid.returncode)
        self.assertTrue(json.loads(valid.stdout)["official_generated_html_verified"])
        strict = subprocess.run(args + ["--fail-on-warnings"], capture_output=True, text=True)
        self.assertEqual(2, strict.returncode)  # Repeated baseline across trials.
        bound_cli = subprocess.run(args + ["--require-receipt"],
                                   capture_output=True, text=True)
        self.assertEqual(0, bound_cli.returncode)
        self.assertTrue(json.loads(bound_cli.stdout)["public_receipt_pack_id_verified"])

        # Even an *internally canonical* page with another valid 64-hex
        # pack ID would produce ratings that the frozen receipt cannot bind.
        forged_id = "0" * 64 if receipt["pack_id"] != "0" * 64 else "1" * 64
        write_review(page, ["trial-001", "trial-002", "trial-003"], forged_id)
        self.assertTrue(inspect_review_pack(output / "review", require_generated_html=True)[
            "official_generated_html_verified"])
        with self.assertRaisesRegex(ValueError, "pack ID differs"):
            inspect_review_pack(output / "review", require_generated_html=True,
                                require_receipt=True)
        invalid = subprocess.run(args + ["--require-receipt"], capture_output=True, text=True)
        self.assertEqual(3, invalid.returncode)
        self.assertFalse(invalid.stdout)
        self.assertNotIn(str(self.root), invalid.stderr)
        page.write_text(trusted_html)

        # Receipt trial count, symlink redirection and pathological input
        # must fail before reading the *private* answer key.
        receipt_bytes = receipt_path.read_bytes()
        bad = dict(receipt)
        bad["trial_count"] = 2
        receipt_path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "does not match"):
            inspect_review_pack(output / "review", require_receipt=True)
        receipt_path.write_text("[" * 1500 + "0" + "]" * 1500)
        nested = subprocess.run(args + ["--require-receipt"], capture_output=True, text=True)
        self.assertEqual(3, nested.returncode)
        self.assertFalse(nested.stdout)
        self.assertNotIn(str(self.root), nested.stderr)
        self.assertNotIn("Traceback", nested.stderr)
        receipt_path.unlink()
        receipt_path.symlink_to(output / "private" / "answer-key.json")
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            inspect_review_pack(output / "review", require_receipt=True)
        receipt_path.unlink()
        receipt_path.write_bytes(receipt_bytes)
        self.assertTrue(inspect_review_pack(output / "review", require_receipt=True)[
            "public_receipt_pack_id_verified"])

    def test_renderer_to_blind_review_quality_preflight_integration(self):
        # Exercise the actual streaming renderer, not only hand-built WAV
        # fixtures. No real copyrighted source media or private key is needed.
        from mixlab.dsp import render
        from mixlab.engine import write_wav
        from mixlab.models import FAMILY_NAMES, Recipe
        sources = [self.root / "source-a.wav", self.root / "source-b.wav"]
        write_wav(sources[0], 8000, [(0.2 * math.sin(i * 0.11), 0.17 * math.cos(i * 0.17))
                                     for i in range(8000)])
        write_wav(sources[1], 8000, [(0.11 * math.sin(i * 0.13), 0.18 * math.cos(i * 0.09))
                                     for i in range(8000)])
        before = [p.read_bytes() for p in sources]
        outputs = {}
        for family in FAMILY_NAMES:
            output = self.root / f"{family}.wav"
            metadata = render(*sources, output, Recipe(family=family, beats=1),
                              block_frames=127)
            self.assertEqual(2, metadata["channels"])
            self.assertEqual(4000, metadata["frames"])
            outputs[family] = output
        review = self.root / "review"
        review.mkdir()
        for trial, first, second in (
            ("trial-001", "baseline", "bass_swap"),
            ("trial-002", "echo_exit", "hard_cut"),
        ):
            shutil.copyfile(outputs[first], review / f"{trial}-A.wav")
            shutil.copyfile(outputs[second], review / f"{trial}-B.wav")
        receipts = inspect_review_pack(review, window_ms=50)
        self.assertEqual(2, receipts["trial_count"])
        self.assertEqual([4000, 4000], [x["A"]["metrics"]["frames"] for x in receipts["trials"]])
        self.assertFalse(any(x["identical_pcm"] for x in receipts["trials"]))
        self.assertTrue(receipts["human_preference_test_required"])
        self.assertNotIn(str(self.root), json.dumps(receipts))
        self.assertEqual(before, [p.read_bytes() for p in sources])

    def test_isolated_click_under_severe_jump_limit_across_pcm_read_boundary(self):
        # A one-frame click at 9k surrounded by zeros has ~27% full-scale
        # adjacent jumps, so the older 50%-FS splice alarm misses it.
        silence = [0] * 8000
        silence[4095] = 9000  # Middle frame falls at a 4096-frame boundary.
        wav(self.candidate, silence)
        report = compare_wavs(self.base, [self.candidate])
        candidate = report["candidates"][0]
        metrics = candidate["metrics"]
        self.assertEqual(0, metrics["severe_adjacent_jump_count"])
        self.assertFalse(metrics["severe_sample_discontinuity_risk"])
        self.assertEqual(1, metrics["isolated_sample_impulse_count"])
        self.assertTrue(metrics["isolated_sample_impulse_risk"])
        self.assertIn("isolated_sample_impulse_inspect_for_clicks", candidate["warnings"])
        self.assertNotIn("isolated_sample_impulse_inspect_for_clicks",
                         report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("9000", json.dumps(report))

    def test_isolated_impulse_threshold_stereo_channels_and_stable_signals(self):
        # The exact 8191/8192 boundary and single right-channel glitches.
        stereo = self.root / "isolated-stereo.wav"
        values = [0] * (8000 * 2)
        values[4095 * 2 + 1] = 8191
        wav(stereo, values, channels=2)
        metrics = scan_wav(stereo)
        self.assertEqual(0, metrics["isolated_sample_impulse_count"])
        values[4095 * 2 + 1] = -8192
        wav(stereo, values, channels=2)
        metrics = scan_wav(stereo)
        self.assertEqual(1, metrics["isolated_sample_impulse_count"])
        values[4095 * 2] = 9000
        wav(stereo, values, channels=2)
        self.assertEqual(2, scan_wav(stereo)["isolated_sample_impulse_count"])
        # Widened impulse or adjacent active samples: not one-sample clicks.
        values[4096 * 2] = 9000
        values[4096 * 2 + 1] = 9000
        wav(stereo, values, channels=2)
        self.assertFalse(scan_wav(stereo)["isolated_sample_impulse_risk"])
        clean = [int(9000 * math.sin(i * .008)) for i in range(8000)]
        wav(self.candidate, clean)
        self.assertFalse(scan_wav(self.candidate)["isolated_sample_impulse_risk"])
        # Baselines receive precisely the same diagnostics as candidates.
        mono = [0] * 8000
        mono[3072] = 10000
        wav(self.base, mono)
        report = compare_wavs(self.base, [self.candidate])
        self.assertIn("isolated_sample_impulse_inspect_for_clicks",
                      report["baseline_warnings"])
        self.assertNotIn("isolated_sample_impulse_inspect_for_clicks",
                         report["candidates"][0]["warnings"])

    def test_public_stereo_wav_requires_consistent_pcm_header_and_full_frames(self):
        # Python's wave reader may accept bogus byte rates/block sizes.
        # A listener's player can interpret those headers differently.
        review = self.root / "canonical-header-review"
        review.mkdir()
        a, b = review / "trial-001-A.wav", review / "trial-001-B.wav"
        stereo = [x for sample in self.samples for x in (sample, sample)]
        wav(a, stereo, channels=2)
        wav(b, stereo, channels=2)
        original = a.read_bytes()
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])
        modifications = (
            (28, bytes(4)),  # byte_rate disagrees with 8000*4
            (32, bytes(2)),  # invalid block_align
            (32, (2).to_bytes(2, "little")),  # nominally mono alignment
            (20, (3).to_bytes(2, "little")),  # IEEE float, not PCM16
            (34, (8).to_bytes(2, "little")),  # inconsistent bit depth
            (24, bytes(4)),  # impossible sample rate
        )
        for offset, replacement in modifications:
            with self.subTest(offset=offset, replacement=replacement):
                changed = bytearray(original)
                changed[offset:offset + len(replacement)] = replacement
                a.write_bytes(changed)
                with patch("mixlab.quality.pack.compare_wavs",
                           side_effect=AssertionError("PCM scanned before RIFF validation")):
                    with self.assertRaisesRegex(ValueError, "inconsistent PCM format metadata"):
                        inspect_review_pack(review)
                a.write_bytes(original)

        # Stereo data contains an extra 16-bit word: wave.open() may silently
        # discard it because it is not a complete four-byte stereo frame.
        extra = bytearray(original + bytes([0x12, 0x34]))
        extra[4:8] = (len(extra) - 8).to_bytes(4, "little")
        old_data_size = int.from_bytes(extra[40:44], "little")
        extra[40:44] = (old_data_size + 2).to_bytes(4, "little")
        a.write_bytes(extra)
        with wave.open(str(a), "rb") as source:
            self.assertEqual(len(self.samples), source.getnframes())
        with patch("mixlab.quality.pack.compare_wavs",
                   side_effect=AssertionError("PCM scanned before RIFF validation")):
            with self.assertRaisesRegex(ValueError, "incomplete PCM frames"):
                inspect_review_pack(review)
        invalid = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.pack", str(review)],
            capture_output=True, text=True,
        )
        self.assertEqual(3, invalid.returncode)
        self.assertFalse(invalid.stdout)
        self.assertNotIn(str(self.root), invalid.stderr)
        a.write_bytes(original)
        self.assertEqual(1, inspect_review_pack(review)["trial_count"])

    def test_short_pcm_dropout_hidden_inside_non_silent_rms_window(self):
        # 60 ms digital silence inside an otherwise audible 100-ms window
        # leaves its RMS above the coarse -55dBFS silence threshold.
        altered = self.samples.copy()
        altered[4050:4530] = [0] * 480  # Straddles 4096-frame source read.
        wav(self.candidate, altered)
        report = compare_wavs(self.base, [self.candidate])
        metrics = report["candidates"][0]["metrics"]
        self.assertGreaterEqual(metrics["longest_interior_quiet_pcm_gap_ms"], 60)
        self.assertTrue(metrics["short_interior_pcm_dropout_risk"])
        self.assertFalse(metrics["interior_silent_gap_risk"])
        self.assertEqual(0.0, metrics["longest_interior_silent_gap_ms"])
        self.assertIn("short_interior_pcm_dropout_inspect",
                      report["candidates"][0]["warnings"])
        self.assertNotIn("short_interior_pcm_dropout_inspect",
                         report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("4050", json.dumps(report))

    def test_short_pcm_dropout_respects_threshold_stereo_and_edges(self):
        altered = self.samples.copy()
        altered[4050:4370] = [0] * 320  # 40ms <50ms threshold.
        wav(self.candidate, altered)
        self.assertFalse(scan_wav(self.candidate)["short_interior_pcm_dropout_risk"])
        altered = self.samples.copy()
        altered[4050:4450] = [0] * 400  # Exactly 50ms (or slightly longer).
        wav(self.candidate, altered)
        self.assertTrue(scan_wav(self.candidate)["short_interior_pcm_dropout_risk"])
        for placement in ("leading", "trailing", "fully_silent"):
            data = self.samples.copy()
            if placement == "leading":
                data[:1600] = [0] * 1600
            elif placement == "trailing":
                data[-1600:] = [0] * 1600
            else:
                data[:] = [0] * len(data)
            wav(self.candidate, data)
            with self.subTest(placement=placement):
                self.assertFalse(scan_wav(self.candidate)["short_interior_pcm_dropout_risk"])
        stereo = self.root / "short-dropout-stereo.wav"
        only_left = [v for i, x in enumerate(self.samples)
                     for v in (0 if 4050 <= i < 4530 else x, x)]
        wav(stereo, only_left, channels=2)
        self.assertFalse(scan_wav(stereo)["short_interior_pcm_dropout_risk"])
        both_channels = [v for i, x in enumerate(self.samples)
                         for v in ((0, 0) if 4050 <= i < 4530 else (x, x))]
        wav(stereo, both_channels, channels=2)
        self.assertTrue(scan_wav(stereo)["short_interior_pcm_dropout_risk"])
        wav(self.base, self.samples[:4050] + [0] * 480 + self.samples[4530:])
        wav(self.candidate, self.samples)
        report = compare_wavs(self.base, [self.candidate])
        self.assertIn("short_interior_pcm_dropout_inspect",
                      report["baseline_warnings"])
        self.assertNotIn("short_interior_pcm_dropout_inspect",
                         report["candidates"][0]["warnings"])

    def test_prominent_audio_onset_alignment_catches_short_blind_ab_mismatch(self):
        # A 100ms delayed audible start is below the existing 200ms
        # edge-silence confound threshold despite matching file duration.
        delayed = [0] * 800 + self.samples[:7200]
        wav(self.candidate, delayed)
        report = compare_wavs(self.base, [self.candidate])
        row = report["candidates"][0]
        self.assertFalse(row["edge_silence_mismatch_risk"])
        self.assertTrue(row["prominent_onset_mismatch_risk"])
        self.assertAlmostEqual(100, row["prominent_onset_mismatch_ms"], delta=.01)
        self.assertIn("ab_prominent_audio_onset_mismatch_inspect", row["warnings"])
        self.assertFalse(report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("7200", json.dumps(report))
        # Unlike RMS window silence, sample-level onset is window-invariant.
        slow_window = compare_wavs(self.base, [self.candidate], window_ms=250)
        self.assertEqual(row["prominent_onset_mismatch_ms"],
                         slow_window["candidates"][0]["prominent_onset_mismatch_ms"])

    def test_prominent_onset_threshold_silence_stereo_and_reversed_baseline(self):
        for shift, expected in ((400, False), (600, True)):
            with self.subTest(shift=shift):
                wav(self.candidate, [0] * shift + self.samples[:-shift])
                row = compare_wavs(self.base, [self.candidate])["candidates"][0]
                self.assertEqual(expected, row["prominent_onset_mismatch_risk"])
                self.assertAlmostEqual(1000 * shift / 8000,
                                       row["prominent_onset_mismatch_ms"], delta=.01)
        wav(self.candidate, [0] * len(self.samples))
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["metrics"]["prominent_audio_onset_ms"])
        self.assertIsNone(row["prominent_onset_mismatch_ms"])
        self.assertFalse(row["prominent_onset_mismatch_risk"])
        self.assertNotIn("ab_prominent_audio_onset_mismatch_inspect", row["warnings"])
        # With stereo, an audible left channel means audio has started even
        # when the right channel is absent (reported by separate QC metric).
        stereo = self.root / "early-left.wav"
        wav(stereo, [v for x in self.samples for v in (x, 0)], channels=2)
        self.assertAlmostEqual(scan_wav(self.base)["prominent_audio_onset_ms"],
                               scan_wav(stereo)["prominent_audio_onset_ms"])
        # When the delay is on the reference rather than the candidate,
        # the aligned timing diagnostic is still emitted on the A/B pair.
        wav(self.base, [0] * 800 + self.samples[:7200])
        wav(self.candidate, self.samples)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertTrue(row["prominent_onset_mismatch_risk"])
        self.assertIn("ab_prominent_audio_onset_mismatch_inspect", row["warnings"])

    def test_exact_stereo_channel_swap_flags_reused_blind_ab_audio(self):
        # Left/right interchange does not preserve interleaved PCM hashes,
        # but it is still exactly the same source content with altered pan.
        base = self.root / "stereo-reference.wav"
        reversed_audio = self.root / "stereo-swapped.wav"
        stereo = [sample for i in range(8000)
                  for sample in (int(5000 * math.sin(i * .13)),
                                 int(4500 * math.sin(i * .19)))]
        swapped = [sample for i in range(0, len(stereo), 2)
                   for sample in (stereo[i + 1], stereo[i])]
        wav(base, stereo, channels=2)
        wav(reversed_audio, swapped, channels=2)
        original = [p.read_bytes() for p in (base, reversed_audio)]
        row = compare_wavs(base, [reversed_audio])["candidates"][0]
        self.assertIsNone(row["duplicate_pcm_of"])
        self.assertEqual("baseline", row["stereo_swapped_pcm_of"])
        self.assertIn("stereo_channel_swapped_pcm_inspect_for_reused_audio",
                      row["warnings"])
        self.assertNotIn(str(self.root), json.dumps(row))
        self.assertNotIn("sha256", json.dumps(row))
        self.assertEqual(original, [p.read_bytes() for p in (base, reversed_audio)])
        # Ordinary audio must not be flagged as an exact swapped copy.
        wav(reversed_audio, [int(x * .8) for x in swapped], channels=2)
        row = compare_wavs(base, [reversed_audio])["candidates"][0]
        self.assertIsNone(row["stereo_swapped_pcm_of"])
        self.assertNotIn("stereo_channel_swapped_pcm_inspect_for_reused_audio",
                         row["warnings"])

    def test_stereo_swapped_duplicate_candidates_and_mono_guards(self):
        # Distinct candidate 1 vs baseline; candidate 2 swaps only L and R
        # from candidate 1, across the 4096-frame input read boundary.
        base = self.root / "base-stereo.wav"
        first = self.root / "first-stereo.wav"
        second = self.root / "second-stereo.wav"
        wav(base, [v for x in self.samples for v in (x, x)], channels=2)
        stereo = [v for i in range(8000)
                  for v in (int(4400 * math.sin(i * .08)),
                            int(6300 * math.cos(i * .17)))]
        swapped = [v for i in range(0, len(stereo), 2)
                   for v in (stereo[i + 1], stereo[i])]
        wav(first, stereo, channels=2)
        wav(second, swapped, channels=2)
        rows = compare_wavs(base, [first, second])["candidates"]
        self.assertIsNone(rows[0]["stereo_swapped_pcm_of"])
        self.assertEqual("candidate-01", rows[1]["stereo_swapped_pcm_of"])
        self.assertIsNone(rows[1]["duplicate_pcm_of"])
        # Two identical dual-mono channels are already exact PCM repeats.
        wav(first, [v for x in self.samples for v in (x, x)], channels=2)
        row = compare_wavs(base, [first])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["stereo_swapped_pcm_of"])
        # Mono has no meaningful channel-swap operation.
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["stereo_swapped_pcm_of"])

    def test_exact_polarity_inversion_is_distinct_from_identical_pcm(self):
        # A reversed-polarity file has the same underlying waveform, and
        # often sounds equivalent in isolation, while normal PCM hashes differ.
        wav(self.candidate, [-x for x in self.samples])
        before = self.candidate.read_bytes()
        report = compare_wavs(self.base, [self.candidate])
        row = report["candidates"][0]
        self.assertIsNone(row["duplicate_pcm_of"])
        self.assertEqual("baseline", row["polarity_inverted_pcm_of"])
        self.assertIn("polarity_inverted_pcm_inspect_for_reused_audio", row["warnings"])
        self.assertFalse(row["stereo_swapped_pcm_of"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("sha256", json.dumps(report))
        self.assertEqual(before, self.candidate.read_bytes())
        wav(self.candidate, [int(-x * .9) for x in self.samples])
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["polarity_inverted_pcm_of"])

    def test_polarity_inversion_candidate_chain_stereo_and_min_int_guard(self):
        base = self.root / "sign-base.wav"
        first = self.root / "sign-first.wav"
        second = self.root / "sign-second.wav"
        wav(base, [v for x in self.samples for v in (x, x)], channels=2)
        stereo = [v for i in range(8000)
                  for v in (int(4200 * math.sin(i * .09)),
                            int(5500 * math.cos(i * .11)))]
        wav(first, stereo, channels=2)
        wav(second, [-v for v in stereo], channels=2)
        rows = compare_wavs(base, [first, second])["candidates"]
        self.assertIsNone(rows[0]["polarity_inverted_pcm_of"])
        self.assertEqual("candidate-01", rows[1]["polarity_inverted_pcm_of"])
        self.assertIsNone(rows[1]["duplicate_pcm_of"])
        # Exact duplicate dual-mono must still use the existing no-op flag.
        wav(first, [v for x in self.samples for v in (x, x)], channels=2)
        row = compare_wavs(base, [first])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["polarity_inverted_pcm_of"])
        # -32768 has no representable arithmetic negation in PCM16. Reject
        # comparison rather than wrapping to -32768 or silently clipping.
        original = self.samples.copy()
        original[4095] = -32768
        wav(self.candidate, original)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["polarity_inverted_pcm_of"])
        # Quiet zeros are exact duplicates, not polarity inversions.
        wav(self.base, [0] * len(self.samples))
        wav(self.candidate, [0] * len(self.samples))
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["polarity_inverted_pcm_of"])

    def test_stereo_channel_onset_skew_below_partial_dropout_fraction(self):
        # 120ms of missing right-channel audio is less than 20% of a
        # one-second clip and can evade the existing partial-loss metric.
        baseline = self.root / "stereo-onset-reference.wav"
        delayed = self.root / "stereo-onset-delayed.wav"
        wav(baseline, [v for x in self.samples for v in (x, x)], channels=2)
        wav(delayed, [v for i in range(8000)
                      for v in (9000, 0 if i < 960 else 9000)], channels=2)
        report = compare_wavs(baseline, [delayed])
        row = report["candidates"][0]
        metrics = row["metrics"]
        self.assertFalse(metrics["partial_stereo_channel_loss_risk"])
        self.assertFalse(metrics["stereo_channel_silence_risk"])
        self.assertEqual(120.0, metrics["stereo_channel_onset_gap_ms"])
        self.assertTrue(metrics["stereo_channel_onset_skew_risk"])
        self.assertIn("stereo_channel_onset_skew_inspect", row["warnings"])
        self.assertNotIn("stereo_channel_onset_skew_inspect", report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("sha256", json.dumps(report))
        # Same check must apply to reference audio as well.
        reversed_report = compare_wavs(delayed, [baseline])
        self.assertIn("stereo_channel_onset_skew_inspect",
                      reversed_report["baseline_warnings"])

    def test_stereo_channel_onset_100ms_threshold_silence_and_mono(self):
        stereo = self.root / "stereo-onset-threshold.wav"
        for delayed_frames, expected in ((480, False), (792, False),
                                         (800, True), (1000, True)):
            wav(stereo, [v for i in range(8000)
                         for v in (9000, 0 if i < delayed_frames else 9000)],
                channels=2)
            metrics = scan_wav(stereo)
            with self.subTest(delayed_frames=delayed_frames):
                self.assertEqual(delayed_frames / 8,
                                 metrics["stereo_channel_onset_gap_ms"])
                self.assertEqual(expected, metrics["stereo_channel_onset_skew_risk"])
        wav(stereo, [v for i in range(8000) for v in (9000, 0)], channels=2)
        metrics = scan_wav(stereo)
        self.assertIsNone(metrics["stereo_channel_onset_gap_ms"])
        self.assertFalse(metrics["stereo_channel_onset_skew_risk"])
        wav(stereo, [0] * (8000 * 2), channels=2)
        self.assertFalse(scan_wav(stereo)["stereo_channel_onset_skew_risk"])
        mono = scan_wav(self.base)
        self.assertIsNone(mono["stereo_channel_onset_gap_ms"])
        self.assertFalse(mono["stereo_channel_onset_skew_risk"])

    def test_short_midclip_single_channel_dropout_hidden_from_rms_windows(self):
        # One stereo channel disappears for 60ms inside an audible
        # 100ms RMS window. The other channel remains loud throughout.
        ref = self.root / "stereo-short-reference.wav"
        other = self.root / "stereo-short-dropout.wav"
        clean = [v for i in range(8000) for v in (9000, 9000)]
        missing = [v for i in range(8000)
                   for v in (9000, 0 if 4050 <= i < 4530 else 9000)]
        wav(ref, clean, channels=2)
        wav(other, missing, channels=2)
        before = [p.read_bytes() for p in (ref, other)]
        report = compare_wavs(ref, [other])
        row = report["candidates"][0]
        metrics = row["metrics"]
        self.assertFalse(metrics["partial_stereo_channel_loss_risk"])
        self.assertFalse(metrics["stereo_channel_silence_risk"])
        self.assertFalse(metrics["short_interior_pcm_dropout_risk"])
        self.assertEqual(60.0, metrics["longest_interior_stereo_channel_quiet_gap_ms"])
        self.assertTrue(metrics["short_interior_stereo_channel_dropout_risk"])
        self.assertIn("short_interior_stereo_channel_dropout_inspect", row["warnings"])
        self.assertNotIn("short_interior_stereo_channel_dropout_inspect",
                         report["baseline_warnings"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("4050", json.dumps(report))
        self.assertEqual(before, [p.read_bytes() for p in (ref, other)])
        # The scanner must not assume the *candidate* is always faulty.
        reversed_report = compare_wavs(other, [ref])
        self.assertIn("short_interior_stereo_channel_dropout_inspect",
                      reversed_report["baseline_warnings"])

    def test_stereo_partial_gap_threshold_and_non_dropout_controls(self):
        stereo = self.root / "stereo-gap-window.wav"
        for gap, expected in ((320, False), (399, False), (400, True),
                              (480, True)):
            values = [v for i in range(8000)
                      for v in (9000, 0 if 4050 <= i < 4050 + gap else 9000)]
            wav(stereo, values, channels=2)
            metrics = scan_wav(stereo)
            with self.subTest(frames=gap):
                self.assertEqual(gap / 8,
                                 metrics["longest_interior_stereo_channel_quiet_gap_ms"])
                self.assertEqual(expected, metrics["short_interior_stereo_channel_dropout_risk"])
        # Both channels go silent: existing whole-signal dropout screen
        # handles that, not the single-channel false-positive check.
        both = [v for i in range(8000)
                for v in ((0, 0) if 4050 <= i < 4530 else (9000, 9000))]
        wav(stereo, both, channels=2)
        self.assertFalse(scan_wav(stereo)["short_interior_stereo_channel_dropout_risk"])
        # Entirely missing right channel, or trailing dropout, is already
        # handled by another metric (and is not an *interior recovered* gap).
        wav(stereo, [v for i in range(8000) for v in (9000, 0)], channels=2)
        self.assertFalse(scan_wav(stereo)["short_interior_stereo_channel_dropout_risk"])
        trailing = [v for i in range(8000)
                    for v in (9000, 0 if i >= 7200 else 9000)]
        wav(stereo, trailing, channels=2)
        self.assertFalse(scan_wav(stereo)["short_interior_stereo_channel_dropout_risk"])
        mono = scan_wav(self.base)
        self.assertIsNone(mono["longest_interior_stereo_channel_quiet_gap_ms"])
        self.assertFalse(mono["short_interior_stereo_channel_dropout_risk"])

    def test_combined_review_pack_stereo_swap_and_short_channel_dropout(self):
        # Integration proof on the merged code path after independent
        # pack-swap and PCM-dropout changes landed in main. Both signals
        # must survive the anonymized review-pack projection together.
        review = self.root / "combined-stereo-review"
        review.mkdir()
        stereo = [v for i in range(8000)
                  for v in (int(6000 * math.sin(i * .11)),
                            int(7000 * math.cos(i * .17)))]
        swapped = [v for i in range(0, len(stereo), 2)
                   for v in (stereo[i + 1], stereo[i])]
        altered = stereo.copy()
        for frame in range(4050, 4530):  # 60ms, crosses 4096-frame read.
            altered[2 * frame + 1] = 0
        unrelated = [v for i in range(8000)
                     for v in (int(4500 * math.sin(i * .21)),
                               int(3200 * math.cos(i * .09)))]
        wav(review / "trial-001-A.wav", stereo, channels=2)
        wav(review / "trial-001-B.wav", unrelated, channels=2)
        wav(review / "trial-002-A.wav", swapped, channels=2)
        wav(review / "trial-002-B.wav", altered, channels=2)
        before = {p.name: p.read_bytes() for p in review.iterdir()}
        report = inspect_review_pack(review)
        self.assertEqual(2, report["trial_count"])
        self.assertEqual(1, report["cross_trial_repeated_variant_count"])
        self.assertEqual(
            ["repeated_pcm_across_trials_inspect_blinding"],
            report["trials"][1]["trial_warnings"],
        )
        self.assertTrue(
            report["trials"][1]["B"]["metrics"]["short_interior_stereo_channel_dropout_risk"]
        )
        self.assertIn(
            "short_interior_stereo_channel_dropout_inspect",
            report["trials"][1]["B"]["warnings"],
        )
        self.assertNotIn("repeated_pcm_across_trials_inspect_blinding",
                         report["trials"][1]["A"]["warnings"])
        self.assertNotIn("repeated_pcm_across_trials_inspect_blinding",
                         report["trials"][1]["B"]["warnings"])
        self.assertFalse(report["answer_key_opened"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("sha256", serialized)
        self.assertNotIn("trial-001-A.wav", serialized)
        self.assertEqual(before, {p.name: p.read_bytes() for p in review.iterdir()})
        strict = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.pack", str(review),
             "--fail-on-warnings"], capture_output=True, text=True,
        )
        self.assertEqual(2, strict.returncode)
        self.assertEqual(report, json.loads(strict.stdout))
        self.assertNotIn(str(self.root), strict.stdout + strict.stderr)

    def test_cli_json_output_no_media_paths(self):
        p = subprocess.run([sys.executable, "-m", "mixlab.quality", str(self.base), str(self.candidate)],
                           capture_output=True, text=True, check=True)
        report = json.loads(p.stdout)
        self.assertEqual(report["candidates"][0]["candidate_id"], "candidate-01")
        self.assertNotIn(str(self.root), p.stdout)
        self.assertTrue(report["human_preference_test_required"])


if __name__ == "__main__":
    unittest.main()
