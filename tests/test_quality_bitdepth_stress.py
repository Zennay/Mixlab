"""Maximum budget tests: generated PCM only, no music or VPS workload."""
from array import array
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import bitdepth


def make_wav(path, frames, *, rate=48000):
    block = array("h")
    for i in range(4096):
        left = 2600 + (i * 1103) % 16000
        block.extend((left, -left + 23))
    if sys.byteorder != "little":
        block.byteswap()
    pcm = block.tobytes()
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        remaining = frames
        while remaining:
            n = min(4096, remaining)
            writer.writeframesraw(pcm[:4 * n])
            remaining -= n


class MaximumResolutionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_real_eight_million_frames_group_at_exact_limit(self):
        paths = [self.root / f"synthetic-{i}.wav" for i in range(4)]
        for path in paths:
            make_wav(path, 2_000_000)
        self.assertLessEqual(sum(p.stat().st_size for p in paths), 4 * bitdepth.MAX_BYTES)
        result = bitdepth.inspect_ab(paths[0], paths[1:])
        self.assertEqual([False, False, False],
                         [row["coarse_resolution_review"] for row in result["candidates"]])
        self.assertEqual(2_000_000, result["frames_per_source"])
        for path in paths:
            self.assertNotIn(path.name, str(result))
        self.assertEqual(3, len(result["candidates"]))

    def test_over_eight_million_frames_rejected_before_any_pcm_read(self):
        paths = [self.root / f"private-{i}.wav" for i in range(8)]
        for path in paths:
            make_wav(path, 1_000_001)
        with patch.object(bitdepth, "_scan", side_effect=AssertionError("unexpected PCM read")):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(paths[0], paths[1:])

    def test_sparse_file_above_32mib_rejected_without_pcm_read(self):
        oversized = self.root / "private-huge.wav"
        with open(oversized, "wb") as handle:
            handle.truncate(bitdepth.MAX_BYTES + 1)
        good = self.root / "small.wav"
        make_wav(good, 8000)
        with patch.object(bitdepth, "_scan", side_effect=AssertionError("unexpected PCM read")):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(good, [oversized])


if __name__ == "__main__":
    unittest.main()
