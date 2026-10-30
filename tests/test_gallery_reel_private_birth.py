"""Real synthetic PCM16 route: private DJ gallery -> human choice -> reel."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.private_transition_gallery import create_gallery
from mixlab.private_transition_reel import create_reel


class GalleryReelPrivateBirthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def source(self, name, tone):
        path = self.root / name
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(bytes((tone, 0, tone, 0)) * (44100 * 7))
        return path

    def gallery(self, index):
        a = self.source(f"synthetic-{index}-a.wav", index + 1)
        b = self.source(f"synthetic-{index}-b.wav", index + 3)
        folder = self.root / f"gallery-{index}"
        page = create_gallery(a, b, folder, bpm=120, beats=8)
        self.assertTrue(page.is_file())
        return folder

    def choice(self, folder, name):
        bytes_ = (folder / "receipt.json").read_bytes()
        destination = self.root / name
        destination.write_text(json.dumps({
            "schema_version": 1, "kind": "mixlab-private-dj-choice",
            "human_choice_not_blind_study": True,
            "receipt_sha256": hashlib.sha256(bytes_).hexdigest(),
            "selected_family": "baseline", "note": "synthetic, not approved audio",
        }))
        return destination

    def assert_private(self, path):
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)

    def test_gallery_receipt_html_are_exclusively_private_from_birth(self):
        previous = os.umask(0)
        try:
            with patch.object(Path, "write_text", side_effect=AssertionError("write-then-chmod forbidden")):
                gallery = self.gallery(1)
        finally:
            os.umask(previous)
        self.assert_private(gallery / "receipt.json")
        self.assert_private(gallery / "index.html")
        self.assertEqual(len(list(gallery.glob("*.wav"))), 4)
        for path in gallery.glob("*.wav"):
            self.assert_private(path)
        self.assertEqual(stat.S_IMODE(gallery.stat().st_mode), 0o700)

    def test_two_source_bound_galleries_publish_private_reel(self):
        one, two = self.gallery(1), self.gallery(2)
        first = self.choice(one, "first-choice.json")
        second = self.choice(two, "second-choice.json")
        target = self.root / "reel"
        previous = os.umask(0)
        try:
            with patch.object(Path, "write_text", side_effect=AssertionError("write-then-chmod forbidden")):
                page = create_reel([(one, first), (two, second)], target)
        finally:
            os.umask(previous)
        self.assertTrue(page.is_file())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
        self.assert_private(target / "receipt.json")
        self.assert_private(target / "index.html")
        for wav in target.glob("*.wav"):
            self.assert_private(wav)
        record = json.loads((target / "receipt.json").read_bytes())
        self.assertEqual(record["chapter_count"], 2)
        self.assertEqual(record["rights_status"], "unverified")


if __name__ == "__main__":
    unittest.main()
