"""Headless Chromium reviewer-code parity, using only synthetic offline HTML.

Tests the canonical generator in either state (unrepaired or patched), plus
the proposed guarded input. A future upstream repair must not break these
quality tests. The instrumented page is disposable and never distributed.
"""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from mixlab.cli import write_review, benchmark, fixture
from mixlab.evaluation import aggregate
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
  const expectedGuarded = input.hasAttribute('pattern');
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
                    if guarded and 'name="reviewer" required pattern="' + BROWSER_PATTERN + '"' not in html:
                        self.assertIn('name="reviewer" required maxlength="40"', html)
                        html = html.replace(
                            'name="reviewer" required maxlength="40"',
                            'name="reviewer" required pattern="' + BROWSER_PATTERN +
                            '" maxlength="40"', 1,
                        )
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



    def test_chromium_reviewer_pattern_matches_actual_python_ingest_edge_matrix(self):
        """Native v-mode pattern agrees with the real aggregator grammar.

        Compare the browser's *sanitized input.value*, not the assigned raw
        test string (HTML text inputs can normalize carriage returns).
        """
        from mixlab.quality.reviewer_export_parity import INGEST_PATTERN
        candidates = [
            "", " ", "A", "a", "7", "-", "_", "0_", "A-", "A_",
            "A"*40, "A"*41, "A"*39+"_", "A"*39+"-", "A"*39+" ",
            "A\n", "A\rB", "A\tB", "é", "Aé", "e\u0301", "B\u200bC",
            "A😀", "🔒", "A！", "a\u00a0", " a", "a ", "A/B",
            "Z" * 39 + "é", "Z" * 40 + "é", "A" * 40 + "-",
        ]
        candidates.extend(chr(n) for n in range(32, 127))
        candidates.extend("A" + chr(n) for n in range(32, 127))
        candidates.extend(chr(n) + "7" for n in range(32, 127))
        candidates.extend("a" * n for n in range(1, 43))
        # Use only synthetic pseudonyms; no personal identifiers or audio.
        self.assertGreater(len(candidates), 300)
        with tempfile.TemporaryDirectory(prefix="mixlab-browser-parity-matrix-") as temp:
            root = Path(temp)
            page = root / "synthetic-pattern.html"
            write_review(page, ["trial-001"], "a" * 64)
            raw = page.read_text(encoding="utf-8").replace(
                'name="reviewer" required maxlength="40"',
                'name="reviewer" required pattern="' + BROWSER_PATTERN +
                '" maxlength="40"', 1,
            )
            script = """
(() => {
  const input = document.querySelector('input[name="reviewer"]');
  const values = __VALUES__;
  const observations = [];
  for (const name of values) {
    input.value = name;
    // Collect what the browser would actually export and its native verdict.
    observations.push([input.value, input.checkValidity()]);
  }
  document.documentElement.dataset.parityMatrix64 =
    btoa(unescape(encodeURIComponent(JSON.stringify(observations))));
})();
""".replace("__VALUES__", json.dumps(candidates, ensure_ascii=True))
            page.write_text(raw.replace("</html>", "<script>" + script + "</script></html>"),
                            encoding="utf-8")
            cmd = [
                _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--disable-background-networking",
                "--disable-extensions", "--no-first-run", "--no-default-browser-check",
                "--disable-sync", "--virtual-time-budget=2500",
                "--user-data-dir=" + str(root / "chrome-profile"),
                "--dump-dom", page.as_uri(),
            ]
            env = dict(os.environ)
            env["HOME"] = str(root)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35, env=env)
            self.assertEqual(result.returncode, 0)
            measured = re.search(r'data-parity-matrix64="([A-Za-z0-9+/=]+)"', result.stdout)
            self.assertIsNotNone(measured, "chromium did not execute input matrix")
            observations = json.loads(base64.b64decode(measured.group(1)).decode("utf-8"))
            self.assertEqual(len(observations), len(candidates))
            for original, (normalized, native_allowed) in zip(candidates, observations):
                with self.subTest(raw=original):
                    self.assertIs(type(native_allowed), bool)
                    self.assertEqual(
                        native_allowed, INGEST_PATTERN.fullmatch(normalized) is not None,
                        "native browser validation differs from real Python rating-ingest regex",
                    )

    def test_real_synthetic_renderer_browser_export_to_aggregate(self):
        """Actual bounded MixLab engine + Chrome + rating ingest; never human evidence."""
        with tempfile.TemporaryDirectory(prefix="mixlab-parity-aggregate-") as temp:
            root = Path(temp)
            manifest = fixture(root / "source")
            pack = root / "pack"
            benchmark(manifest, pack, seed=17)
            page = pack / "review" / "index.html"
            canonical_html = page.read_text(encoding="utf-8")
            # Only instrument a *temporary copy*: canonical pack files remain
            # immutable so verify_pack() can independently check every PCM hash.
            disposable = root / "instrumented-review.html"
            script = r"""
(() => {
  const form = document.querySelector('form');
  const selects = [...form.querySelectorAll('fieldset select')];
  selects.forEach(select => select.value = 'Tie');
  const input = form.querySelector('input[name="reviewer"]');
  const OriginalBlob = window.Blob;
  const captured = [];
  window.Blob = class CapturedJSON extends OriginalBlob {
    constructor(parts, options) {
      super(parts, options);
      captured.push(parts.join(''));
    }
  };
  HTMLAnchorElement.prototype.click = function() {};
  URL.createObjectURL = () => 'blob:synthetic';
  URL.revokeObjectURL = () => {};
  const submit = name => {
    input.value = name;
    const previous = captured.length;
    form.requestSubmit();
    if (captured.length !== previous + 1) return null;
    return captured[captured.length - 1];
  };
  const guarded = input.hasAttribute('pattern');
  const invalid = submit('listener 01');
  const valid = submit('listener-01');
  const toBase64 = value => btoa(unescape(encodeURIComponent(value)));
  // Current production accepts invalid identities. After the owner fixes
  // native HTML validation, that same browser submission MUST be blocked.
  if (!valid || Boolean(invalid) === guarded) {
    document.documentElement.dataset.mixlabEndToEnd = 'fail';
    return;
  }
  document.documentElement.dataset.mixlabEndToEnd = 'pass';
  document.documentElement.dataset.reviewerGateState = guarded ? 'guarded' : 'unguarded';
  document.documentElement.dataset.invalidRating64 = invalid ? toBase64(invalid) : '';
  document.documentElement.dataset.validRating64 = toBase64(valid);
})();
"""
            disposable.write_text(
                canonical_html.replace("</html>", "<script>" + script + "</script></html>"),
                encoding="utf-8",
            )
            cmd = [
                _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--disable-background-networking",
                "--disable-extensions", "--no-first-run", "--no-default-browser-check",
                "--disable-sync", "--virtual-time-budget=2500",
                "--user-data-dir=" + str(root / "chrome-e2e"),
                "--dump-dom", disposable.as_uri(),
            ]
            env = dict(os.environ)
            env["HOME"] = str(root)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35, env=env)
            self.assertEqual(result.returncode, 0, "synthetic Chromium execution failed")
            marker = re.search(r'data-mixlab-end-to-end="([^"]+)"', result.stdout)
            self.assertIsNotNone(marker, "e2e browser marker absent")
            self.assertEqual(marker.group(1), "pass", "browser did not export both samples")

            def extract(attribute):
                found = re.search(attribute + r'="([^"]+)"', result.stdout)
                self.assertIsNotNone(found, "offline JSON payload absent")
                payload = json.loads(base64.b64decode(found.group(1)))
                self.assertEqual(payload["pack_id"],
                                 json.loads((pack / "receipt.json").read_text())["pack_id"])
                self.assertEqual(3, len(payload["ratings"]))
                self.assertTrue(all(r["preference"] == "Tie" for r in payload["ratings"]))
                return payload

            gate = re.search(r'data-reviewer-gate-state="(guarded|unguarded)"', result.stdout)
            self.assertIsNotNone(gate, "expected explicit browser gate state")
            valid = extract("data-valid-rating64")
            self.assertEqual(valid["reviewer"], "listener-01")
            broken_path, good_path = root / "invalid.json", root / "valid.json"
            good_path.write_text(json.dumps(valid), encoding="utf-8")
            if gate.group(1) == "guarded":
                # The future fixed generator must prevent an unusable export.
                self.assertIn('data-invalid-rating64=""', result.stdout)
            else:
                # Until then, prove that a completed browser session is lost.
                invalid = extract("data-invalid-rating64")
                self.assertEqual(invalid["reviewer"], "listener 01")
                broken_path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid reviewer pseudonym"):
                    aggregate(pack, [broken_path])
            accepted = aggregate(pack, [good_path])
            self.assertEqual(accepted["reviewers"], 1)
            self.assertEqual(accepted["trials"], 3)
            self.assertEqual(accepted["counts"]["ties"], 3)
            self.assertFalse(accepted["milestone_pass"])


if __name__ == "__main__":
    unittest.main()
