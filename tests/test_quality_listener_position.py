"""End-to-end synthetic reviewer position QA with genuine PCM/rating aggregation."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from mixlab.evaluation import aggregate
from mixlab.quality.listener_position import inspect_listener_sides, ListenerPositionError


class ListenerPositionTests(unittest.TestCase):
    def setUp(self):
        # Import in setUp to avoid accidentally running all existing study
        # binding tests through unittest's imported test-case discovery.
        from test_quality_study_binding import FrozenStudyBindingTests
        self.fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.pack = self.fixture.pack
        self.paths = []

    def ratings(self, ballots):
        receipt = json.loads((self.pack / "receipt.json").read_text())
        self.paths = []
        for index, choices in enumerate(ballots, 1):
            path = self.root / f"private-vote-{index}.json"
            vote = {
                "schema_version": 1,
                "pack_id": receipt["pack_id"],
                "reviewer": f"listener-{index:02d}",
                "ratings": [
                    {"trial": f"trial-{i:03d}", "preference": preference}
                    for i, preference in enumerate(choices, 1)
                ],
            }
            path.write_text(json.dumps(vote), encoding="utf-8")
            self.paths.append(path)
        return self.paths

    def inspect(self):
        return inspect_listener_sides(self.pack, self.paths)

    def test_genuine_three_reviewer_mixed_sides_can_be_screened(self):
        paths = self.ratings([
            ["A", "B", "A", "B", "A"],
            ["B", "A", "B", "A", "B"],
            ["A", "B", "B", "A", "A"],
        ])
        self.assertEqual(aggregate(self.pack, paths)["reviewers"], 3)
        report = self.inspect()
        self.assertTrue(report["sufficient_for_position_screen"])
        self.assertIs(report["aggregate_position_dominance_review"], False)
        self.assertFalse(report["individual_position_pattern_review"])
        self.assertEqual(report["decisive_vote_count"], 15)
        self.assertFalse(report["milestone_pass"])
        text = json.dumps(report)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("listener-", text)
        self.assertNotIn("pack_id", text)
        self.assertNotIn("source_hashes", text)

    def test_genuine_all_choose_A_is_review_not_musical_evidence(self):
        self.ratings([["A"] * 5 for _ in range(3)])
        self.assertEqual(aggregate(self.pack, self.paths)["reviewers"], 3)
        report = self.inspect()
        self.assertIs(report["aggregate_position_dominance_review"], True)
        self.assertTrue(report["individual_position_pattern_review"])
        self.assertFalse(report["human_preference_proven"])

    def test_within_reviewer_pattern_detected_despite_balanced_total(self):
        self.ratings([["A"] * 5, ["B"] * 5, ["A", "B", "B", "A", "B"]])
        report = self.inspect()
        self.assertIs(report["aggregate_position_dominance_review"], False)
        self.assertTrue(report["individual_position_pattern_review"])

    def test_ties_and_unusable_do_not_fake_decisive_evidence(self):
        self.ratings([
            ["Tie"] * 5,
            ["Both unusable"] * 5,
            ["A", "B", "Tie", "Both unusable", "Tie"],
        ])
        result = self.inspect()
        self.assertFalse(result["sufficient_for_position_screen"])
        self.assertIsNone(result["aggregate_position_dominance_review"])
        self.assertEqual(result["decisive_vote_count"], 2)

    def test_two_real_rating_files_remain_insufficient(self):
        self.ratings([["A", "B", "A", "B", "A"], ["B", "A", "B", "A", "B"]])
        result = self.inspect()
        self.assertEqual(result["reviewer_count"], 2)
        self.assertFalse(result["sufficient_for_position_screen"])

    def test_official_rating_grammar_and_pack_binding_remain_mandatory(self):
        self.ratings([["A", "B", "A", "B", "A"]] * 3)
        first = self.paths[0]
        vote = json.loads(first.read_text())
        vote["reviewer"] = "private reviewer invalid"
        first.write_text(json.dumps(vote))
        with self.assertRaises(ListenerPositionError) as raised:
            self.inspect()
        self.assertNotIn(str(first), str(raised.exception))

        vote["reviewer"] = "listener-01"
        vote["pack_id"] = "0" * 64
        first.write_text(json.dumps(vote))
        with self.assertRaises(ListenerPositionError):
            self.inspect()

    def test_duplicate_json_keys_rejected_even_when_aggregator_could_tolerate(self):
        self.ratings([["A", "B", "A", "B", "A"]] * 3)
        first = self.paths[0]
        original = first.read_text()
        first.write_text(original.replace('{"schema_version":', '{"schema_version": 1, "schema_version":'))
        with self.assertRaises(ListenerPositionError):
            self.inspect()

    def test_observable_mutation_during_genuine_aggregate_is_rejected(self):
        self.ratings([["A", "B", "A", "B", "A"]] * 3)
        from mixlab.quality import listener_position as module
        genuine = module.aggregate

        def changed(pack, paths):
            result = genuine(pack, paths)
            vote = json.loads(paths[0].read_text())
            vote["ratings"][0]["preference"] = "B"
            paths[0].write_text(json.dumps(vote))
            return result

        with mock.patch.object(module, "aggregate", side_effect=changed):
            with self.assertRaises(ListenerPositionError):
                self.inspect()

    @unittest.skipUnless(hasattr(__import__("os"), "symlink"), "symlinks unavailable")
    def test_symlinked_rating_file_and_parent_are_refused(self):
        from pathlib import Path
        self.ratings([["A", "B", "A", "B", "A"]] * 3)
        target = self.paths[0]
        link = self.root / "linked-rating.json"
        link.symlink_to(target)
        with self.assertRaises(ListenerPositionError):
            inspect_listener_sides(self.pack, [link, *self.paths[1:]])
        directory = self.root / "real-private-folder"
        directory.mkdir()
        nested = directory / "votes.json"
        nested.write_bytes(target.read_bytes())
        parent_link = self.root / "linked-parent"
        parent_link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(ListenerPositionError):
            inspect_listener_sides(
                self.pack, [parent_link / "votes.json", *self.paths[1:]])

    def test_hostile_pathlike_never_executes_or_exposes_private_error(self):
        self.ratings([["A", "B", "A", "B", "A"]] * 3)
        class Hostile:
            def __fspath__(self):
                raise RuntimeError("TOP-SECRET-REVIEW-LOCATION")
        with self.assertRaises(ListenerPositionError) as raised:
            inspect_listener_sides(self.pack, [Hostile(), *self.paths[1:]])
        self.assertNotIn("TOP-SECRET", str(raised.exception))
        with self.assertRaises(ListenerPositionError):
            inspect_listener_sides(Hostile(), self.paths)

    def test_relative_rating_and_pack_paths_stay_pinned_on_cwd_change(self):
        import os
        from mixlab.quality import listener_position as module
        self.ratings([["A", "B", "A", "B", "A"],
                      ["B", "A", "B", "A", "B"],
                      ["A", "B", "B", "A", "B"]])
        first_cwd = Path.cwd()
        genuine = module.aggregate
        changed_cwd = self.root / "unrelated-cwd"
        changed_cwd.mkdir()

        def change_during_aggregation(pack, paths):
            # Original paths were relative on entry. Name admission must
            # remain tied to the initial lexical directory even after chdir.
            os.chdir(changed_cwd)
            return genuine(pack, paths)

        try:
            os.chdir(self.root)
            relative = [path.name for path in self.paths]
            with mock.patch.object(module, "aggregate", side_effect=change_during_aggregation):
                report = inspect_listener_sides("pack", relative)
            self.assertFalse(report["aggregate_position_dominance_review"])
        finally:
            os.chdir(first_cwd)

    def test_cli_exit_codes_and_no_private_identity_disclosure(self):
        self.ratings([["A", "B", "A", "B", "A"],
                      ["B", "A", "B", "A", "B"],
                      ["A", "B", "A", "B", "B"]])
        command = [
            sys.executable, "-m", "mixlab.quality.listener_position",
            str(self.pack), *(str(path) for path in self.paths),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertNotIn("listener-", result.stdout)
        report = json.loads(result.stdout)
        self.assertFalse(report["milestone_pass"])

        self.ratings([["A"] * 5 for _ in range(3)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertTrue(json.loads(result.stdout)["aggregate_position_dominance_review"])

    def test_cli_insufficient_and_bad_private_path(self):
        self.ratings([["Tie"] * 5 for _ in range(3)])
        base = [sys.executable, "-m", "mixlab.quality.listener_position", str(self.pack)]
        result = subprocess.run(base + [str(p) for p in self.paths],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["aggregate_position_dominance_review"])
        secret = self.root / "SECRET-TRACK-PATH" / "review.json"
        result = subprocess.run(base + [str(secret)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(secret), result.stdout + result.stderr)
        self.assertNotIn("SECRET-TRACK-PATH", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
