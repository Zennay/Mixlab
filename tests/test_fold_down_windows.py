"""ML-07: relative mono fold-down can differ by time even if totals match.

Synthetic PCM16 stereo. Reversing when channels cancel can preserve
whole-clip stereo and mono power, but make aligned A/B windows radically
different for mono playback. No source names or window envelopes exported.
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
    with wave.open(str(path), "wb") as fp:
        fp.setnchannels(len(frames[0]))
        fp.setsampwidth(2)
        fp.setframerate(8000)
        fp.writeframes(data.tobytes())


class FoldDownWindowAbTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="SECRET_ML07_FOLD_WIN_")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "PRIVATE_baseline.wav"
        self.alt = self.root / "PRIVATE_candidate.wav"
        self.samples = [int(5200 * math.sin(i * .13 + .17)) for i in range(8000)]
        self.same = [(v, v) for v in self.samples]
        self.cancel = [(v, -v) for v in self.samples]

    def row(self):
        report = compare_wavs(self.base, [self.alt])
        raw = json.dumps(report)
        self.assertNotIn("PRIVATE_", raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("envelope", raw)
        return report["candidates"][0]

    def test_switched_halves_match_global_mono_power_but_not_local_windows(self):
        save(self.base, self.cancel[:4000] + self.same[4000:])
        save(self.alt, self.same[:4000] + self.cancel[4000:])
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])
        self.assertFalse(row["ab_mono_fold_down_level_confound_risk"])
        self.assertTrue(row["ab_mono_fold_down_window_level_confound_risk"])
        self.assertGreaterEqual(row["ab_mono_fold_down_window_level_mismatch_fraction"], .9)
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIn("ab_mono_fold_down_window_confound_inspect_not_lufs", row["warnings"])

    def test_single_window_mono_cancellation_is_below_sustained_threshold(self):
        save(self.base, self.same)
        alt = list(self.same)
        alt[:800] = self.cancel[:800]
        save(self.alt, alt)
        row = self.row()
        self.assertAlmostEqual(.1, row["ab_mono_fold_down_window_level_mismatch_fraction"])
        self.assertFalse(row["ab_mono_fold_down_window_level_confound_risk"])

    def test_three_of_ten_mono_cancelling_windows_trigger_warning(self):
        save(self.base, self.same)
        alt = list(self.same)
        alt[:2400] = self.cancel[:2400]
        save(self.alt, alt)
        row = self.row()
        self.assertAlmostEqual(.3, row["ab_mono_fold_down_window_level_mismatch_fraction"])
        self.assertTrue(row["ab_mono_fold_down_window_level_confound_risk"])

    def test_matching_mono_envelopes_do_not_create_false_relative_risk(self):
        clip = self.cancel[:4000] + self.same[4000:]
        save(self.base, clip)
        save(self.alt, clip)
        row = self.row()
        self.assertEqual(0.0, row["ab_mono_fold_down_window_level_mismatch_fraction"])
        self.assertFalse(row["ab_mono_fold_down_window_level_confound_risk"])

    def test_fully_silent_stereo_has_no_audible_fold_down_window_evidence(self):
        save(self.base, [(0, 0)] * len(self.samples))
        save(self.alt, [(0, 0)] * len(self.samples))
        row = self.row()
        self.assertIsNone(row["ab_mono_fold_down_window_level_mismatch_fraction"])
        self.assertFalse(row["ab_mono_fold_down_window_level_confound_risk"])

    def test_mono_ignores_stereo_to_mono_fold_down_window_comparison(self):
        save(self.base, [(v,) for v in self.samples])
        save(self.alt, [(int(v * .98),) for v in self.samples])
        row = self.row()
        self.assertIsNone(row["ab_mono_fold_down_window_level_mismatch_fraction"])
        self.assertFalse(row["ab_mono_fold_down_window_level_confound_risk"])


if __name__ == "__main__":
    unittest.main()
