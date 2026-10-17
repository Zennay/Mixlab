"""Rights-safe synthetic contracts for the standalone blind review control gate."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mixlab.cli import write_review
from mixlab.quality.listener_controls import check_review_controls


class ListenerControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "private-review-index.html"
        write_review(self.path, ["trial-001", "trial-002"], "a" * 64)

    def mutate(self, before, after):
        page = self.path.read_text(encoding="utf-8")
        self.assertIn(before, page)
        self.path.write_text(page.replace(before, after, 1), encoding="utf-8")

    def reject(self):
        with self.assertRaisesRegex(ValueError, "^invalid or inaccessible offline review controls$"):
            check_review_controls(self.path)

    def test_generated_offline_review_is_accepted_without_private_wavs(self):
        actual = check_review_controls(self.path)
        self.assertEqual(actual["trial_count"], 2)
        self.assertEqual(actual["playback_controls"], 4)
        self.assertEqual(actual["required_rating_controls"], 2)
        self.assertTrue(actual["static_listener_controls_verified"])
        self.assertFalse(actual["human_musical_preference_verified"])
        self.assertNotIn(str(self.root), json.dumps(actual))
        self.assertNotIn("a" * 64, json.dumps(actual))

    def test_missing_required_preference_is_rejected(self):
        self.mutate('<select required name="trial-001">', '<select name="trial-001">')
        self.reject()

    def test_missing_or_transposed_choice_is_rejected(self):
        self.mutate('<option>Tie</option>', '<option>Both unusable</option>')
        self.reject()

    def test_swapped_rating_name_is_rejected(self):
        self.mutate('<select required name="trial-001">', '<select required name="trial-002">')
        self.reject()

    def test_review_audio_without_controls_is_rejected(self):
        self.mutate('<audio controls preload="none"', '<audio preload="none"')
        self.reject()

    def test_cross_trial_audio_src_is_rejected(self):
        self.mutate('src="trial-001-A.wav"', 'src="trial-002-A.wav"')
        self.reject()

    def test_audio_label_removed_is_rejected(self):
        self.mutate('<label>A<audio', '<label>Unlabelled<audio')
        self.reject()

    def test_disabled_select_is_rejected(self):
        self.mutate('<select required', '<select disabled required')
        self.reject()

    def test_hidden_audio_is_rejected(self):
        self.mutate('<audio controls', '<audio aria-hidden="true" controls')
        self.reject()

    def test_negative_tabindex_rejected(self):
        self.mutate('<button>', '<button tabindex="-1">')
        self.reject()

    def test_review_identifier_must_be_anonymous_canonical(self):
        self.mutate('data-pack-id="' + "a" * 64 + '"', 'data-pack-id="private-music"')
        self.reject()

    def test_no_unlabelled_reviewer_field(self):
        self.mutate('<label>Anonymous reviewer code ', '<label> ')
        self.reject()

    def test_no_optional_reviewer_field(self):
        self.mutate('name="reviewer" required', 'name="reviewer"')
        self.reject()

    def test_duplicate_html_attribute_is_rejected(self):
        self.mutate('<audio controls', '<audio controls controls')
        self.reject()

    def test_duplicate_or_missing_trial_rejected(self):
        self.mutate('data-trial="trial-002"', 'data-trial="trial-001"')
        self.reject()

    def test_nonsequential_trial_rejected(self):
        self.mutate('data-trial="trial-002"', 'data-trial="trial-003"')
        self.reject()

    def test_status_announcer_must_be_available(self):
        self.mutate('id="status" aria-live="polite"', 'id="status"')
        self.reject()

    def test_extra_unlabelled_audio_rejected(self):
        self.mutate('</fieldset>', '<audio controls preload="none" src="extra.wav"></audio></fieldset>')
        self.reject()

    def test_browser_inert_wrappers_are_rejected(self):
        for wrapper in ("template", "noscript", "textarea", "xmp", "plaintext"):
            with self.subTest(wrapper=wrapper):
                write_review(self.path, ["trial-001", "trial-002"], "a" * 64)
                self.mutate('<fieldset data-trial="trial-001">',
                            f'<{wrapper}><fieldset data-trial="trial-001">')
                self.reject()

    def test_event_handler_on_audio_or_submit_is_rejected(self):
        for before, after in (
            ('<audio controls', '<audio onplay="alert(1)" controls'),
            ('<button>', '<button onclick="alert(1)">'),
        ):
            with self.subTest(element=before):
                write_review(self.path, ["trial-001", "trial-002"], "a" * 64)
                self.mutate(before, after)
                self.reject()

    def test_inline_css_hiding_and_positive_tab_reorder_are_rejected(self):
        for before, after in (
            ('<label>A<audio', '<label style="display:none">A<audio'),
            ('<button>', '<button tabindex="999">'),
        ):
            with self.subTest(element=before):
                write_review(self.path, ["trial-001", "trial-002"], "a" * 64)
                self.mutate(before, after)
                self.reject()

    def test_form_action_cannot_upload_private_answers(self):
        self.mutate('<form data-pack-id=', '<form action="https://example.invalid/ratings" data-pack-id=')
        self.reject()

    def test_external_script_disallowed(self):
        self.mutate('<script>', '<script src="https://example.invalid/remote.js">')
        self.reject()

    def test_trailing_inert_markup_rejected(self):
        self.mutate('</html>', '<template>hidden answers</template></html>')
        self.reject()

    def test_valid_one_trial(self):
        write_review(self.path, ["trial-001"], "f" * 64)
        self.assertEqual(check_review_controls(self.path)["trial_count"], 1)

    def test_zero_and_excess_trials_rejected(self):
        for count in (0, 61):
            with self.subTest(count=count):
                write_review(self.path, [f"trial-{n:03d}" for n in range(1, count + 1)], "a" * 64)
                self.reject()

    def test_symlink_and_symlinked_parent_are_rejected(self):
        link = self.root / "symlink.html"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            check_review_controls(link)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            check_review_controls(alias / self.path.name)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_refused_before_read(self):
        fifo = self.root / "fifo.html"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            check_review_controls(fifo)

    def test_oversize_and_invalid_utf8_rejected(self):
        self.path.write_bytes(b"z" * (1024 * 1024 + 1))
        self.reject()
        self.path.write_bytes(b"\xff\xfe")
        self.reject()

    def test_source_mutation_between_reads_rejected(self):
        import mixlab.quality.listener_controls as module
        opener = module._open_no_symlink_components
        calls = 0
        def mutate_after_first_open(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                page = self.path.read_bytes()
                self.path.write_bytes(page[:-1] + b" ")
            return opener(path)
        with patch.object(module, "_open_no_symlink_components", side_effect=mutate_after_first_open):
            self.reject()

    def test_cli_success_and_no_private_data(self):
        proc = subprocess.run([sys.executable, "-m", "mixlab.quality.listener_controls",
                               str(self.path)], capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["static_listener_controls_verified"])
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)

    def test_cli_error_with_private_paths_redacted(self):
        private = self.root / "TOP SECRET Song 2026.wav"
        for args in ([str(private)], [str(self.path), str(private)], ["--unknown=" + str(private)]):
            with self.subTest(args=args):
                proc = subprocess.run([sys.executable, "-m", "mixlab.quality.listener_controls",
                                       *args], capture_output=True, text=True, timeout=15)
                self.assertIn(proc.returncode, (2, 3))
                self.assertEqual(proc.stdout, "")
                self.assertNotIn(str(private), proc.stderr)
                self.assertNotIn(str(self.root), proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

    def test_invalid_markup_doctype_not_counted_as_complete_form(self):
        self.path.write_text("<!doctype html><html lang='en'></html>")
        self.reject()


if __name__ == "__main__":
    unittest.main()
