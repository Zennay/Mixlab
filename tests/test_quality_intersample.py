"""Deterministic synthetic quality regressions: no copyrighted audio."""
import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.intersample import compare_intersample, AudioInputError, _PHASES


def write_wav(path, samples, *, rate=8000, channels=1):
    data = array.array("h", samples)
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(2)
        dst.setframerate(rate)
        dst.writeframes(data.tobytes())


class IntersampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = self.root / "private_A_recording.wav"
        self.b = self.root / "private_B_recording.wav"

    def test_filter_dc_conservation(self):
        for coeff in _PHASES:
            self.assertAlmostEqual(1.0, sum(coeff), places=12)

    def test_regular_signal_mono_stereo_and_anonymity(self):
        sine = [round(16000 * math.sin(2 * math.pi * 310 * i / 8000)) for i in range(1600)]
        for channels in (1, 2):
            with self.subTest(channels=channels):
                pcm = sine if channels == 1 else [v for s in sine for v in (s, s)]
                write_wav(self.a, pcm, channels=channels)
                write_wav(self.b, pcm, channels=channels)
                before = self.a.read_bytes(), self.b.read_bytes()
                report = compare_intersample(self.a, [self.b])
                self.assertFalse(report["baseline"]["intersample_over_risk"])
                self.assertTrue(report["baseline"]["screen_evaluable"])
                self.assertEqual(channels, report["channels"])
                self.assertEqual(before, (self.a.read_bytes(), self.b.read_bytes()))
                serialized = json.dumps(report)
                self.assertNotIn(str(self.root), serialized)
                self.assertNotIn("recording", serialized)
                self.assertNotIn("winner", serialized)

    def test_subsample_over_detects_hot_plateau_with_samples_in_range(self):
        # Two adjacent legal sample peaks can overshoot under reconstruction.
        pcm = [0, 0, 0, 30000, 30000, 0, 0, 0] * 100
        self.assertLess(max(map(abs, pcm)), 32768)
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        report = compare_intersample(self.a, [self.b])
        self.assertFalse(report["baseline"]["intersample_over_risk"])
        self.assertTrue(report["candidates"][0]["intersample_over_risk"])
        self.assertGreater(report["candidates"][0]["intersample_overs_estimated"], 0)
        self.assertLess(report["candidates"][0]["sample_peak_dbfs"], 0)
        self.assertGreater(report["candidates"][0]["interpolated_peak_dbfs_estimate"], 0)

    def test_shape_mismatch_refused_before_read_and_symlink_refused(self):
        write_wav(self.a, [0] * 800)
        write_wav(self.b, [0] * 799)
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [self.b])
        self.b.unlink()
        self.b.symlink_to(self.a)
        with self.assertRaises(OSError):
            compare_intersample(self.a, [self.b])

    def test_hardlink_reuse_refused(self):
        write_wav(self.a, [0] * 800)
        os.link(self.a, self.b)
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [self.b])

    def test_truncation_rejected_with_no_private_path_in_cli(self):
        write_wav(self.a, [0] * 800)
        write_wav(self.b, [0] * 800)
        with self.b.open("r+b") as f:
            f.truncate(44 + 300)
        proc = self.cli(str(self.a), str(self.b))
        self.assertEqual(3, proc.returncode)
        self.assertNotIn(str(self.root), proc.stderr + proc.stdout)

    def test_cli_help_parser_errors_success_and_risk_gate(self):
        self.assertEqual(0, self.cli("--help").returncode)
        proc = self.cli("--not-a-valid-opt", "private-secret")
        self.assertEqual(2, proc.returncode)
        self.assertNotIn("private-secret", proc.stderr)
        write_wav(self.a, [0] * 800)
        write_wav(self.b, [0] * 800)
        proc = self.cli(str(self.a), str(self.b), "--fail-on-risk")
        self.assertEqual(0, proc.returncode)
        self.assertIn("baseline", json.loads(proc.stdout))

    def test_cli_positive_risk_gate(self):
        pcm = [0, 0, 0, 30000, 30000, 0, 0, 0] * 100
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        result = self.cli(str(self.a), str(self.b), "--fail-on-risk")
        self.assertEqual(2, result.returncode)
        self.assertTrue(json.loads(result.stdout)["candidates"][0]["intersample_over_risk"])
        self.assertNotIn(str(self.root), result.stdout + result.stderr)

    def test_short_clip_explicitly_not_evaluable(self):
        write_wav(self.a, [0] * 4)
        write_wav(self.b, [0] * 4)
        report = compare_intersample(self.a, [self.b])
        self.assertFalse(report["baseline"]["screen_evaluable"])
        self.assertFalse(report["candidates"][0]["screen_evaluable"])

    def test_multicandidate_identity_and_count_bounds(self):
        third = self.root / "secret_third.wav"
        samples = [0] * 800
        for item in (self.a, self.b, third):
            write_wav(item, samples)
        report = compare_intersample(self.a, [self.b, third])
        self.assertEqual(["candidate-1", "candidate-2"],
                         [c["candidate_id"] for c in report["candidates"]])
        self.assertEqual(800, report["frames_per_source"])
        self.assertNotIn("secret_third", json.dumps(report))
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [])
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [self.b] * 4)

    def test_mismatched_rate_or_channels_rejected(self):
        write_wav(self.a, [0] * 800)
        write_wav(self.b, [0] * 800, rate=11025)
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [self.b])
        write_wav(self.b, [0] * 1600, channels=2)
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [self.b])

    def test_unsupported_sample_width_rejected(self):
        write_wav(self.a, [0] * 800)
        with wave.open(str(self.b), "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(1)
            dst.setframerate(8000)
            dst.writeframes(bytes([128]) * 800)
        with self.assertRaises(AudioInputError):
            compare_intersample(self.a, [self.b])

    def test_streaming_interpolation_across_4096_boundary(self):
        pcm = [0] * 4110
        pcm[4092:4100] = [0, 0, 0, 30000, 30000, 0, 0, 0]
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["intersample_over_risk"])

    def test_high_frequency_analytic_overshoot_is_not_cleared_by_short_fir(self):
        # At 0.4 cycles/sample the true bandlimited sine has 34,200/32,768
        # full-scale amplitude, but every stored sample stays <0dBFS.
        # Our 8-tap Blackman sinc attenuates this near-Nyquist content.
        # It must abstain rather than incorrectly certify "no over".
        pcm = [round(34200 * math.sin(2 * math.pi * 0.4 * i)) for i in range(400)]
        self.assertGreater(34200, 32768)
        self.assertLess(max(map(abs, pcm)), 32768)
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["intersample_over_risk"])  # original 8-tap miss
        self.assertTrue(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertTrue(row["technical_review_required"])
        self.assertGreater(row["high_frequency_near_ceiling_crossings"], 0)
        self.assertLess(row["interpolated_peak_dbfs_estimate"], 0)
        cli = self.cli(str(self.a), str(self.b), "--fail-on-risk")
        self.assertEqual(2, cli.returncode)
        self.assertNotIn(str(self.root), cli.stdout + cli.stderr)

    def test_low_level_high_frequency_is_not_falsely_marked_near_ceiling(self):
        pcm = [round(12000 * math.sin(2 * math.pi * 0.4 * i)) for i in range(400)]
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertEqual(0, row["high_frequency_near_ceiling_crossings"])
        self.assertFalse(row["technical_review_required"])

    def test_high_level_low_frequency_is_not_automatically_flagged(self):
        pcm = [round(32700 * math.sin(2 * math.pi * 0.01 * i)) for i in range(1000)]
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertEqual(0, row["high_frequency_near_ceiling_crossings"])

    def test_stereo_one_channel_ambiguity_and_redacted_count(self):
        pcm = [round(34200 * math.sin(2 * math.pi * 0.4 * i)) for i in range(400)]
        stereo = [value for s in pcm for value in (s, 0)]
        write_wav(self.a, [0] * len(stereo), channels=2)
        write_wav(self.b, stereo, channels=2)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertGreater(row["high_frequency_near_ceiling_crossings"], 0)
        output = json.dumps(row)
        self.assertNotIn(str(self.root), output)
        self.assertNotIn("frame_index", output)

    def test_unevaluable_short_clip_blocks_risk_gate(self):
        write_wav(self.a, [0] * 4)
        write_wav(self.b, [0] * 4)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["screen_evaluable"])
        self.assertTrue(row["technical_review_required"])
        self.assertEqual(2, self.cli(str(self.a), str(self.b), "--fail-on-risk").returncode)

    def test_high_frequency_crossing_across_streaming_chunk_boundary(self):
        pcm = [0] * 8200
        pcm[4095] = 20102
        pcm[4096] = -32526
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertEqual(1, row["high_frequency_near_ceiling_crossings"])

    def test_hot_start_without_full_fir_context_requires_review(self):
        pcm = [0] * 80
        pcm[0] = 32500
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["intersample_over_risk"])
        self.assertTrue(row["screen_evaluable"])
        self.assertTrue(row["edge_interpolation_ambiguity_risk"])
        self.assertTrue(row["technical_review_required"])
        self.assertEqual(2, self.cli(str(self.a), str(self.b), "--fail-on-risk").returncode)

    def test_hot_final_sample_without_right_context_requires_review(self):
        pcm = [0] * 80
        pcm[-1] = -32500
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["edge_interpolation_ambiguity_risk"])
        self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])

    def test_hot_interior_impulse_with_quiet_edges_remains_evaluable(self):
        pcm = [0] * 80
        pcm[40] = 32500
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["edge_interpolation_ambiguity_risk"])
        self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertFalse(row["technical_review_required"])

    def test_stereo_single_channel_hot_edge_is_not_ignored(self):
        stereo = [0] * 160
        stereo[1] = 32600
        write_wav(self.a, [0] * len(stereo), channels=2)
        write_wav(self.b, stereo, channels=2)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["edge_interpolation_ambiguity_risk"])
        self.assertNotIn(str(self.root), json.dumps(row))

    def test_signed_pcm_rails_are_not_cleared_as_safe(self):
        for rail in (-32768, 32767):
            with self.subTest(rail=rail):
                pcm = [0] * 80
                pcm[40] = rail
                write_wav(self.a, [0] * len(pcm))
                write_wav(self.b, pcm)
                row = compare_intersample(self.a, [self.b])["candidates"][0]
                self.assertEqual(1, row["full_scale_pcm_samples"])
                self.assertTrue(row["full_scale_pcm_risk"])
                self.assertTrue(row["technical_review_required"])
                self.assertFalse(row["edge_interpolation_ambiguity_risk"])
                self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])
                self.assertEqual(2, self.cli(str(self.a), str(self.b), "--fail-on-risk").returncode)

    def test_near_rail_but_legal_pcm_does_not_get_rail_warning(self):
        pcm = [0] * 80
        pcm[40] = 32760
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertEqual(0, row["full_scale_pcm_samples"])
        self.assertFalse(row["full_scale_pcm_risk"])

    def test_stereo_single_channel_pcm_rail_redacted(self):
        stereo = [0] * 160
        stereo[81] = -32768
        write_wav(self.a, [0] * len(stereo), channels=2)
        write_wav(self.b, stereo, channels=2)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertEqual(1, row["full_scale_pcm_samples"])
        self.assertTrue(row["technical_review_required"])
        self.assertNotIn(str(self.root), json.dumps(row))

    def test_sixteen_tap_detects_analytic_quarter_rate_over_missed_by_eight_taps(self):
        # A 0.25-cycles/sample sine with phase pi/4 is sampled at only
        # ~70.7% of its true peak; 8-tap Blackman interpolation stayed at
        # 32,273 (<32,768), but 16 taps reconstruct ~33,008 (>32,768).
        amp = 33000
        pcm = [round(amp * math.sin(2 * math.pi * 0.25 * i + math.pi / 4))
               for i in range(320)]
        self.assertLess(max(map(abs, pcm)), 32768)
        self.assertGreater(amp, 32768)
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["screen_evaluable"])
        self.assertTrue(row["intersample_over_risk"])
        self.assertGreater(row["interpolated_peak_dbfs_estimate"], 0)
        self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertFalse(row["edge_interpolation_ambiguity_risk"])

    def test_quarter_rate_lower_amplitude_has_no_intersample_over(self):
        pcm = [round(28000 * math.sin(2 * math.pi * 0.25 * i + math.pi / 4))
               for i in range(320)]
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["intersample_over_risk"])
        self.assertFalse(row["technical_review_required"])

    def test_fifteen_frames_are_insufficient_for_sixteen_tap_screen(self):
        write_wav(self.a, [0] * 15)
        write_wav(self.b, [0] * 15)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertFalse(row["screen_evaluable"])
        self.assertTrue(row["technical_review_required"])
        self.assertEqual(2, self.cli(str(self.a), str(self.b), "--fail-on-risk").returncode)

    def test_sixteen_tap_kernel_span_is_fixed_and_dc_preserving(self):
        for coeff in _PHASES:
            self.assertEqual(16, len(coeff))
            self.assertAlmostEqual(1.0, sum(coeff), places=12)

    def test_adaptive_eighth_sample_catches_quarter_rate_phase_false_negative(self):
        # At pi/16 phase an ideal 33,000 peak has legal PCM samples;
        # even 16-tap 4x samples stay <32768 (~32,369), but eighth
        # phases resolve a >32768 crossing (~33,001).
        pcm = [round(33000 * math.sin(2 * math.pi * 0.25 * i + math.pi / 16))
               for i in range(320)]
        self.assertLess(max(map(abs, pcm)), 32768)
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertTrue(row["intersample_over_risk"])
        self.assertGreater(row["adaptive_8x_refined_windows"], 0)
        self.assertGreater(row["interpolated_peak_dbfs_estimate"], 0)
        self.assertFalse(row["high_frequency_near_ceiling_ambiguity_risk"])
        self.assertEqual(2, self.cli(str(self.a), str(self.b), "--fail-on-risk").returncode)

    def test_quiet_signal_avoids_adaptive_cpu_work(self):
        pcm = [round(12000 * math.sin(2 * math.pi * .25 * i + math.pi / 16))
               for i in range(320)]
        write_wav(self.a, [0] * len(pcm))
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertEqual(0, row["adaptive_8x_refined_windows"])
        self.assertFalse(row["intersample_over_risk"])

    def test_loud_but_safe_dc_refined_without_fabricating_overs(self):
        pcm = [32600] * 128
        write_wav(self.a, pcm)
        write_wav(self.b, pcm)
        row = compare_intersample(self.a, [self.b])["candidates"][0]
        self.assertGreater(row["adaptive_8x_refined_windows"], 0)
        self.assertFalse(row["intersample_over_risk"])
        self.assertTrue(row["edge_interpolation_ambiguity_risk"])

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "mixlab.quality.intersample", *args],
                              capture_output=True, text=True, timeout=20)


if __name__ == "__main__":
    unittest.main()
