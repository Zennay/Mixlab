"""Rights-safe tests of the combined pilot/ML-07 technical gate.

Uses the frozen-study fixture that actually verifies private PCM references.
No purchased music, listener ratings, URLs or VPS files.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from mixlab.cli import write_review
from mixlab.quality.pilot_preflight import inspect_pilot_preflight
from test_quality_study_binding import FrozenStudyBindingTests


class PilotPreflightTests(unittest.TestCase):
    def setUp(self):
        # Reuse the independently tested frozen 5-pair, 10-render fixture
        # without subclassing it (which would rerun all its tests here).
        fixture = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.pack = fixture.pack
        self.study = fixture.study
        self.pinned = fixture.pinned
        receipt = json.loads((self.pack / "receipt.json").read_text())
        write_review(
            self.pack / "review" / "index.html",
            [f"trial-{n:03d}" for n in range(1, 6)],
            receipt["pack_id"]
        )

    def check(self):
        return inspect_pilot_preflight(self.pack, self.study, self.pinned)

    def test_true_frozen_pcm_study_reports_anonymous_technical_verdict(self):
        report = self.check()
        self.assertEqual(report["trial_count"], 5)
        self.assertIn(report["technical_gate"], {"pass", "hold"})
        self.assertTrue(report["official_review_form_checked"])
        self.assertTrue(report["public_receipt_and_audio_checked"])
        self.assertTrue(report["externally_pinned_study_metadata_consistent"])
        self.assertFalse(report["actual_source_rights_independently_authenticated"])
        self.assertFalse(report["actual_source_audio_authenticated"])
        self.assertFalse(report["independent_listeners_verified"])
        self.assertFalse(report["human_preference_proven"])
        self.assertFalse(report["release_authorized"])
        self.assertFalse(report["milestone_pass"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.fixture.root), serialized)
        self.assertNotIn(self.pinned, serialized)
        self.assertNotIn("trial-001", serialized)
        self.assertNotIn(json.loads((self.pack/"receipt.json").read_text())["pack_id"],
                         serialized)

    def test_clean_technical_metrics_eligible_but_never_human_approval(self):
        original = self.check()
        # Reproduce a PCM technical pass as a narrowly simulated result;
        # real metadata and frozen binding are still fully verified.
        with patch("mixlab.quality.pilot_preflight.inspect_review_pack",
                   return_value={
                       "trial_count": 5, "warning_trial_count": 0,
                       "cross_trial_repeated_variant_count": 0,
                       "official_generated_html_verified": True,
                       "public_receipt_pack_id_verified": True,
                       "review_page_audio_links_verified": True,
                       "answer_key_opened": False,
                   }):
            clean = self.check()
        self.assertEqual(clean["technical_gate"], "pass")
        self.assertFalse(clean["release_authorized"])
        self.assertFalse(clean["milestone_pass"])
        if original["technical_gate"] == "hold":
            self.assertGreater(
                original["technical_warning_trial_count"] +
                original["cross_trial_repeated_variant_count"], 0
            )

    def test_unpinned_and_foreign_study_ids_fail_closed(self):
        for id_ in ("", "private", "F" * 64, "f" * 64, None, 7):
            with self.subTest(id=id_):
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    inspect_pilot_preflight(self.pack, self.study, id_)

    def test_missing_or_modified_generated_form_is_invalid(self):
        page = self.pack / "review/index.html"
        page.unlink()
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.check()
        receipt = json.loads((self.pack / "receipt.json").read_text())
        write_review(page, [f"trial-{n:03d}" for n in range(1, 6)],
                     receipt["pack_id"])
        html = page.read_text()
        page.write_text(html.replace("<script>", "<script>document.body.remove();", 1))
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.check()

    def test_changed_private_pcm_never_passes(self):
        source = self.pack / "review/trial-001-A.wav"
        source.write_bytes(b"RIFF" + b"\0" * 40)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.check()

    def test_study_and_private_render_provenance_tampering_fails(self):
        document = json.loads(self.study.read_text())
        document["max_track_uses"] = 4
        self.study.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.check()

    def test_report_excludes_raw_warning_text_and_private_trials(self):
        report = self.check()
        self.assertEqual(set(report), {
            "schema_version", "technical_gate", "trial_count",
            "technical_warning_trial_count", "cross_trial_repeated_variant_count",
            "official_review_form_checked", "public_receipt_and_audio_checked",
            "externally_pinned_study_metadata_consistent",
            "actual_source_rights_independently_authenticated",
            "actual_source_audio_authenticated",
            "independent_listeners_verified", "human_preference_proven",
            "release_authorized", "milestone_pass",
        })

    def test_cli_returns_hold_or_pass_and_redacts_sensitive_options(self):
        args = [sys.executable, "-m", "mixlab.quality.pilot_preflight",
                str(self.pack), "--study", str(self.study),
                "--expected-study-id", self.pinned]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=45)
        self.assertIn(proc.returncode, (0, 2), proc.stderr)
        self.assertEqual(proc.returncode,
                         0 if json.loads(proc.stdout)["technical_gate"] == "pass" else 2)
        self.assertNotIn(self.pinned, proc.stdout)
        self.assertNotIn(str(self.fixture.root), proc.stdout + proc.stderr)
        for operands in (["--bad=" + str(self.study)],
                         [str(self.pack)],
                         [str(self.pack), "--study", str(self.study),
                          "--expected-study-id", "INVALID"]):
            invalid = subprocess.run(
                [sys.executable, "-m", "mixlab.quality.pilot_preflight", *operands],
                capture_output=True, text=True, timeout=45
            )
            self.assertEqual(invalid.returncode, 3)
            self.assertEqual(invalid.stdout, "")
            self.assertNotIn(str(self.fixture.root), invalid.stderr)
            self.assertNotIn("Traceback", invalid.stderr)

    def test_review_html_replaced_after_static_checks_is_refused(self):
        """Sequential validators must share one immutable file-set snapshot."""
        from mixlab.quality.study_binding import verify_study_pack_binding
        original = verify_study_pack_binding
        page = self.pack / "review/index.html"
        def mutate_after_public_pcm(study, pack, identifier):
            result = original(study, pack, identifier)
            # An untrusted process changes the canonical listener form after
            # the browser/PCM inspectors validated its old contents.
            payload = page.read_text(encoding="utf-8")
            page.write_text(payload.replace(
                "Which transition works?", "Biased first answer: A"))
            return result
        with patch("mixlab.quality.pilot_preflight.verify_study_pack_binding",
                   side_effect=mutate_after_public_pcm):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                self.check()

    def test_receipt_changed_after_binding_is_refused(self):
        from mixlab.quality.study_binding import verify_study_pack_binding
        original = verify_study_pack_binding
        receipt_path = self.pack / "receipt.json"
        def mutate_after_binding(study, pack, identifier):
            result = original(study, pack, identifier)
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
            data["status"] = "forged-validated"
            receipt_path.write_text(json.dumps(data), encoding="utf-8")
            return result
        with patch("mixlab.quality.pilot_preflight.verify_study_pack_binding",
                   side_effect=mutate_after_binding):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                self.check()

    def test_component_mismatches_never_show_a_clean_gate(self):
        real_report = self.check()
        common = {
            "trial_count": 5, "warning_trial_count": 0,
            "cross_trial_repeated_variant_count": 0,
            "official_generated_html_verified": True,
            "public_receipt_pack_id_verified": True,
            "review_page_audio_links_verified": True,
            "answer_key_opened": False,
        }
        for key,value in (
            ("trial_count", 6),
            ("official_generated_html_verified", False),
            ("public_receipt_pack_id_verified", False),
            ("review_page_audio_links_verified", False),
            ("answer_key_opened", True),
            ("warning_trial_count", -1),
            ("warning_trial_count", 1.0),
            ("cross_trial_repeated_variant_count", -1)
        ):
            with self.subTest(key=key, value=value):
                with patch("mixlab.quality.pilot_preflight.inspect_review_pack",
                           return_value={**common, key:value}):
                    if key in ("warning_trial_count","cross_trial_repeated_variant_count") and value == -1 or isinstance(value,float):
                        with self.assertRaises(ValueError):
                            self.check()
                    elif key == "warning_trial_count" and value != 0:
                        with self.assertRaises(ValueError):
                            self.check()
                    else:
                        with self.assertRaises(ValueError):
                            self.check()


if __name__ == "__main__":
    unittest.main()
