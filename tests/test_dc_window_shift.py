"""ML-07: opposing or transient DC bias can cancel over a whole WAV.

Window-local DC shift creates potential switching clicks even when whole
file mean DC stays at zero, stereo RMS stays comparable and no large
adjacent PCM step is detected. Private synthetic PCM16 only.
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
    data = array("h", (value for frame in frames for value in frame))
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as sink:
        sink.setnchannels(len(frames[0]))
        sink.setsampwidth(2)
        sink.setframerate(8000)
        sink.writeframes(data.tobytes())


class TemporalDcMismatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="HIDDEN_DC_OFFSET_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "PRIVATE__baseline.wav"
        self.alt = self.root / "PRIVATE__candidate.wav"
        self.signal = [int(3900 * math.sin(i * .13 + .2)) for i in range(8000)]
        write(self.base, [(s,) for s in self.signal])

    def row(self):
        report = compare_wavs(self.base, [self.alt])
        raw = json.dumps(report)
        self.assertNotIn("PRIVATE__", raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("dc_window_means", raw)
        self.assertNotIn("sha256", raw)
        return report["candidates"][0]

    def test_opposing_time_half_dc_has_zero_global_mean_but_all_windows_biased(self):
        candidate = [s + (1050 if i < 4000 else -1050)
                     for i, s in enumerate(self.signal)]
        write(self.alt, [(s,) for s in candidate])
        before = self.alt.read_bytes()
        row = self.row()
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])
        self.assertFalse(row["metrics"]["dc_offset_risk"])
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["metrics"]["severe_sample_discontinuity_risk"])
        self.assertEqual(1.0, row["ab_dc_window_mismatch_fraction"])
        self.assertTrue(row["ab_dc_window_mismatch_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIn("ab_temporal_dc_offset_mismatch_inspect_for_clicks",
                      row["warnings"])
        self.assertEqual(before, self.alt.read_bytes())

    def test_two_affected_windows_below_sustained_threshold(self):
        write(self.alt, [(s + (1050 if i < 1600 else 0),)
                         for i, s in enumerate(self.signal)])
        row = self.row()
        self.assertAlmostEqual(.2, row["ab_dc_window_mismatch_fraction"])
        self.assertFalse(row["ab_dc_window_mismatch_risk"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_three_affected_windows_trigger_conservative_review(self):
        write(self.alt, [(s + (1050 if i < 2400 else 0),)
                         for i, s in enumerate(self.signal)])
        row = self.row()
        self.assertAlmostEqual(.3, row["ab_dc_window_mismatch_fraction"])
        self.assertTrue(row["ab_dc_window_mismatch_risk"])
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])

    def test_one_stereo_channel_biased_is_sufficient(self):
        write(self.base, [(s, s) for s in self.signal])
        write(self.alt, [(s, s + (1050 if i < 4000 else -1050))
                         for i, s in enumerate(self.signal)])
        row = self.row()
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])
        self.assertTrue(row["ab_dc_window_mismatch_risk"])

    def test_identical_and_fully_silent_pcm_no_spurious_warnings(self):
        write(self.alt, [(s,) for s in self.signal])
        row = self.row()
        self.assertEqual(0.0, row["ab_dc_window_mismatch_fraction"])
        self.assertFalse(row["ab_dc_window_mismatch_risk"])
        silence = [(0,)] * 8000
        write(self.base, silence)
        write(self.alt, silence)
        row = self.row()
        self.assertIsNone(row["ab_dc_window_mismatch_fraction"])
        self.assertFalse(row["ab_dc_window_mismatch_risk"])

    def test_exact_pcm_sample_cutoff_distinguishes_983_from_984(self):
        # 3% full-scale lies between 983 and 984 PCM16 counts.
        for delta, expected in ((983, False), (984, True)):
            with self.subTest(delta=delta):
                write(self.alt, [(s + delta,) for s in self.signal])
                row = self.row()
                self.assertEqual(expected, row["ab_dc_window_mismatch_risk"])
                self.assertEqual(float(expected), row["ab_dc_window_mismatch_fraction"])

    def test_boundary_crossing_and_truncated_last_window(self):
        # 20ms at 8kHz = 160 frames. 9003 frames: 56 full windows
        # plus a final 43-frame window. PCM read blocks end at frame 4096.
        sequence = [int(2600 * math.sin(i * .11 + .29)) for i in range(9003)]
        write(self.base, [(s,) for s in sequence])
        affected_windows = 23
        write(self.alt, [(s + (1100 if i < affected_windows * 160 else 0),)
                         for i, s in enumerate(sequence)])
        result = compare_wavs(self.base, [self.alt], window_ms=20)
        row = result["candidates"][0]
        self.assertEqual(57, row["metrics"]["window_count"])
        self.assertAlmostEqual(round(affected_windows / 57, 6),
                               row["ab_dc_window_mismatch_fraction"], places=6)
        self.assertTrue(row["ab_dc_window_mismatch_risk"])
        self.assertFalse(row["ab_dc_offset_mismatch_risk"])
        self.assertNotIn("PRIVATE__", json.dumps(result))

    def test_single_window_has_insufficient_sustained_evidence(self):
        write(self.alt, [(s + 1050,) for s in self.signal])
        report = compare_wavs(self.base, [self.alt], window_ms=1000)
        row = report["candidates"][0]
        self.assertEqual(1.0, row["ab_dc_window_mismatch_fraction"])
        self.assertFalse(row["ab_dc_window_mismatch_risk"])


if __name__ == "__main__":
    unittest.main()
