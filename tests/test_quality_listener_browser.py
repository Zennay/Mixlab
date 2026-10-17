"""Actual Chromium DOM/form submission smoke on synthetic offline MixLab review HTML.

No WAVs, external packages, networks, or real reviewer responses are used.
This is an interactive browser check, not an accessibility certification.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from mixlab.cli import write_review

_BROWSER = (shutil.which("google-chrome") or shutil.which("google-chrome-stable")
            or shutil.which("chromium") or shutil.which("chromium-browser"))

_SCRIPT = r"""
(() => {
  const form = document.querySelector('form');
  const radios = [...document.querySelectorAll('fieldset select')];
  const controls = [...document.querySelectorAll('fieldset audio')];
  const fields = [...document.querySelectorAll('fieldset')];
  const originalBlob = window.Blob;
  let output = null;
  window.Blob = class RecordingBlob extends originalBlob {
    constructor(parts, options) {
      super(parts, options);
      output = parts.join('');
    }
  };
  // An isolated synthetic smoke must not initiate a real file download.
  HTMLAnchorElement.prototype.click = function() {};
  URL.createObjectURL = () => 'blob:synthetic-local';
  URL.revokeObjectURL = () => {};
  const values = ['A', 'B', 'Tie', 'Both unusable', 'A'];
  form.querySelector('input[name="reviewer"]').value = 'synthetic-listener';
  radios.forEach((select, index) => select.value = values[index]);
  radios[2].value = '';
  form.requestSubmit();
  const requiredActuallyWorks = output === null && !radios[2].validity.valid;
  radios[2].value = values[2];
  form.requestSubmit();
  let exported = null;
  try { exported = JSON.parse(output); } catch (e) {}
  const expected = fields.map((el, index) => ({
    trial: 'trial-' + String(index+1).padStart(3, '0'),
    preference: values[index],
  }));
  const ok = (
    requiredActuallyWorks &&
    form.dataset.packId === 'a'.repeat(64) &&
    controls.length === 10 && controls.every(a => a.controls) &&
    fields.length === 5 &&
    fields.every((el, i) => el.querySelector('legend')?.textContent === expected[i].trial) &&
    radios.every(select => select.required && select.validity.valid) &&
    exported?.schema_version === 1 &&
    exported?.pack_id === 'a'.repeat(64) &&
    exported?.reviewer === 'synthetic-listener' &&
    JSON.stringify(exported?.ratings) === JSON.stringify(expected) &&
    document.getElementById('status')?.textContent.includes('Ratings downloaded')
  );
  document.documentElement.setAttribute('data-mixlab-browser-check', ok ? 'pass' : 'fail');
})();
"""


@unittest.skipUnless(_BROWSER, "Optional local Chromium executable not available")
class BrowserFormTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_real_browser_submits_and_serializes_all_choices(self):
        page = self.root / "synthetic-review.html"
        write_review(page, [f"trial-{i:03d}" for i in range(1, 6)], "a" * 64)
        # The instrumentation is isolated to this test file, not the canonical
        # review page and not any private study's original HTML.
        raw = page.read_text(encoding="utf-8")
        self.assertIn("</html>", raw)
        page.write_text(raw.replace("</html>", "<script>" + _SCRIPT + "</script></html>"),
                        encoding="utf-8")
        command = [
            _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-extensions", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--virtual-time-budget=2500",
            "--user-data-dir=" + str(self.root / "chrome-profile"),
            "--dump-dom", page.as_uri(),
        ]
        env = dict(os.environ)
        env["HOME"] = str(self.root)
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  timeout=35, env=env)
        except subprocess.TimeoutExpired:
            self.fail("bounded synthetic Chrome DOM test timed out")
        self.assertEqual(done.returncode, 0, "Chromium DOM smoke failed")
        match = re.search(r"<html\b[^>]*data-mixlab-browser-check=\"([^\"]+)\"",
                          done.stdout, flags=re.IGNORECASE)
        self.assertIsNotNone(match, "instrumented browser marker was not rendered")
        self.assertEqual(match.group(1), "pass", "browser controls/export integrity failed")


if __name__ == "__main__":
    unittest.main()
