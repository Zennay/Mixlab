"""ML-07 independent regression for reused stereo material with one inverted channel.

No private tracks, service startup, model dependencies or source audio uploads.
This suite is intentionally separate from the concurrently edited test_quality.py.
"""
import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs, scan_wav


def write_stereo(path, frames):
    samples = array.array("h", [sample for pair in frames for sample in pair])
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())


def signal():
    return [(round(5000 * math.sin(i * 0.14)),
             round(3500 * math.sin(i * 0.19 + 0.7)))
            for i in range(9000)]  # cross 4096-frame reads


def flip(frames, side):
    return [(-l, r) if side == 0 else (l, -r) for l, r in frames]


class OneChannelPolarityQualityTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.base = self.root / "sensitive private baseline.wav"
        self.other = self.root / "sensitive private variant.wav"
        self.frames = signal()
        write_stereo(self.base, self.frames)

    def test_left_and_right_sign_flip_are_inspected_not_ranked(self):
        for side in (0, 1):
            with self.subTest(channel=side):
                write_stereo(self.other, flip(self.frames, side))
                original = self.other.read_bytes()
                result = compare_wavs(self.base, [self.other])
                row = result["candidates"][0]
                self.assertEqual(
                    "baseline", row["single_channel_polarity_inverted_pcm_of"])
                self.assertIn(
                    "single_stereo_channel_polarity_flip_inspect_for_reused_audio",
                    row["warnings"])
                self.assertIsNone(row["duplicate_pcm_of"])
                self.assertIsNone(row["polarity_inverted_pcm_of"])
                self.assertTrue(row["requires_human_review"])
                self.assertTrue(result["human_preference_test_required"])
                self.assertNotIn(str(self.root), json.dumps(result))
                self.assertNotIn("sensitive private", json.dumps(result))
                self.assertEqual(original, self.other.read_bytes())

    def test_detects_reuse_of_prior_candidate_not_source_metadata(self):
        prior = self.root / "first candidate.wav"
        # Not identical to the baseline and not an overall sign inversion.
        different = [(int(l * 0.73), int(r * 0.91)) for l, r in self.frames]
        write_stereo(prior, different)
        write_stereo(self.other, flip(different, 1))
        rows = compare_wavs(self.base, [prior, self.other])["candidates"]
        self.assertIsNone(rows[0]["single_channel_polarity_inverted_pcm_of"])
        self.assertEqual(
            "candidate-01", rows[1]["single_channel_polarity_inverted_pcm_of"])
        self.assertIsNone(rows[1]["duplicate_pcm_of"])

    def test_nonmatching_edit_and_exact_duplicate_are_not_inversion(self):
        changed = list(self.frames)
        changed[5200] = (changed[5200][0] + 1, changed[5200][1])
        write_stereo(self.other, changed)
        row = compare_wavs(self.base, [self.other])["candidates"][0]
        self.assertIsNone(row["single_channel_polarity_inverted_pcm_of"])
        write_stereo(self.other, self.frames)
        row = compare_wavs(self.base, [self.other])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["single_channel_polarity_inverted_pcm_of"])

    def test_minimum_pcm16_sample_is_never_approximated_as_exact_inversion(self):
        source = list(self.frames)
        source[4096] = (-32768, source[4096][1])
        write_stereo(self.base, source)
        # PCM16 has no +32768; a saturated transformation is not exact.
        clipped_flip = flip(source, 0)
        clipped_flip[4096] = (32767, source[4096][1])
        write_stereo(self.other, clipped_flip)
        row = compare_wavs(self.base, [self.other])["candidates"][0]
        self.assertIsNone(row["single_channel_polarity_inverted_pcm_of"])
        # The other channel remains invertible, regardless of L=-32768.
        write_stereo(self.other, flip(source, 1))
        row = compare_wavs(self.base, [self.other])["candidates"][0]
        self.assertEqual("baseline", row["single_channel_polarity_inverted_pcm_of"])

    def test_cli_only_emits_neutral_ids_and_sanitized_metrics(self):
        write_stereo(self.other, flip(self.frames, 1))
        check = subprocess.run(
            [sys.executable, "-m", "mixlab.quality", str(self.base),
             str(self.other), "--fail-on-warnings"],
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(2, check.returncode, check.stderr)
        self.assertFalse(check.stderr)
        report = json.loads(check.stdout)
        self.assertEqual("baseline", report["candidates"][0][
            "single_channel_polarity_inverted_pcm_of"])
        self.assertNotIn(str(self.root), check.stdout)
        self.assertNotIn("sensitive private", check.stdout)
        self.assertNotIn("pcm_digest", check.stdout)

    def test_mono_scanner_preserves_existing_contract(self):
        mono = self.root / "mono.wav"
        values = array.array("h", [int(5000 * math.sin(i * 0.18)) for i in range(8000)])
        if sys.byteorder != "little":
            values.byteswap()
        with wave.open(str(mono), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(values.tobytes())
        self.assertEqual(1, scan_wav(mono)["channels"])
        row = compare_wavs(mono, [mono])["candidates"][0]
        self.assertIsNone(row["single_channel_polarity_inverted_pcm_of"])
        self.assertEqual("baseline", row["duplicate_pcm_of"])


if __name__ == "__main__":
    unittest.main()
