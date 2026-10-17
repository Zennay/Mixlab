"""Rights-free contract tests; no listener identities or audio uploads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
        self.patch('name="reviewer" required maxlength="40"',
                   'name="reviewer" required pattern="' + BROWSER_PATTERN +
                   '" maxlength="40"')

    def test_current_canonical_generator_has_real_ingest_mismatch(self):
        # Expected release HOLD until the separate CLI generator owner fixes it.
        report = self.checked()
        self.assertEqual(report["technical_gate"], "hold")
        self.assertFalse(report["reviewer_input_contract_compatible"])
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
        hold = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        self.assertEqual(hold.returncode, 3, hold.stderr)
        self.assertEqual(json.loads(hold.stdout)["technical_gate"], "hold")
        self.fixed()
        passed = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads(passed.stdout)["technical_gate"], "pass")
        self.page.unlink()
        invalid = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        self.assertEqual(invalid.returncode, 2)
        for result in (hold, passed, invalid):
            self.assertNotIn(str(self.root), result.stdout + result.stderr)
        extra = subprocess.run(cmd + [str(self.root / "SECRET.wav")],
                               text=True, capture_output=True, timeout=10)
        self.assertEqual(extra.returncode, 2)
        self.assertNotIn(str(self.root), extra.stdout + extra.stderr)


if __name__ == "__main__":
    unittest.main()
