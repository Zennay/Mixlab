"""Isolated synthetic regression matrix for ML-05's frozen render cardinality.

The stand-alone verifier in the in-flight study PR previously selected only
the expected rows and ignored extra evidence rows. The integrated ML-07
binding must refuse *every* unselected render before touching private PCM.
"""
import copy
import json
import unittest
from unittest.mock import patch

from mixlab.quality.study_binding import _preflight_render_claims

FAMILIES = ("bass_swap", "echo_exit", "hard_cut")


def frozen_fixture():
    pairs = []
    rows = []
    for i in range(1, 6):
        ident = f"pair-{i:02d}"
        family = FAMILIES[(i - 1) % len(FAMILIES)]
        source = ["a" * 62 + f"{2*i:02x}", "b" * 62 + f"{2*i+1:02x}"]
        pairs.append({
            "pair_id": ident, "candidate_family": family,
            "a": f"record-a-{i}", "b": f"record-b-{i}",
            "a_sha256": source[0], "b_sha256": source[1],
            "a_bpm": 120.0, "b_bpm": 120.0,
        })
        for rendered_family in ("baseline", family):
            rows.append({
                "study_pair": ident, "pair": f"frozen-pair-{i}",
                "family": rendered_family, "source_hashes": source,
                "output_sha256": "c" * 64,
                "recipe": {
                    "family": rendered_family, "bpm": 120.0,
                    "a_bpm": 120.0, "b_bpm": 120.0,
                    "beats": 8, "a_start": 0.0, "b_start": 0.0,
                    "gain_db": -6.0,
                },
            })
    return {"pairs": pairs}, {"renders": rows}


class OrphanRenderAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.study, self.evidence = frozen_fixture()

    def check(self):
        return _preflight_render_claims(self.study, self.evidence)

    def test_exact_two_per_frozen_pair_is_admitted(self):
        result = self.check()
        self.assertEqual(len(result), 5)
        self.assertEqual([row[0] for row in result], list(range(1, 6)))

    def test_one_orphan_with_plausible_forged_pair_never_passes(self):
        orphan = copy.deepcopy(self.evidence["renders"][0])
        orphan["study_pair"] = "pair-99"
        orphan["pair"] = "hidden-unselected-audio"
        self.evidence["renders"].append(orphan)
        with self.assertRaises(ValueError):
            self.check()

    def test_an_extra_render_of_existing_study_pair_does_not_pass(self):
        self.evidence["renders"].append(copy.deepcopy(self.evidence["renders"][0]))
        with self.assertRaises(ValueError):
            self.check()

    def test_orphan_after_swapping_one_expected_render_is_refused(self):
        self.evidence["renders"][-1]["study_pair"] = "pair-99"
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_candidate_family_cannot_replace_frozen_baseline(self):
        self.evidence["renders"][0]["family"] = "echo_exit"
        with self.assertRaises(ValueError):
            self.check()

    def test_reassigned_render_with_unchanged_study_id_is_refused(self):
        self.evidence["renders"][1]["study_pair"] = "pair-02"
        with self.assertRaises(ValueError):
            self.check()

    def test_source_identity_swap_cannot_pass_with_same_render_count(self):
        self.evidence["renders"][2]["source_hashes"] = self.evidence["renders"][0]["source_hashes"]
        with self.assertRaises(ValueError):
            self.check()

    def test_mismatched_baseline_and_candidate_gain_is_refused(self):
        self.evidence["renders"][1]["recipe"]["gain_db"] = -3.0
        with self.assertRaises(ValueError):
            self.check()

    def test_forged_study_id_orphan_data_is_not_echoed_to_public_stdout(self):
        orphan = copy.deepcopy(self.evidence["renders"][0])
        orphan["study_pair"] = "pair-99"
        orphan["pair"] = "SECRET-REAL-MUSIC-DO-NOT-LOG"
        self.evidence["renders"].append(orphan)
        with self.assertRaises(ValueError) as err:
            self.check()
        self.assertNotIn("SECRET-REAL-MUSIC-DO-NOT-LOG", str(err.exception))

    def test_rehashed_orphan_pack_passes_legacy_pcm_validator_but_not_pinned_binding(self):
        """Real procedural WAVs, checksum-consistent receipt, no actual music.

        A forged orphan metadata row can survive verify_pack's base checks;
        the dedicated frozen-study gate must reject it before rescanning PCM.
        """
        import hashlib
        from pathlib import Path
        from test_quality_study_binding import FrozenStudyBindingTests
        from mixlab.evaluation import verify_pack
        from mixlab.quality.study_binding import verify_study_pack_binding

        fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts"
        )
        fixture.setUp()
        try:
            self.assertEqual(len(verify_pack(fixture.pack)[2]), 5)
            with (fixture.private / "evidence.json").open(encoding="utf-8") as handle:
                evidence = json.load(handle)
            with (fixture.private / "answer-key.json").open(encoding="utf-8") as handle:
                answers = json.load(handle)
            with (fixture.pack / "receipt.json").open(encoding="utf-8") as handle:
                receipt = json.load(handle)
            extra = copy.deepcopy(evidence["renders"][0])
            extra["study_pair"] = "pair-99"
            extra["pair"] = "synthetic-orphan-unselected"
            extra["output_sha256"] = "f" * 64
            evidence["renders"].append(extra)
            identity = {
                "manifest": evidence["manifest_sha256"], "answers": answers,
                "outputs": [row["output_sha256"] for row in evidence["renders"]],
            }
            forged_pack_id = hashlib.sha256(
                json.dumps(identity, sort_keys=True).encode("utf-8")
            ).hexdigest()
            evidence["pack_id"] = forged_pack_id
            receipt["pack_id"] = forged_pack_id
            receipt["render_count"] = len(evidence["renders"])
            (fixture.private / "evidence.json").write_text(json.dumps(evidence))
            (fixture.pack / "receipt.json").write_text(json.dumps(receipt))

            # The generic PCM pack verifier accepts the now checksum-consistent
            # extra metadata row because it only opens selected A/B trial WAVs.
            generic_receipt, _, generic_trials = verify_pack(fixture.pack)
            self.assertEqual(generic_receipt["render_count"], 11)
            self.assertEqual(len(generic_trials), 5)
            with patch("mixlab.quality.study_binding.verify_pack",
                       side_effect=AssertionError("orphan reached private audio")) as scanner:
                with self.assertRaisesRegex(ValueError, "do not match"):
                    verify_study_pack_binding(fixture.study, fixture.pack, fixture.pinned)
                scanner.assert_not_called()
        finally:
            fixture.doCleanups()

    def test_early_rejection_does_not_invoke_private_pcm_scanner(self):
        self.evidence["renders"].append(copy.deepcopy(self.evidence["renders"][0]))
        with patch("mixlab.quality.study_binding.verify_pack",
                   side_effect=AssertionError("audio was opened")) as scanner:
            with self.assertRaises(ValueError):
                self.check()
            scanner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
