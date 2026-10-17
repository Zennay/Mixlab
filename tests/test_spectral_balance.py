"""Deterministic synthetic-only tests for the isolated ML-07 spectral proxy."""
from array import array
import json
import math
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.spectral import compare_spectral_balance, scan_spectral_proxy
import mixlab.quality.spectral as spectral


def make_wav(path, *, freq=100, gain=8000, rate=48000, channels=1, duration=0.25, width=2):
    frames = round(rate * duration)
    if width == 2:
        samples = array("h")
        for i in range(frames):
            sample = int(gain * math.sin(2 * math.pi * freq * i / rate))
            samples.extend([sample] * channels)
        if sys.byteorder != "little":
            samples.byteswap()
        raw = samples.tobytes()
    else:
        raw = bytes([128] * frames * channels)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(raw)


def make_segmented_wav(path, freqs, *, rate=48000, channels=1, gain=8000):
    # Exactly eight aligned intervals; transitions deliberately synthetic.
    frames_per_span = 6000
    samples = array("h")
    for segment, freq in enumerate(freqs):
        for offset in range(frames_per_span):
            frame = segment * frames_per_span + offset
            amplitude = int(gain * math.sin(2 * math.pi * freq * frame / rate))
            samples.extend([amplitude] * channels)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())


class SpectralBalanceTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.dir = Path(root.name)
        self.base = self.dir / "secret_base.wav"
        self.other = self.dir / "secret_candidate.wav"
        make_wav(self.base)
        make_wav(self.other)

    def report(self, **kwargs):
        return compare_spectral_balance(self.base, [self.other], **kwargs)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "mixlab.quality.spectral", *map(str, args)],
            text=True, capture_output=True, timeout=15
        )

    def test_equal_pcm_has_equal_proxies_and_no_warning(self):
        before = self.base.read_bytes(), self.other.read_bytes()
        result = self.report()
        row = result["candidates"][0]
        self.assertEqual([], row["warnings"])
        self.assertAlmostEqual(0, row["low_proxy_delta_db"], places=6)
        self.assertAlmostEqual(0, row["high_proxy_delta_db"], places=6)
        self.assertTrue(result["human_preference_test_required"])
        self.assertEqual(before, (self.base.read_bytes(), self.other.read_bytes()))
        self.assertNotIn(str(self.dir), json.dumps(result))

    def test_equal_rms_low_to_high_sine_flags_both_band_proxies(self):
        make_wav(self.other, freq=5000)
        result = self.report()
        row = result["candidates"][0]
        self.assertLess(row["low_proxy_delta_db"], -6)
        self.assertGreater(row["high_proxy_delta_db"], 6)
        self.assertIn("low_spectral_balance_shift_inspect", row["warnings"])
        self.assertIn("high_spectral_balance_shift_inspect", row["warnings"])
        self.assertAlmostEqual(
            result["baseline"]["rms_dbfs"], row["metrics"]["rms_dbfs"], delta=0.1
        )

    def test_gain_only_does_not_trigger_relative_spectrum(self):
        make_wav(self.other, gain=6000)
        row = self.report()["candidates"][0]
        self.assertEqual([], row["warnings"])
        self.assertAlmostEqual(row["low_proxy_delta_db"], 0, delta=0.02)
        self.assertAlmostEqual(row["high_proxy_delta_db"], 0, delta=0.02)

    def test_stereo_and_channel_order_are_symmetric(self):
        make_wav(self.base, freq=400, channels=2)
        make_wav(self.other, freq=400, channels=2)
        row = self.report()["candidates"][0]
        self.assertEqual(2, row["metrics"]["channels"])
        self.assertEqual([], row["warnings"])
        make_wav(self.other, freq=4000, channels=2)
        row = self.report()["candidates"][0]
        self.assertIn("high_spectral_balance_shift_inspect", row["warnings"])

    def test_two_candidates_get_only_opaque_ids(self):
        third = self.dir / "SECRET_THIRD.wav"
        make_wav(third, freq=5000)
        report = compare_spectral_balance(self.base, [self.other, third])
        self.assertEqual(["candidate-01", "candidate-02"],
                         [x["id"] for x in report["candidates"]])
        out = json.dumps(report)
        for item in (str(self.dir), self.base.name, self.other.name, third.name):
            self.assertNotIn(item, out)

    def test_silence_is_never_misrepresented_as_comparable(self):
        make_wav(self.other, gain=0)
        row = self.report()["candidates"][0]
        self.assertIn("insufficient_audible_energy_for_spectral_comparison", row["warnings"])
        self.assertIsNone(row["low_proxy_delta_db"])
        self.assertIsNone(row["high_proxy_delta_db"])
        make_wav(self.base, gain=0)
        self.assertTrue(self.report()["candidates"][0]["warnings"])

    def test_format_mismatches_fail_closed(self):
        for kwargs in ({"rate": 44100}, {"channels": 2}, {"duration": 0.3}):
            make_wav(self.other, **kwargs)
            with self.assertRaises(ValueError):
                self.report()
        make_wav(self.other, width=1)
        with self.assertRaises(ValueError):
            self.report()

    def test_reject_unbounded_and_malformed_thresholds(self):
        for value in (float("nan"), float("inf"), -1, 0, 25, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.report(threshold_db=value)
        with self.assertRaises(ValueError):
            compare_spectral_balance(self.base, [])
        with self.assertRaises(ValueError):
            compare_spectral_balance(self.base, [self.other] * 9)

    def test_nonregular_inputs_and_truncated_audio_do_not_block(self):
        fifo = self.dir / "SECRET_FIFO"
        if hasattr(os, "mkfifo"):
            os.mkfifo(fifo)
            with self.assertRaises((ValueError, OSError)):
                scan_spectral_proxy(fifo)
        symlink = self.dir / "SECRET_SYMLINK"
        symlink.symlink_to(self.base)
        with self.assertRaises((ValueError, OSError)):
            scan_spectral_proxy(symlink)
        make_wav(self.other)
        self.other.write_bytes(self.other.read_bytes()[:-2])
        with self.assertRaises((ValueError, wave.Error)):
            self.report()

    def test_per_source_frame_budget_is_checked_before_pcm_reads(self):
        with self.assertRaises(ValueError):
            scan_spectral_proxy(self.base, max_frames=11999)
        for budget in (0, True, -1, 2_000_001):
            with self.assertRaises(ValueError):
                scan_spectral_proxy(self.base, max_frames=budget)

    def test_aggregate_frame_budget_is_enforced_before_extra_pcm(self):
        before = self.base.read_bytes(), self.other.read_bytes()
        calls = []
        original = wave.Wave_read.readframes

        def traced(source, count):
            calls.append(count)
            return original(source, count)

        # 12000 baseline + 12000 first candidate leave one frame;
        # the next candidate must fail at header admission, not PCM scan.
        with patch.object(spectral, "MAX_AGGREGATE_FRAMES", 24001):
            with patch.object(wave.Wave_read, "readframes", traced):
                with self.assertRaises(ValueError):
                    compare_spectral_balance(self.base, [self.other, self.other])
        self.assertEqual(6, len(calls))
        self.assertEqual(before, (self.base.read_bytes(), self.other.read_bytes()))

    def test_swapped_spectral_halves_are_detected_despite_matched_global_ratios(self):
        base_frequencies = [100] * 4 + [5000] * 4
        make_segmented_wav(self.base, base_frequencies)
        make_segmented_wav(self.other, base_frequencies[::-1])
        report = self.report()
        row = report["candidates"][0]
        # A whole-file signature is nearly the same even though the segments
        # have been swapped: this is a *temporal* A/B confound.
        self.assertLess(abs(row["low_proxy_delta_db"]), 6)
        self.assertLess(abs(row["high_proxy_delta_db"]), 6)
        self.assertGreaterEqual(row["temporal_low_proxy_mismatch_fraction"], 0.25)
        self.assertGreaterEqual(row["temporal_high_proxy_mismatch_fraction"], 0.25)
        self.assertIn("low_temporal_spectral_shift_inspect", row["warnings"])
        self.assertIn("high_temporal_spectral_shift_inspect", row["warnings"])
        serialized = json.dumps(report)
        self.assertNotIn("spectral_spans", serialized)
        self.assertNotIn("_spans", serialized)
        self.assertNotIn(str(self.dir), serialized)

    def test_one_short_spectral_change_does_not_trigger_persistent_bias(self):
        make_segmented_wav(self.base, [100] * 8)
        make_segmented_wav(self.other, [5000] + [100] * 7)
        row = self.report()["candidates"][0]
        self.assertLess(row["temporal_low_proxy_mismatch_fraction"], 0.25)
        self.assertNotIn("low_temporal_spectral_shift_inspect", row["warnings"])
        self.assertNotIn("high_temporal_spectral_shift_inspect", row["warnings"])

    def test_temporal_proxy_is_gain_invariant_and_works_on_stereo(self):
        make_segmented_wav(self.base, [200, 250, 300, 350] * 2, channels=2)
        make_segmented_wav(self.other, [200, 250, 300, 350] * 2, channels=2, gain=6000)
        row = self.report()["candidates"][0]
        self.assertEqual(0.0, row["temporal_low_proxy_mismatch_fraction"])
        self.assertEqual(0.0, row["temporal_high_proxy_mismatch_fraction"])
        self.assertNotIn("low_temporal_spectral_shift_inspect", row["warnings"])

    def test_silent_segments_have_no_fake_zero_db_temporal_evidence(self):
        make_wav(self.other, gain=0)
        row = self.report()["candidates"][0]
        self.assertIsNone(row["temporal_low_proxy_mismatch_fraction"])
        self.assertIsNone(row["temporal_high_proxy_mismatch_fraction"])
        self.assertIn("insufficient_audible_energy_for_spectral_comparison", row["warnings"])

    def test_cli_output_status_and_argument_privacy(self):
        clean = self.cli(self.base, self.other)
        self.assertEqual(0, clean.returncode, clean.stderr)
        report = json.loads(clean.stdout)
        self.assertEqual([], report["candidates"][0]["warnings"])
        for secret in (str(self.base), str(self.other), str(self.dir)):
            self.assertNotIn(secret, clean.stdout + clean.stderr)
        make_wav(self.other, freq=5000)
        flagged = self.cli(self.base, self.other, "--fail-on-warnings")
        self.assertEqual(2, flagged.returncode, flagged.stderr)
        self.assertTrue(json.loads(flagged.stdout)["candidates"][0]["warnings"])
        canary = "/private/PRIVATE_CANARY_VALUE"
        for params, code in (
            ((self.base, self.other, "--threshold-db", canary), 2),
            ((self.base, self.other, "--unknown=" + canary), 2),
            ((self.base, self.other, "--threshold-db", "nan"), 3),
            ((self.base, canary), 3),
        ):
            response = self.cli(*params)
            self.assertEqual(code, response.returncode, response.stderr)
            self.assertNotIn(canary, response.stdout + response.stderr)
            self.assertEqual("", response.stdout)


if __name__ == "__main__":
    unittest.main()
