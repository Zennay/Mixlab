import copy
import json
from pathlib import Path
import tempfile
import unittest
from mixlab.cli import fixture
from mixlab.ingest import validate_library, inspect_wav, digest, pcm_blocks

class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = fixture(Path(self.temp.name) / "library")
        self.original = json.loads(self.manifest.read_text())

    def write(self, value):
        self.manifest.write_text(json.dumps(value))

    def test_compatible_fixture_and_chunked_read(self):
        _, tracks = validate_library(self.manifest)
        t = tracks["synthetic-1"]
        self.assertEqual(t["frame_count"], 128000)
        self.assertEqual(sum(len(b) for b in pcm_blocks(t["resolved_path"], 10, 1025, 128)), 2050)

    def test_reject_malformed_fields(self):
        for field, value in (("bpm", True), ("bpm", float("nan")), ("path", "../x.wav"),
                             ("path", "/tmp/a.wav"), ("path", "a\\b.wav"), ("rights", "unknown"),
                             ("provenance", " "), ("id", "../escape"), ("sha256", "bad")):
            with self.subTest(field=field, value=value):
                m = copy.deepcopy(self.original)
                m["tracks"][0][field] = value
                self.write(m)
                with self.assertRaises(ValueError):
                    validate_library(self.manifest)

    def test_duplicate_ids_and_json_keys(self):
        m = copy.deepcopy(self.original)
        m["tracks"][1]["id"] = m["tracks"][0]["id"]
        self.write(m)
        with self.assertRaises(ValueError): validate_library(self.manifest)
        self.manifest.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): validate_library(self.manifest)

    def test_hash_and_truncation(self):
        path = self.manifest.parent / self.original["tracks"][0]["path"]
        path.write_bytes(path.read_bytes()[:-2])
        with self.assertRaises(ValueError): inspect_wav(path)
        with self.assertRaises(ValueError): validate_library(self.manifest)

    def test_pair_bounds_and_types(self):
        for field, value in (("beats", True), ("beats", 64), ("a_start", -1),
                             ("a_start", 7), ("bpm", 121), ("a", ["bad"])):
            m = copy.deepcopy(self.original)
            m["pairs"][0][field] = value
            self.write(m)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_library(self.manifest)

    def test_partition_leakage_and_cross_partition_pair(self):
        m = copy.deepcopy(self.original)
        m["tracks"][0]["partition"] = "development"
        m["tracks"][1]["partition"] = "evaluation"
        self.write(m)
        with self.assertRaisesRegex(ValueError, "crosses"): validate_library(self.manifest)
        m["tracks"][1]["recording_id"] = m["tracks"][0]["id"]
        self.write(m)
        with self.assertRaisesRegex(ValueError, "leaks"): validate_library(self.manifest)

    def test_pcm_leakage_ignores_header_metadata(self):
        m = copy.deepcopy(self.original)
        source = self.manifest.parent / m["tracks"][0]["path"]
        target = self.manifest.parent / m["tracks"][1]["path"]
        target.write_bytes(source.read_bytes())
        m["tracks"][1]["sha256"] = digest(target)
        m["tracks"][0]["partition"] = "development"
        m["tracks"][1]["partition"] = "evaluation"
        self.write(m)
        with self.assertRaisesRegex(ValueError, "leaks"): validate_library(self.manifest)

    def test_symlink_escape(self):
        outside = Path(self.temp.name) / "outside.wav"
        outside.write_bytes((self.manifest.parent / "source-1.wav").read_bytes())
        link = self.manifest.parent / "escape.wav"
        link.symlink_to(outside)
        m = copy.deepcopy(self.original)
        m["tracks"][0]["path"] = "escape.wav"
        self.write(m)
        with self.assertRaises(ValueError): validate_library(self.manifest)
