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
                    decisive_vote_count=15,
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
                    full_decisive_vote_count=15,
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
                if key == "sufficient_for_position_screen":
                    # A real underpowered position report has a null finding.
                    # Both independent analyses must agree on its vote count.
                    inputs[2]["decisive_vote_count"] = 3
                    inputs[4]["full_decisive_vote_count"] = 3
                    inputs[2]["aggregate_position_dominance_review"] = None
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
            (4, "schema_version", 99),
            (4, "schema_version", True),
            (0, "schema_version", True),
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

    def test_tristate_position_contract_for_underpowered_pilots(self):
        low = reports()
        low[2]["sufficient_for_position_screen"] = False
        low[2]["aggregate_position_dominance_review"] = None
        low[2]["decisive_vote_count"] = 3
        low[4]["full_decisive_vote_count"] = 3
        self.assertEqual(compose(*low)["technical_screen"], "REVIEW_REQUIRED")
        # Inconclusive is not a permissible substitute for the result when
        # there actually are enough decisive observations.
        high = reports()
        high[2]["aggregate_position_dominance_review"] = None
        with self.assertRaises(M1GateBundleError):
            compose(*high)
        # A forged decisive conclusion while insufficient is also rejected.
        low[2]["aggregate_position_dominance_review"] = False
        with self.assertRaises(M1GateBundleError):
            compose(*low)

    def test_mismatched_decisive_votes_or_forged_power_cannot_pass(self):
        for index, field, value in (
            (2, "decisive_vote_count", 13),
            (4, "full_decisive_vote_count", 14),
            (2, "decisive_vote_count", True),
            (4, "full_decisive_vote_count", True),
            (2, "decisive_vote_count", -1),
            (4, "full_decisive_vote_count", 16),
            (2, "sufficient_for_position_screen", False),
        ):
            with self.subTest(index=index, field=field):
                items = reports()
                items[index][field] = value
                with self.assertRaises(M1GateBundleError):
                    compose(*items)

    def test_exact_decisive_threshold_uses_tri_state_only_below_twelve(self):
        for count in (0, 1, 11, 12, 13, 15):
            with self.subTest(decisive=count):
                items = reports()
                items[2]["decisive_vote_count"] = count
                items[4]["full_decisive_vote_count"] = count
                powered = count >= 12
                items[2]["sufficient_for_position_screen"] = powered
                items[2]["aggregate_position_dominance_review"] = (
                    False if powered else None)
                result = compose(*items)
                self.assertEqual(result["technical_screen"],
                                 "SCREENED" if powered else "REVIEW_REQUIRED")
                self.assertIs(result["milestone_pass"], False)

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

    def test_inconclusive_real_pcm_ballots_hold_instead_of_invalid_data(self):
        # Exactly valid trial/pack/PCM inputs, with no enough decisive answers.
        # These must be REVIEW_REQUIRED (exit 3), not invalid-data (exit 2).
        for count in (3, 4, 5):
            for choice in ("Tie", "Both unusable"):
                with self.subTest(reviewers=count, choice=choice):
                    self.ballots = self.fixture.generate_reviews([[choice] * 5] * count)
                    result = self.bundle()
                    self.assertEqual(result["technical_screen"], "REVIEW_REQUIRED")
                    self.assertIn("position-bias-or-insufficient-data",
                                  result["review_reasons"])
                    self.assertIn("pair-sensitivity-or-insufficient-data",
                                  result["review_reasons"])
                    self.assertIs(result["milestone_pass"], False)

    def test_mixed_valid_low_information_ballots_hold(self):
        self.ballots = self.fixture.generate_reviews([
            ["candidate", "Tie", "Tie", "Tie", "Tie"],
            ["baseline", "Tie", "Tie", "Tie", "Tie"],
            ["candidate", "Tie", "Tie", "Tie", "Tie"],
        ])
        report = self.bundle()
        self.assertEqual(report["technical_screen"], "REVIEW_REQUIRED")
        self.assertIn("position-bias-or-insufficient-data", report["review_reasons"])

    def test_inconclusive_real_cli_uses_review_exit_three(self):
        self.ballots = self.fixture.generate_reviews([["Tie"] * 5] * 3)
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.m1_gate_bundle",
            str(self.fixture.study), str(self.fixture.pack),
            *map(str, self.ballots), "--expected-study-id", self.fixture.pinned,
        ], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 3, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["technical_screen"], "REVIEW_REQUIRED")
        self.assertNotIn(str(self.fixture.root), result.stdout + result.stderr)

    def _expand_private_pcm_fixture_to_ten_pairs(self):
        """Exercise the actual documented max pair/cardinality, not mocks.

        The existing frozen five-pair fixture is extended with FIVE NEW,
        original 8kHz PCM16 waves per blinded variant and unique synthetic
        source identifiers. Study and pack commitments are rebuilt exactly.
        """
        import hashlib
        import math
        import struct
        import wave
        from mixlab.evaluation import verify_pack
        from test_quality_study_binding import _canonical_sha, _write_json

        study = json.loads(self.fixture.study.read_text())
        key_path = self.fixture.pack / "private" / "answer-key.json"
        evidence_path = self.fixture.pack / "private" / "evidence.json"
        receipt_path = self.fixture.pack / "receipt.json"
        keys = json.loads(key_path.read_text())
        evidence = json.loads(evidence_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        for i in range(6, 11):
            number = f"{i:02d}"
            left = hashlib.sha256(f"maxpilot-original-a-{number}".encode()).hexdigest()
            right = hashlib.sha256(f"maxpilot-original-b-{number}".encode()).hexdigest()
            family = ("hard_cut", "bass_swap", "echo_exit", "hard_cut", "bass_swap")[i - 6]
            study["pairs"].append({
                "pair_id": f"pair-{number}", "a": f"newtrack-{number}-a",
                "b": f"newtrack-{number}-b", "a_sha256": left, "b_sha256": right,
                "a_bpm": 120.0, "b_bpm": 120.0,
                "renderable_without_stretch": True, "candidate_family": family,
            })
            trial = f"trial-{i:03d}"
            pair = f"synthetic-alignment-{number}"
            answer = {"trial": trial, "pair": pair,
                      "A": "baseline" if i % 2 else family,
                      "B": family if i % 2 else "baseline"}
            keys.append(answer)
            for label in ("A", "B"):
                variant = answer[label]
                wav_path = self.fixture.pack / "review" / f"{trial}-{label}.wav"
                with wave.open(str(wav_path), "wb") as out:
                    out.setnchannels(1)
                    out.setsampwidth(2)
                    out.setframerate(8000)
                    out.writeframes(b"".join(
                        struct.pack("<h", int(2000 * math.sin(
                            2 * math.pi * (92 + i * 17 + (label == "B") * 13)
                            * frame / 8000
                        ))) for frame in range(800)
                    ))
                evidence["renders"].append({
                    "pair": pair, "study_pair": f"pair-{number}",
                    "family": variant, "source_hashes": [left, right],
                    "recipe": {"family": variant, "bpm": 120.0, "beats": 4,
                               "a_start": 0.0, "b_start": 0.0,
                               "gain_db": -6.0,
                               "a_bpm": 120.0, "b_bpm": 120.0},
                    "output_sha256": hashlib.sha256(wav_path.read_bytes()).hexdigest(),
                })

        study.pop("study_id")
        self.fixture.pinned = _canonical_sha(study)
        study["study_id"] = self.fixture.pinned
        evidence["study_id"] = self.fixture.pinned
        pack_identity = {
            "manifest": evidence["manifest_sha256"], "answers": keys,
            "outputs": [row["output_sha256"] for row in evidence["renders"]],
        }
        pack_id = hashlib.sha256(
            json.dumps(pack_identity, sort_keys=True).encode()
        ).hexdigest()
        evidence["pack_id"] = receipt["pack_id"] = pack_id
        receipt["trial_count"] = 10
        receipt["render_count"] = 20
        _write_json(self.fixture.study, study)
        _write_json(key_path, keys)
        _write_json(evidence_path, evidence)
        _write_json(receipt_path, receipt)
        self.fixture.answers = keys
        self.fixture.receipt = receipt
        self.assertEqual(len(verify_pack(self.fixture.pack)[2]), 10)

    def test_max_ten_pair_five_rater_real_pcm_path(self):
        self._expand_private_pcm_fixture_to_ten_pairs()
        patterns = [
            ["candidate"] * 10, ["baseline"] * 10,
            ["candidate" if i % 2 else "baseline" for i in range(10)],
            ["Tie"] * 10, ["candidate"] * 10,
        ]
        self.ballots = self.fixture.generate_reviews(patterns)
        report = self.bundle()
        self.assertEqual(report["frozen_pair_count"], 10)
        self.assertEqual(report["reviewer_file_count"], 5)
        self.assertIn(report["technical_screen"], ("SCREENED", "REVIEW_REQUIRED"))
        self.assertIs(report["milestone_pass"], False)
        wire = json.dumps(report)
        self.assertNotIn(self.fixture.pinned, wire)
        self.assertNotIn(str(self.fixture.root), wire)

    def test_max_ten_pair_five_rater_all_unusable_is_valid_hold(self):
        self._expand_private_pcm_fixture_to_ten_pairs()
        self.ballots = self.fixture.generate_reviews([["Both unusable"] * 10] * 5)
        report = self.bundle()
        self.assertEqual(report["frozen_pair_count"], 10)
        self.assertEqual(report["reviewer_file_count"], 5)
        self.assertEqual(report["technical_screen"], "REVIEW_REQUIRED")
        self.assertIn("position-bias-or-insufficient-data", report["review_reasons"])

    def _stdin_cli(self, document, *extra, raw=False):
        payload = document if raw else json.dumps(document).encode("utf-8")
        return subprocess.run([
            sys.executable, "-m", "mixlab.quality.m1_gate_bundle",
            "--private-input-stdin", *extra,
        ], input=payload, capture_output=True, timeout=45)

    def _private_request(self):
        return {
            "study": str(self.fixture.study),
            "pack": str(self.fixture.pack),
            "ratings": list(map(str, self.ballots)),
            "expected_study_id": self.fixture.pinned,
        }

    def test_private_stdin_invocation_executes_real_pcm_without_path_argv(self):
        request = self._private_request()
        result = self._stdin_cli(request)
        expected = self.bundle()
        self.assertEqual(result.returncode, 3 if expected["technical_screen"]
                         == "REVIEW_REQUIRED" else 0, result.stderr.decode())
        response = json.loads(result.stdout)
        self.assertEqual(response, expected)
        self.assertNotIn(str(self.fixture.root), str(result.stdout + result.stderr))
        self.assertEqual(response["frozen_pair_count"], 5)
        self.assertIs(response["milestone_pass"], False)

    def test_stdin_all_tie_is_a_valid_review_hold_not_corruption(self):
        self.ballots = self.fixture.generate_reviews([["Tie"] * 5] * 3)
        result = self._stdin_cli(self._private_request())
        self.assertEqual(result.returncode, 3, result.stderr.decode())
        self.assertEqual(json.loads(result.stdout)["technical_screen"], "REVIEW_REQUIRED")
        self.assertNotIn(str(self.fixture.root), str(result.stdout + result.stderr))

    def test_private_stdin_max_ten_pairs_five_reviewers_stays_private(self):
        self._expand_private_pcm_fixture_to_ten_pairs()
        self.ballots = self.fixture.generate_reviews([
            ["candidate"] * 10,
            ["baseline"] * 10,
            ["Tie"] * 10,
            ["candidate" if i % 2 else "baseline" for i in range(10)],
            ["Both unusable"] * 10,
        ])
        expected = self.bundle()
        result = self._stdin_cli(self._private_request())
        self.assertEqual(result.returncode,
                         3 if expected["technical_screen"] == "REVIEW_REQUIRED" else 0,
                         result.stderr.decode())
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertEqual(expected["frozen_pair_count"], 10)
        self.assertEqual(expected["reviewer_file_count"], 5)
        self.assertNotIn(str(self.fixture.root), str(result.stdout + result.stderr))
        self.assertIs(expected["milestone_pass"], False)

    def test_stdin_input_parser_rejects_ambiguity_and_secret_exposure(self):
        secret = "SECRET_PRIVATE_MUSIC_PATH_123"
        cases = [
            b"",
            b"null",
            b"[]",
            b"{}",
            b"not-json",
            b"\xff",
            b'{"study":"SECRET", "study":"SECRET2"}',
            b'{"study":"SECRET", "ratings": ["R"], "unknown": "UNTRUSTED"}',
            b"{" + b" " * 32768 + b"}",
        ]
        for item in cases:
            with self.subTest(case=item[:32]):
                response = self._stdin_cli(item, raw=True)
                self.assertEqual(response.returncode, 2)
                self.assertFalse(response.stdout)
                self.assertNotIn(b"SECRET", response.stderr)
                self.assertNotIn(b"Traceback", response.stderr)
        request = self._private_request()
        request["unknown_secret_field"] = secret
        response = self._stdin_cli(request)
        self.assertEqual(response.returncode, 2)
        self.assertNotIn(secret.encode(), response.stdout + response.stderr)

    def test_stdin_mode_refuses_legacy_paths_and_flags_together(self):
        request = self._private_request()
        for extras in (
            (str(self.fixture.study),),
            ("--expected-study-id", self.fixture.pinned),
            ("--SECRET_PRIVATE_MUSIC",),
        ):
            with self.subTest(extras=extras):
                result = self._stdin_cli(request, *extras)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(str(self.fixture.root), str(result.stdout + result.stderr))
                self.assertNotIn(b"SECRET_PRIVATE_MUSIC", result.stdout + result.stderr)

    def _write_bound_size_pcm(self, frames):
        """Write 96 kHz stereo WAV *streaming*, then re-sign the true pack.

        Two independent channels and two distinct A/B waveforms are required
        for a genuine A/B comparison. No 8 MB PCM byte buffer is retained.
        """
        import hashlib
        import math
        import struct
        import wave
        from test_quality_study_binding import _write_json

        answers = json.loads((self.fixture.pack / "private" / "answer-key.json").read_text())
        evidence_path = self.fixture.pack / "private" / "evidence.json"
        receipt_path = self.fixture.pack / "receipt.json"
        evidence = json.loads(evidence_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        target = answers[0]
        for label in ("A", "B"):
            wav_path = self.fixture.pack / "review" / f"{target['trial']}-{label}.wav"
            # A 4096-frame stereo block carries deterministic original PCM.
            tone = 132 + (label == "B") * 17
            block = b"".join(
                struct.pack("<hh",
                            int(3100 * math.sin(2 * math.pi * tone * i / 96000)),
                            int(2700 * math.sin(2 * math.pi * (tone + 29) * i / 96000)))
                for i in range(4096)
            )
            with wave.open(str(wav_path), "wb") as sink:
                sink.setnchannels(2)
                sink.setsampwidth(2)
                sink.setframerate(96000)
                for _ in range(frames // 4096):
                    sink.writeframesraw(block)
                sink.writeframesraw(block[:4 * (frames % 4096)])
                sink.writeframes(b"")
            digest = hashlib.sha256()
            with wav_path.open("rb") as stream:
                for piece in iter(lambda: stream.read(65536), b""):
                    digest.update(piece)
            render = next(row for row in evidence["renders"]
                          if row["pair"] == target["pair"]
                          and row["family"] == target[label])
            render["output_sha256"] = digest.hexdigest()
        identity = {
            "manifest": evidence["manifest_sha256"],
            "answers": answers,
            "outputs": [row["output_sha256"] for row in evidence["renders"]],
        }
        pack_id = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
        evidence["pack_id"] = pack_id
        receipt["pack_id"] = pack_id
        _write_json(evidence_path, evidence)
        _write_json(receipt_path, receipt)
        self.fixture.receipt = receipt

    def test_real_maximum_two_million_frame_pcm_passes_all_five_gates(self):
        from mixlab.evaluation import verify_pack
        self._write_bound_size_pcm(2_000_000)
        self.assertEqual(len(verify_pack(self.fixture.pack)[2]), 5)
        self.ballots = self.fixture.generate_reviews([["candidate"] * 5] * 3)
        result = self.bundle()
        self.assertIn(result["technical_screen"], ("SCREENED", "REVIEW_REQUIRED"))
        self.assertEqual(result["frozen_pair_count"], 5)
        self.assertEqual(result["reviewer_file_count"], 3)
        self.assertEqual(len(result["mandatory_gates_executed"]), 5)
        self.assertIs(result["milestone_pass"], False)
        self.assertNotIn(str(self.fixture.root), json.dumps(result))

        # A REAL wave with one frame past the public scanner limit must fail
        # even after reconstructing otherwise internally consistent commits.
        self._write_bound_size_pcm(2_000_001)
        self.ballots = self.fixture.generate_reviews([["candidate"] * 5] * 3)
        with self.assertRaises(M1GateBundleError) as error:
            self.bundle()
        self.assertNotIn(str(self.fixture.root), str(error.exception))

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
