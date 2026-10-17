"""Only locally generated synthetic PCM; genuine five-pair frozen-pack binding."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from mixlab.quality.assignment_balance import (
    AssignmentBalanceError, audit_study_assignment, inspect_assignments,
)


class AssignmentBiasTests(unittest.TestCase):
    def setUp(self):
        # Import here so discovery does not accidentally run the entire
        # existing canonical study-binding suite a second time.
        from test_quality_study_binding import FrozenStudyBindingTests
        self.fixtures = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        self.fixtures.setUp()
        self.addCleanup(self.fixtures.doCleanups)
        self.pack = self.fixtures.pack
        self.private = self.fixtures.private
        self.study = self.fixtures.study
        self.pinned = self.fixtures.pinned

    def audit(self):
        return audit_study_assignment(self.study, self.pack, self.pinned)

    def assign(self, baseline_sides):
        """Change the *actual* blind WAV mapping, then correctly rehash pack.

        This is not merely a syntactically bogus answer key: the generic
        checksum-bound verifier must continue to accept each revised pack.
        """
        from mixlab.evaluation import verify_pack
        evidence_path = self.private / "evidence.json"
        key_path = self.private / "answer-key.json"
        receipt_path = self.pack / "receipt.json"
        rows = json.loads(key_path.read_text())
        evidence = json.loads(evidence_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(len(rows), len(baseline_sides))
        for row, baseline_label in zip(rows, baseline_sides):
            self.assertIn(baseline_label, ("A", "B"))
            existing = "A" if row["A"] == "baseline" else "B"
            if existing != baseline_label:
                a = self.pack / "review" / f"{row['trial']}-A.wav"
                b = self.pack / "review" / f"{row['trial']}-B.wav"
                contents_a, contents_b = a.read_bytes(), b.read_bytes()
                a.write_bytes(contents_b)
                b.write_bytes(contents_a)
                row["A"], row["B"] = row["B"], row["A"]
        identity = {
            "manifest": evidence["manifest_sha256"],
            "answers": rows,
            "outputs": [r["output_sha256"] for r in evidence["renders"]],
        }
        pack_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        evidence["pack_id"] = receipt["pack_id"] = pack_id
        key_path.write_text(json.dumps(rows))
        evidence_path.write_text(json.dumps(evidence))
        receipt_path.write_text(json.dumps(receipt))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)

    def test_original_synthetic_pack_has_balanced_assignments(self):
        report = self.audit()
        self.assertEqual(report["trial_count"], 5)
        self.assertFalse(report["side_assignment_review_required"])
        self.assertEqual(report["milestone_pass"], False)
        self.assertNotIn(str(self.fixtures.root), json.dumps(report))
        self.assertNotIn("baseline_A_count", report)
        self.assertNotIn("source", json.dumps(report).lower().replace("source_rights_authenticated", ""))

    def test_fully_rehashed_all_one_side_fails_closed_to_review(self):
        self.assign(["A"] * 5)
        report = self.audit()
        self.assertTrue(report["global_side_imbalance"])
        self.assertTrue(report["candidate_family_side_imbalance"])
        self.assertTrue(report["consecutive_side_streak"])
        self.assertTrue(report["side_assignment_review_required"])

    def test_balanced_total_with_early_three_trial_run_is_flagged(self):
        self.assign(["A", "A", "A", "B", "B"])
        report = self.audit()
        self.assertFalse(report["global_side_imbalance"])
        self.assertFalse(report["candidate_family_side_imbalance"])
        self.assertTrue(report["consecutive_side_streak"])

    def test_balanced_total_and_short_runs_can_hide_family_side_bias(self):
        # Families 1/4 are bass_swap; 2/5 echo_exit; 3 hard_cut.
        self.assign(["A", "B", "B", "A", "B"])
        report = self.audit()
        self.assertFalse(report["global_side_imbalance"])
        self.assertTrue(report["candidate_family_side_imbalance"])
        self.assertFalse(report["consecutive_side_streak"])

    def test_unmodified_assignment_tamper_rejected_by_real_pcm_binding(self):
        rows = json.loads((self.private / "answer-key.json").read_text())
        rows[0]["A"], rows[0]["B"] = rows[0]["B"], rows[0]["A"]
        (self.private / "answer-key.json").write_text(json.dumps(rows))
        with self.assertRaises(ValueError):
            self.audit()

    def test_wrong_external_study_commitment_never_certified(self):
        with self.assertRaises(ValueError):
            audit_study_assignment(self.study, self.pack, "0" * 64)

    def test_key_mutation_during_real_study_validation_is_rejected(self):
        from unittest import mock
        from mixlab.quality import assignment_balance as module
        original = module.verify_study_pack_binding

        def mutate(study, pack, pinned):
            result = original(study, pack, pinned)
            key = self.private / "answer-key.json"
            rows = json.loads(key.read_text())
            rows[0]["pair"] = "forged-after-verification"
            key.write_text(json.dumps(rows))
            return result

        with mock.patch.object(module, "verify_study_pack_binding", side_effect=mutate):
            with self.assertRaises(AssignmentBalanceError):
                self.audit()

    def test_rejects_malformed_keys_and_boolean_confusion(self):
        valid = [{"trial": f"trial-{i:03d}", "A": "baseline", "B": "bass_swap"}
                 for i in range(1, 6)]
        for invalid in ([], {}, valid[:-1], valid + valid * 10,
                        [dict(valid[0], A="baseline", B="baseline"), *valid[1:]],
                        [dict(valid[0], A=True), *valid[1:]],
                        [dict(valid[0], trial="SECRET_ID"), *valid[1:]]):
            with self.subTest(value=type(invalid).__name__):
                with self.assertRaises(AssignmentBalanceError):
                    inspect_assignments(invalid)

    def test_good_cli_emits_only_aggregate_flags_and_zero(self):
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.assignment_balance",
            str(self.study), str(self.pack), "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["side_assignment_review_required"])
        self.assertNotIn(str(self.fixtures.root), result.stdout + result.stderr)

    def test_skewed_cli_returns_hold_without_leaking_answer_key(self):
        self.assign(["B"] * 5)
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.assignment_balance",
            str(self.study), str(self.pack), "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertTrue(json.loads(result.stdout)["side_assignment_review_required"])
        self.assertNotIn(str(self.fixtures.root), result.stdout + result.stderr)
        self.assertNotIn("trial-001", result.stdout)

    def test_invalid_cli_private_path_is_redacted(self):
        secret = self.fixtures.root / "SECRET-MUSIC-PATH" / "study.json"
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.assignment_balance",
            str(secret), str(self.pack), "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(self.fixtures.root), result.stdout + result.stderr)
        self.assertNotIn("SECRET-MUSIC-PATH", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
