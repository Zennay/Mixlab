"""Synthetic security/immutability tests for the isolated ML-07 FD guard."""
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import wave

from mixlab.quality.fd_guard import MAX_BYTES, admitted_pcm16


def make_wav(path, *, frames=200, channels=1, rate=8000, width=2):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(b"\x05\x01" * frames * channels if width == 2 else b"\x01" * frames * channels * width)


class PrivateFdGuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "private-secret-track.wav"
        make_wav(self.source)

    def assert_rejected(self, path):
        with self.assertRaisesRegex(ValueError, r"Private WAV admission rejected") as ctx:
            with admitted_pcm16(path) as reader:
                reader.readframes(10)
        self.assertNotIn(str(self.root), str(ctx.exception))
        self.assertNotIn("private-secret-track", str(ctx.exception))

    def test_regular_pcm16_mono_fully_reads_immutably(self):
        original = self.source.read_bytes()
        with admitted_pcm16(self.source) as reader:
            self.assertEqual((1, 2, 8000), (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()))
            self.assertEqual(200, reader.getnframes())
            self.assertEqual(400, len(reader.readframes(200)))
        self.assertEqual(original, self.source.read_bytes())

    def test_regular_stereo_accepted(self):
        make_wav(self.source, channels=2)
        with admitted_pcm16(self.source) as reader:
            self.assertEqual(800, len(reader.readframes(200)))

    def test_symlink_rejected_without_following(self):
        alias = self.root / "alias.wav"
        alias.symlink_to(self.source)
        self.assert_rejected(alias)

    def test_fifo_rejected_without_blocking(self):
        fifo = self.root / "private-secret-pipe.wav"
        os.mkfifo(fifo)
        self.assert_rejected(fifo)

    def test_directory_and_missing_path_rejected(self):
        self.assert_rejected(self.root)
        self.assert_rejected(self.root / "missing-private.wav")

    def test_sparse_oversize_rejected_before_wave_decoding(self):
        with open(self.source, "r+b") as file:
            file.truncate(MAX_BYTES + 1)
        self.assert_rejected(self.source)

    def test_exact_maximum_byte_size_is_admissible_if_header_valid(self):
        with open(self.source, "r+b") as file:
            file.truncate(MAX_BYTES)
        with admitted_pcm16(self.source) as reader:
            self.assertEqual(200, reader.getnframes())
            self.assertEqual(400, len(reader.readframes(200)))

    def test_truncated_claimed_pcm_payload_rejected(self):
        with open(self.source, "r+b") as file:
            file.truncate(44 + 20)
        self.assert_rejected(self.source)

    def test_24bit_format_rejected(self):
        make_wav(self.source, width=3)
        self.assert_rejected(self.source)

    def test_unsupported_sample_rate_rejected(self):
        make_wav(self.source, rate=1000)
        self.assert_rejected(self.source)

    def test_more_than_two_channels_rejected(self):
        make_wav(self.source, channels=3)
        self.assert_rejected(self.source)

    def test_zero_frames_rejected(self):
        make_wav(self.source, frames=0)
        self.assert_rejected(self.source)

    def test_more_than_two_million_frames_rejected_from_header(self):
        # A sparse extension avoids allocating >4 MiB sample arrays.
        with open(self.source, "r+b") as file:
            file.seek(40)
            file.write(struct.pack("<I", 2_000_001 * 2))
            file.truncate(44 + 2_000_001 * 2)
        self.assert_rejected(self.source)

    def test_same_inode_modified_while_open_rejected(self):
        with self.assertRaisesRegex(ValueError, "admission rejected"):
            with admitted_pcm16(self.source) as reader:
                reader.readframes(4)
                with open(self.source, "r+b") as file:
                    file.seek(44)
                    file.write(b"\x04")
                os.utime(self.source, ns=(1_500_000_000_000_000_000, 1_500_000_000_000_000_000))

    def test_path_rebound_to_another_regular_inode_rejected(self):
        replacement = self.root / "replacement.wav"
        make_wav(replacement)
        with self.assertRaisesRegex(ValueError, "admission rejected"):
            with admitted_pcm16(self.source) as reader:
                reader.readframes(4)
                os.replace(replacement, self.source)

    def test_path_swapped_to_symlink_while_reading_rejected(self):
        real_file = self.root / "real.wav"
        with self.assertRaisesRegex(ValueError, "admission rejected"):
            with admitted_pcm16(self.source) as reader:
                reader.readframes(4)
                self.source.rename(real_file)
                self.source.symlink_to(real_file)

    def test_malformed_short_fmt_chunk_is_sanitized(self):
        # wave._read_fmt_chunk can surface struct.error from unpacking a
        # declared fmt chunk that contains fewer than the mandatory bytes.
        # It must never bypass the bounded path-redacted admission contract.
        payload = (b"WAVE" + b"fmt " + struct.pack("<I", 2) + b"\x01\x00"
                   + b"data" + struct.pack("<I", 8) + b"x" * 8
                   + b"\x00" * 16)
        self.source.write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)
        self.assert_rejected(self.source)

    def test_corrupt_and_tiny_headers_rejected(self):
        self.source.write_bytes(b"not a valid WAV" + b"x" * 45)
        self.assert_rejected(self.source)
        self.source.write_bytes(b"RIFF")
        self.assert_rejected(self.source)

    def test_outputs_no_private_path_or_audio_and_no_writes(self):
        original = self.source.read_bytes()
        with admitted_pcm16(self.source) as reader:
            size = len(reader.readframes(10))
        self.assertEqual(20, size)
        self.assertEqual(original, self.source.read_bytes())
        self.assertNotIn(str(self.root), json.dumps({"bytes_read": size}))


if __name__ == "__main__":
    unittest.main()
