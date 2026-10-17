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

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "mixlab.quality.intersample", *args],
                              capture_output=True, text=True, timeout=20)


if __name__ == "__main__":
    unittest.main()
