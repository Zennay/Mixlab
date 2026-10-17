"""Fail-fast ML-07 parameter validation must precede any source admission.

A malformed quality request should not touch a private path or start
a bounded multi-file WAV header pass before rejecting invalid controls.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

from mixlab.quality import compare_wavs


class QualityRequestPreflightTests(unittest.TestCase):
    def test_invalid_window_is_rejected_before_filesystem_access(self):
        private = Path("/DO_NOT_LOG_SECRET_ARTIST.wav")
        for window in (0, 19, 1001, -1, 100.0, True, False, None, "100"):
            with self.subTest(window=window):
                with patch("mixlab.quality.private_path_identity",
                           side_effect=AssertionError("source inspected before parameter check")):
                    with self.assertRaisesRegex(ValueError, "window_ms must be"):
                        compare_wavs(private, [private], window_ms=window)

    def test_invalid_rms_tolerance_still_rejected_before_source_admission(self):
        private = Path("/DO_NOT_LOG_SECRET_ARTIST.wav")
        for tolerance in (0, -1, 12.01, float("inf"), float("nan"), True, "1.5"):
            with self.subTest(tolerance=tolerance):
                with patch("mixlab.quality.private_path_identity",
                           side_effect=AssertionError("source inspected before parameter check")):
                    with self.assertRaisesRegex(ValueError, "loudness_tolerance_db must be"):
                        compare_wavs(private, [private], loudness_tolerance_db=tolerance)

    def test_no_candidates_is_rejected_without_source_read(self):
        private = Path("/DO_NOT_LOG_SECRET_ARTIST.wav")
        with patch("mixlab.quality.private_path_identity",
                   side_effect=AssertionError("source read")):
            with self.assertRaisesRegex(ValueError, "At least one candidate"):
                compare_wavs(private, [])


if __name__ == "__main__":
    unittest.main()
