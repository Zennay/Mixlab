"""ML-07: actual mono playback RMS must respect A/B level tolerance.

A phase-shifted stereo sine can match BOTH channel RMS and combined
stereo power yet play several dB softer in mono, below the historical
6 dB *fold-down loss difference* warning threshold. Synthetic PCM only.
"""
from array import array
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs


def save(path, frames):
    data = array("h", (value for frame in frames for value in frame))
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(len(frames[0]))
        dst.setsampwidth(2)
        dst.setframerate(8000)
        dst.writeframes(data.tobytes())


class MonoPlaybackLevelTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="ML07_SECRET_monoplay_")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.base = self.root / "UNLICENSED_FAKE__baseline.wav"
        self.alt = self.root / "UNLICENSED_FAKE__candidate.wav"
        self.frames = 8000
        self.left = [int(4300 * math.sin(i * .13)) for i in range(self.frames)]
        save(self.base, [(v, v) for v in self.left])

    def stereo_with_shifted_right(self, theta):
        return [(v, int(4300 * math.sin(i * .13 + theta)))
                for i, v in enumerate(self.left)]

    def row(self, **kwargs):
        report = compare_wavs(self.base, [self.alt], **kwargs)
        raw = json.dumps(report)
        self.assertNotIn("UNLICENSED_FAKE", raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("mono_fold_down_window_peaks", raw)
        return report["candidates"][0]

    def test_four_db_mono_playback_bias_evades_six_db_fold_loss_policy(self):
        save(self.alt, self.stereo_with_shifted_right(1.8))
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])
        self.assertFalse(row["ab_mono_fold_down_level_confound_risk"])
        self.assertFalse(row["ab_mono_fold_down_window_level_confound_risk"])
        self.assertLess(row["mono_playback_rms_delta_db_vs_baseline"], -3.5)
        self.assertTrue(row["mono_playback_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIn("ab_mono_playback_rms_level_mismatch_not_lufs", row["warnings"])

    def test_small_phase_shift_keeps_mono_playback_within_tolerance(self):
        save(self.alt, self.stereo_with_shifted_right(.25))
        row = self.row()
        self.assertLess(abs(row["mono_playback_rms_delta_db_vs_baseline"]), .2)
        self.assertFalse(row["mono_playback_level_confound_risk"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_configured_tolerance_controls_mono_playback_guard(self):
        save(self.alt, self.stereo_with_shifted_right(1.8))
        row = self.row(loudness_tolerance_db=5)
        self.assertFalse(row["mono_playback_level_confound_risk"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_swapping_baseline_and_candidate_reverses_delta(self):
        shifted = self.stereo_with_shifted_right(1.8)
        save(self.alt, shifted)
        first = self.row()["mono_playback_rms_delta_db_vs_baseline"]
        save(self.base, shifted)
        save(self.alt, [(v, v) for v in self.left])
        second = self.row()["mono_playback_rms_delta_db_vs_baseline"]
        self.assertAlmostEqual(-first, second, places=3)
        self.assertTrue(self.row()["mono_playback_level_confound_risk"])

    def test_exact_mono_cancellation_has_no_finite_reported_delta(self):
        save(self.alt, [(v, -v) for v in self.left])
        row = self.row()
        self.assertIsNone(row["mono_playback_rms_delta_db_vs_baseline"])
        self.assertTrue(row["mono_playback_level_confound_risk"])

    def test_mono_and_stereo_silence_do_not_fake_delta(self):
        save(self.base, [(0, 0)] * self.frames)
        save(self.alt, [(0, 0)] * self.frames)
        row = self.row()
        self.assertIsNone(row["mono_playback_rms_delta_db_vs_baseline"])
        self.assertFalse(row["mono_playback_level_confound_risk"])
        save(self.base, [(v,) for v in self.left])
        save(self.alt, [(int(v * .98),) for v in self.left])
        row = self.row()
        self.assertIsNone(row["mono_playback_rms_delta_db_vs_baseline"])
        self.assertFalse(row["mono_playback_level_confound_risk"])


if __name__ == "__main__":
    unittest.main()
