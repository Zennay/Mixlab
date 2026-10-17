"""ML-07 private WAV fd binding / mutation admission regression.

No non-synthetic audio. Mutations are isolated inside temporary files only.
"""
from array import array
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import MAX_SOURCE_BYTES, compare_wavs, scan_wav


def write_wav(path, *, amplitude=2100, channels=2):
    samples = array("h", [
        int(amplitude * ((i % 31) - 15) / 15)
        for i in range(4099) for _ in range(channels)
    ])
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(8000)
        target.writeframes(samples.tobytes())


class PrivateSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mixlab-private-fd-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.private = self.root / "sensitive-artist-original.wav"
        self.other = self.root / "sensitive-artist-other.wav"
        write_wav(self.private)
        write_wav(self.other)

    def test_verified_regular_source_remains_usable_and_unchanged(self):
        before = self.private.read_bytes()
        self.assertEqual(4099, scan_wav(self.private)["frames"])
        self.assertEqual("baseline", compare_wavs(
            self.private, [self.other])["candidates"][0]["duplicate_pcm_of"])
        self.assertEqual(before, self.private.read_bytes())

    def test_decoder_receives_the_exact_verified_open_file_handle(self):
        # The previous double-open implementation handed wave.open a fresh
        # filename after RIFF inspection, permitting a pathname-swap gap.
        native = wave.open
        calls = []

        def intercept(source, mode="rb"):
            self.assertEqual("rb", mode)
            self.assertTrue(hasattr(source, "fileno"))
            self.assertTrue(stat.S_ISREG(os.fstat(source.fileno()).st_mode))
            calls.append(os.fstat(source.fileno()).st_ino)
            return native(source, mode)

        with patch("mixlab.quality.private_source.wave.open", side_effect=intercept):
            self.assertEqual(4099, scan_wav(self.private)["frames"])
        self.assertEqual(1, len(calls))
        self.assertEqual(os.stat(self.private).st_ino, calls[0])

    def test_pathname_replacement_between_header_and_decoder_does_not_switch_audio(self):
        native = wave.open
        old = self.root / "original-moved.wav"
        malicious = b"RIFX" + b"\x00" * 60
        used = []

        def change_path(source, mode="rb"):
            used.append(os.fstat(source.fileno()).st_ino)
            self.private.rename(old)
            self.private.write_bytes(malicious)
            return native(source, mode)

        with patch("mixlab.quality.private_source.wave.open", side_effect=change_path):
            # Renaming the opened inode updates ctime. The verified handle
            # is still the old file, but the post-scan mutation guard must
            # conservatively reject rather than publish a stale report.
            with self.assertRaisesRegex(ValueError, "changed during quality preflight"):
                scan_wav(self.private)
        self.assertEqual([old.stat().st_ino], used)
        self.assertEqual(malicious, self.private.read_bytes())

    def test_same_inode_mutation_during_decode_fails_closed_even_when_size_unchanged(self):
        native = wave.open
        old_bytes = self.private.read_bytes()

        def mutate(source, mode="rb"):
            # Modify one PCM16 frame *in place* after RIFF preflight.
            # The fd's size and inode remain identical; mtime/ctime change.
            with self.private.open("r+b") as writer:
                writer.seek(46)
                writer.write(b"\x7a\x61")
            return native(source, mode)

        with patch("mixlab.quality.private_source.wave.open", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during quality preflight"):
                scan_wav(self.private)
        self.assertNotEqual(old_bytes, self.private.read_bytes())
        self.assertEqual(len(old_bytes), self.private.stat().st_size)

    def test_symlink_directory_and_fifo_rejected_before_wave_decode(self):
        paths = []
        linked = self.root / "private-link.wav"
        linked.symlink_to(self.private)
        paths.append(linked)
        directory = self.root / "fake-directory.wav"
        directory.mkdir()
        paths.append(directory)
        if hasattr(os, "mkfifo"):
            fifo = self.root / "unopened-fifo.wav"
            os.mkfifo(fifo)
            paths.append(fifo)

        native = wave.open
        with patch("mixlab.quality.private_source.wave.open",
                   side_effect=AssertionError("Wave parser reached nonregular input")):
            for path in paths:
                with self.subTest(name=path.name):
                    with self.assertRaises((ValueError, OSError)):
                        scan_wav(path)
        # No attempts to read those paths into memory or follow the symlink.
        self.assertEqual(4099, scan_wav(self.private)["frames"])

    def test_sparse_oversize_file_is_denied_before_wave_decode(self):
        oversized = self.root / "oversized-private.wav"
        with oversized.open("wb") as writer:
            writer.truncate(MAX_SOURCE_BYTES + 1)
        with patch("mixlab.quality.private_source.wave.open",
                   side_effect=AssertionError("Wave opened oversized input")):
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                scan_wav(oversized)

    def test_all_stereo_fingerprints_keep_reads_bounded_at_4096_frames(self):
        # Even with the complete signed stereo/per-channel fingerprint set,
        # a quality scan cannot request a whole recording in one read.
        long_source = self.root / "long-private-stereo.wav"
        samples = array("h", [
            int(3400 * ((i % 37) - 18) / 18)
            for i in range(9003) for _ in range(2)
        ])
        if sys.byteorder != "little":
            samples.byteswap()
        with wave.open(str(long_source), "wb") as target:
            target.setnchannels(2)
            target.setsampwidth(2)
            target.setframerate(8000)
            target.writeframes(samples.tobytes())
        original = wave.Wave_read.readframes
        requested = []

        def guarded(reader, frame_count):
            self.assertGreater(frame_count, 0)
            self.assertLessEqual(frame_count, 4096)
            requested.append(frame_count)
            return original(reader, frame_count)

        with patch.object(wave.Wave_read, "readframes", guarded):
            report = compare_wavs(long_source, [long_source])
        self.assertEqual("baseline", report["candidates"][0]["duplicate_pcm_of"])
        self.assertEqual(9003, report["baseline"]["frames"])
        # 9003 frames require exactly 4096 + 4096 + 811 per side.
        self.assertEqual([4096, 4096, 811, 4096, 4096, 811], requested)

    def test_missing_file_error_does_not_reveal_secret_filename(self):
        missing = self.root / "PRIVATE_EXPERIMENTAL_TRACK_CREDS_443.wav"
        with self.assertRaises(ValueError) as captured:
            scan_wav(missing)
        self.assertNotIn("PRIVATE_EXPERIMENTAL_TRACK", str(captured.exception))
        self.assertNotIn(str(self.root), str(captured.exception))
        self.assertIn("regular file", str(captured.exception))

    def test_failure_returns_no_private_source_path(self):
        # The direct library intentionally raises a generic message; only
        # the CLI wrappers implement stdout/stderr privacy and exit codes.
        corrupted = self.private.read_bytes()
        self.private.write_bytes(b"RIFX" + corrupted[4:])
        with self.assertRaises(ValueError) as captured:
            scan_wav(self.private)
        self.assertNotIn(str(self.root), str(captured.exception))
        self.assertNotIn("sensitive-artist", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
