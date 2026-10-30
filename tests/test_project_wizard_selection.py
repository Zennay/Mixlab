"""Synthetic input regressions for the offline private music wizard."""
import tempfile
from pathlib import Path
import unittest

from mixlab.project_wizard import _selection, create_manifest


class ProjectWizardSelectionTests(unittest.TestCase):
    def test_same_song_cannot_be_selected_with_different_numeric_spelling(self):
        for choice in ("01,1", "1,001", "2,02", "001,1,2"):
            with self.subTest(choice=choice):
                with self.assertRaisesRegex(ValueError, "Each song"):
                    _selection(3)(choice)

    def test_distinct_song_numbers_preserve_explicit_order(self):
        self.assertEqual(_selection(3)("3,01,2"), [3, 1, 2])

    def test_private_music_directory_symlink_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            real.mkdir()
            (real / "one.wav").write_bytes(b"synthetic")
            (real / "two.wav").write_bytes(b"synthetic")
            alias = Path(temp) / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                create_manifest(
                    alias, real / "new-private.json",
                    read=lambda _: "1,2",
                    write=lambda _: None,
                )
            self.assertFalse((real / "new-private.json").exists())


if __name__ == "__main__":
    unittest.main()
