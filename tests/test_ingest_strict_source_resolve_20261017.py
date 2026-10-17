"""ML-02 source preflight regression on Python 3.14 symlink resolution.

Synthetic fixture only; no licensed/private audio or production state.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mixlab.cli import fixture
from mixlab.ingest import validate_library


class StrictSourceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ml02-resolution-")
        self.addCleanup(self.tmp.cleanup)
        self.manifest = fixture(Path(self.tmp.name) / "library")
        self.payload = json.loads(self.manifest.read_text())

    def reject_before_audio(self, raw_path):
        payload = json.loads(json.dumps(self.payload))
        payload["tracks"][-1]["path"] = raw_path
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        with mock.patch("mixlab.ingest.inspect_wav_and_digest",
                        side_effect=AssertionError("private WAV read")) as inspect:
            with self.assertRaisesRegex(ValueError, "resolved safely"):
                validate_library(self.manifest)
            inspect.assert_not_called()

    def test_self_referential_source_symlink_fails_before_audio(self):
        (self.manifest.parent / "self-cycle.wav").symlink_to("self-cycle.wav")
        self.reject_before_audio("self-cycle.wav")

    def test_two_node_symlink_cycle_fails_before_audio(self):
        (self.manifest.parent / "first-cycle.wav").symlink_to("second-cycle.wav")
        (self.manifest.parent / "second-cycle.wav").symlink_to("first-cycle.wav")
        self.reject_before_audio("first-cycle.wav")

    def test_missing_leaf_fails_schema_preflight_without_pcm(self):
        self.reject_before_audio("nonexistent-private-source.wav")


if __name__ == "__main__":
    unittest.main()
