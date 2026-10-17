"""ML-07: matched stereo RMS must not mask an unequal mono fold-down.

Synthetic PCM16 only. A mono playback route can cancel a stereo
candidate while both stereo channels and all RMS windows appear matched.
The warning is technical and still requires human listening.
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


def write(path, frames, channels=2):
    data = array("h", (v for frame in frames for v in frame))
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as sink:
        sink.setnchannels(channels)
        sink.setsampwidth(2)
        sink.setframerate(8000)
        sink.writeframes(data.tobytes())


class FoldDownAbLevelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="SENSITIVE_ml07_folddown_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "PRIVATE_SONG__baseline.wav"
        self.candidate = self.root / "PRIVATE_SONG__candidate.wav"
        self.signal = [int(4500 * math.sin(i * .113 + .24)) for i in range(8000)]
        write(self.base, [(x, x) for x in self.signal])

    def row(self):
        report = compare_wavs(self.base, [self.candidate])
        raw = json.dumps(report)
        self.assertNotIn("PRIVATE_SONG__", raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("sha256", raw)
        return report["candidates"][0]

    def test_opposite_phase_exact_stereo_rms_hides_full_mono_cancellation(self):
        write(self.candidate, [(x, -x) for x in self.signal])
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertFalse(row["stereo_window_channel_level_confound_risk"])
        self.assertTrue(row["ab_mono_fold_down_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIsNone(row["mono_fold_down_level_delta_db_vs_baseline"])
        self.assertIn("ab_mono_fold_down_level_confound_inspect_not_lufs",
                      row["warnings"])

    def test_large_but_finite_mono_cancellation_diff_is_flagged(self):
        # Stereo overall RMS drops <1 dB, but mono fold-down nearly vanishes.
        write(self.candidate, [(x, int(-.75 * x)) for x in self.signal])
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertTrue(row["ab_mono_fold_down_level_confound_risk"])
        self.assertGreater(row["mono_fold_down_level_delta_db_vs_baseline"], 6)

    def test_small_pan_gain_change_is_not_flagged(self):
        write(self.candidate, [(x, int(.9 * x)) for x in self.signal])
        row = self.row()
        self.assertFalse(row["ab_mono_fold_down_level_confound_risk"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_baseline_cancels_but_candidate_does_not(self):
        write(self.base, [(x, -x) for x in self.signal])
        write(self.candidate, [(x, x) for x in self.signal])
        row = self.row()
        self.assertTrue(row["ab_mono_fold_down_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_identical_cancelling_stereo_is_not_relative_mismatch(self):
        anti = [(x, -x) for x in self.signal]
        write(self.base, anti)
        write(self.candidate, anti)
        row = self.row()
        self.assertFalse(row["ab_mono_fold_down_level_confound_risk"])
        self.assertIsNone(row["mono_fold_down_level_delta_db_vs_baseline"])

    def test_silent_stereo_and_mono_keep_null_fold_down_delta(self):
        write(self.base, [(0, 0)] * 8000)
        write(self.candidate, [(0, 0)] * 8000)
        row = self.row()
        self.assertFalse(row["ab_mono_fold_down_level_confound_risk"])
        self.assertIsNone(row["mono_fold_down_level_delta_db_vs_baseline"])
        write(self.base, [(x,) for x in self.signal], channels=1)
        write(self.candidate, [(int(x * .9),) for x in self.signal], channels=1)
        row = self.row()
        self.assertFalse(row["ab_mono_fold_down_level_confound_risk"])
        self.assertIsNone(row["mono_fold_down_level_delta_db_vs_baseline"])


if __name__ == "__main__":
    unittest.main()
