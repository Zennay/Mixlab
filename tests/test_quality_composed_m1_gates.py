"""End-to-end combined M1 QA: one genuine PCM pack, four opt-in gates.

Independent source-bound technical checks do not imply human musical
preference. This suite intentionally asserts milestone_pass=False for all.
"""
import json
import unittest
from pathlib import Path

from mixlab.quality.assignment_balance import audit_study_assignment
from mixlab.quality.listener_position import inspect_listener_sides
from mixlab.quality.pilot_sensitivity import inspect_real_pilot
from mixlab.quality.reviewer_influence import inspect_real_reviewer_influence


class CombinedM1GatesTests(unittest.TestCase):
    def setUp(self):
        # Imported locally so unittest discovery does not execute the
        # original frozen-study fixture's entire suite twice.
        from test_quality_study_binding import FrozenStudyBindingTests
        self.fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.study = self.fixture.study
        self.pack = self.fixture.pack
        self.pinned = self.fixture.pinned
        self.answers = json.loads(
            (self.pack / "private" / "answer-key.json").read_text())
        self.receipt = json.loads((self.pack / "receipt.json").read_text())
        self.ratings = []

    def generate_reviews(self, matrices):
        self.ratings = []
        for index, selections in enumerate(matrices):
            self.assertEqual(len(selections), len(self.answers))
            rows = []
            for key, choice in zip(self.answers, selections):
                if choice == "candidate":
                    candidate = (
                        key["B"] if key["A"] == "baseline" else key["A"])
                    pref = "A" if key["A"] == candidate else "B"
                elif choice == "baseline":
                    pref = "A" if key["A"] == "baseline" else "B"
                else:
                    pref = choice
                rows.append({"trial": key["trial"], "preference": pref})
            path = self.root / f"cross-gate-private-rater-{index}.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "pack_id": self.receipt["pack_id"],
                "reviewer": f"synthetic-cross-gate-{index}",
                "ratings": rows,
            }), encoding="utf-8")
            self.ratings.append(path)
        return self.ratings

    def all_four(self):
        return {
            "assignment": audit_study_assignment(self.study, self.pack, self.pinned),
            "button": inspect_listener_sides(self.pack, self.ratings),
            "pair": inspect_real_pilot(self.study, self.pack, self.pinned, self.ratings),
            "reviewer": inspect_real_reviewer_influence(
                self.study, self.pack, self.pinned, self.ratings),
        }

    def verify_privacy_and_never_passing(self, results):
        self.assertEqual(set(results), {"assignment", "button", "pair", "reviewer"})
        for name, report in results.items():
            with self.subTest(gate=name):
                self.assertFalse(report["milestone_pass"])
                raw = json.dumps(report, sort_keys=True)
                self.assertNotIn(str(self.root), raw)
                self.assertNotIn(self.receipt["pack_id"], raw)
                self.assertNotIn("synthetic-cross-gate-", raw)
                self.assertNotIn("trial-001", raw)
                self.assertNotIn("source_hashes", raw)

    def test_all_four_gates_accept_checksum_bound_unanimous_candidate_votes(self):
        self.generate_reviews([["candidate"] * 5 for _ in range(3)])
        result = self.all_four()
        self.verify_privacy_and_never_passing(result)
        self.assertEqual(result["assignment"]["trial_count"], 5)
        self.assertEqual(result["button"]["reviewer_count"], 3)
        self.assertEqual(result["pair"]["frozen_pair_count"], 5)
        self.assertEqual(result["reviewer"]["reviewer_file_count"], 3)
        self.assertAlmostEqual(
            result["pair"]["one_sided_pair_sign_reference_probability"], 1 / 32)
        self.assertAlmostEqual(
            result["pair"]["worst_leave_one_pair_out_reference_probability"], 1 / 16)
        self.assertTrue(result["pair"]["pair_sensitivity_review_required"])
        self.assertFalse(result["reviewer"]["omission_flips_candidate_plurality"])
        self.assertFalse(result["button"]["aggregate_position_dominance_review"])

    def test_all_a_answers_flag_button_position_despite_valid_pack(self):
        self.generate_reviews([["A"] * 5 for _ in range(3)])
        result = self.all_four()
        self.verify_privacy_and_never_passing(result)
        self.assertTrue(result["button"]["aggregate_position_dominance_review"])
        self.assertTrue(result["button"]["individual_position_pattern_review"])
        self.assertTrue(result["button"]["milestone_pass"] is False)

    def test_outlying_reviewer_flips_vote_plurality_without_invalidating_pcm(self):
        self.generate_reviews([
            ["candidate"] * 5,
            ["candidate"] * 3 + ["baseline"] * 2,
            ["baseline"] * 5,
        ])
        result = self.all_four()
        self.verify_privacy_and_never_passing(result)
        self.assertEqual(result["reviewer"]["full_decisive_vote_count"], 15)
        self.assertAlmostEqual(result["reviewer"]["full_candidate_preference_fraction"], 8 / 15)
        self.assertAlmostEqual(
            result["reviewer"]["min_leave_one_reviewer_out_candidate_fraction"], 3 / 10)
        self.assertTrue(result["reviewer"]["omission_flips_candidate_plurality"])
        self.assertTrue(result["reviewer"]["reviewer_influence_review_required"])
        self.assertTrue(result["pair"]["pair_sensitivity_review_required"])

    def test_corrupt_real_pcm_is_rejected_by_all_four_independently(self):
        self.generate_reviews([["candidate"] * 5 for _ in range(3)])
        wav = self.pack / "review" / "trial-001-A.wav"
        original = bytearray(wav.read_bytes())
        original[-12] ^= 0x40
        wav.write_bytes(original)
        gates = (
            lambda: audit_study_assignment(self.study, self.pack, self.pinned),
            lambda: inspect_listener_sides(self.pack, self.ratings),
            lambda: inspect_real_pilot(self.study, self.pack, self.pinned, self.ratings),
            lambda: inspect_real_reviewer_influence(
                self.study, self.pack, self.pinned, self.ratings),
        )
        for index, check in enumerate(gates):
            with self.subTest(gate=index), self.assertRaises(ValueError) as exc:
                check()
            self.assertNotIn(str(self.root), str(exc.exception))

    def test_pinned_study_id_drift_cannot_be_cleared_by_any_study_bound_gate(self):
        self.generate_reviews([["candidate"] * 5 for _ in range(3)])
        wrong = "f" * 64 if self.pinned != "f" * 64 else "0" * 64
        for name, check in (
            ("assignment", lambda: audit_study_assignment(self.study, self.pack, wrong)),
            ("pair", lambda: inspect_real_pilot(
                self.study, self.pack, wrong, self.ratings)),
            ("reviewer", lambda: inspect_real_reviewer_influence(
                self.study, self.pack, wrong, self.ratings)),
        ):
            with self.subTest(gate=name), self.assertRaises(ValueError):
                check()

    def test_unchanged_synthetic_pack_remains_frozen_before_after_all_gates(self):
        self.generate_reviews([["candidate"] * 5] * 3)
        before = {
            path.name: path.read_bytes()
            for path in (self.pack / "private" / "answer-key.json",
                         self.pack / "receipt.json",
                         self.pack / "private" / "evidence.json")
        }
        report = self.all_four()
        self.verify_privacy_and_never_passing(report)
        for path in (self.pack / "private" / "answer-key.json",
                     self.pack / "receipt.json",
                     self.pack / "private" / "evidence.json"):
            self.assertEqual(path.read_bytes(), before[path.name])


if __name__ == "__main__":
    unittest.main()
