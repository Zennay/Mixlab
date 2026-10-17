"""ML-02: verified source WAV metadata and checksum must use one stable fd."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import wave

from mixlab.cli import fixture
from mixlab.ingest import digest, inspect_wav, inspect_wav_and_digest, validate_library


class IngestOneDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="mixlab-ingest-fd-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = fixture(self.root / "library")
        self.records = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.audio = self.manifest.parent / self.records["tracks"][0]["path"]

    def test_normal_metadata_and_checksum_share_valid_source(self):
        info, checksum = inspect_wav_and_digest(self.audio)
        self.assertEqual(checksum, digest(self.audio))
        self.assertEqual(info, inspect_wav(self.audio))
        self.assertEqual(info["frame_count"], 128000)
        self.assertEqual(len(validate_library(self.manifest)[1]), 2)

    def test_inflight_identical_bytes_inode_replacement_fails_manifest(self):
        """A second pathname read would falsely approve X metadata + Y hash."""
        replacement = self.audio.with_name("replacement-same-bytes.wav")
        replacement.write_bytes(self.audio.read_bytes())
        original_open = wave.open
        switched = []

        def switch_once(source, mode="rb"):
            opened = original_open(source, mode)
            if not switched:
                switched.append(True)
                os.replace(replacement, self.audio)
            return opened

        with mock.patch("mixlab.ingest.wave.open", side_effect=switch_once):
            with self.assertRaisesRegex(ValueError, "Source changed during inspection"):
                validate_library(self.manifest)
        self.assertEqual([True], switched)
        # The replacement contains the SAME exact bytes and original valid hash.
        self.assertEqual(digest(self.audio), self.records["tracks"][0]["sha256"])

    def test_inflight_same_inode_append_rejected(self):
        original_open = wave.open
        modified = []

        def append_during_decode(source, mode="rb"):
            opened = original_open(source, mode)
            if not modified:
                modified.append(True)
                with self.audio.open("ab") as handle:
                    handle.write(b"X")
            return opened

        with mock.patch("mixlab.ingest.wave.open", side_effect=append_during_decode):
            with self.assertRaisesRegex(ValueError, "Source changed during inspection"):
                inspect_wav(self.audio)
        self.assertEqual([True], modified)

    def test_final_symlink_rejected_before_reading_outside(self):
        target = self.root / "shadow.wav"
        target.write_bytes(self.audio.read_bytes())
        link = self.root / "shortcut.wav"
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "accessible regular"):
            inspect_wav_and_digest(link)
        self.assertEqual(target.read_bytes(), self.audio.read_bytes())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_fifo_input_does_not_block(self):
        pipe = self.root / "audio-pipe.wav"
        os.mkfifo(pipe)
        with self.assertRaisesRegex(ValueError, "32 MiB"):
            inspect_wav_and_digest(pipe)

    def test_directory_rejected_without_path_leak(self):
        try:
            inspect_wav_and_digest(self.root)
        except ValueError as error:
            self.assertNotIn(str(self.root), str(error))
        else:
            self.fail("Expected refusal of nonregular source")

    def test_missing_source_rejected_without_path_leak(self):
        try:
            inspect_wav_and_digest(self.root / "missing.wav")
        except ValueError as error:
            self.assertNotIn(str(self.root), str(error))
        else:
            self.fail("Expected refusal of missing WAV")


if __name__ == "__main__":
    unittest.main()
