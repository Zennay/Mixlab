"""Private synthetic ML-07 admission tests: no licensed media or listeners."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from mixlab.evaluation.json_admission import load_bounded_json
from mixlab.quality.study_json_path_guard import inspect_pinned_study_json_paths
from mixlab.quality import study_json_path_guard as gate

from test_quality_study_binding import FrozenStudyBindingTests


class PinnedJSONPathTests(unittest.TestCase):
    def setUp(self):
        self.fx = FrozenStudyBindingTests(
            "test_valid_five_pair_study_is_bound_to_actual_pcm_receipts"
        )
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def checked(self, study=None, pack=None, identity=None):
        return inspect_pinned_study_json_paths(
            study if study is not None else self.fx.study,
            pack if pack is not None else self.fx.pack,
            identity if identity is not None else self.fx.pinned,
        )

    def test_normal_rights_free_five_trial_pack_passes_without_release_claim(self):
        report = self.checked()
        self.assertEqual(report["technical_gate"], "pass")
        self.assertTrue(report["no_symlink_json_ancestors_verified"])
        self.assertTrue(report["externally_pinned_study_binding_verified"])
        for key in ("release_authorized", "public_review_ui_verified",
                    "actual_source_rights_authenticated",
                    "independent_human_preference_proven"):
            self.assertIs(report[key], False)
        self.assertNotIn(str(self.fx.root), json.dumps(report))
        self.assertNotIn(self.fx.pinned, json.dumps(report))

    def test_actual_shared_loader_accepts_linked_parent_but_gate_refuses(self):
        linked = self.fx.root / "linked-evaluation"
        linked.symlink_to(self.fx.root, target_is_directory=True)
        linked_study = linked / self.fx.study.name
        # Reproduce the real gap: the existing loader's O_NOFOLLOW is only
        # applied to the final basename; a parent component is followed.
        self.assertEqual(load_bounded_json(linked_study)["study_id"], self.fx.pinned)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked(study=linked_study)

    def test_parent_symlink_on_pack_root_is_rejected(self):
        linked = self.fx.root / "linked-pack"
        linked.symlink_to(self.fx.pack, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked(pack=linked)

    def test_parent_symlink_in_private_subdirectory_is_rejected(self):
        original = self.fx.private
        original.rename(self.fx.pack / "private-actual")
        original.symlink_to(self.fx.pack / "private-actual", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()

    def test_parent_symlink_in_review_subdirectory_is_rejected(self):
        original = self.fx.review
        original.rename(self.fx.pack / "review-actual")
        original.symlink_to(self.fx.pack / "review-actual", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()

    def test_symlink_on_final_study_json_is_rejected(self):
        linked = self.fx.root / "alias-study.json"
        linked.symlink_to(self.fx.study)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked(study=linked)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX-only named pipes")
    def test_fifo_private_json_rejected_without_blocking(self):
        self.fx.study.unlink()
        os.mkfifo(self.fx.study)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()

    def test_oversize_or_missing_private_json_rejected_without_echo(self):
        self.fx.study.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()
        self.fx.study.unlink()
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()

    def test_strict_external_study_id_must_match(self):
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked(identity="f" * 64)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked(identity="not-an-immutable-digest")

    def test_midscan_json_modification_is_not_certified_as_stable(self):
        real = gate.verify_study_pack_binding

        def change_after_real_scan(*args, **kwargs):
            result = real(*args, **kwargs)
            evidence = self.fx.private / "evidence.json"
            evidence.write_bytes(evidence.read_bytes() + b" ")
            return result

        with patch.object(gate, "verify_study_pack_binding",
                          side_effect=change_after_real_scan):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                self.checked()

    def test_midscan_directory_replacement_cannot_escape_inventory(self):
        real = gate.verify_study_pack_binding

        def replace_folder_after_scan(*args, **kwargs):
            result = real(*args, **kwargs)
            review = self.fx.review
            review.rename(self.fx.pack / "review-former")
            (self.fx.pack / "review").mkdir()
            return result

        with patch.object(gate, "verify_study_pack_binding",
                          side_effect=replace_folder_after_scan):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                self.checked()

    def test_cli_pass_and_private_paths_redacted(self):
        cmd = [sys.executable, "-m", "mixlab.quality.study_json_path_guard",
               str(self.fx.study), str(self.fx.pack), "--expected-study-id",
               self.fx.pinned]
        good = subprocess.run(cmd, text=True, capture_output=True, timeout=45)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["technical_gate"], "pass")
        bad = subprocess.run(cmd[:-1] + [str(self.fx.root / "PRIVATE-SECRET")],
                             text=True, capture_output=True, timeout=45)
        self.assertEqual(bad.returncode, 2)
        extra = subprocess.run(cmd + ["--PRIVATE-SECRET-OPTION"],
                               text=True, capture_output=True, timeout=45)
        self.assertEqual(extra.returncode, 2)
        for result in (good, bad, extra):
            self.assertNotIn(str(self.fx.root), result.stdout + result.stderr)
            self.assertNotIn(self.fx.pinned, result.stdout + result.stderr)
            self.assertNotIn("PRIVATE-SECRET", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
