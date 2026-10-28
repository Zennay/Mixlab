"""ML-07: RMS similarity alone is insufficient to greenlight a blind level check.

Checks that the new *technical*, not perceptual/music, level preflight
uses sufficient aligned audible windows and catches temporal masking.
"""
import math
from pathlib import Path
import tempfile
import unittest
import wave
from array import array
import sys
import json

from mixlab.quality import compare_wavs


def write(path, samples):
    a = array("h", samples)
    if sys.byteorder != "little":
        a.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(a.tobytes())


class WholeAndShortWindowLevelGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ML07_SECRET_LEVEL_GATE_")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.root = root
        self.baseline = root / "PRIVATE___baseline.wav"
        self.candidate = root / "PRIVATE___candidate.wav"
        self.samples = [int(6500 * math.sin(i * .13)) for i in range(8000)]
        write(self.baseline, self.samples)

    def row(self, **kwargs):
        report = compare_wavs(self.baseline, [self.candidate], **kwargs)
        self.assertNotIn("PRIVATE___", json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        return report["candidates"][0]

    def test_aligned_audible_equal_levels_pass_technical_check(self):
        write(self.candidate, self.samples)
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])
        self.assertFalse(row["short_window_level_mismatch_risk"])

    def test_global_level_match_but_temporal_level_confound_must_fail(self):
        # Existing legacy RMS flag is intentionally unchanged for consumers;
        # this stricter gate must not report it ready for a level-balanced A/B.
        samples = [int(x * .1) for x in self.samples[:4000]] + [
            int(x * 1.4) for x in self.samples[4000:]
        ]
        write(self.candidate, samples)
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertTrue(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_uniform_six_db_difference_fails_both_level_gates(self):
        write(self.candidate, [int(x / 2) for x in self.samples])
        row = self.row()
        self.assertFalse(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_one_window_even_at_equal_rms_is_insufficient_evidence(self):
        write(self.candidate, self.samples)
        # At 1 second per window the entire clip is only one observation.
        row = self.row(window_ms=1000)
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_short_sub_300ms_pair_is_not_claimed_ready(self):
        write(self.baseline, self.samples[:800])
        write(self.candidate, self.samples[:800])
        row = self.row()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_silent_candidate_has_no_verified_level_comparison(self):
        write(self.candidate, [0] * len(self.samples))
        row = self.row()
        self.assertFalse(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])


if __name__ == "__main__":
    unittest.main()
