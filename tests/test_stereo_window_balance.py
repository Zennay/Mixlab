"""Detect stereo-window level/pan confounds hidden by equal global RMS.

Fixtures are generated PCM16 and never exported. Combined RMS and global
per-channel RMS can both match while channel balance changes over time.
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


def write_pcm(path, frames, *, channels=2):
    values = array("h", (v for frame in frames for v in frame))
    if sys.byteorder != "little":
        values.byteswap()
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(channels)
        destination.setsampwidth(2)
        destination.setframerate(8000)
        destination.writeframes(values.tobytes())


class StereoWindowLevelConfoundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ML07_PRIVATE_TIME_PAN_")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "PRIVATE__original.wav"
        self.candidate = self.root / "PRIVATE__alternative.wav"
        self.signal = [int(4900 * math.sin(i * .11 + .31)) for i in range(8000)]
        self.frames = [(int(x * (1.4 if i < 4000 else .2)),
                        int(x * (.2 if i < 4000 else 1.4)))
                       for i, x in enumerate(self.signal)]
        write_pcm(self.base, self.frames)

    def row(self):
        report = compare_wavs(self.base, [self.candidate])
        raw = json.dumps(report)
        self.assertNotIn("PRIVATE__", raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("channel_window", raw)
        return report["candidates"][0]

    def test_time_varying_stereo_swap_matches_global_levels_but_fails_local_gate(self):
        transformed = [(r, l) for l, r in self.frames]
        l, r = transformed[4200]
        transformed[4200] = (l + 1, r)  # not a byte-exact global stereo swap
        write_pcm(self.candidate, transformed)
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertTrue(row["stereo_window_channel_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIn("stereo_window_channel_level_mismatch_inspect_not_lufs",
                      row["warnings"])
        self.assertIsNone(row["stereo_swapped_pcm_of"])

    def test_a_single_swapped_window_below_fraction_threshold_is_not_sustained(self):
        transformed = list(self.frames)
        transformed[:800] = [(r, l) for l, r in transformed[:800]]
        write_pcm(self.candidate, transformed)
        row = self.row()
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])
        self.assertAlmostEqual(.1, row["stereo_window_channel_level_mismatch_fraction"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_four_swapped_windows_across_both_halves_are_sustained(self):
        transformed = list(self.frames)
        for start in (0, 800, 4800, 5600):
            transformed[start:start + 800] = [
                (r, l) for l, r in transformed[start:start + 800]
            ]
        write_pcm(self.candidate, transformed)
        row = self.row()
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertTrue(row["stereo_window_channel_level_confound_risk"])
        self.assertGreaterEqual(row["stereo_window_channel_level_mismatch_fraction"], .4)

    def test_partial_right_channel_mute_is_confound_only_when_sustained(self):
        # A muted channel for two of ten windows is below the 25% policy.
        # Three windows cross the policy even when aggregate RMS remains
        # roughly level matched and channel source names stay private.
        for windows, expected_risk in ((2, False), (3, True)):
            with self.subTest(muted_windows=windows):
                changed = list(self.frames)
                for i in range(windows * 800):
                    changed[i] = (changed[i][0], 0)
                write_pcm(self.candidate, changed)
                row = self.row()
                self.assertEqual(expected_risk, row["stereo_window_channel_level_confound_risk"])
                self.assertAlmostEqual(windows / 10, row["stereo_window_channel_level_mismatch_fraction"])

    def test_identical_stereo_remains_passed_without_exposing_envelopes(self):
        write_pcm(self.candidate, self.frames)
        row = self.row()
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])
        self.assertEqual(0.0, row["stereo_window_channel_level_mismatch_fraction"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_silent_stereo_has_no_audible_comparison_windows(self):
        frames = [(0, 0)] * 8000
        write_pcm(self.base, frames)
        write_pcm(self.candidate, frames)
        row = self.row()
        self.assertIsNone(row["stereo_window_channel_level_mismatch_fraction"])
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])

    def test_mono_does_not_have_stereo_window_metrics(self):
        mono = [(x,) for x in self.signal]
        write_pcm(self.base, mono, channels=1)
        write_pcm(self.candidate, [(int(x * .98),) for x in self.signal], channels=1)
        row = self.row()
        self.assertIsNone(row["stereo_window_channel_level_mismatch_fraction"])
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])


if __name__ == "__main__":
    unittest.main()
