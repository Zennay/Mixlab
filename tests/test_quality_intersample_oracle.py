"""Analytic pure-sine screening characterization; no music or private audio.

A bandlimited sine has a known continuous peak amplitude. The cases in the
positive grid all exceed PCM16 FS analytically while every *sample* is legal.
This reports sensitivity of a screening proxy, not standard-compliant dBTP.
"""
import array
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from mixlab.quality.intersample import _scan


def scan_synthetic_tone(path: Path, *, frequency: float, phase: float, amplitude: int):
    pcm = [round(amplitude * math.sin(2 * math.pi * frequency * i + phase))
           for i in range(256)]
    if any(abs(value) >= 32768 for value in pcm):
        return None
    data = array.array("h", pcm)
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(data.tobytes())
    with wave.open(str(path), "rb") as source:
        return _scan(source, 1, len(pcm))


class AnalyticSineOracleTests(unittest.TestCase):
    def test_known_analytic_overs_screening_characterization(self):
        checked = flagged = 0
        by_frequency = {}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_only.wav"
            for freq in (0.05, 0.10, 0.15, 0.20, 0.25,
                         0.30, 0.35, 0.40, 0.45, 0.48):
                for amplitude in (33000, 34200, 36000, 40000, 60000):
                    # The unquantized analytic amplitude always exceeds FS.
                    self.assertGreater(amplitude, 32768)
                    for phase_index in range(64):
                        phase = 2 * math.pi * phase_index / 64
                        report = scan_synthetic_tone(
                            path, frequency=freq, phase=phase, amplitude=amplitude
                        )
                        if report is None:
                            continue  # already unrepresentable in PCM16
                        checked += 1
                        if report["technical_review_required"]:
                            flagged += 1
                        else:
                            by_frequency[freq] = by_frequency.get(freq, 0) + 1
        self.assertGreaterEqual(checked, 300)
        self.assertGreaterEqual(flagged / checked, 0.99)
        # Do not assert 100%: finite FIR screens cannot guarantee it.
        # The exact count is evidence, not a standardized sensitivity claim.
        print(f"ML07 analytic sine oracle: eligible={checked}, flagged={flagged}, "
              f"uncleared={checked - flagged}, uncleared_by_frequency={by_frequency}")

    def test_known_safe_tones_have_no_spurious_review_flags(self):
        checked = 0
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_safe.wav"
            for freq in (0.05, 0.20, 0.25, 0.40, 0.48):
                for phase_index in range(16):
                    report = scan_synthetic_tone(
                        path, frequency=freq, phase=2 * math.pi * phase_index / 16,
                        amplitude=20000
                    )
                    self.assertIsNotNone(report)
                    self.assertFalse(report["technical_review_required"])
                    checked += 1
        self.assertEqual(80, checked)


if __name__ == "__main__":
    unittest.main()
