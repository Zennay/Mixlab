"""ML-05: an editable source declaration must never erase scientific caveats.

Synthetic fixture and ratings only. No copyrighted music, listener identities,
network I/O or external packages. The frozen pack ID intentionally does not
authenticate evidence.kind or source_permission_declarations.
"""
import json
from pathlib import Path
import tempfile
import unittest

from mixlab.cli import benchmark, fixture
from mixlab.evaluation import aggregate

SYNTHETIC_CAUTION = "synthetic input cannot establish musical preference"
UNAUTHENTICATED_CAUTION = "source permission declarations are not independently authenticated"


class ProvenanceDowngradeRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="mixlab-provenance-qa-")
        cls.root = Path(cls.temporary.name)
        manifest = fixture(cls.root / "library")
        cls.pack = cls.root / "pack"
        benchmark(manifest, cls.pack, seed=17)
        cls.evidence_path = cls.pack / "private" / "evidence.json"
        cls.original_evidence = cls.evidence_path.read_bytes()
        receipt = json.loads((cls.pack / "receipt.json").read_text(encoding="utf-8"))
        key = json.loads((cls.pack / "private" / "answer-key.json").read_text(encoding="utf-8"))
        cls.rating = cls.root / "ratings.json"
        cls.rating.write_text(json.dumps({
            "schema_version": 1, "pack_id": receipt["pack_id"],
            "reviewer": "synthetic-fixture-only",
            "ratings": [{"trial": trial["trial"], "preference": "Tie"} for trial in key],
        }), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        self.evidence_path.write_bytes(self.original_evidence)

    def _assert_safe(self, report):
        self.assertIn(SYNTHETIC_CAUTION, report["limitations"])
        self.assertIn(UNAUTHENTICATED_CAUTION, report["limitations"])
        self.assertFalse(report["milestone_pass"])
        self.assertEqual(report["status"], "descriptive-only-requires-independent-human-review")
        self.assertNotIn(str(self.root), json.dumps(report["limitations"]))

    def test_original_generated_synthetic_pack_has_non_bypassable_cautions(self):
        self._assert_safe(aggregate(self.pack, [self.rating]))

    def test_forged_kind_and_missing_one_render_declaration_cannot_downgrade(self):
        before = aggregate(self.pack, [self.rating])
        evidence = json.loads(self.original_evidence)
        evidence["kind"] = "licensed-real-music"
        evidence["renders"][0]["metrics"]["source_permission_declarations"] = {}
        self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        after = aggregate(self.pack, [self.rating])
        self.assertEqual(before["pack_id"], after["pack_id"])
        self._assert_safe(after)

    def test_forging_all_sources_as_licensed_cannot_remove_scientific_caveat(self):
        evidence = json.loads(self.original_evidence)
        evidence["kind"] = "licensed-real-music"
        for render in evidence["renders"]:
            render["metrics"]["source_permission_declarations"] = {
                "a": "licensed", "b": "licensed",
            }
        self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self._assert_safe(aggregate(self.pack, [self.rating]))


if __name__ == "__main__":
    unittest.main()
