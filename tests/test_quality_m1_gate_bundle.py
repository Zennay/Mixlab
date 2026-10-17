"""ML-07 orchestration contract: synthetic reports and genuine frozen PCM+ratings."""
import copy
import json
import subprocess
import sys
import unittest
from unittest import mock

from mixlab.quality.m1_gate_bundle import (
    M1GateBundleError, compose_m1_gate_reports, inspect_real_m1_gate_bundle,
)


def reports():
    binding = dict(schema_version=1, milestone_pass=False,
                   trial_count=5, study_pack_metadata_consistent_with_pinned_id=True)
    assignment = dict(schema_version=1, milestone_pass=False,
                      trial_count=5, side_assignment_review_required=False)
    position = dict(schema_version=1, milestone_pass=False,
                    trial_count=5, reviewer_count=3,
                    sufficient_for_position_screen=True,
                    aggregate_position_dominance_review=False,
                    individual_position_pattern_review=False)
    pair = dict(schema_version=1, milestone_pass=False,
                frozen_pair_count=5, reviewer_file_count=3,
                minimum_data_for_pair_reference=True,
                pair_sensitivity_review_required=False,
                audio_confounds_reported=False)
    reviewer = dict(schema_version=1, milestone_pass=False,
                    frozen_pair_count=5, reviewer_file_count=3,
                    sufficient_for_reviewer_influence_screen=True,
                    reviewer_influence_review_required=False,
                    official_audio_confounds_reported=False)
    return [binding, assignment, position, pair, reviewer]


def compose(*inputs):
    return compose_m1_gate_reports(*inputs, rating_count=3)


class PureM1ReportContract(unittest.TestCase):
    def test_clean_screen_never_becomes_milestone_approval(self):
        report = compose(*reports())
        self.assertEqual(report["technical_screen"], "SCREENED")
        self.assertEqual(len(report["mandatory_gates_executed"]), 5)
        self.assertEqual(report["review_reasons"], [])
        self.assertIs(report["milestone_pass"], False)
        self.assertFalse(report["human_musical_preference_proven"])
        self.assertFalse(report["independent_human_listeners_authenticated"])
        self.assertNotIn("candidate_preference_fraction", report)

    def test_each_component_hold_forces_aggregate_review(self):
        choices = ((1, "side_assignment_review_required"),
                   (2, "aggregate_position_dominance_review"),
                   (2, "individual_position_pattern_review"),
                   (3, "pair_sensitivity_review_required"),
                   (3, "audio_confounds_reported"),
                   (4, "reviewer_influence_review_required"))
        for index, field in choices:
            with self.subTest(component=index, flag=field):
                inputs = reports()
                inputs[index][field] = True
                if field == "audio_confounds_reported":
                    inputs[4]["official_audio_confounds_reported"] = True
                result = compose(*inputs)
                self.assertEqual(result["technical_screen"], "REVIEW_REQUIRED")
                self.assertTrue(result["review_reasons"])
                self.assertIs(result["milestone_pass"], False)

    def test_insufficient_data_even_without_positive_risks_requires_review(self):
        for idx, key in ((2, "sufficient_for_position_screen"),
                         (3, "minimum_data_for_pair_reference"),
                         (4, "sufficient_for_reviewer_influence_screen")):
            with self.subTest(field=key):
                inputs = reports()
                inputs[idx][key] = False
                self.assertEqual(compose(*inputs)["technical_screen"], "REVIEW_REQUIRED")

    def test_rejects_inconsistent_counts_forged_success_and_missing_gates(self):
        for idx, field, value in (
            (0, "trial_count", 6),
            (1, "trial_count", 4),
            (2, "reviewer_count", 4),
            (3, "frozen_pair_count", 10),
            (3, "reviewer_file_count", 1),
            (4, "frozen_pair_count", 6),
            (4, "reviewer_file_count", 5),
            (0, "study_pack_metadata_consistent_with_pinned_id", False),
            (0, "milestone_pass", True),
            (2, "milestone_pass", True),
            (4, "schema_version", 99),\n            (4, "schema_version", True),\n            (0, "schema_version", True),
            (3, "audio_confounds_reported", "false"),
            (4, "official_audio_confounds_reported", None),
        ):
            with self.subTest(component=idx, field=field):
                rows = reports()
                rows[idx][field] = value
                with self.assertRaises(M1GateBundleError):
                    compose(*rows)
        for idx in range(5):
            inputs = reports()
            inputs[idx] = {}
            with self.assertRaises(M1GateBundleError):
                compose(*inputs)

    def test_refuses_component_disagreement_over_pcm_warnings(self):
        rows = reports()
        rows[3]["audio_confounds_reported"] = True
        with self.assertRaises(M1GateBundleError):
            compose(*rows)

    def test_refuses_boolean_as_count_and_unexpected_rating_cardinality(self):
        for idx, field in ((0, "trial_count"), (2, "reviewer_count"),
                           (3, "frozen_pair_count"), (4, "reviewer_file_count")):
            with self.subTest(index=idx, field=field):
                inputs = reports()
                inputs[idx][field] = True
                with self.assertRaises(M1GateBundleError):
                    compose(*inputs)
        for count in (0, 1, 2, 6, 10, True, 3.0, None):
            with self.subTest(count=count):
                with self.assertRaises(M1GateBundleError):
                    compose_m1_gate_reports(*reports(), rating_count=count)

    def test_refuses_malformed_required_flag_instead_of_treating_false(self):
        for idx, key in ((1, "side_assignment_review_required"),
                         (2, "aggregate_position_dominance_review"),
                         (3, "pair_sensitivity_review_required"),
                         (4, "reviewer_influence_review_required")):
            rows = reports()
            del rows[idx][key]
            with self.assertRaises(M1GateBundleError):
                compose(*rows)

    def test_does_not_echo_private_data_from_input_reports(self):
        rows = reports()
        for report in rows:
            report["SECRET-PATH-PRIVATE-MUSIC"] = "listener-secret"
        published = json.dumps(compose(*rows))
        self.assertNotIn("SECRET", published)
        self.assertNotIn("listener-secret", published)
        self.assertNotIn("pack_id", published)


