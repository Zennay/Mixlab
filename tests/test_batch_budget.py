"""ML-07 CPU-first aggregate workload admission: synthetic WAVs only."""
from array import array
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import compare_wavs


def fixture(path, *, frames=128, channels=2, rate=8000):
    samples = array("h", [
        int(1200 * ((i % 29) - 14) / 14)
        for i in range(frames) for _ in range(channels)
    ])
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(2)
        dst.setframerate(rate)
        dst.writeframes(samples.tobytes())


class BatchAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ml07-private-budget-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "SECRET_artist_baseline.wav"
        self.other = self.root / "SECRET_artist_candidate.wav"
        fixture(self.base)
        fixture(self.other)

    def test_total_byte_budget_rejects_before_pcm_or_header_decode(self):
        import mixlab.quality as quality
        combined = self.base.stat().st_size + self.other.stat().st_size
        with patch.object(quality, "MAX_COMPARE_TOTAL_SOURCE_BYTES", combined - 1):
            with patch.object(quality, "_scan_wav_with_digest",
                              side_effect=AssertionError("PCM scanned before admission")):
                with patch.object(quality, "private_wav_format",
                                  side_effect=AssertionError("Header scanned before byte gate")):
                    with self.assertRaisesRegex(ValueError, "total input byte budget"):
                        compare_wavs(self.base, [self.other])

    def test_total_frames_rejects_before_any_pcm_decode(self):
        import mixlab.quality as quality
        with patch.object(quality, "MAX_COMPARE_TOTAL_FRAMES", 255):
            with patch.object(quality, "_scan_wav_with_digest",
                              side_effect=AssertionError("PCM scanned before frame admission")):
                with self.assertRaisesRegex(ValueError, "total PCM frame budget"):
                    compare_wavs(self.base, [self.other])

    def test_exact_boundary_is_admitted_and_report_remains_private(self):
        import mixlab.quality as quality
        combined = self.base.stat().st_size + self.other.stat().st_size
        with patch.object(quality, "MAX_COMPARE_TOTAL_SOURCE_BYTES", combined), \
             patch.object(quality, "MAX_COMPARE_TOTAL_FRAMES", 256):
            report = compare_wavs(self.base, [self.other])
        self.assertEqual("baseline", report["candidates"][0]["duplicate_pcm_of"])
        self.assertEqual(128, report["baseline"]["frames"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("SECRET_artist", json.dumps(report))
        self.assertNotIn("total_source_bytes", json.dumps(report))

    def test_twenty_short_candidates_remain_supported(self):
        import mixlab.quality as quality
        # Candidate count limits are unchanged: small jobs still admit 20.
        with patch.object(quality, "MAX_COMPARE_TOTAL_FRAMES", 21 * 128):
            report = compare_wavs(self.base, [self.other] * 20)
        self.assertEqual(20, len(report["candidates"]))
        self.assertEqual("candidate-20", report["candidates"][-1]["candidate_id"])

    def test_duplicate_input_paths_still_consume_aggregate_budget(self):
        import mixlab.quality as quality
        # Repeating an input 20 times must not sidestep CPU accounting.
        with patch.object(quality, "MAX_COMPARE_TOTAL_FRAMES", 20 * 128):
            with patch.object(quality, "_scan_wav_with_digest",
                              side_effect=AssertionError("PCM scanned before admission")):
                with self.assertRaisesRegex(ValueError, "total PCM frame budget"):
                    compare_wavs(self.base, [self.base] * 20)

    def test_input_changed_during_header_admission_refused_pre_pcm(self):
        import mixlab.quality as quality
        native = quality.private_wav_format
        seen = 0

        def changed_after_header(path, *, max_bytes):
            nonlocal seen
            result = native(path, max_bytes=max_bytes)
            seen += 1
            if seen == 1:
                with self.base.open("r+b") as handle:
                    handle.seek(46)
                    handle.write(b"\x77\x66")
            return result

        with patch.object(quality, "private_wav_format",
                          side_effect=changed_after_header):
            with patch.object(quality, "_scan_wav_with_digest",
                              side_effect=AssertionError("PCM scanned after mutation")):
                with self.assertRaisesRegex(ValueError, "changed during quality comparison"):
                    compare_wavs(self.base, [self.other])
        self.assertEqual(2, seen)

    def test_single_input_frame_limit_rejects_before_any_pcm_read(self):
        import mixlab.quality as quality
        fixture(self.base, frames=64)
        with patch.object(quality, "MAX_SOURCE_FRAMES", 100):
            with patch.object(quality, "_scan_wav_with_digest",
                              side_effect=AssertionError("PCM decoded")):
                with self.assertRaisesRegex(ValueError, "Frames must be"):
                    compare_wavs(self.base, [self.other])

    def test_trailing_candidate_duration_mismatch_fails_before_baseline_decode(self):
        import mixlab.quality as quality
        third = self.root / "PRIVATE_duration_mismatch.wav"
        fixture(third, frames=129)
        with patch.object(quality, "_scan_wav_with_digest",
                          side_effect=AssertionError("PCM decoded")):
            with self.assertRaisesRegex(ValueError, "Candidate 2 frames differs"):
                compare_wavs(self.base, [self.other, third])

    def test_sample_rate_mismatch_fails_before_any_pcm_read(self):
        import mixlab.quality as quality
        fixture(self.other, rate=16000)
        with patch.object(quality, "_scan_wav_with_digest",
                          side_effect=AssertionError("PCM decoded")):
            with self.assertRaisesRegex(ValueError, "Candidate 1 sample_rate differs"):
                compare_wavs(self.base, [self.other])

    def test_channel_layout_mismatch_fails_before_any_pcm_read(self):
        import mixlab.quality as quality
        fixture(self.other, channels=1)
        with patch.object(quality, "_scan_wav_with_digest",
                          side_effect=AssertionError("PCM decoded")):
            with self.assertRaisesRegex(ValueError, "Candidate 1 channels differs"):
                compare_wavs(self.base, [self.other])

    def test_pathless_error_on_byte_or_frame_budget_breach(self):
        import mixlab.quality as quality
        for limit, name in ((1, "MAX_COMPARE_TOTAL_SOURCE_BYTES"),
                            (1, "MAX_COMPARE_TOTAL_FRAMES")):
            with self.subTest(name=name), patch.object(quality, name, limit):
                with self.assertRaises(ValueError) as caught:
                    compare_wavs(self.base, [self.other])
                self.assertNotIn("SECRET_artist", str(caught.exception))
                self.assertNotIn(str(self.root), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
