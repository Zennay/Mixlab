"""Synthetic offline private-player publication boundaries, no real audio."""
import hashlib
import json
import wave
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from mixlab.private_rehearsal_player import _copy_private_audio, create_player


class PrivatePlayerPublicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.source = root / "synthetic-input.wav"
        self.source.write_bytes(b"synthetic-not-real-media" * 12)
        self.target = root / "private-rehearsal.wav"
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_audio_is_private_at_the_first_read_not_after_chmod(self):
        original_read = os.read
        birth_modes = []
        def inspected_read(fd, length):
            if self.target.exists():
                birth_modes.append(stat.S_IMODE(self.target.stat().st_mode))
            return original_read(fd, length)
        previous = os.umask(0)
        try:
            with patch("mixlab.private_rehearsal_player.os.read", side_effect=inspected_read):
                _copy_private_audio(self.source, self.target, self.sha)
        finally:
            os.umask(previous)
        self.assertTrue(birth_modes)
        self.assertEqual(set(birth_modes), {0o600})
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_never_overwrite_unrelated_target(self):
        self.target.write_bytes(b"this-is-a-rival")
        with self.assertRaises(FileExistsError):
            _copy_private_audio(self.source, self.target, self.sha)
        self.assertEqual(self.target.read_bytes(), b"this-is-a-rival")

    def test_sha_failure_does_not_leave_private_audio_artifact(self):
        with self.assertRaisesRegex(ValueError, "receipt"):
            _copy_private_audio(self.source, self.target, "0"*64)
        self.assertFalse(self.target.exists())

    def test_entire_synthetic_player_publishes_three_private_files(self):
        # Two 1000-frame synthetic silence chapters; no real music or upload.
        with wave.open(str(self.source), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\x00\x00" * 2000)
        actual_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        receipt = {
            "schema_version": 1, "kind": "mixlab-private-gapped-rehearsal",
            "status": "human-rehearsal-preview-only", "rights_status": "unverified",
            "seamless_dj_mix": False, "rights_verified": False,
            "blind_preference_verified": False, "audio_sha256": actual_sha,
            "original_reel_receipt_sha256": "a" * 64,
            "sample_rate": 8000, "channels": 1, "frames": 2000, "gap_ms": 0,
            "chapters": [
                {"original_chapter": i, "frames": 1000, "family": "baseline",
                 "private_note": "synthetic-only", "selected_wav_sha256": "b" * 64,
                 "source_gallery_receipt_sha256": "c" * 64,
                 "human_choice_sha256": "d" * 64} for i in (1, 2)
            ],
        }
        sidecar = self.source.with_suffix(".rehearsal.json")
        sidecar.write_text(json.dumps(receipt))
        destination = self.source.parent / "private-player"
        previous = os.umask(0)
        try:
            page = create_player(self.source, destination)
        finally:
            os.umask(previous)
        self.assertEqual(page, destination / "index.html")
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        for name in ("rehearsal.wav", "index.html", "original-receipt.json"):
            item = destination / name
            self.assertTrue(item.is_file(), name)
            self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o600, name)
        self.assertEqual(hashlib.sha256((destination / "rehearsal.wav").read_bytes()).hexdigest(), actual_sha)
        self.assertIn("synthetic-only", page.read_text())
        with self.assertRaises(ValueError):
            create_player(self.source, destination)


if __name__ == "__main__":
    unittest.main()
