"""Independent ML-07 family-selection risk / multiplicity regressions.

All files are synthetic. The real integration tests use MixLab's existing
checksum-bound five-pair WAV fixture, not fabricated aggregate() results.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from mixlab.quality.family_sensitivity import (
    FamilySensitivityError, _sign_tail, inspect_family_sensitivity,
    inspect_real_families,
)


def summary(signs, families=None, reviewers=3):
    if families is None:
        families = ["bass_swap", "echo_exit", "hard_cut"] * 4
    rows = []
    for i, sign in enumerate(signs):
        values = {"candidate": 0, "baseline": 0, "ties": 0,
                  "both_unusable": 0}
        values[{"win": "candidate", "loss": "baseline",
                "tie": "ties", "bad": "both_unusable"}[sign]] = reviewers
        rows.append({"pair": f"private-pair-{i:02d}",
                     "candidate_family": families[i], **values})
    return {
        "reviewers": reviewers, "trials": len(signs),
        "per_pair_family": rows, "audio_confounds": [],
        "counts": {key: sum(row[key] for row in rows)
                   for key in ("candidate", "baseline", "ties", "both_unusable")},
        "milestone_pass": False,
    }


class PureFamilySensitivityTests(unittest.TestCase):
    def test_three_balanced_families_all_five_candidates_never_pass_m1(self):
        report = inspect_family_sensitivity(summary(["win"] * 5))
        self.assertEqual(report["represented_family_count"], 3)
        self.assertFalse(report["milestone_pass"])
        self.assertTrue(report["family_sensitivity_review_required"])
        self.assertFalse(report["any_robust_nominal_family_reference"])
        self.assertEqual(5, sum(r["pair_count"] for r in report["anonymous_family_strata"]))
        self.assertNotIn("private-pair", json.dumps(report))
        self.assertNotIn("bass_swap", json.dumps(report))
        self.assertFalse(report["musical_preference_proven"])

    def test_opposite_family_pattern_hidden_in_positive_overall_vote(self):
        groups = ["bass_swap"] * 7 + ["echo_exit"] * 2 + ["hard_cut"]
        report = inspect_family_sensitivity(
            summary(["win"] * 7 + ["loss"] * 2 + ["tie"], groups))
        self.assertTrue(report["opposing_family_directions_review"])
        self.assertTrue(report["family_sensitivity_review_required"])
        self.assertFalse(report["milestone_pass"])
        self.assertEqual(3, report["represented_family_count"])

    def test_six_unanimous_pairs_nominal_reference_fails_leave_one_out(self):
        groups = ["bass_swap"] * 6 + ["echo_exit"] * 2
        report = inspect_family_sensitivity(
            summary(["win"] * 6 + ["tie"] * 2, groups))
        first = report["anonymous_family_strata"][0]
        self.assertEqual(6, first["decisive_pair_count"])
        self.assertAlmostEqual(first["familywise_adjusted_reference"], 3 / 64)
        self.assertAlmostEqual(
            first["worst_leave_one_pair_out_adjusted_reference"], 3 / 32)
        self.assertFalse(first["robust_nominal_family_reference"])

    def test_seven_unanimous_pairs_have_descriptive_signal_but_no_proven_claim(self):
        groups = ["bass_swap"] * 7 + ["echo_exit"] * 2 + ["hard_cut"]
        report = inspect_family_sensitivity(summary(["win"] * 10, groups))
        self.assertTrue(report["anonymous_family_strata"][0]["robust_nominal_family_reference"])
        self.assertTrue(report["unequal_family_coverage_review"])
        self.assertTrue(report["family_sensitivity_review_required"])
        self.assertFalse(report["listener_independence_authenticated"])
        self.assertFalse(report["milestone_pass"])

    def test_ties_unusable_and_small_reviewer_count_are_not_independent_wins(self):
        record = summary(["win", "win", "tie", "bad", "loss"], reviewers=2)
        report = inspect_family_sensitivity(record)
        self.assertEqual(5, report["frozen_pair_count"])
        self.assertEqual(2, report["reviewer_file_count"])
        self.assertEqual(2, sum(r["tie_or_unusable_pairs"]
                                for r in report["anonymous_family_strata"]))
        self.assertTrue(all(not r["sufficient_for_family_reference"]
                            for r in report["anonymous_family_strata"]))
        self.assertFalse(report["any_robust_nominal_family_reference"])

    def test_exact_binomial_tails_not_reviewer_click_pseudoreplication(self):
        self.assertAlmostEqual(_sign_tail(5, 5), 1 / 32)
        self.assertAlmostEqual(_sign_tail(4, 5), 6 / 32)
        self.assertAlmostEqual(_sign_tail(0, 5), 1)
        self.assertIsNone(_sign_tail(0, 0))
        # Not 15 supposedly independent observations from three raters.
        data = summary(["win"] * 5, reviewers=3)
        report = inspect_family_sensitivity(data)
        self.assertLessEqual(
            max(r["decisive_pair_count"] for r in report["anonymous_family_strata"]), 2)

    def test_malformed_and_forged_aggregation_is_never_trusted(self):
        good = summary(["win"] * 5)
        mutations = [
            lambda d: d.update(milestone_pass=True),
            lambda d: d.update(reviewers=True),
            lambda d: d.update(trials=6),
            lambda d: d.update(audio_confounds="none"),
            lambda d: d["counts"].update(candidate=999),
            lambda d: d["counts"].update(ties=1.0),
            lambda d: d["per_pair_family"][0].update(candidate=3.0),
            lambda d: d["per_pair_family"][0].update(candidate=True),
            lambda d: d["per_pair_family"][0].update(candidate=5),
            lambda d: d["per_pair_family"][0].update(pair=""),
            lambda d: d["per_pair_family"][1].update(
                pair=d["per_pair_family"][0]["pair"]),
            lambda d: d["per_pair_family"][0].update(candidate_family="unknown"),
            lambda d: d["per_pair_family"][0].update(candidate_family=[]),
            lambda d: d["per_pair_family"][0].pop("baseline"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=str(mutate)):
                bad = copy.deepcopy(good)
                mutate(bad)
                with self.assertRaises(FamilySensitivityError):
                    inspect_family_sensitivity(bad)

    def test_definite_confounds_cannot_report_robust_reference(self):
        groups = ["bass_swap"] * 7 + ["echo_exit"] * 2 + ["hard_cut"]
        data = summary(["win"] * 10, groups)
        data["audio_confounds"] = [{"trial": "SECRET", "warnings": ["PCM"]}]
        report = inspect_family_sensitivity(data)
        self.assertTrue(report["official_audio_confounds_reported"])
        self.assertFalse(report["any_robust_nominal_family_reference"])
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertFalse(report["milestone_pass"])

    def test_missing_families_count_as_missing_evidence_not_a_perfect_experiment(self):
        record = summary(["win"] * 5, ["bass_swap"] * 5)
        report = inspect_family_sensitivity(record)
        self.assertEqual(1, report["represented_family_count"])
        self.assertTrue(report["unequal_family_coverage_review"])
        self.assertTrue(report["family_sensitivity_review_required"])
        self.assertEqual(3, report["candidate_family_space_count"])


class GenuineFrozenPackFamilyTests(unittest.TestCase):
    def setUp(self):
        from test_quality_study_binding import FrozenStudyBindingTests
        fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.pack = fixture.pack
        self.study = fixture.study
        self.pinned = fixture.pinned
        self.root = fixture.root
        key = json.loads((self.pack / "private/answer-key.json").read_text())
        receipt = json.loads((self.pack / "receipt.json").read_text())
        self.ratings = []
        for index in range(3):
            path = self.root / f"private-listener-{index}.json"
            path.write_text(json.dumps({
                "schema_version": 1, "pack_id": receipt["pack_id"],
                "reviewer": f"anon-{index}",
                "ratings": [
                    {"trial": row["trial"], "preference": (
                        "A" if row["A"] != "baseline" else "B")}
                    for row in key],
            }), encoding="utf-8")
            self.ratings.append(path)

    def audit(self):
        return inspect_real_families(
            self.study, self.pack, self.pinned, self.ratings)

    def test_real_checksum_bound_five_pair_audio_and_actual_aggregator(self):
        report = self.audit()
        self.assertEqual(report["frozen_pair_count"], 5)
        self.assertEqual(report["reviewer_file_count"], 3)
        self.assertTrue(report["family_sensitivity_review_required"])
        self.assertFalse(report["milestone_pass"])
        output = json.dumps(report)
        for secret in (str(self.root), self.pinned, "private-listener",
                       "synthetic-alignment"):
            self.assertNotIn(secret, output)

    def test_study_id_and_real_pcm_byte_mutations_cannot_pass(self):
        with self.assertRaises(FamilySensitivityError):
            inspect_real_families(self.study, self.pack, "f" * 64, self.ratings)
        wav = self.pack / "review/trial-001-A.wav"
        raw = bytearray(wav.read_bytes())
        raw[-2] ^= 0x01
        wav.write_bytes(raw)
        with self.assertRaises(FamilySensitivityError):
            self.audit()

    def test_actual_aggregate_family_relabel_is_rejected(self):
        from mixlab.evaluation import aggregate
        original = aggregate(self.pack, self.ratings)
        original["per_pair_family"][0]["candidate_family"] = "hard_cut"
        with patch("mixlab.quality.family_sensitivity.aggregate", return_value=original):
            with self.assertRaises(FamilySensitivityError):
                self.audit()

    def test_aggregator_rejects_incomplete_reviewer_submission(self):
        path = self.ratings[0]
        vote = json.loads(path.read_text())
        vote["ratings"].pop()
        path.write_text(json.dumps(vote), encoding="utf-8")
        with self.assertRaises(FamilySensitivityError):
            self.audit()

    def test_valid_real_cli_returns_hold_and_no_private_identity(self):
        command = [
            sys.executable, "-m", "mixlab.quality.family_sensitivity",
            str(self.study), str(self.pack), *map(str, self.ratings),
            "--expected-study-id", self.pinned,
        ]
        run = subprocess.run(command, capture_output=True, text=True, timeout=25)
        self.assertEqual(run.returncode, 3, run.stderr)
        self.assertFalse(json.loads(run.stdout)["milestone_pass"])
        for secret in (str(self.root), self.pinned, "private-listener"):
            self.assertNotIn(secret, run.stdout + run.stderr)

    def test_invalid_paths_and_unknown_cli_flags_are_redacted(self):
        unknown = self.root / "SUPER_SECRET_AB_TEST" / "missing.json"
        command = [
            sys.executable, "-m", "mixlab.quality.family_sensitivity",
            str(unknown), str(self.pack), str(self.ratings[0]),
            "--expected-study-id", self.pinned,
        ]
        for extra in ([], ["--SUPER_SECRET_UNKNOWN_FLAG"]):
            with self.subTest(extra=extra):
                run = subprocess.run(command + extra, capture_output=True, text=True, timeout=8)
                self.assertEqual(run.returncode, 2)
                self.assertNotIn(str(self.root), run.stdout + run.stderr)
                self.assertNotIn("SUPER_SECRET", run.stdout + run.stderr)
                self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
