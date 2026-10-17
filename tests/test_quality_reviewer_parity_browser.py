"""Headless Chromium reviewer-code parity, using only synthetic offline HTML.

Tests both the vulnerable canonical generator and the proposed guarded
input. The instrumented page is disposable and never distributed to listeners.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from mixlab.cli import write_review
from mixlab.quality.reviewer_export_parity import BROWSER_PATTERN

_BROWSER = (shutil.which("google-chrome") or shutil.which("google-chrome-stable")
            or shutil.which("chromium") or shutil.which("chromium-browser"))

_SCRIPT = r"""
(() => {
  const form = document.querySelector('form');
  const input = form.querySelector('input[name=reviewer]');
  const choice = form.querySelector('fieldset select');
  const captures = [];
  const OriginalBlob = window.Blob;
  window.Blob = class CapturedOnly extends OriginalBlob {
    constructor(parts, opts) { super(parts, opts); captures.push(parts.join('')); }
  };
  HTMLAnchorElement.prototype.click = function() {};
  URL.createObjectURL = () => 'blob:synthetic-test';
  URL.revokeObjectURL = () => {};
  choice.value = 'Tie';
  const invalid = ['listener 01', 'équipe', ' leading', '-leading', '_leading'];
  const observed = [];
  for (const code of invalid) {
    input.value = code;
    const valid = form.checkValidity();
    const before = captures.length;
    form.requestSubmit();
    observed.push({
      valid,
      exported: captures.length > before,
    });
  }
  input.value = 'listener_01';
  const validAllowed = form.checkValidity();
  const before = captures.length;
  form.requestSubmit();
  let decoded = null;
  if (captures.length > before) {
    try { decoded = JSON.parse(captures[captures.length - 1]); } catch (e) {}
  }
  // The original generated HTML is supposed to demonstrate the defect;
  // proposed guarded HTML must refuse the invalid identities.
  const expectedGuarded = document.documentElement.dataset.guarded === 'yes';
  const failures = observed.filter(r => expectedGuarded ? (r.valid || r.exported)
                                                        : (!r.valid || !r.exported));
  const success =
    failures.length === 0 &&
    validAllowed && decoded?.reviewer === 'listener_01' &&
    decoded?.pack_id === 'a'.repeat(64) &&
    JSON.stringify(decoded?.ratings) === JSON.stringify([
      {trial: 'trial-001', preference: 'Tie'}
    ]) &&
    document.querySelector('#status')?.textContent.includes('Ratings downloaded');
  document.documentElement.dataset.parityBrowserCheck = success ? 'pass' : 'fail';
})();
"""


@unittest.skipUnless(_BROWSER, "Chromium unavailable; dedicated hosted CI requires it")
class ReviewerParityBrowserTests(unittest.TestCase):
    def test_browser_reproduces_current_export_mismatch_and_guards_proposed_fix(self):
        with tempfile.TemporaryDirectory(prefix="mixlab-synthetic-parity-") as temp:
            root = Path(temp)
            for guarded in (False, True):
                with self.subTest(guarded=guarded):
                    page = root / ("guarded.html" if guarded else "current.html")
                    write_review(page, ["trial-001"], "a" * 64)
                    html = page.read_text(encoding="utf-8")
                    if guarded:
                        html = html.replace(
                            'name="reviewer" required maxlength="40"',
                            'name="reviewer" required pattern="' + BROWSER_PATTERN +
                            '" maxlength="40"',
                            1,
                        )
                        html = html.replace('<html lang="en">',
                                            '<html lang="en" data-guarded="yes">', 1)
                    self.assertIn("</html>", html)
                    page.write_text(html.replace(
                        "</html>", "<script>" + _SCRIPT + "</script></html>"
                    ), encoding="utf-8")
                    profile = root / ("chrome-guarded" if guarded else "chrome-current")
                    cmd = [
                        _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
                        "--disable-dev-shm-usage", "--disable-background-networking",
                        "--disable-extensions", "--no-first-run",
                        "--no-default-browser-check", "--disable-sync",
                        "--virtual-time-budget=2500",
                        "--user-data-dir=" + str(profile), "--dump-dom", page.as_uri(),
                    ]
                    env = dict(os.environ)
                    env["HOME"] = str(root)
                    done = subprocess.run(cmd, capture_output=True, text=True,
                                          timeout=35, env=env)
                    self.assertEqual(done.returncode, 0, "headless Chromium failed")
                    marker = re.search(
                        r"<html\b[^>]*data-parity-browser-check=\"([^\"]+)\"",
                        done.stdout, flags=re.IGNORECASE,
                    )
                    self.assertIsNotNone(marker, "browser QA marker absent")
                    self.assertEqual(marker.group(1), "pass",
                                     "browser reviewer grammar/export mismatch")


if __name__ == "__main__":
    unittest.main()
