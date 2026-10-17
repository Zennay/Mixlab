"""Integration tests for the existing ML-05 evaluator's bounded JSON gate.

Synthetic JSON only; no private audio, human claims, production or deployment.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from mixlab.evaluation import _load, verify_pack
from mixlab.cli import fixture, benchmark
from mixlab.ingest import MAX_BYTES
from mixlab.evaluation import json_admission


class EvaluationAdmissionIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mixlab-eval-integration-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "synthetic-rating.json"
        self.path.write_text('{"reviewer":"synthetic","ratings":[]}', encoding="utf-8")

    def test_real_evaluator_uses_strict_json_gate(self):
        self.assertEqual(_load(self.path)["reviewer"], "synthetic")
        self.path.write_text('{"ratings":[],"ratings":[1]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            _load(self.path)

    def test_symlink_and_directory_fail_closed(self):
        link = self.root / "alias.json"
        link.symlink_to(self.path)
        for path in (link, self.root):
            with self.subTest(kind=path.name), self.assertRaises(ValueError):
                _load(path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_fifo_rejected_before_blocking_read(self):
        fifo = self.root / "private-reviewer-pipe.json"
        os.mkfifo(fifo)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "regular file"):
            _load(fifo)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_oversize_rejected_without_reading_payload(self):
        with self.path.open("wb") as f:
            f.truncate(json_admission.MAX_EVALUATION_JSON_BYTES + 1)
        with mock.patch.object(json_admission, "_read_bounded",
                               side_effect=AssertionError("should not read")):
            with self.assertRaisesRegex(ValueError, "4 MiB"):
                _load(self.path)

    def test_path_replacement_rejected_in_real_evaluator(self):
        original_read = json_admission._read_bounded
        replacement = self.root / "replacement.json"
        replacement.write_bytes(self.path.read_bytes())
        def swap_after_read(fd):
            data = original_read(fd)
            os.replace(replacement, self.path)
            return data
        with mock.patch.object(json_admission, "_read_bounded",
                               side_effect=swap_after_read):
            with self.assertRaisesRegex(ValueError, "changed"):
                _load(self.path)

    def test_cli_missing_private_pack_path_never_disclosed(self):
        secret = "PRIVATE_REVIEWER_SECRET_7835"
        missing = self.root / secret / "unavailable-pack"
        proc = subprocess.run(
            [sys.executable, "-m", "mixlab.evaluation", str(missing),
             str(self.path)], capture_output=True, text=True, timeout=8)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("invalid or unavailable private input", proc.stderr)
        self.assertNotIn(secret, proc.stdout + proc.stderr)
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_cli_invalid_private_rating_path_never_disclosed(self):
        # A structurally invalid synthetic pack also exercises generic CLI
        # errors without exposing the pack's private absolute pathname.
        pack = self.root / "SECRET_RATING_SOURCE_781"
        (pack / "private").mkdir(parents=True)
        (pack / "receipt.json").write_text('{"pack_id":"placeholder"}')
        (pack / "private" / "evidence.json").write_text('{"renders":[]}')
        (pack / "private" / "answer-key.json").write_text('[]')
        proc = subprocess.run(
            [sys.executable, "-m", "mixlab.evaluation", str(pack),
             str(self.path)], capture_output=True, text=True, timeout=8)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("SECRET_RATING_SOURCE_781", proc.stdout + proc.stderr)
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class FrozenReviewAudioAdmissionTests(unittest.TestCase):
    """Frozen synthetic review WAVs must remain bounded regular inputs."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mixlab-eval-audio-")
        cls.root = Path(cls.temp.name)
        manifest = fixture(cls.root / "library")
        cls.pack = cls.root / "pack"
        benchmark(manifest, cls.pack, seed=17)
        cls.wav = cls.pack / "review" / "trial-001-A.wav"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_synthetic_frozen_pack_still_verifies(self):
        _receipt, _evidence, trials = verify_pack(self.pack)
        self.assertIn("trial-001", trials)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_replaced_review_wav_fifo_fails_before_blocking(self):
        original = self.wav.with_suffix(".original")
        self.wav.rename(original)
        try:
            os.mkfifo(self.wav)
            started = time.monotonic()
            with self.assertRaises(ValueError):
                verify_pack(self.pack)
            self.assertLess(time.monotonic() - started, 2.0)
        finally:
            self.wav.unlink()
            original.rename(self.wav)

    def test_replaced_review_wav_symlink_rejected(self):
        original = self.wav.with_suffix(".original")
        self.wav.rename(original)
        try:
            self.wav.symlink_to(original.name)
            with self.assertRaisesRegex(ValueError, "regular PCM16 WAV"):
                verify_pack(self.pack)
        finally:
            self.wav.unlink()
            original.rename(self.wav)

    def test_oversize_sparse_review_wav_refused(self):
        original = self.wav.with_suffix(".original")
        self.wav.rename(original)
        try:
            with self.wav.open("wb") as stream:
                stream.truncate(MAX_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                verify_pack(self.pack)
        finally:
            self.wav.unlink()
            original.rename(self.wav)


if __name__ == "__main__":
    unittest.main()
