"""Deterministic metamorphic proof for ML-07 exact PCM identities.

A separate oracle validates private fingerprints across arbitrary chunk layouts,
including RIFF read boundaries; only local synthetic PCM16 is ever created.
"""
from array import array
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs
from mixlab.quality.pcm_identity import EdgeSilencePcmFingerprint


def pcm_bytes(frames):
    values = array("h", (sample for frame in frames for sample in frame))
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def write_pcm16(path, frames):
    channels = len(frames[0])
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(8000)
        target.writeframes(pcm_bytes(frames))


def trimmed_oracle(frames):
    first = next((i for i, frame in enumerate(frames) if any(frame)), None)
    if first is None:
        return None
    last = next(i for i in range(len(frames) - 1, first - 1, -1) if any(frames[i]))
    return hashlib.sha256(pcm_bytes(frames[first:last + 1])).digest()


class ExactPcmMetamorphicTests(unittest.TestCase):
    def test_randomized_oracle_agrees_across_stream_chunk_boundaries(self):
        for channels in (1, 2):
            for seed in range(24):
                with self.subTest(channels=channels, seed=seed):
                    rng = random.Random(6187 + seed * 23 + channels)
                    silent = (0,) * channels
                    frames = [silent] * rng.randrange(0, 310)
                    for i in range(5300):
                        if rng.randrange(13) < 3:
                            frames.append(silent)
                        else:
                            # Include extreme PCM16 values; zeroed whole
                            # frames and nonzero interior samples are distinct.
                            frames.append(tuple(rng.choice(
                                (-32768, -32767, -3072, -1, 0, 1, 9, 3072, 32767)
                            ) for _ in range(channels)))
                    frames.extend([silent] * rng.randrange(0, 310))
                    expected = trimmed_oracle(frames)
                    raw = pcm_bytes(frames)
                    width = 2 * channels
                    for layout in ("whole", "single_frame", "randomized"):
                        stream = EdgeSilencePcmFingerprint(channels)
                        if layout == "whole":
                            stream.update(raw)
                        elif layout == "single_frame":
                            # Few frames on this path still exercise every
                            # state transition without quadratic test runtime.
                            for offset in range(0, min(len(frames), 73) * width, width):
                                stream.update(raw[offset:offset + width])
                            stream.update(raw[min(len(frames), 73) * width:])
                        else:
                            at = 0
                            while at < len(frames):
                                n = min(rng.randrange(1, 5032), len(frames) - at)
                                stream.update(raw[at * width:(at + n) * width])
                                at += n
                        self.assertEqual(expected, stream.digest())

    def test_silence_only_and_empty_updates_never_claim_audio(self):
        for channels in (1, 2):
            digest = EdgeSilencePcmFingerprint(channels)
            digest.update(b"")
            for _ in range(5):
                digest.update(bytes(4096 * 2 * channels))
            self.assertIsNone(digest.digest())
            with self.assertRaisesRegex(ValueError, "Incomplete PCM16 frame"):
                digest.update(b"\x00")
            self.assertIsNone(digest.digest())

    def test_every_exact_stereo_signed_permutation_flags_reuse(self):
        temp = tempfile.TemporaryDirectory(prefix="ml07-private-metamorphic-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        baseline = root / "PRIVATE__MUSIC_REFERENCE.wav"
        candidate = root / "PRIVATE__MUSIC_TEST.wav"
        frames = [
            (int(9000 * ((i % 37) - 18) / 18),
             int(7000 * ((i * 3 % 31) - 15) / 15))
            for i in range(5099)
        ]
        write_pcm16(baseline, frames)
        reference_bytes = baseline.read_bytes()
        transformations = (
            ("plain_swap", lambda l, r: (r, l), "stereo_swapped_pcm_of"),
            ("invert_left", lambda l, r: (-l, r), "single_channel_polarity_inverted_pcm_of"),
            ("invert_right", lambda l, r: (l, -r), "single_channel_polarity_inverted_pcm_of"),
            ("invert_both", lambda l, r: (-l, -r), "polarity_inverted_pcm_of"),
            ("swap_invert_left", lambda l, r: (-r, l), "signed_stereo_swap_pcm_of"),
            ("swap_invert_right", lambda l, r: (r, -l), "signed_stereo_swap_pcm_of"),
            ("swap_invert_both", lambda l, r: (-r, -l), "signed_stereo_swap_pcm_of"),
        )
        for label, transform, key in transformations:
            with self.subTest(transform=label):
                write_pcm16(candidate, [transform(l, r) for l, r in frames])
                before = candidate.read_bytes()
                row = compare_wavs(baseline, [candidate])["candidates"][0]
                self.assertEqual("baseline", row[key])
                self.assertIsNone(row["duplicate_pcm_of"])
                self.assertTrue(row["requires_human_review"])
                public = json.dumps(row)
                self.assertNotIn("PRIVATE__MUSIC", public)
                self.assertNotIn(str(root), public)
                self.assertNotIn("sha256", public)
                self.assertEqual(before, candidate.read_bytes())
        self.assertEqual(reference_bytes, baseline.read_bytes())


if __name__ == "__main__":
    unittest.main()
