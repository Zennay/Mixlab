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

    def test_invalid_last_record_does_not_open_earlier_audio(self):
        # Previously even a trivial error in record 2 consumed record 1's
        # full WAV and SHA read before failing the library as a whole.
        for field, value, error in (
            ("rights", [], "Explicit permission"),
            ("provenance", " ", "Provenance"),
            ("bpm", "120", "manual bpm"),
            ("sha256", "invalid", "source checksum"),
            ("recording_id", [], "recording id"),
            ("downbeat_seconds", [], "manual downbeat"),
            ("downbeat_seconds", {}, "manual downbeat"),
            ("path", "bad\\\\path.wav", "relative POSIX"),
        ):
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(self.original))
                manifest["tracks"][-1][field] = value
                self._assert_rejected_without_audio(manifest, error)

    def test_duplicate_late_id_does_not_open_earlier_audio(self):
        manifest = json.loads(json.dumps(self.original))
        manifest["tracks"][-1]["id"] = manifest["tracks"][0]["id"]
        self._assert_rejected_without_audio(manifest, "Duplicate track id")

    def test_invalid_pair_recipes_never_open_any_audio(self):
        # Prior implementation verified every WAV before checking pairs.
        cases = (
            ("pair ID", "id", {}, "Invalid pair id"),
            ("unknown track", "a", "not-registered", "distinct registered tracks"),
            ("same track", "b", self.original["pairs"][0]["a"], "distinct registered tracks"),
            ("invalid bpm", "bpm", [], "pair bpm"),
            ("invalid beats", "beats", True, "beats must"),
            ("invalid a start", "a_start", {}, "a_start"),
            ("invalid b start", "b_start", -1, "b_start"),
            ("invalid pair source", "a", [], "pair a"),
        )
        for label, field, value, error in cases:
            with self.subTest(case=label):
                manifest = json.loads(json.dumps(self.original))
                manifest["pairs"][0][field] = value
                self._assert_rejected_without_audio(manifest, error)

    def test_invalid_pair_list_and_duplicate_ids_rejected_early(self):
        manifest = json.loads(json.dumps(self.original))
        manifest["pairs"] = []
        self._assert_rejected_without_audio(manifest, "1–10 pairs")
        manifest["pairs"] = json.loads(json.dumps(self.original["pairs"]))
        manifest["pairs"].append(json.loads(json.dumps(manifest["pairs"][0])))
        self._assert_rejected_without_audio(manifest, "Duplicate pair id")

    def test_valid_pair_preflight_preserves_fixture(self):
        manifest, tracks = validate_library(self.manifest)
        self.assertEqual(len(manifest["pairs"]), len(self.original["pairs"]))
        self.assertEqual(len(tracks), len(self.original["tracks"]))

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
