"""ML-07: exact audio reuse with BOTH zero-edge shifts and channel transforms.

These transformations can mask a reused blind A/B excerpt from the existing
separate full-PCM sign/swap and edge-trimmed-PCM detectors.
Synthetic PCM16 only; a match is a human-review warning, not music quality.
"""
from array import array
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs


def write_pcm(path, frames):
    values = array("h", (v for frame in frames for v in frame))
    if sys.byteorder != "little":
        values.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(len(frames[0]))
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(values.tobytes())


def padded(signal, left, total=8000):
    assert len(signal) + left <= total
    zero = (0,) * len(signal[0])
    return [zero] * left + signal + [zero] * (total - left - len(signal))


STEREO_TRANSFORMS = (
    ("swap", lambda l, r: (r, l)),
    ("invert_left", lambda l, r: (-l, r)),
    ("invert_right", lambda l, r: (l, -r)),
    ("invert_both", lambda l, r: (-l, -r)),
    ("swap_invert_left", lambda l, r: (-r, l)),
    ("swap_invert_right", lambda l, r: (r, -l)),
    ("swap_invert_both", lambda l, r: (-r, -l)),
)


class ShiftedTransformedPcmTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="PRIVATE_ML07_TRANSFORM_")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.base = root / "SENSITIVE__baseline.wav"
        self.candidate = root / "SENSITIVE__candidate.wav"
        self.earlier = root / "SENSITIVE__earlier.wav"
        self.stereo = [
            (int(4000 * math.sin(i * .17 + .2)) + 17,
             int(2900 * math.sin(i * .23 + .7)) + 29)
            for i in range(5201)
        ]
        write_pcm(self.base, padded(self.stereo, 1200))

    def test_all_seven_stereo_reuses_with_shift_need_inspection(self):
        original_bytes = self.base.read_bytes()
        for name, transform in STEREO_TRANSFORMS:
            with self.subTest(transform=name):
                shifted = padded([transform(l, r) for l, r in self.stereo], 1311)
                write_pcm(self.candidate, shifted)
                before = self.candidate.read_bytes()
                row = compare_wavs(self.base, [self.candidate])["candidates"][0]
                self.assertIsNone(row["duplicate_pcm_of"])
                self.assertIsNone(row["edge_silence_shifted_pcm_of"])
                self.assertIsNone(row["signed_stereo_swap_pcm_of"])
                self.assertEqual("baseline", row["edge_silence_transformed_pcm_of"])
                self.assertIn("edge_silence_transformed_pcm_inspect_for_reused_audio",
                              row["warnings"])
                self.assertTrue(row["requires_human_review"])
                serialized = json.dumps(row)
                self.assertNotIn("SENSITIVE__", serialized)
                self.assertNotIn(str(self.candidate.parent), serialized)
                self.assertNotIn("sha256", serialized)
                self.assertEqual(before, self.candidate.read_bytes())
        self.assertEqual(original_bytes, self.base.read_bytes())

    def test_mono_inverse_with_shift_detected_without_audio_leak(self):
        signal = [(l,) for l, _ in self.stereo]
        write_pcm(self.base, padded(signal, 1200))
        write_pcm(self.candidate, padded([(-l,) for (l,) in signal], 1307))
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["edge_silence_transformed_pcm_of"])
        self.assertIsNone(row["polarity_inverted_pcm_of"])

    def test_previous_distinct_candidate_is_anonymous_match(self):
        independent = [(int(l * .74), int(r * .61)) for l, r in self.stereo]
        write_pcm(self.earlier, padded(independent, 900))
        write_pcm(self.candidate, padded([(-r, l) for l, r in independent], 1005))
        rows = compare_wavs(self.base, [self.earlier, self.candidate])["candidates"]
        self.assertIsNone(rows[0]["edge_silence_transformed_pcm_of"])
        self.assertEqual("candidate-01", rows[1]["edge_silence_transformed_pcm_of"])
        self.assertNotIn("SENSITIVE__", json.dumps(rows))

    def test_changed_sample_never_claims_exact_match(self):
        shifted = padded([(-r, l) for l, r in self.stereo], 1311)
        l, r = shifted[4253]
        shifted[4253] = (l + 1, r)
        write_pcm(self.candidate, shifted)
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["edge_silence_transformed_pcm_of"])

    def test_signed_minimum_never_saturates_to_invent_identity(self):
        source = list(self.stereo)
        source[4096] = (-32768, source[4096][1])
        write_pcm(self.base, padded(source, 1200))
        # A sign-flipped -32768 is unrepresentable in PCM16. Saturation is
        # NOT an exact transform and must never be accepted as a reuse match.
        approximation = [(-l if l > -32768 else 32767, r) for l, r in source]
        write_pcm(self.candidate, padded(approximation, 1311))
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertIsNone(row["edge_silence_transformed_pcm_of"])

    def test_identical_shift_without_transform_keeps_existing_label(self):
        write_pcm(self.candidate, padded(self.stereo, 1311))
        row = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertEqual("baseline", row["edge_silence_shifted_pcm_of"])
        self.assertIsNone(row["edge_silence_transformed_pcm_of"])


if __name__ == "__main__":
    unittest.main()
