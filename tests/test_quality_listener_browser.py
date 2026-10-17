"""Actual Chromium DOM/form submission smoke on synthetic offline MixLab review HTML.

Only generated rights-safe synthetic PCM16 WAVs, never real music, are used.
This is an interactive browser check, not an accessibility certification.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import struct
import wave
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


_AUDIO_SCRIPT = r"""
(() => {
  // Confirm the ACTUAL local file-backed WAV can be opened and decoded by the
  // browser, rather than trusting merely visible <audio controls> markup.
  const clips = [...document.querySelectorAll('fieldset audio')];
  if (clips.length !== 10) {
    document.documentElement.dataset.mixlabAudioCheck = 'fail';
    return;
  }
  let complete = false;
  const timeout = setTimeout(() => {
    if (!complete) document.documentElement.dataset.mixlabAudioCheck = 'timeout';
  }, 3000);
  Promise.all(clips.map((clip) => new Promise(resolve => {
    let settled = false;
    const finish = success => {
      if (settled) return;
      settled = true;
      resolve(success);
    };
    clip.addEventListener('loadedmetadata', () => finish(
      clip.readyState >= HTMLMediaElement.HAVE_METADATA &&
      clip.error === null &&
      clip.currentSrc.startsWith('file:') &&
      clip.duration >= 0.35 && clip.duration <= 0.45 &&
      clip.videoWidth === undefined
    ), {once: true});
    clip.addEventListener('error', () => finish(false), {once: true});
    clip.preload = 'auto';
    clip.load();
  }))).then(results => {
    complete = true;
    clearTimeout(timeout);
    document.documentElement.dataset.mixlabAudioCheck =
      results.every(Boolean) ? 'pass' : 'fail';
  });
})();
"""


def _synthetic_pcm_wav(path: Path, *, sample_rate=8000, channels=2):
    """Make a private, deterministic, permitted 0.4s PCM16 fixture."""
    frames = sample_rate * 2 // 5
    pcm = bytearray()
    for i in range(frames):
        # Non-silent, band-limited repeating ramp; no external source media.
        val = ((i % 64) - 32) * 280
        for channel in range(channels):
            pcm.extend(struct.pack("<h", val if channel == 0 else -val))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)


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


    def test_real_browser_loads_all_ten_offline_pcm16_sources(self):
        """No missing audio can pass: actual Chrome decodes all ten references."""
        page = self.root / "index.html"
        write_review(page, [f"trial-{i:03d}" for i in range(1, 6)], "a" * 64)
        for i in range(1, 6):
            for option in ("A", "B"):
                _synthetic_pcm_wav(self.root / f"trial-{i:03d}-{option}.wav",
                                   channels=1 if option == "A" else 2)
        source = page.read_text(encoding="utf-8")
        page.write_text(source.replace("</html>",
                                      "<script>" + _AUDIO_SCRIPT + "</script></html>"),
                        encoding="utf-8")
        command = [
            _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-extensions", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--virtual-time-budget=4500",
            "--user-data-dir=" + str(self.root / "pcm-chrome-profile"),
            "--dump-dom", page.as_uri(),
        ]
        env = dict(os.environ)
        env["HOME"] = str(self.root)
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  timeout=35, env=env)
        except subprocess.TimeoutExpired:
            self.fail("bounded synthetic Chrome WAV loading timed out")
        self.assertEqual(done.returncode, 0, "Offline Chromium WAV load failed")
        match = re.search(r'<html\b[^>]*data-mixlab-audio-check="([^"]+)"',
                          done.stdout, flags=re.IGNORECASE)
        self.assertIsNotNone(match, "offline Chrome media status marker was not rendered")
        self.assertEqual(match.group(1), "pass", "browser failed to decode a local WAV")



if __name__ == "__main__":
    unittest.main()
