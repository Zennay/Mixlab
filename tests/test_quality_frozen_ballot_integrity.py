"""Cross-gate regression for genuine frozen PCM and hostile *synthetic* ballots.

This exercises the real packaged evaluator behind three different ML-07
post-rating reports. The pre-rating side-assignment check has no ballot input.
No person, music recording, licensed source or external service is involved.
"""
import copy
import json
import unittest

from mixlab.quality.assignment_balance import audit_study_assignment
from mixlab.quality.listener_position import inspect_listener_sides
from mixlab.quality.pilot_sensitivity import inspect_real_pilot
from mixlab.quality.reviewer_influence import inspect_real_reviewer_influence
from test_quality_composed_m1_gates import CombinedM1GatesTests


class FrozenBallotContractTests(unittest.TestCase):
    def setUp(self):
        self.base = CombinedM1GatesTests(
            "test_all_four_gates_accept_checksum_bound_unanimous_candidate_votes"
        )
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.generate_reviews([["candidate"] * 5 for _ in range(3)])
        self.stash = tuple(self.base.ratings)
        self.private = tuple(
            self.base.pack / filename for filename in (
                "receipt.json", "private/answer-key.json", "private/evidence.json"
            )
        )

    def post_rating_gates(self):
        b = self.base
        return (
            ("button", lambda: inspect_listener_sides(b.pack, b.ratings)),
            ("pair", lambda: inspect_real_pilot(
                b.study, b.pack, b.pinned, b.ratings)),
            ("reviewer", lambda: inspect_real_reviewer_influence(
                b.study, b.pack, b.pinned, b.ratings)),
        )

    def patch_rating(self, index, action):
        file = self.stash[index]
        data = json.loads(file.read_text(encoding="utf-8"))
        action(data)
        file.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")

    def assert_no_private_leaks(self, report):
        serialized = json.dumps(report, sort_keys=True, allow_nan=False)
        for secret in (str(self.base.root), self.base.pinned,
                       self.base.receipt["pack_id"], "synthetic-cross-gate-",
                       "trial-001", "source_hashes"):
            self.assertNotIn(secret, serialized)
        self.assertIs(report["milestone_pass"], False)

    def test_valid_ballots_remain_accepted_and_anonymized_by_all_gates(self):
        before = [file.read_bytes() for file in self.private + self.stash]
        result = audit_study_assignment(
            self.base.study, self.base.pack, self.base.pinned)
        self.assert_no_private_leaks(result)
        for _, check in self.post_rating_gates():
            self.assert_no_private_leaks(check())
        self.assertEqual(
            [file.read_bytes() for file in self.private + self.stash], before)

    def test_all_ties_are_admissible_but_never_imply_preference(self):
        self.base.generate_reviews([["Tie"] * 5 for _ in range(3)])
        reports = dict((name, check()) for name, check in self.post_rating_gates())
        for report in reports.values():
            self.assert_no_private_leaks(report)
        self.assertFalse(reports["button"]["sufficient_for_position_screen"])
        self.assertFalse(reports["pair"]["minimum_data_for_pair_reference"])
        self.assertTrue(reports["pair"]["pair_sensitivity_review_required"])
        self.assertFalse(reports["reviewer"]["sufficient_for_reviewer_influence_screen"])
        self.assertTrue(reports["reviewer"]["reviewer_influence_review_required"])

    def test_eight_invalid_ballot_conditions_refused_by_every_rating_gate(self):
        # Alter just the disposable private reviewer fixture; restore it before
        # each next mutation. The same real ten WAVs and frozen hashes remain.
        def one(index, callback):
            self.patch_rating(index, callback)

        cases = (
            ("wrong_pack", lambda: one(0, lambda d: d.__setitem__("pack_id", "f" * 64))),
            ("bad_reviewer", lambda: one(0, lambda d: d.__setitem__("reviewer", "listener 01"))),
            ("duplicate_reviewer_casefold", lambda: one(1, lambda d: d.__setitem__(
                "reviewer", "SYNTHETIC-CROSS-GATE-0"))),
            ("bool_schema", lambda: one(0, lambda d: d.__setitem__("schema_version", True))),
            ("missing_trial", lambda: one(0, lambda d: d["ratings"].pop())),
            ("duplicate_trial", lambda: one(0, lambda d: d["ratings"].__setitem__(
                1, copy.deepcopy(d["ratings"][0])))),
            ("foreign_trial", lambda: one(0, lambda d: d["ratings"][0].__setitem__(
                "trial", "trial-999"))),
            ("unknown_choice", lambda: one(0, lambda d: d["ratings"][0].__setitem__(
                "preference", "candidate"))),
        )
        frozen = [file.read_bytes() for file in self.private]
        for label, mutate in cases:
            with self.subTest(condition=label):
                self.base.generate_reviews([["candidate"] * 5 for _ in range(3)])
                mutate()
                damaged_votes = [file.read_bytes() for file in self.stash]
                for gate, check in self.post_rating_gates():
                    with self.subTest(gate=gate):
                        with self.assertRaises(ValueError) as error:
                            check()
                        for secret in (str(self.base.root), "listener 01",
                                       "synthetic-cross-gate-", "trial-999"):
                            self.assertNotIn(secret, str(error.exception))
                        self.assertEqual([p.read_bytes() for p in self.stash],
                                         damaged_votes)
                        self.assertEqual([p.read_bytes() for p in self.private],
                                         frozen)

    def test_reusing_one_ballot_path_is_never_a_second_independent_listener(self):
        self.base.ratings = [self.stash[0], self.stash[0], self.stash[2]]
        for gate, check in self.post_rating_gates():
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                check()
        self.assert_no_private_leaks(audit_study_assignment(
            self.base.study, self.base.pack, self.base.pinned))

    def test_pre_rating_assignment_cannot_certify_invalid_ballots(self):
        self.patch_rating(0, lambda d: d.__setitem__("pack_id", "f" * 64))
        pre = audit_study_assignment(self.base.study, self.base.pack, self.base.pinned)
        self.assert_no_private_leaks(pre)
        self.assertNotIn("ratings", pre)
        for gate, check in self.post_rating_gates():
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                check()


if __name__ == "__main__":
    unittest.main()
