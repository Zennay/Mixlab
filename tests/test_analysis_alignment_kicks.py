from pathlib import Path
import tempfile
import unittest
from mixlab.analysis.alignment import kick_offset
from tests.test_analysis_kick import club

BPM = 124.
PERIOD = 60 / BPM


class KickOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.a, cls.b = root / "a.wav", root / "b.wav"
        club(cls.a, bpm=BPM, phase=.2, seed=1)
        club(cls.b, bpm=BPM, phase=.2, seed=7)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def measure(self, offset):
        # Starting B `offset` late in its own timeline makes its kicks arrive early.
        return kick_offset(self.a, .2 + 8 * PERIOD, self.b, .2 + 2 * PERIOD + offset, BPM, 16 * PERIOD)

    def test_known_offsets_are_measured_and_classified(self):
        for offset, verdict in ((0., "aligned"), (.02, "flam"), (.06, "flam"),
                                (PERIOD / 2, "off-beat (train-wreck risk)")):
            with self.subTest(offset=offset):
                result = self.measure(offset)
                self.assertEqual(result.verdict, verdict)
                expected = -offset if offset < PERIOD / 2 else offset
                self.assertAlmostEqual(abs(result.lag_seconds), abs(expected), delta=.006)

    def test_nudging_by_the_measured_lag_realigns(self):
        first = self.measure(.06)
        corrected = kick_offset(self.a, .2 + 8 * PERIOD, self.b, .2 + 2 * PERIOD + .06 + first.lag_seconds,
                                BPM, 16 * PERIOD)
        self.assertEqual(corrected.verdict, "aligned")

    def test_no_kicks_is_not_called_aligned(self):
        with tempfile.TemporaryDirectory() as temp:
            silent = Path(temp) / "pad.wav"
            club(silent, bpm=BPM, kick=False)
            result = kick_offset(silent, 2., silent, 4., BPM, 16 * PERIOD)
            self.assertNotEqual(result.verdict, "aligned")


if __name__ == "__main__":
    unittest.main()
