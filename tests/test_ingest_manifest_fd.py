"""ML-02: bounded manifest JSON reads, file identity and nonblocking admission.

Pure stdlib, synthetic CLI fixture; no external music, models or network.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from mixlab.cli import fixture
from mixlab.ingest import MAX_MANIFEST_BYTES, validate_library


class ManifestFDTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mixlab-manifest-fd-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = fixture(self.root / "library")
        self.pristine = self.manifest.read_bytes()

    def test_unmodified_manifest_keeps_existing_contract(self):
        result, tracks = validate_library(self.manifest)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(self.pristine, self.manifest.read_bytes())

    def test_linked_manifest_rejected_without_dereference(self):
        link = self.root / "linked-private.json"
        link.symlink_to(self.manifest)
        with self.assertRaisesRegex(ValueError, "regular file"):
            validate_library(link)
        self.assertEqual(self.pristine, self.manifest.read_bytes())

    def test_directory_manifest_rejected(self):
        directory = self.root / "directory.json"
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, "regular file"):
            validate_library(directory)

    def test_fifo_manifest_rejected_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("POSIX FIFO test only")
        pipe = self.root / "never-open-fifo.json"
        os.mkfifo(pipe)
        # Bug: Path.stat().st_size == 0 for FIFO and read_text() blocks.
        self.assertEqual(pipe.stat().st_size, 0)
        with self.assertRaisesRegex(ValueError, "regular file"):
            validate_library(pipe)

    def test_sparse_giant_manifest_rejected_before_read(self):
        giant = self.root / "giant.json"
        with giant.open("wb") as out:
            out.seek(MAX_MANIFEST_BYTES)
            out.write(b"x")
        with self.assertRaisesRegex(ValueError, "size"):
            validate_library(giant)

    def test_empty_manifest_fails_before_json_decode(self):
        empty = self.root / "empty.json"
        empty.touch()
        with self.assertRaisesRegex(ValueError, "size"):
            validate_library(empty)

    def test_invalid_utf8_rejected_without_private_filename(self):
        private = self.root / "PRIVATE_MUSIC_FILENAME.json"
        private.write_bytes(b"\xff\xff\xff")
        with self.assertRaises(ValueError) as caught:
            validate_library(private)
        self.assertIn("UTF-8", str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))
        self.assertNotIn("PRIVATE_MUSIC_FILENAME", str(caught.exception))

    def test_same_inode_append_during_read_fails(self):
        real = os.fstat
        calls = 0
        def mutation(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                with self.manifest.open("ab") as out:
                    out.write(b" ")
            return real(fd)
        try:
            with mock.patch("mixlab.ingest.os.fstat", side_effect=mutation):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    validate_library(self.manifest)
        finally:
            self.manifest.write_bytes(self.pristine)
        self.assertEqual(calls, 2)

    def test_same_bytes_different_inode_replacement_fails(self):
        real = os.fstat
        calls = 0
        def replacement(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                temp = self.manifest.with_suffix(".replacement")
                temp.write_bytes(self.pristine)
                temp.replace(self.manifest)
            return real(fd)
        with mock.patch("mixlab.ingest.os.fstat", side_effect=replacement):
            with self.assertRaisesRegex(ValueError, "changed during"):
                validate_library(self.manifest)
        self.assertEqual(calls, 2)
        self.assertEqual(self.pristine, self.manifest.read_bytes())

    def test_manifest_reads_from_exactly_one_descriptor(self):
        from mixlab.ingest import _read_bounded_manifest
        with mock.patch("mixlab.ingest.os.fdopen", wraps=os.fdopen) as wrapper:
            self.assertEqual(_read_bounded_manifest(self.manifest),
                             self.pristine.decode("utf-8"))
        self.assertEqual(wrapper.call_count, 1)


if __name__ == "__main__":
    unittest.main()
