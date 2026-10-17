"""Synthetic genuine PCM/pack/reviewer jackknife QA regression tests."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from mixlab.evaluation import aggregate
from mixlab.quality.reviewer_influence import (
    ReviewerInfluenceError, inspect_real_reviewer_influence,
)


class ReviewerInfluenceTests(unittest.TestCase):
    def setUp(self):
        # Fixture imported only inside setUp: avoids discovering its 42
        # separate existing tests as part of this focused test module.
        from test_quality_study_binding import FrozenStudyBindingTests
        self.fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.study = self.fixture.study
        self.pack = self.fixture.pack
        self.pinned = self.fixture.pinned
        self.answer_key = json.loads(
            (self.pack / "private" / "answer-key.json").read_text())
        self.pack_id = json.loads((self.pack / "receipt.json").read_text())["pack_id"]
        self.rating_paths = []

    def ballots(self, reviewer_choices):
        self.rating_paths = []
        for index, choices in enumerate(reviewer_choices):
            rows = []
            for trial, choice in zip(self.answer_key, choices):
                if choice in ("baseline", "candidate"):
                    candidate = (
                        trial["B"] if trial["A"] == "baseline" else trial["A"])
                    variant = "baseline" if choice == "baseline" else candidate
                    selected = "A" if trial["A"] == variant else "B"
                else:
                    selected = choice
                rows.append({"trial": trial["trial"], "preference": selected})
            path = self.root / f"private-reviewer-{index:02d}.json"
            path.write_text(json.dumps({
                "schema_version": 1, "pack_id": self.pack_id,
                "reviewer": f"synthetic-{index:02d}",
                "ratings": rows,
            }), encoding="utf-8")
            self.rating_paths.append(path)
        return self.rating_paths

    def inspect(self):
        return inspect_real_reviewer_influence(
            self.study, self.pack, self.pinned, self.rating_paths)

    def test_all_reviewers_agree_strongly_with_candidate(self):
        rating_paths = self.ballots([["candidate"] * 5] * 3)
        self.assertEqual(aggregate(self.pack, rating_paths)["counts"]["candidate"], 15)
        result = self.inspect()
        self.assertEqual(result["full_candidate_preference_fraction"], 1)
        self.assertEqual(result["min_leave_one_reviewer_out_candidate_fraction"], 1)
        self.assertEqual(result["max_leave_one_reviewer_out_candidate_fraction"], 1)
        self.assertEqual(result["max_absolute_reviewer_omission_fraction_shift"], 0)
        self.assertIs(result["omission_flips_candidate_plurality"], False)
        self.assertTrue(result["sufficient_for_reviewer_influence_screen"])
        self.assertFalse(result["human_musical_preference_proven"])
        self.assertFalse(result["milestone_pass"])
        raw = json.dumps(result)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn(self.pack_id, raw)
        self.assertNotIn("synthetic-00", raw)

    def test_one_reviewers_votes_can_flip_candidate_majority(self):
        self.ballots([
            ["candidate"] * 5,
            ["candidate"] * 3 + ["baseline"] * 2,
            ["baseline"] * 5,
        ])
        report = self.inspect()
        self.assertAlmostEqual(report["full_candidate_preference_fraction"], 8 / 15)
        self.assertAlmostEqual(
            report["min_leave_one_reviewer_out_candidate_fraction"], 3 / 10)
        self.assertAlmostEqual(
            report["max_leave_one_reviewer_out_candidate_fraction"], 8 / 10)
        self.assertAlmostEqual(
            report["max_absolute_reviewer_omission_fraction_shift"], 8 / 10 - 8 / 15)
        self.assertTrue(report["omission_flips_candidate_plurality"])
        self.assertTrue(report["reviewer_influence_review_required"])

    def test_one_reviewer_omission_strong_shift_without_plurality_flip(self):
        self.ballots([["candidate"] * 5,
                      ["candidate"] * 5,
                      ["baseline"] * 4 + ["candidate"]])
        report = self.inspect()
        self.assertAlmostEqual(report["full_candidate_preference_fraction"], 11 / 15)
        self.assertFalse(report["omission_flips_candidate_plurality"])
        self.assertGreaterEqual(report["max_absolute_reviewer_omission_fraction_shift"], .20)
        self.assertTrue(report["reviewer_influence_review_required"])

    def test_tied_and_unusable_votes_do_not_imply_candidate_preference(self):
        self.ballots([["Tie"] * 5,
                      ["Both unusable"] * 5,
                      ["Tie"] * 5])
        report = self.inspect()
        self.assertIsNone(report["full_candidate_preference_fraction"])
        self.assertIsNone(report["min_leave_one_reviewer_out_candidate_fraction"])
        self.assertIsNone(report["omission_flips_candidate_plurality"])
        self.assertFalse(report["sufficient_for_reviewer_influence_screen"])
        self.assertTrue(report["reviewer_influence_review_required"])

    def test_duplicate_reviewer_pseudonym_and_wrong_id_fail_closed(self):
        self.ballots([["candidate"] * 5] * 3)
        second = self.rating_paths[1]
        value = json.loads(second.read_text())
        value["reviewer"] = "SYNTHETIC-00"
        second.write_text(json.dumps(value))
        with self.assertRaises(ReviewerInfluenceError) as ctx:
            self.inspect()
        self.assertNotIn("SYNTHETIC-00", str(ctx.exception))
        value["reviewer"] = "synthetic-01"
        value["pack_id"] = "f" * 64
        second.write_text(json.dumps(value))
        with self.assertRaises(ReviewerInfluenceError):
            self.inspect()

    def test_observable_changed_vote_during_true_omission_scan_is_rejected(self):
        self.ballots([["candidate"] * 5] * 3)
        from mixlab.quality import reviewer_influence as module
        genuine = module.aggregate
        count = 0

        def changed_midrun(pack, paths):
            nonlocal count
            result = genuine(pack, paths)
            count += 1
            if count == 2:
                row = json.loads(self.rating_paths[0].read_text())
                row["ratings"][0]["preference"] = (
                    "B" if row["ratings"][0]["preference"] == "A" else "A")
                self.rating_paths[0].write_text(json.dumps(row))
            return result

        with mock.patch.object(module, "aggregate", side_effect=changed_midrun):
            with self.assertRaises(ReviewerInfluenceError):
                self.inspect()

    def test_mutating_or_conflicting_official_subset_tally_is_rejected(self):
        self.ballots([["candidate"] * 5] * 3)
        from mixlab.quality import reviewer_influence as module
        genuine = module.aggregate
        count = 0

        def fabricate_subset(pack, paths):
            nonlocal count
            result = genuine(pack, paths)
            count += 1
            if count == 2:
                result["counts"]["candidate"] -= 1
                result["counts"]["baseline"] += 1
            return result

        with mock.patch.object(module, "aggregate", side_effect=fabricate_subset):
            with self.assertRaises(ReviewerInfluenceError):
                self.inspect()

    def test_bounded_reviewers_hostile_pathlike_and_path_privacy(self):
        self.ballots([["candidate"] * 5] * 3)
        with self.assertRaises(ReviewerInfluenceError):
            inspect_real_reviewer_influence(
                self.study, self.pack, self.pinned, self.rating_paths[:2])
        with self.assertRaises(ReviewerInfluenceError):
            inspect_real_reviewer_influence(
                self.study, self.pack, self.pinned, self.rating_paths * 2)
        class Hostile:
            def __fspath__(self):
                raise RuntimeError("PRIVATE-MUSIC-STUDY-PATH")
        with self.assertRaises(ReviewerInfluenceError) as ctx:
            inspect_real_reviewer_influence(
                Hostile(), self.pack, self.pinned, self.rating_paths)
        self.assertNotIn("PRIVATE-MUSIC", str(ctx.exception))

    def test_final_rating_files_cannot_be_symlinked(self):
        self.ballots([["candidate"] * 5] * 3)
        link = self.root / "alias-reviewer.json"
        link.symlink_to(self.rating_paths[0])
        with self.assertRaises(ReviewerInfluenceError):
            inspect_real_reviewer_influence(
                self.study, self.pack, self.pinned,
                [link, *self.rating_paths[1:]])

    def test_cli_anonymous_exit_zero_review_three_and_invalid_two(self):
        base = [sys.executable, "-m", "mixlab.quality.reviewer_influence"]
        self.ballots([["candidate"] * 5] * 3)
        command = base + [str(self.study), str(self.pack), *map(str, self.rating_paths),
                          "--expected-study-id", self.pinned]
        clean = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertFalse(json.loads(clean.stdout)["milestone_pass"])
        self.assertNotIn(str(self.root), clean.stdout + clean.stderr)

        self.ballots([
            ["candidate"] * 5,
            ["candidate"] * 3 + ["baseline"] * 2,
            ["baseline"] * 5,
        ])
        warning = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(warning.returncode, 3, warning.stderr)
        self.assertTrue(json.loads(warning.stdout)["omission_flips_candidate_plurality"])

        private = self.root / "PRIVATE-TRACK-SECRET" / "review.json"
        command[3] = str(private)
        invalid = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn("PRIVATE-TRACK-SECRET", invalid.stdout + invalid.stderr)
        self.assertNotIn(str(self.root), invalid.stdout + invalid.stderr)


if __name__ == "__main__":
    unittest.main()
