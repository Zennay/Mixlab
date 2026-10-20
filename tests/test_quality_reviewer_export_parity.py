"""Rights-free contract tests; no listener identities or audio uploads."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mixlab.cli import write_review
from mixlab.quality.reviewer_export_parity import (
    BROWSER_PATTERN, INGEST_PATTERN, inspect_reviewer_export_contract,
)


class ReviewerExportParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.page = self.root / "private reviewer page.html"
        write_review(self.page, ["trial-001", "trial-002"], "a" * 64)

    def checked(self):
        return inspect_reviewer_export_contract(self.page)

    def patch(self, old, new):
        html = self.page.read_text(encoding="utf-8")
        self.assertIn(old, html)
        self.page.write_text(html.replace(old, new, 1), encoding="utf-8")

    def fixed(self):
        """Idempotent after the CLI integration owner ships the pattern."""
        page = self.page.read_text(encoding="utf-8")
        reviewer_tag = re.search(r'<input\b[^>]*\bname="reviewer"[^>]*>', page)
        self.assertIsNotNone(reviewer_tag)
        if 'pattern="' + BROWSER_PATTERN + '"' in reviewer_tag.group():
            return
        self.patch('name="reviewer" required maxlength="40"',
                   'name="reviewer" required pattern="' + BROWSER_PATTERN +
                   '" maxlength="40"')

    def test_canonical_generator_emits_a_truthful_ingest_parity_verdict(self):
        # Current main is HOLD. Once the CLI owner fixes it, this test must
        # turn green-as-PASS rather than forever expecting the known defect.
        html = self.page.read_text(encoding="utf-8")
        reviewer_tag = re.search(r'<input\b[^>]*\bname="reviewer"[^>]*>', html)
        self.assertIsNotNone(reviewer_tag)
        has_guard = 'pattern="' + BROWSER_PATTERN + '"' in reviewer_tag.group()
        self.assertTrue(has_guard or 'maxlength="40"' in reviewer_tag.group())
        report = self.checked()
        self.assertEqual(report["technical_gate"], "pass" if has_guard else "hold")
        self.assertIs(report["reviewer_input_contract_compatible"], has_guard)
        self.assertFalse(report["release_authorized"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("trial-001", json.dumps(report))

    def test_contract_with_browser_safe_pattern_passes_static_parity(self):
        self.fixed()
        report = self.checked()
        self.assertEqual(report["technical_gate"], "pass")
        self.assertTrue(report["reviewer_input_contract_compatible"])
        self.assertFalse(report["browser_runtime_verified"])
        self.assertFalse(report["full_review_page_verified"])
        self.assertFalse(report["ratings_aggregate_verified"])
        self.assertFalse(report["human_musical_preference_proven"])

    def test_future_generator_patch_is_accepted_and_invalid_modification_still_holds(self):
        """Simulate owner's legitimate repair without editing their CLI scope."""
        from mixlab import cli

        original = cli.write_review

        def future_write_review(path, trial_ids, pack_id):
            original(path, trial_ids, pack_id)
            file = Path(path)
            body = file.read_text(encoding="utf-8")
            old = 'name="reviewer" required maxlength="40"'
            guarded = 'name="reviewer" required pattern="' + BROWSER_PATTERN + '" maxlength="40"'
            if old in body:
                body = body.replace(old, guarded, 1)
                file.write_text(body, encoding="utf-8")

        with patch.object(cli, "write_review", side_effect=future_write_review):
            future_write_review(self.page, ["trial-001", "trial-002"], "a" * 64)
            self.assertEqual(self.checked()["technical_gate"], "pass")
            # Even after the upstream repair, a changed JS response mapping
            # must still HOLD rather than inheriting trust from the generator.
            self.patch("preference:f.get(el.dataset.trial)", "preference:'A'")
            self.assertEqual(self.checked()["technical_gate"], "hold")

    def test_representative_pseudonym_acceptance_matches_aggregate(self):
        valid = ("A", "listener-01", "a9-_", "z" * 40)
        invalid = ("", " ", "listener 01", "équipe", " abc", "-bad", "_bad", "z" * 41)
        self.assertTrue(all(INGEST_PATTERN.fullmatch(code) for code in valid))
        self.assertTrue(all(not INGEST_PATTERN.fullmatch(code) for code in invalid))
        self.assertIn(r"\-", BROWSER_PATTERN)

    def test_weakened_browser_contracts_fail_closed(self):
        changes = [
            (' pattern="' + BROWSER_PATTERN + '"', ""),
            (' pattern="' + BROWSER_PATTERN + '"', ' pattern=".*"'),
            (' maxlength="40"', ' maxlength="39"'),
            (' maxlength="40"', ""),
            (' required', ""),
            (' name="reviewer"', ' name="listener"'),
            (' name="reviewer"', ' name="reviewer" readonly'),
            (' name="reviewer"', ' name="reviewer" value="listener-01"'),
            (' name="reviewer"', ' name="reviewer" hidden'),
            (' name="reviewer"', ' name="reviewer" disabled'),
            (' name="reviewer"', ' name="reviewer" type="email"'),
            (' name="reviewer"', ' name="reviewer" required'),
            ('<form data-pack-id=', '<form novalidate data-pack-id='),
            ('<button>', '<button formnovalidate>'),
            ('<button>', '<button formaction="https://example.invalid">'),
        ]
        for old, new in changes:
            with self.subTest(change=(old, new)):
                write_review(self.page, ["trial-001", "trial-002"], "a" * 64)
                self.fixed()
                self.patch(old, new)
                self.assertEqual(self.checked()["technical_gate"], "hold")


    def test_injected_bias_or_changed_export_script_cannot_certify_parity(self):
        attacks = (
            ("<form data-pack-id=", '<h2>Correct answer: A</h2><form data-pack-id='),
            ("<form data-pack-id=", '<a href="https://example.invalid">Send your rating</a><form data-pack-id='),
            ("preference:f.get(el.dataset.trial)", "preference:'A'"),
            ("document.querySelector('form').addEventListener", "document.querySelector('form').addEventListener('change',()=>{});document.querySelector('form').addEventListener"),
            ('<audio controls preload="none" src="trial-001-A.wav">',
             '<audio controls preload="none" src="trial-001-B.wav">'),
            ("<button>Download my ratings</button>",
             '<button>Download my ratings</button><script>fetch("https://example.invalid")</script>'),
            ("<style>", "<style>fieldset{display:none;}"),
        )
        for old, new in attacks:
            with self.subTest(attack=old):
                write_review(self.page, ["trial-001", "trial-002"], "a" * 64)
                self.fixed()
                self.patch(old, new)
                self.assertEqual(self.checked()["technical_gate"], "hold")

    def test_fake_pack_id_or_noncontiguous_trial_never_passes(self):
        edits = (
            ('data-pack-id="' + 'a' * 64 + '"',
             'data-pack-id="' + 'not-a-digest' + '"'),
            ('<fieldset data-trial="trial-002">',
             '<fieldset data-trial="trial-003">'),
            ('<fieldset data-trial="trial-002">',
             '<fieldset data-trial="trial-001">'),
        )
        for before, after in edits:
            with self.subTest(edit=before):
                write_review(self.page, ["trial-001", "trial-002"], "a" * 64)
                self.fixed()
                self.patch(before, after)
                self.assertEqual(self.checked()["technical_gate"], "hold")

    def test_duplicate_reviewer_input_is_rejected(self):
        self.fixed()
        self.patch('<button>Download my ratings</button>',
                   '<input name="reviewer" required pattern="' + BROWSER_PATTERN +
                   '" maxlength="40"><button>Download my ratings</button>')
        self.assertEqual(self.checked()["technical_gate"], "hold")

    def test_no_follow_source_or_ancestor_symlinks(self):
        self.fixed()
        alias = self.root / "alias.html"
        alias.symlink_to(self.page)
        with self.assertRaises(ValueError):
            inspect_reviewer_export_contract(alias)
        parent = self.root / "linked"
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            inspect_reviewer_export_contract(parent / self.page.name)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX only")
    def test_fifo_is_refused_without_blocking(self):
        fifo = self.root / "private FIFO.html"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            inspect_reviewer_export_contract(fifo)

    def test_large_utf8_and_missing_files_fail_without_private_path(self):
        self.page.write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()
        self.page.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()
        self.page.unlink()
        with self.assertRaisesRegex(ValueError, "details withheld"):
            self.checked()

    def test_cli_distinguishes_hold_from_invalid_from_parity(self):
        cmd = [sys.executable, "-m", "mixlab.quality.reviewer_export_parity", str(self.page)]
        baseline = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        official_html = self.page.read_text(encoding="utf-8")
        reviewer_tag = re.search(r'<input\b[^>]*\bname="reviewer"[^>]*>', official_html)
        self.assertIsNotNone(reviewer_tag)
        official_guarded = 'pattern="' + BROWSER_PATTERN + '"' in reviewer_tag.group()
        self.assertEqual(baseline.returncode, 0 if official_guarded else 3, baseline.stderr)
        self.assertEqual(json.loads(baseline.stdout)["technical_gate"],
                         "pass" if official_guarded else "hold")
        self.fixed()
        passed = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads(passed.stdout)["technical_gate"], "pass")
        self.page.unlink()
        invalid = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        self.assertEqual(invalid.returncode, 2)
        for result in (baseline, passed, invalid):
            self.assertNotIn(str(self.root), result.stdout + result.stderr)
        extra = subprocess.run(cmd + [str(self.root / "SECRET.wav")],
                               text=True, capture_output=True, timeout=10)
        self.assertEqual(extra.returncode, 2)
        self.assertNotIn(str(self.root), extra.stdout + extra.stderr)


if __name__ == "__main__":
    unittest.main()
