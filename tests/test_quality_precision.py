"""Synthetic, rights-safe validation for candidate PCM16 precision regression."""
from __future__ import annotations

from array import array
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.precision import compare_precision, _scan, MAX_BYTES


def wav(path: Path, *, channels=1, frames=12000, coarse=(), silence=False,
        seed=1, rate=48000):
    state = seed
    samples = array("h")
    for _ in range(frames):
        for channel in range(channels):
            state = (1103515245 * state + 12345) & 0x7fffffff
            value = ((state >> 8) & 0xffff) - 32768
            if silence:
                value = 0
            elif channel in coarse:
                value = (value // 256) * 256
            samples.append(value)
    # Fixtures are little-endian PCM16, independent of test host byte order.
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


class PrecisionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / "private BASE.wav"
        self.b = self.root / "private CAND.wav"

    def test_detects_monophonic_8bit_grid_loss(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        result = compare_precision(self.a, self.b)
        self.assertTrue(result["candidate_precision_loss_inspect"])
        self.assertEqual(result["warnings"], ["candidate_low_bit_precision_loss_inspect"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_detects_loss_in_only_one_stereo_channel(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(1,))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_detects_loss_in_both_stereo_channels(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_no_false_positive_for_full_resolution_audio(self):
        wav(self.a, seed=1)
        wav(self.b, seed=2)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_no_false_positive_for_identical_input(self):
        wav(self.a)
        self.assertIs(compare_precision(self.a, self.a)["candidate_precision_loss_inspect"], False)

    def test_coarse_baseline_is_not_falsely_treated_as_high_resolution(self):
        wav(self.a, coarse=(0,))
        wav(self.b, coarse=(0,), seed=2)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_insufficient_silent_signal_abstains(self):
        wav(self.a)
        wav(self.b, silence=True)
        result = compare_precision(self.a, self.b)
        self.assertIsNone(result["candidate_precision_loss_inspect"])
        self.assertEqual(result["warnings"], [])

    def test_one_uninformative_stereo_channel_never_gives_false_clean(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0,), silence=True)
        self.assertIsNone(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_read_chunk_size_does_not_change_detection(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0,))
        self.assertEqual(compare_precision(self.a, self.b, chunk_frames=1),
                         compare_precision(self.a, self.b, chunk_frames=4096))
        with self.assertRaises(ValueError):
            _scan(self.a, chunk_frames=0)

    def test_mismatched_channels_and_sample_rate_are_rejected(self):
        wav(self.a)
        wav(self.b, channels=2)
        with self.assertRaises(ValueError):
            compare_precision(self.a, self.b)
        wav(self.b, rate=44100)
        with self.assertRaises(ValueError):
            compare_precision(self.a, self.b)

    def test_mismatched_frame_count_is_rejected(self):
        wav(self.a)
        wav(self.b, frames=8000)
        with self.assertRaises(ValueError):
            compare_precision(self.a, self.b)

    def test_truncated_pcm_is_rejected(self):
        wav(self.a)
        wav(self.b)
        with self.b.open("r+b") as f:
            f.truncate(1000)
        with self.assertRaises((ValueError, EOFError)):
            compare_precision(self.a, self.b)

    def test_oversize_rejected_before_scan(self):
        with self.a.open("wb") as f:
            f.truncate(MAX_BYTES + 1)
        with self.assertRaises(ValueError):
            _scan(self.a)

    @unittest.skipUnless(os.name == "posix", "POSIX no-follow/fifo guard")
    def test_symlink_and_fifo_are_rejected(self):
        wav(self.a)
        self.b.symlink_to(self.a)
        with self.assertRaises((OSError, ValueError)):
            _scan(self.b)
        self.b.unlink()
        os.mkfifo(self.b)
        with self.assertRaises((OSError, ValueError)):
            _scan(self.b)

    def test_cli_valid_json_and_no_private_path_leak_on_failure(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        cmd = [sys.executable, "-m", "mixlab.quality.precision",
               str(self.a), str(self.b)]
        good = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)["candidate_precision_loss_inspect"])
        missing = self.root / "private-secret-never-print.wav"
        for badcmd in ([*cmd[:-1], str(missing)], [*cmd, str(missing)]):
            bad = subprocess.run(badcmd, text=True, capture_output=True, timeout=20)
            self.assertEqual(bad.returncode, 3)
            self.assertNotIn(str(self.root), bad.stdout + bad.stderr)
            self.assertNotIn(missing.name, bad.stdout + bad.stderr)


if __name__ == "__main__":
    unittest.main()
