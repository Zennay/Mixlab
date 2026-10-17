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
        # Change the container without changing PCM to prove audio-only
        # fingerprinting; a file hash would miss this repeat.
        with (review / "trial-002-B.wav").open("ab") as f:
            f.write(b"unrelated-non-audio-container-trailer")
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

    def test_cli_json_output_no_media_paths(self):
        p = subprocess.run([sys.executable, "-m", "mixlab.quality", str(self.base), str(self.candidate)],
                           capture_output=True, text=True, check=True)
        report = json.loads(p.stdout)
        self.assertEqual(report["candidates"][0]["candidate_id"], "candidate-01")
        self.assertNotIn(str(self.root), p.stdout)
        self.assertTrue(report["human_preference_test_required"])


if __name__ == "__main__":
    unittest.main()
