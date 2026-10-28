"""Exact edge-zero-trimmed PCM checks for blind A/B; synthetic audio only."""
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs
from mixlab.quality.pcm_identity import EdgeSilencePcmFingerprint


def write_pcm(path, frames):
    channels = len(frames[0])
    values = array("h", [v for frame in frames for v in frame])
    if sys.byteorder != "little":
        values.byteswap()
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(values.tobytes())


def signal_frames(channels=2):
    samples = [(int(3100 * math.sin(i * .11 + .1)),
                int(2700 * math.sin(i * .17 + .3)))
               for i in range(7000)]
    return samples if channels == 2 else [(left,) for left, _ in samples]


def padded(content, left_zeros, total=9000):
    right_zeros = total - len(content) - left_zeros
    if right_zeros < 0:
        raise AssertionError("bad synthetic fixture")
    z = (0,) * len(content[0])
    return [z] * left_zeros + content + [z] * right_zeros


class EdgeSilencePcmQualityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ml07-private-shift-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.baseline = self.root / "SECRET_TRACK__baseline.wav"
        self.candidate = self.root / "SECRET_TRACK__candidate.wav"
        self.signal = signal_frames()
        self.original = padded(self.signal, 1000)
        write_pcm(self.baseline, self.original)

    def test_silence_padded_audio_shift_across_stream_blocks_matches_baseline(self):
        write_pcm(self.candidate, padded(self.signal, 1011))
        before = self.candidate.read_bytes()
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["edge_silence_shifted_pcm_of"])
        self.assertIn("edge_silence_shifted_pcm_inspect_for_reused_audio", row["warnings"])
        self.assertIsNone(row["duplicate_pcm_of"])
        self.assertEqual(before, self.candidate.read_bytes())

    def test_previous_candidate_shift_detected_without_confusing_baseline(self):
        prior = self.root / "SECRET_TRACK__prior.wav"
        other = [(int(left * .8), int(right * .7)) for left, right in self.signal]
        write_pcm(prior, padded(other, 900))
        write_pcm(self.candidate, padded(other, 1100))
        rows = compare_wavs(self.baseline, [prior, self.candidate])["candidates"]
        self.assertIsNone(rows[0]["edge_silence_shifted_pcm_of"])
        self.assertEqual("candidate-01", rows[1]["edge_silence_shifted_pcm_of"])

    def test_nonzero_changed_sample_is_not_exact_shift_match(self):
        changed = padded(self.signal, 1011)
        l, r = changed[4100]
        changed[4100] = (l + 1, r)
        write_pcm(self.candidate, changed)
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertIsNone(row["edge_silence_shifted_pcm_of"])

    def test_interior_silence_must_not_be_trimmed(self):
        changed = list(self.signal)
        changed[3200] = (0, 0)
        write_pcm(self.candidate, padded(changed, 1011))
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertIsNone(row["edge_silence_shifted_pcm_of"])

    def test_raw_pcm_duplicate_stays_separate_from_edge_shift(self):
        write_pcm(self.candidate, self.original)
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["edge_silence_shifted_pcm_of"])

    def test_fully_silent_recording_does_not_claim_shift_reuse(self):
        silent = [(0, 0)] * len(self.original)
        write_pcm(self.baseline, silent)
        write_pcm(self.candidate, silent)
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["edge_silence_shifted_pcm_of"])
        write_pcm(self.candidate, self.original)
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertIsNone(row["edge_silence_shifted_pcm_of"])

    def test_mono_exact_edge_shift_is_detected(self):
        mono = signal_frames(1)
        write_pcm(self.baseline, padded(mono, 1000))
        write_pcm(self.candidate, padded(mono, 1020))
        row = compare_wavs(self.baseline, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["edge_silence_shifted_pcm_of"])
        self.assertIsNone(row["stereo_swapped_pcm_of"])

    def test_direct_digest_uses_bounded_zero_runs_and_preserves_interior(self):
        # This also covers a 4096-frame block made entirely of silence.
        z = b"\x00\x00\x00\x00"
        a = b"\x2a\x01\x01\x02"
        b = b"\x15\x01\x02\x03"
        first = EdgeSilencePcmFingerprint(2)
        second = EdgeSilencePcmFingerprint(2)
        first.update(z * 500)
        first.update(a + z * 4096)
        first.update(z * 200 + b)
        first.update(z * 120)
        second.update(z * 502 + a + z * 4296 + b + z * 118)
        self.assertEqual(first.digest(), second.digest())
        altered = EdgeSilencePcmFingerprint(2)
        altered.update(a + z * 4295 + b)
        self.assertNotEqual(first.digest(), altered.digest())
        empty = EdgeSilencePcmFingerprint(2)
        empty.update(z * 9000)
        self.assertIsNone(empty.digest())
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            empty.update(b"\x00")

    def test_anonymous_strict_cli_flags_shift_without_exposing_source(self):
        write_pcm(self.candidate, padded(self.signal, 1011))
        check = subprocess.run(
            [sys.executable, "-m", "mixlab.quality",
             str(self.baseline), str(self.candidate), "--fail-on-warnings"],
            capture_output=True, text=True, timeout=30,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(2, check.returncode)
        self.assertEqual("", check.stderr)
        report = json.loads(check.stdout)
        self.assertEqual("baseline", report["candidates"][0]["edge_silence_shifted_pcm_of"])
        self.assertNotIn("SECRET_TRACK", check.stdout)
        self.assertNotIn(str(self.root), check.stdout)
        self.assertNotIn("sha256", check.stdout)


if __name__ == "__main__":
    unittest.main()
