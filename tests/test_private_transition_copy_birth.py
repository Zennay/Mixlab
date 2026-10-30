"""Regression: all MixLab source-verified WAV handoffs share private atomic copy."""
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from mixlab.private_transition_selection import _copy_and_verify_wav


class VerifiedWavCopyBirthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / "synthetic-only.wav"
        self.source.write_bytes(b"not-real-audio" * 12)
        self.destination = root / "private-copy.wav"
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_create_is_0600_before_first_byte_is_read(self):
        observed = []
        original_read = os.read
        def read_and_inspect(fd, size):
            if self.destination.exists():
                observed.append(stat.S_IMODE(self.destination.stat().st_mode))
            return original_read(fd, size)
        saved = os.umask(0)
        try:
            with patch("mixlab.private_transition_selection.os.read", side_effect=read_and_inspect):
                copied = _copy_and_verify_wav(self.source, self.destination, self.digest)
        finally:
            os.umask(saved)
        self.assertEqual(copied, self.source.stat().st_size)
        self.assertEqual(set(observed), {0o600})

    def test_existing_target_is_never_replaced(self):
        self.destination.write_bytes(b"rival audio")
        with self.assertRaises(FileExistsError):
            _copy_and_verify_wav(self.source, self.destination, self.digest)
        self.assertEqual(self.destination.read_bytes(), b"rival audio")

    def test_invalid_sha_rolls_back_only_own_output(self):
        with self.assertRaisesRegex(ValueError, "receipt"):
            _copy_and_verify_wav(self.source, self.destination, "0" * 64)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
