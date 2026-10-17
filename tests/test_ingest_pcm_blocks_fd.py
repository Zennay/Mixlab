"""ML-02: private PCM16 block-reader single-FD safety, synthetic audio only."""
from array import array
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import wave

from mixlab.ingest import MAX_BYTES, pcm_blocks


class PCMBlockFDTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mixlab-pcm-fd-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "private.wav"
        self.frames = 9003
        with wave.open(str(self.path), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(b"".join(struct.pack("<hh", i % 1000, -(i % 1000))
                                     for i in range(self.frames)))
        self.original = self.path.read_bytes()

    def test_stereo_blocks_preserve_frame_bounds_and_native_pcm(self):
        blocks = list(pcm_blocks(self.path))
        self.assertEqual([len(block) for block in blocks], [8192, 8192, 1622])
        self.assertEqual(sum(len(block) for block in blocks), 2 * self.frames)
        self.assertEqual(list(blocks[0][:4]), [0, 0, 1, -1])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_partial_reader_returns_exact_requested_frames(self):
        blocks = list(pcm_blocks(self.path, start=5, frames=4097, block_frames=1024))
        self.assertEqual([len(block) for block in blocks], [2048, 2048, 2048, 2048, 2])
        self.assertEqual(list(blocks[0][:4]), [5, -5, 6, -6])
        self.assertEqual(list(pcm_blocks(self.path, start=self.frames)), [])

    def test_nonregular_fifo_symlink_directory_and_missing_do_not_block(self):
        directory = self.root / "directory.wav"
        directory.mkdir()
        link = self.root / "link.wav"
        link.symlink_to(self.path)
        sources = [directory, link, self.root / "missing.wav"]
        if hasattr(os, "mkfifo"):
            fifo = self.root / "fifo.wav"
            os.mkfifo(fifo)
            sources.append(fifo)
        for source in sources:
            with self.subTest(source=source.name), self.assertRaises(ValueError) as caught:
                list(pcm_blocks(source))
            self.assertNotIn(str(self.root), str(caught.exception))

    def test_sparse_oversize_file_fails_before_decoder(self):
        source = self.root / "oversized.wav"
        with source.open("wb") as handle:
            handle.seek(MAX_BYTES)
            handle.write(b"x")
        with self.assertRaisesRegex(ValueError, "size or identity"):
            list(pcm_blocks(source))

    def test_wrong_pcm_width_is_rejected(self):
        source = self.root / "pcm8.wav"
        with wave.open(str(source), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(1)
            out.setframerate(8000)
            out.writeframes(b"\x7f" * 128)
        with self.assertRaisesRegex(ValueError, "PCM16"):
            list(pcm_blocks(source))

    def test_declared_truncated_pcm_is_rejected(self):
        self.path.write_bytes(self.original[:-2])
        with self.assertRaises(ValueError):
            list(pcm_blocks(self.path))

    def test_valid_start_frame_validation_and_block_budget(self):
        cases = [
            {"start": True}, {"start": -1}, {"start": self.frames + 1},
            {"frames": True}, {"frames": -1}, {"frames": self.frames + 1},
            {"block_frames": 0}, {"block_frames": 65537}, {"block_frames": 1.5},
        ]
        for params in cases:
            with self.subTest(params=params), self.assertRaises(ValueError):
                list(pcm_blocks(self.path, **params))

    def test_path_replacement_after_pcm_stream_fails_closed(self):
        original_fstat = os.fstat
        calls = 0

        def inject_replace(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                new_path = self.root / "replacement.wav"
                new_path.write_bytes(self.original)
                new_path.replace(self.path)
            return original_fstat(fd)

        with mock.patch("mixlab.ingest.os.fstat", side_effect=inject_replace):
            with self.assertRaisesRegex(ValueError, "changed while reading"):
                list(pcm_blocks(self.path, frames=4097))
        self.assertEqual(calls, 2)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_same_inode_append_during_pcm_stream_fails_closed(self):
        original_fstat = os.fstat
        calls = 0

        def inject_append(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                with self.path.open("ab") as dst:
                    dst.write(b"extra")
            return original_fstat(fd)

        with mock.patch("mixlab.ingest.os.fstat", side_effect=inject_append):
            with self.assertRaisesRegex(ValueError, "changed while reading"):
                list(pcm_blocks(self.path, frames=2048))
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
