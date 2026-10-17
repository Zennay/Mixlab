"""Deterministic synthetic-only tests for the isolated ML-07 spectral proxy."""
from array import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.spectral import compare_spectral_balance, scan_spectral_proxy


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
            compare_spectral_balance(self.base, [self.other] * 61)

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
