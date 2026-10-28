"""Metamorphic RIFF chunk-layout admission tests for the private ML-07 reader.

Permitted private metadata must not change measured audio. Corrupt trailers
must fail before any PCM decoding. Fixtures are synthetic and path-private.
"""
from array import array
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import scan_wav


RATE = 8000
CHANNELS = 2
FMT = struct.pack("<HHIIHH", 1, CHANNELS, RATE, RATE * CHANNELS * 2, CHANNELS * 2, 16)
SAMPLES = [(int(6000 * ((i % 41) - 20) / 20),
            int(4500 * ((i * 7 % 43) - 21) / 21)) for i in range(5007)]


def pcm_data():
    samples = array("h", (value for frame in SAMPLES for value in frame))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def chunk(tag, payload):
    return tag + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")


def riff(*chunks):
    payload = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


class PrivateRiffMetamorphicTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ml07-PRIVATE-artist-RIFF-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "PRIVATE__song.wav"
        self.source.write_bytes(riff(chunk(b"fmt ", FMT), chunk(b"data", pcm_data())))

    def test_irrelevant_metadata_layout_does_not_change_pcm_metrics(self):
        expected = scan_wav(self.source)
        for seed in range(18):
            with self.subTest(seed=seed):
                rng = random.Random(seed + 7216)
                before_payload = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 19)))
                after_payload = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 19)))
                layout = riff(
                    chunk(b"JUNK", before_payload),
                    chunk(b"fmt ", FMT),
                    chunk(b"data", pcm_data()),
                    chunk(b"LIST", after_payload),
                )
                self.source.write_bytes(layout)
                before = self.source.read_bytes()
                self.assertEqual(expected, scan_wav(self.source))
                self.assertEqual(before, self.source.read_bytes())
                self.assertNotIn("PRIVATE__", json.dumps(scan_wav(self.source)))

    def test_trailing_second_data_chunk_rejected_without_audio_decode(self):
        original = chunk(b"data", pcm_data())
        cases = (
            chunk(b"data", b""),
            chunk(b"data", b"\0" * 4),
            chunk(b"fmt ", FMT),
        )
        for extra in cases:
            with self.subTest(extra=extra[:4]):
                self.source.write_bytes(riff(chunk(b"fmt ", FMT), original, extra))
                with patch("mixlab.quality.private_source.wave.open",
                           side_effect=AssertionError("PCM opened before RIFF rejection")):
                    with self.assertRaises(ValueError):
                        scan_wav(self.source)

    def test_bogus_trailing_chunk_extent_rejected_without_pcm_decode(self):
        wav_bytes = riff(chunk(b"fmt ", FMT), chunk(b"data", pcm_data()),
                         b"JUNK" + struct.pack("<I", 0xFFFFFFFF))
        self.source.write_bytes(wav_bytes)
        with patch("mixlab.quality.private_source.wave.open",
                   side_effect=AssertionError("PCM opened before invalid chunk rejection")):
            with self.assertRaisesRegex(ValueError, "RIFF boundary"):
                scan_wav(self.source)

    def test_chunk_count_budget_is_enforced_before_pcm(self):
        # The declared RIFF can be large within the file byte budget while
        # containing thousands of zero-byte chunks. Do not allow a slow scan.
        excessive = [chunk(b"JUNK", b"")] * 4097
        self.source.write_bytes(riff(chunk(b"fmt ", FMT), *excessive,
                                     chunk(b"data", pcm_data())))
        with patch("mixlab.quality.private_source.wave.open",
                   side_effect=AssertionError("PCM opened beyond chunk budget")):
            with self.assertRaisesRegex(ValueError, "too many chunks"):
                scan_wav(self.source)


if __name__ == "__main__":
    unittest.main()
