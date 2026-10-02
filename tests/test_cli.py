import json
from pathlib import Path
import tempfile
import unittest

from mixlab.cli import benchmark, fixture, validate_library


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = fixture(self.root / "library")

    def test_end_to_end_and_blinding(self):
        receipt = benchmark(self.manifest, self.root / "pack", seed=1)
        info = json.loads(receipt.read_text())
        self.assertEqual(info["render_count"], 4)
        self.assertEqual(info["trial_count"], 3)
        review = self.root / "pack/review"
        self.assertEqual(len(list(review.glob("*.wav"))), 6)
        page = (review / "index.html").read_text()
        self.assertEqual(len(info["pack_id"]), 64)
        self.assertIn(info["pack_id"], page)
        for word in ("bass_swap", "echo_exit", "hard_cut", "baseline"):
            self.assertNotIn(word, page)
        self.assertFalse((review / "answer-key.json").exists())
        key = json.loads((self.root / "pack/private/answer-key.json").read_text())
        self.assertTrue(all("baseline" in (row["A"], row["B"]) for row in key))

    def test_reject_unknown_rights_and_changed_source(self):
        data = json.loads(self.manifest.read_text())
        data["tracks"][0]["rights"] = "unknown"
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            validate_library(self.manifest)
        data["tracks"][0]["rights"] = "synthetic"
        data["tracks"][0]["sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_library(self.manifest)

    def test_reject_mismatched_bpm_and_escaping_path(self):
        data = json.loads(self.manifest.read_text())
        data["pairs"][0]["bpm"] = 121
        self.manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "equal"):
            validate_library(self.manifest)
        data["tracks"][0]["path"] = "../outside.wav"
        self.manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "within"):
            validate_library(self.manifest)

    def test_existing_pack_is_never_overwritten(self):
        (self.root / "existing").mkdir()
        with self.assertRaises(FileExistsError):
            benchmark(self.manifest, self.root / "existing")

    def test_invalid_pair_recipe_rejected_before_render(self):
        data = json.loads(self.manifest.read_text())
        data["pairs"][0]["beats"] = True
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            benchmark(self.manifest, self.root / "bad-pack")
        self.assertFalse((self.root / "bad-pack").exists())

    def test_segment_bounds_rejected_before_render(self):
        data = json.loads(self.manifest.read_text())
        data["pairs"][0]["a_start"] = 7
        self.manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "too short"):
            benchmark(self.manifest, self.root / "bad-pack")
        self.assertFalse((self.root / "bad-pack").exists())


if __name__ == "__main__":
    unittest.main()