class RealPCMEndToEndTests(unittest.TestCase):
    def setUp(self):
        # Existing integrated fixture creates genuine synthetic WAV/JSON,
        # but it is NOT a rights-cleared real-music/human-listener dataset.
        from test_quality_composed_m1_gates import CombinedM1GatesTests
        self.fixture = CombinedM1GatesTests(
            "test_all_four_gates_accept_checksum_bound_unanimous_candidate_votes")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ballots = self.fixture.generate_reviews([["candidate"] * 5] * 3)

    def bundle(self):
        return inspect_real_m1_gate_bundle(
            self.fixture.study, self.fixture.pack, self.fixture.pinned, self.ballots)

    def test_actual_five_pair_pcm_and_three_ballots_execute_all_checks(self):
        report = self.bundle()
        self.assertEqual(report["frozen_pair_count"], 5)
        self.assertEqual(report["reviewer_file_count"], 3)
        self.assertEqual(len(report["mandatory_gates_executed"]), 5)
        self.assertIn(report["technical_screen"], ("SCREENED", "REVIEW_REQUIRED"))
        self.assertIs(report["milestone_pass"], False)
        wire = json.dumps(report)
        self.assertNotIn(str(self.fixture.root), wire)
        self.assertNotIn("trial-001", wire)
        self.assertNotIn("synthetic-cross-gate", wire)

    def test_midrun_ballot_edit_is_rejected_after_real_checks(self):
        from mixlab.quality import m1_gate_bundle as module
        original = module.inspect_real_pilot

        def tamper(*args):
            report = original(*args)
            path = self.ballots[0]
            vote = json.loads(path.read_text())
            vote["ratings"][0]["preference"] = (
                "B" if vote["ratings"][0]["preference"] == "A" else "A")
            path.write_text(json.dumps(vote))
            return report

        with mock.patch.object(module, "inspect_real_pilot", side_effect=tamper):
            with self.assertRaises(M1GateBundleError) as error:
                self.bundle()
        self.assertNotIn(str(self.fixture.root), str(error.exception))

    def test_duplicate_paths_rejected_before_opening_wav(self):
        with mock.patch(
            "mixlab.quality.m1_gate_bundle.verify_study_pack_binding",
            side_effect=AssertionError("Private PCM must not be touched")):
            with self.assertRaises(M1GateBundleError):
                inspect_real_m1_gate_bundle(
                    self.fixture.study, self.fixture.pack, self.fixture.pinned,
                    [self.ballots[0]] * 3)

    def test_real_cli_runs_private_checks_and_never_approves_m1(self):
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.m1_gate_bundle",
            str(self.fixture.study), str(self.fixture.pack),
            *map(str, self.ballots), "--expected-study-id", self.fixture.pinned,
        ], capture_output=True, text=True, timeout=45)
        self.assertIn(result.returncode, (0, 3), result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reviewer_file_count"], 3)
        self.assertEqual(len(payload["mandatory_gates_executed"]), 5)
        self.assertIs(payload["milestone_pass"], False)
        self.assertNotIn(str(self.fixture.root), result.stdout + result.stderr)

    def test_symlinked_ancestor_is_refused_before_any_private_pcm_scan(self):
        from pathlib import Path
        alias = Path(self.fixture.root) / "SECRET-ALIAS-TO-PRIVATE"
        alias.symlink_to(Path(self.fixture.study).parent, target_is_directory=True)
        redirected = alias / Path(self.fixture.study).name
        with mock.patch(
            "mixlab.quality.m1_gate_bundle.verify_study_pack_binding",
            side_effect=AssertionError("Symlink must fail before PCM")):
            with self.assertRaises(M1GateBundleError) as error:
                inspect_real_m1_gate_bundle(
                    redirected, self.fixture.pack, self.fixture.pinned, self.ballots)
        self.assertNotIn("SECRET-ALIAS", str(error.exception))

    def test_fifo_ballot_is_refused_without_blocking(self):
        import os
        from pathlib import Path
        fifo = Path(self.fixture.root) / "SECRET-UNBOUNDED-RATING-PIPE"
        os.mkfifo(fifo)
        with mock.patch(
            "mixlab.quality.m1_gate_bundle.verify_study_pack_binding",
            side_effect=AssertionError("FIFO must fail before PCM")):
            with self.assertRaises(M1GateBundleError) as error:
                inspect_real_m1_gate_bundle(
                    self.fixture.study, self.fixture.pack, self.fixture.pinned,
                    [fifo, *self.ballots[1:]])
        self.assertNotIn("SECRET-UNBOUNDED", str(error.exception))


class DefensiveCLI(unittest.TestCase):
    def test_bad_cli_input_has_no_private_path_or_traceback(self):
        secret = "/tmp/SECRET-MIXLAB-PRIVATE-LISTENER.wav"
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.m1_gate_bundle",
            secret, secret, secret, "--expected-study-id", "1" * 64,
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SECRET-MIXLAB", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_argument_does_not_echo_sensitive_value(self):
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.m1_gate_bundle",
            "--sensitive-path=SECRET-MUSIC",
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SECRET-MUSIC", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
