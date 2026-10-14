import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import compare_wavs, scan_wav


def wav(path, samples, *, rate=8000, channels=1, width=2):
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(width)
        dst.setframerate(rate)
        values = array.array("h", samples)
        if sys.byteorder != "little":
            values.byteswap()
        dst.writeframes(values.tobytes())


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "base.wav"
        self.candidate = self.root / "candidate.wav"
        self.samples = [int(6000 * math.sin(i * 0.15)) for i in range(8000)]
        wav(self.base, self.samples)
        wav(self.candidate, self.samples)

    def test_equal_pcm_is_level_comparable_with_no_path_leak(self):
        before = self.candidate.read_bytes()
        report = compare_wavs(self.base, [self.candidate])
        self.assertEqual(report["baseline"], report["candidates"][0]["metrics"])
        self.assertEqual(0, report["candidates"][0]["rms_delta_db_vs_baseline"])
        self.assertTrue(report["candidates"][0]["level_comparable_for_blind_ab"])
        self.assertFalse(report["candidates"][0]["warnings"])
        self.assertTrue(report["human_preference_test_required"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(before, self.candidate.read_bytes())

    def test_quieter_candidate_reports_rms_confound_not_best_music(self):
        wav(self.candidate, [int(x / 2) for x in self.samples])
        report = compare_wavs(self.base, [self.candidate])
        row = report["candidates"][0]
        self.assertAlmostEqual(-6.02, row["rms_delta_db_vs_baseline"], delta=0.05)
        self.assertIn("rms_level_mismatch_not_lufs", row["warnings"])
        self.assertFalse(row["level_comparable_for_blind_ab"])
        self.assertNotIn("score", json.dumps(report))

    def test_silent_and_near_full_scale_candidates(self):
        wav(self.candidate, [0] * 8000)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["rms_delta_db_vs_baseline"])
        self.assertEqual(row["metrics"]["silent_window_fraction"], 1)
        self.assertIn("silence_prevents_rms_level_comparison", row["warnings"])
        wav(self.candidate, [32767] * 8000)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIn("near_full_scale_samples_inspect_for_clipping", row["warnings"])

    def test_stereo_stream_windows_and_determinism(self):
        stereo = self.root / "stereo.wav"
        interleaved = [sample for x in self.samples for sample in (x, -x)]
        wav(stereo, interleaved, channels=2)
        once, twice = scan_wav(stereo, window_ms=50), scan_wav(stereo, window_ms=50)
        self.assertEqual(once, twice)
        self.assertEqual(2, once["channels"])
        self.assertEqual(20, once["window_count"])
        self.assertAlmostEqual(0, once["dc_per_channel"][0] + once["dc_per_channel"][1])
        with self.assertRaisesRegex(ValueError, "channels"):
            compare_wavs(self.base, [stereo])

    def test_mismatched_duration_rate_and_format_are_fail_closed(self):
        wav(self.candidate, self.samples[:-10])
        with self.assertRaisesRegex(ValueError, "frames"):
            compare_wavs(self.base, [self.candidate])
        wav(self.candidate, self.samples, rate=16000)
        with self.assertRaisesRegex(ValueError, "sample_rate"):
            compare_wavs(self.base, [self.candidate])
        invalid = self.root / "invalid.wav"
        invalid.write_bytes(b"broken audio data")
        with self.assertRaises(ValueError):
            scan_wav(invalid)
        with wave.open(str(invalid), "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(1)
            dst.setframerate(8000)
            dst.writeframes(bytes(800))
        with self.assertRaisesRegex(ValueError, "PCM16"):
            scan_wav(invalid)

    def test_bounds_and_invalid_parameters(self):
        with self.assertRaisesRegex(ValueError, "window_ms"):
            scan_wav(self.base, window_ms=0)
        for value in (float("nan"), float("inf"), -1, 0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "loudness_tolerance_db"):
                compare_wavs(self.base, [self.candidate], loudness_tolerance_db=value)
        with self.assertRaisesRegex(ValueError, "At least one"):
            compare_wavs(self.base, [])
        with self.assertRaisesRegex(ValueError, "At most 20"):
            compare_wavs(self.base, [self.candidate] * 21)
        with patch("mixlab.quality.MAX_SOURCE_FRAMES", 500):
            with self.assertRaisesRegex(ValueError, "Frames"):
                scan_wav(self.base)
        with patch("mixlab.quality.MAX_SOURCE_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                scan_wav(self.base)

    def test_cli_json_output_no_media_paths(self):
        p = subprocess.run([sys.executable, "-m", "mixlab.quality", str(self.base), str(self.candidate)],
                           capture_output=True, text=True, check=True)
        report = json.loads(p.stdout)
        self.assertEqual(report["candidates"][0]["candidate_id"], "candidate-01")
        self.assertNotIn(str(self.root), p.stdout)
        self.assertTrue(report["human_preference_test_required"])


if __name__ == "__main__":
    unittest.main()
