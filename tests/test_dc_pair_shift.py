"""ML-07: a large RELATIVE DC offset is hidden by two individually safe DC offsets.

A signed mean shift can preserve all RMS and anti-clipping checks while
introducing a discontinuity between two blind-review variants. All fixtures
are synthetic PCM16, report fields anonymous, and source bytes immutable.
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


def write(path, frames):
    data = array("h", (x for frame in frames for x in frame))
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(len(frames[0]))
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(data.tobytes())


class RelativeDcMismatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="SECRET_DC_ML07_")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.base = root / "PRIVATE__baseline.wav"
        self.candidate = root / "PRIVATE__candidate.wav"
        self.samples = [int(4800 * math.sin(i * .13 + .23)) for i in range(8000)]

    def row(self):
        result = compare_wavs(self.base, [self.candidate])
        raw = json.dumps(result)
        self.assertNotIn(str(self.base.parent), raw)
        self.assertNotIn("PRIVATE__", raw)
        self.assertNotIn("sha256", raw)
        return result["candidates"][0]

    def test_opposite_subthreshold_mono_dc_biases_must_be_compared(self):
        write(self.base, [(x + 700,) for x in self.samples])
        write(self.candidate, [(x - 700,) for x in self.samples])
        before_base, before_candidate = self.base.read_bytes(), self.candidate.read_bytes()
        row = self.row()
        self.assertFalse(row["metrics"]["dc_offset_risk"])
        self.assertFalse(row["metrics"]["severe_sample_discontinuity_risk"])
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertTrue(row["ab_dc_offset_mismatch_risk"])
        self.assertAlmostEqual(1400 / 32768, row["ab_max_channel_dc_offset_delta_fs"], places=6)
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIn("ab_channel_dc_offset_mismatch_inspect_for_clicks", row["warnings"])
        self.assertEqual(before_base, self.base.read_bytes())
        self.assertEqual(before_candidate, self.candidate.read_bytes())

    def test_single_stereo_channel_bias_is_detected(self):
        write(self.base, [(x + 700, x) for x in self.samples])
        write(self.candidate, [(x - 700, x) for x in self.samples])
        row = self.row()
        self.assertTrue(row["ab_dc_offset_mismatch_risk"])
        self.assertFalse(row["metrics"]["dc_offset_risk"])

    def test_same_absolute_offset_does_not_create_relative_warning(self):
        write(self.base, [(x + 700,) for x in self.samples])
        write(self.candidate, [(x + 700,) for x in self.samples])
        row = self.row()
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])
        self.assertAlmostEqual(0.0, row["ab_max_channel_dc_offset_delta_fs"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_small_relative_offset_stays_below_inspection_threshold(self):
        write(self.base, [(x + 450,) for x in self.samples])
        write(self.candidate, [(x - 450,) for x in self.samples])
        row = self.row()
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_silent_stereo_does_not_invent_relative_dc(self):
        write(self.base, [(0, 0)] * 8000)
        write(self.candidate, [(0, 0)] * 8000)
        row = self.row()
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])
        self.assertAlmostEqual(0.0, row["ab_max_channel_dc_offset_delta_fs"])


if __name__ == "__main__":
    unittest.main()
