"""Synthetic regression suite for optional ML-07 temporal-envelope confound QA."""
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.alignment import compare_envelopes


def make_wav(path, samples, *, rate=8000, channels=1, width=2):
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(width)
        dst.setframerate(rate)
        if width == 2:
            pcm = array("h", samples)
            if sys.byteorder != "little":
                pcm.byteswap()
            dst.writeframes(pcm.tobytes())
        else:
            dst.writeframes(bytes(samples))


def pattern():
    # Continuous, non-silent floor: first-prominent/onset and >200ms silence
    # heuristics alone cannot identify this A/B timing confound.
    points = (0.10, 0.27, 0.49, 0.85, 1.14, 1.49, 1.81)
    beats = [int(p * 8000) for p in points]
    return [25000 if any(k <= i < k + 120 for k in beats) else 2000
            for i in range(16000)]


class EnvelopeAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name) / "baseline.wav"
        self.other = Path(self.folder.name) / "candidate.wav"
        self.samples = pattern()
        make_wav(self.base, self.samples)
        make_wav(self.other, self.samples)

    def row(self):
        return compare_envelopes(self.base, [self.other])["candidates"][0]

    def test_exact_time_alignment_is_not_flagged(self):
        self.assertIs(self.row()["temporal_envelope_shift_risk"], False)
        self.assertEqual([], self.row()["warnings"])

    def test_continuous_audio_80ms_shift_detected_without_exporting_lag(self):
        offset = 640
        make_wav(self.other, self.samples[-offset:] + self.samples[:-offset])
        row = self.row()
        self.assertIs(row["temporal_envelope_shift_risk"], True)
        self.assertEqual(
            ["microtiming_envelope_shift_inspect_not_beat_alignment"], row["warnings"])
        public = json.dumps(compare_envelopes(self.base, [self.other]))
        self.assertNotIn("640", public)
        self.assertNotIn(str(self.folder.name), public)
        self.assertNotIn("sha256", public)
        self.assertNotIn("envelope_bins", public)

    def test_simple_common_gain_does_not_invent_a_shift(self):
        make_wav(self.other, [round(x * 0.8) for x in self.samples])
        self.assertIs(self.row()["temporal_envelope_shift_risk"], False)

    def test_unstructured_constant_signal_abstains_instead_of_false_clean(self):
        flat = [2000] * len(self.samples)
        make_wav(self.base, flat)
        make_wav(self.other, flat)
        row = self.row()
        self.assertIsNone(row["temporal_envelope_shift_risk"])
        self.assertEqual(["microtiming_alignment_inconclusive_inspect"], row["warnings"])

    def test_too_short_audio_abstains(self):
        make_wav(self.base, self.samples[:2400])
        make_wav(self.other, self.samples[:2400])
        self.assertIsNone(self.row()["temporal_envelope_shift_risk"])

    def test_different_frame_counts_fail_closed_before_scan(self):
        make_wav(self.other, self.samples[:-1])
        with self.assertRaises(ValueError):
            self.row()

    def test_different_channel_count_fails_closed(self):
        make_wav(self.other, [v for x in self.samples for v in (x, x)], channels=2)
        with self.assertRaises(ValueError):
            self.row()

    def test_invalid_pcm_width_fails_closed(self):
        make_wav(self.other, [128] * len(self.samples), width=1)
        with self.assertRaises(ValueError):
            self.row()

    def test_symlink_is_rejected(self):
        self.other.unlink()
        self.other.symlink_to(self.base)
        with self.assertRaises(OSError):
            self.row()

    @unittest.skipUnless(hasattr(__import__("os"), "mkfifo"), "FIFO requires POSIX")
    def test_fifo_rejected_without_waiting_for_writer(self):
        import os
        self.other.unlink()
        os.mkfifo(self.other)
        with self.assertRaises(ValueError):
            self.row()

    def test_max_eight_candidates_and_aggregate_budget(self):
        self.assertEqual(8, len(compare_envelopes(self.base, [self.other] * 8)["candidates"]))
        with self.assertRaises(ValueError):
            compare_envelopes(self.base, [self.other] * 9)

    def test_sources_are_unchanged(self):
        before = self.base.read_bytes(), self.other.read_bytes()
        compare_envelopes(self.base, [self.other])
        self.assertEqual(before, (self.base.read_bytes(), self.other.read_bytes()))

    def test_cli_paths_are_private_in_success_and_invalid_arguments(self):
        secret = "PRIVATE_AUDIO_TRACK_FILENAME"
        path = Path(self.folder.name) / (secret + ".wav")
        make_wav(path, self.samples)
        ok = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                             str(self.base), str(path)],
                            capture_output=True, text=True, timeout=20)
        self.assertEqual(0, ok.returncode)
        self.assertNotIn(secret, ok.stdout + ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["human_listening_required"])
        bad = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                              str(self.base), str(path), "--" + secret],
                             capture_output=True, text=True, timeout=20)
        self.assertEqual(2, bad.returncode)
        self.assertNotIn(secret, bad.stdout + bad.stderr)

    def test_cli_fail_on_warnings_is_bounded_and_redacted(self):
        offset = 640
        make_wav(self.other, self.samples[-offset:] + self.samples[:-offset])
        proc = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                               str(self.base), str(self.other), "--fail-on-warnings"],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(2, proc.returncode)
        self.assertNotIn(self.folder.name, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["candidates"][0]["warnings"])

    def test_cli_rejects_unreadable_path_without_disclosure(self):
        secret = "secret_source_filename"
        proc = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                               str(self.base), str(Path(self.folder.name) / secret)],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(3, proc.returncode)
        self.assertNotIn(secret, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
