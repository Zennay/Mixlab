"""ML-02: schema type admission must fail before private audio I/O.

Uses only the generated synthetic fixtures; no real audio, VPS or network.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mixlab.cli import fixture
from mixlab.ingest import validate_library


class IngestPreflightTypesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mixlab-ingest-types-")
        self.addCleanup(tmp.cleanup)
        self.manifest = fixture(Path(tmp.name) / "library")
        self.original = json.loads(self.manifest.read_text())

    def _assert_rejected_without_audio(self, records, message):
        self.manifest.write_text(json.dumps(records), encoding="utf-8")
        with mock.patch("mixlab.ingest.inspect_wav_and_digest",
                        side_effect=AssertionError("PCM opened before schema gate")) as audio:
            with self.assertRaisesRegex(ValueError, message):
                validate_library(self.manifest)
            audio.assert_not_called()

    def test_invalid_rights_types_fail_closed_before_audio(self):
        for value in ([], {}, ["synthetic"], {"synthetic": True}, None,
                      False, 7, "not-permitted"):
            with self.subTest(rights=value):
                manifest = json.loads(json.dumps(self.original))
                manifest["tracks"][0]["rights"] = value
                self._assert_rejected_without_audio(
                    manifest, "Explicit permission required")

    def test_invalid_partition_types_fail_closed_before_audio(self):
        for value in ([], {}, ["development"], {"value": "development"},
                      None, True, 1, "unapproved"):
            with self.subTest(partition=value):
                manifest = json.loads(json.dumps(self.original))
                manifest["tracks"][0]["partition"] = value
                manifest["tracks"][1]["partition"] = "development"
                self._assert_rejected_without_audio(
                    manifest, "development/evaluation partition")

    def test_valid_partitioned_synthetic_fixture_still_passes(self):
        manifest = json.loads(json.dumps(self.original))
        for record in manifest["tracks"]:
            record["partition"] = "development"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        _, tracks = validate_library(self.manifest)
        self.assertEqual(len(tracks), 2)
        self.assertTrue(all(track["partition"] == "development"
                            for track in tracks.values()))


if __name__ == "__main__":
    unittest.main()
