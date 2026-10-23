"""Synthetic, real checksum-bound pack and exact pair-level reference tests.

No actual music, participants, personal data, licensing or remote audio.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from mixlab.evaluation import aggregate
from mixlab.quality.pilot_sensitivity import (
    PilotSensitivityError, inspect_pair_sensitivity, inspect_real_pilot,
    _sign_reference,
)


def synthetic_aggregate(pattern, reviewers=3, *, confounds=None):
    rows = []
    for i, direction in enumerate(pattern):
        candidate = reviewers if direction == "candidate" else 0
        baseline = reviewers if direction == "baseline" else 0
        ties = reviewers if direction == "tie" else 0
        rows.append({
            "pair": f"frozen-{i:02d}", "candidate_family":
                ("bass_swap", "echo_exit", "hard_cut")[i % 3],
            "candidate": candidate, "baseline": baseline,
            "ties": ties, "both_unusable": 0,
        })
    return {
        "reviewers": reviewers, "trials": len(pattern),
        "per_pair_family": rows,
        "counts": {
            name: sum(row[name] for row in rows)
            for name in ("candidate", "baseline", "ties", "both_unusable")
        },
        "audio_confounds": [] if confounds is None else confounds,
        "milestone_pass": False,
    }


class PairSensitivityTests(unittest.TestCase):
    def test_tiny_5_pair_unanimous_vote_is_not_robust(self):
        report = inspect_pair_sensitivity(synthetic_aggregate(["candidate"] * 5))
        self.assertEqual(report["decisive_pair_count"], 5)
        self.assertAlmostEqual(report["one_sided_pair_sign_reference_probability"], 1 / 32)
        self.assertAlmostEqual(report["worst_leave_one_pair_out_reference_probability"], 1 / 16)
        self.assertTrue(report["nominal_pair_reference_threshold_met"])
        self.assertTrue(report["one_pair_omission_removes_nominal_signal"])
        self.assertTrue(report["pair_sensitivity_review_required"])
        self.assertFalse(report["milestone_pass"])

    def test_10_pair_perfect_direction_survives_single_pair_removal_but_never_passes_m1(self):
        report = inspect_pair_sensitivity(synthetic_aggregate(["candidate"] * 10))
        self.assertEqual(report["candidate_favored_pair_count"], 10)
        self.assertAlmostEqual(report["one_sided_pair_sign_reference_probability"], 1 / 1024)
        self.assertAlmostEqual(report["worst_leave_one_pair_out_reference_probability"], 1 / 512)
        self.assertFalse(report["one_pair_omission_removes_nominal_signal"])
        self.assertFalse(report["pair_sensitivity_review_required"])
        self.assertFalse(report["human_musical_preference_proven"])
        self.assertFalse(report["listener_independence_authenticated"])
        self.assertFalse(report["milestone_pass"])

    def test_one_baseline_favored_pair_removes_nominal_reference(self):
        report = inspect_pair_sensitivity(
            synthetic_aggregate(["candidate"] * 4 + ["baseline"]))
        self.assertAlmostEqual(report["one_sided_pair_sign_reference_probability"], 6 / 32)
        self.assertFalse(report["nominal_pair_reference_threshold_met"])
        self.assertTrue(report["pair_sensitivity_review_required"])

    def test_ties_do_not_act_as_independent_confirmations(self):
        report = inspect_pair_sensitivity(
            synthetic_aggregate(["candidate"] * 4 + ["tie"] * 3))
        self.assertEqual(report["decisive_pair_count"], 4)
        self.assertEqual(report["tied_or_unusable_pair_count"], 3)
        self.assertIsNone(report["one_sided_pair_sign_reference_probability"])
        self.assertIsNone(report["worst_leave_one_pair_out_reference_probability"])
        self.assertFalse(report["minimum_data_for_pair_reference"])

    def test_reviewer_count_and_source_reuse_prevent_false_independence(self):
        for reviewer_count, reused in ((2, False), (3, True)):
            with self.subTest(reviewers=reviewer_count, reused=reused):
                report = inspect_pair_sensitivity(
                    synthetic_aggregate(["candidate"] * 10, reviewers=reviewer_count),
                    source_reuse=reused)
                self.assertIsNone(report["one_sided_pair_sign_reference_probability"])
                self.assertTrue(report["pair_sensitivity_review_required"])
                self.assertFalse(report["minimum_data_for_pair_reference"])

    def test_audio_confounds_hold_even_when_pair_sign_reference_is_strong(self):
        report = inspect_pair_sensitivity(synthetic_aggregate(
            ["candidate"] * 10, confounds=[{"trial": "trial-001", "warnings": ["level"]}]))
        self.assertTrue(report["audio_confounds_reported"])
        self.assertFalse(report["pair_sensitivity_review_required"] is False)
        self.assertNotIn("trial-001", json.dumps(report))

    def test_no_aggregate_vote_is_a_quality_pass(self):
        for n in (5, 6, 7, 8, 9, 10):
            for wins in range(n + 1):
                pattern = ["candidate"] * wins + ["baseline"] * (n - wins)
                result = inspect_pair_sensitivity(synthetic_aggregate(pattern))
                self.assertFalse(result["milestone_pass"])
                self.assertFalse(result["source_rights_independently_authenticated"])
                self.assertAlmostEqual(
                    result["one_sided_pair_sign_reference_probability"],
                    _sign_reference(wins, n))
                self.assertEqual(result["candidate_favored_pair_count"], wins)

    def test_rejects_fake_counts_bool_types_alias_pairs_and_exploration(self):
        good = synthetic_aggregate(["candidate"] * 5)
        for mutate in (
            lambda d: d.update(reviewers=True),
            lambda d: d.update(trials=4),
            lambda d: d["per_pair_family"][1].update(pair=d["per_pair_family"][0]["pair"]),
            lambda d: d["per_pair_family"][0].update(candidate=True),
            lambda d: d["per_pair_family"][0].update(candidate=100),
            lambda d: d["counts"].update(candidate=-1),
            lambda d: d.update(audio_confounds=None),
            lambda d: d.update(milestone_pass=True),
            lambda d: d["per_pair_family"].append(d["per_pair_family"][0]),
        ):
            value = copy.deepcopy(good)
            mutate(value)
            with self.subTest(case=mutate.__code__.co_firstlineno), self.assertRaises(PilotSensitivityError):
                inspect_pair_sensitivity(value)
        with self.assertRaises(PilotSensitivityError):
            inspect_pair_sensitivity(good, source_reuse="false")


class PinnedRealPackSensitivityTests(unittest.TestCase):
    def setUp(self):
        # Prevent unintentionally rediscovering the entire existing binding
        # test suite: import fixtures only within the test setUp.
        from test_quality_study_binding import FrozenStudyBindingTests
        self.fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.pack = self.fixture.root, self.fixture.pack
        self.study, self.pinned = self.fixture.study, self.fixture.pinned

    def ratings(self, decisions):
        key = json.loads((self.pack / "private" / "answer-key.json").read_text())
        receipt = json.loads((self.pack / "receipt.json").read_text())
        result = []
        for i in range(1, 4):
            rows = []
            for pair, outcome in zip(key, decisions):
                preference = (
                    ("A" if pair["A"] == outcome else "B")
                    if outcome in ("baseline", pair["B"] if pair["A"] == "baseline" else pair["A"])
                    else outcome
                )
                rows.append({"trial": pair["trial"], "preference": preference})
            path = self.root / f"synthetic-rating-{i}.json"
            path.write_text(json.dumps({
                "schema_version": 1, "pack_id": receipt["pack_id"],
                "reviewer": f"subject-{i:02d}", "ratings": rows}))
            result.append(path)
        return result

    def inspect(self, ratings):
        return inspect_real_pilot(self.study, self.pack, self.pinned, ratings)

    def test_real_pcm_and_genuine_aggregate_exposes_five_pair_fragility(self):
        receipt = json.loads((self.pack / "receipt.json").read_text())
        key = json.loads((self.pack / "private" / "answer-key.json").read_text())
        candidates = [
            pair["B"] if pair["A"] == "baseline" else pair["A"]
            for pair in key
        ]
        ratings = self.ratings(candidates)
        self.assertEqual(aggregate(self.pack, ratings)["reviewers"], 3)
        report = self.inspect(ratings)
        self.assertAlmostEqual(report["one_sided_pair_sign_reference_probability"], 1 / 32)
        self.assertAlmostEqual(report["worst_leave_one_pair_out_reference_probability"], 1 / 16)
        self.assertTrue(report["pair_sensitivity_review_required"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn(receipt["pack_id"], json.dumps(report))
        self.assertFalse(report["milestone_pass"])

    def test_real_rating_change_and_wrong_external_id_never_certify(self):
        key = json.loads((self.pack / "private" / "answer-key.json").read_text())
        candidates = [p["B"] if p["A"] == "baseline" else p["A"] for p in key]
        ratings = self.ratings(candidates)
        with self.assertRaises(PilotSensitivityError):
            inspect_real_pilot(self.study, self.pack, "f" * 64, ratings)
        vote = json.loads(ratings[0].read_text())
        vote["pack_id"] = "f" * 64
        ratings[0].write_text(json.dumps(vote))
        with self.assertRaises(PilotSensitivityError):
            self.inspect(ratings)

    def test_real_study_with_rehashed_shared_source_refuses_reference(self):
        # Reusing the same rights-free track across frozen pairs (within its
        # declared reuse ceiling) makes independent pair signs questionable.
        # This direct test only checks that the pure gate refuses to treat
        # such a layout as independent; changing an externally pinned study
        # itself is never allowed.
        report = inspect_pair_sensitivity(
            synthetic_aggregate(["candidate"] * 5), source_reuse=True)
        self.assertIsNone(report["one_sided_pair_sign_reference_probability"])
        self.assertTrue(report["pair_sensitivity_review_required"])

    def test_cli_failure_hides_private_study_path_and_unknown_arguments(self):
        private = self.root / "SECRET-PRIVATE-STUDY" / "unknown.json"
        key = json.loads((self.pack / "private" / "answer-key.json").read_text())
        candidates = [p["B"] if p["A"] == "baseline" else p["A"] for p in key]
        ratings = self.ratings(candidates)
        base = [sys.executable, "-m", "mixlab.quality.pilot_sensitivity"]
        cmd = base + [str(private), str(self.pack), *map(str, ratings),
                      "--expected-study-id", self.pinned]
        failure = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        self.assertEqual(failure.returncode, 2)
        self.assertNotIn("SECRET-PRIVATE-STUDY", failure.stderr)
        self.assertNotIn(str(self.root), failure.stdout + failure.stderr)
        bad_flag = subprocess.run(
            base + [str(self.study), str(self.pack), *map(str, ratings),
                    "--expected-study-id", self.pinned,
                    "--SECRET-TOKEN-/path"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(bad_flag.returncode, 2)
        self.assertNotIn("SECRET-TOKEN", bad_flag.stderr)

    def test_genuine_cli_reports_only_anonymous_pair_reference_and_exit_three(self):
        key = json.loads((self.pack / "private" / "answer-key.json").read_text())
        candidates = [p["B"] if p["A"] == "baseline" else p["A"] for p in key]
        rating_paths = self.ratings(candidates)
        run = subprocess.run([
            sys.executable, "-m", "mixlab.quality.pilot_sensitivity",
            str(self.study), str(self.pack), *map(str, rating_paths),
            "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 3, run.stderr)
        report = json.loads(run.stdout)
        self.assertFalse(report["milestone_pass"])
        self.assertNotIn(str(self.root), run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
