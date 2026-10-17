"""Independent PCM16 oracle for stereo-to-mono downmix diagnostics.

Verifies the new comparative gates are built on the correct existing
mid-channel energy, including 4096-frame stream boundaries, and never
report an audio/filename envelope. Only synthetic PCM16.
"""
from array import array
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs, scan_wav


def write(path, frames):
    samples = array("h", (s for frame in frames for s in frame))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as fp:
        fp.setnchannels(2)
        fp.setsampwidth(2)
        fp.setframerate(8000)
        fp.writeframes(samples.tobytes())


def exact_fold_down_db(frames):
    stereo_power = sum(left * left + right * right for left, right in frames)
    mid_power = sum(((left + right) / 2) ** 2 for left, right in frames)
    return round(10 * math.log10(stereo_power / (2 * mid_power)), 3) if mid_power else None


class StereoFoldDownOracleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="PRIVATE_fold_oracle_")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.wav = self.root / "SECRET__unlicensed_fake.wav"
        self.variant = self.root / "SECRET__variant.wav"

    def test_independent_mono_energy_oracle_across_stream_blocks(self):
        rng = random.Random(20261017)
        for frames_count in (1, 799, 800, 801, 4095, 4096, 4097, 9003):
            with self.subTest(frames=frames_count):
                frames = [(rng.randint(-24000, 24000), rng.randint(-24000, 24000))
                          for _ in range(frames_count)]
                write(self.wav, frames)
                original = self.wav.read_bytes()
                metrics = scan_wav(self.wav)
                self.assertEqual(exact_fold_down_db(frames),
                                 metrics["mono_fold_down_loss_db"])
                self.assertEqual(original, self.wav.read_bytes())
                self.assertNotIn("SECRET__", json.dumps(metrics))
                self.assertNotIn(str(self.root), json.dumps(metrics))

    def test_dual_mono_is_zero_db_fold_down_loss(self):
        frames = [(int(4900 * math.sin(i * .11)),) * 2 for i in range(8000)]
        write(self.wav, frames)
        self.assertEqual(0.0, scan_wav(self.wav)["mono_fold_down_loss_db"])

    def test_opposite_phase_is_nonfinite_loss_representation(self):
        frames = [(int(4900 * math.sin(i * .11)), -int(4900 * math.sin(i * .11)))
                  for i in range(8000)]
        write(self.wav, frames)
        metrics = scan_wav(self.wav)
        self.assertIsNone(metrics["mono_fold_down_loss_db"])
        self.assertTrue(metrics["mono_fold_down_cancellation_risk"])

    def test_left_only_stereo_is_approximately_three_db_loss(self):
        frames = [(int(4900 * math.sin(i * .11)), 0) for i in range(8000)]
        write(self.wav, frames)
        self.assertEqual(3.01, scan_wav(self.wav)["mono_fold_down_loss_db"])

    def test_one_signed_minimum_is_finite_and_exact(self):
        frames = [(int(4900 * math.sin(i * .11)), int(3100 * math.sin(i * .17)))
                  for i in range(9003)]
        frames[4096] = (-32768, 0)
        frames[8192] = (0, -32768)
        write(self.wav, frames)
        self.assertEqual(exact_fold_down_db(frames),
                         scan_wav(self.wav)["mono_fold_down_loss_db"])

    def test_comparative_output_has_no_per_window_mid_envelopes(self):
        frames = [(int(4100 * math.sin(i * .09)), int(3100 * math.sin(i * .13)))
                  for i in range(9003)]
        write(self.wav, frames)
        write(self.variant, frames)
        report = compare_wavs(self.wav, [self.variant])
        text = json.dumps(report)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("SECRET__", text)
        self.assertNotIn("mono_fold_down_window_peaks", text)
        self.assertNotIn("base_fold_down_windows", text)
        self.assertFalse(report["candidates"][0]["ab_mono_fold_down_level_confound_risk"])
        self.assertFalse(report["candidates"][0]["ab_mono_fold_down_window_level_confound_risk"])


if __name__ == "__main__":
    unittest.main()
