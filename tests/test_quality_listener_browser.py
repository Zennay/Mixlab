"""Actual Chromium DOM/form submission smoke on synthetic offline MixLab review HTML.

Only generated rights-safe synthetic PCM16 WAVs, never real music, are used.
This is an interactive browser check, not an accessibility certification.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import struct
import wave
import subprocess
import tempfile
import unittest

from mixlab.cli import benchmark, fixture, write_review
from mixlab.evaluation import aggregate, verify_pack
from mixlab.quality.listener_controls import check_review_controls
from mixlab.quality.pack import inspect_review_pack

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


_FULL_DECODE_SCRIPT = r"""
(() => {
  const result = value => {
    document.documentElement.dataset.mixlabFullDecodeCheck = value;
  };
  try {
    const raw = atob('__PCM_BASE64__');
    const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
    // OfflineAudioContext does not require a physical playback device.
    // decodeAudioData must parse ALL frames and produce non-silent PCM.
    const context = new OfflineAudioContext(2, 3200, 8000);
    context.decodeAudioData(bytes.buffer).then(buffer => {
      const left = buffer.getChannelData(0);
      const right = buffer.getChannelData(1);
      const ok = buffer.sampleRate === 8000 &&
        buffer.numberOfChannels === 2 && buffer.length === 3200 &&
        Math.abs(left[100]) > 0.01 &&
        Math.abs(left[100] + right[100]) < 0.001 &&
        Math.abs(left[100]) < 1 &&
        buffer.duration >= 0.39 && buffer.duration <= 0.41;
      result(ok ? 'pass' : 'fail');
    }).catch(() => result('fail'));
  } catch (error) {
    result('fail');
  }
})();
"""


_PLAYBACK_SCRIPT = r"""
(() => {
  const clip = document.querySelector('fieldset audio');
  const finish = outcome => {
    document.documentElement.dataset.mixlabPlaybackCheck = outcome;
  };
  if (!clip) { finish('fail'); return; }
  const markStage = label => {
    document.documentElement.dataset.mixlabPlaybackStage = label;
  };
  markStage('requested');
  clip.addEventListener('loadedmetadata', () => markStage('metadata'), {once:true});
  clip.addEventListener('playing', () => markStage('playing'), {once:true});
  clip.addEventListener('timeupdate', () => {
    if (clip.currentTime >= 0.2) markStage('time-advanced');
  });
  let resolved = false;
  const done = success => {
    if (resolved) return;
    resolved = true;
    clearTimeout(timeout);
    finish(success ? 'pass' : 'fail');
  };
  const timeout = setTimeout(() => done(false), 3500);
  clip.addEventListener('error', () => {
    markStage('media-error');
    done(false);
  }, {once: true});
  clip.addEventListener('ended', () => done(
    clip.ended && clip.error === null && clip.currentTime >= 0.35
  ), {once: true});
  // This synthetic-only headless browser has an explicit autoplay policy,
  // never an external audio device or access to user media.
  clip.play().then(() => {
    markStage('play-promise-resolved');
    // Hosted Chrome virtual-time may outrun real audio time progression.
    // The resolved HTMLMediaElement.play() promise proves media playback
    // initiation was accepted, NOT that physical audio finished.
    done(clip.error === null &&
         clip.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA);
  }).catch(() => { markStage('play-promise-rejected'); done(false); });
})();
"""


_INTEGRATED_SCRIPT = r"""
(() => {
  const clips = [...document.querySelectorAll('fieldset audio')];
  const form = document.querySelector('form');
  let payload = null;
  const realBlob = window.Blob;
  window.Blob = class CapturedSyntheticBlob extends realBlob {
    constructor(parts, options) {
      super(parts, options);
      payload = parts.join('');
    }
  };
  HTMLAnchorElement.prototype.click = function() {};
  URL.createObjectURL = () => 'blob:synthetic-local-only';
  URL.revokeObjectURL = () => {};
  form.querySelector('input[name="reviewer"]').value = 'synthetic-reviewer';
  const choices = ['A', 'Tie', 'Both unusable'];
  [...form.querySelectorAll('fieldset select')].forEach(
    (select, i) => { select.value = choices[i]; }
  );
  form.requestSubmit();
  let rating = null;
  try { rating = JSON.parse(payload); } catch(e) {}
  const ratingsOk = rating?.schema_version === 1 &&
    rating?.pack_id === form.dataset.packId &&
    rating?.reviewer === 'synthetic-reviewer' &&
    JSON.stringify(rating?.ratings) === JSON.stringify([
      {trial:'trial-001', preference:'A'},
      {trial:'trial-002', preference:'Tie'},
      {trial:'trial-003', preference:'Both unusable'}
    ]) &&
    document.querySelector('#status')?.textContent.includes('Ratings downloaded');
  // Wait for genuine browser metadata events from actual M1-engine WAV
  // renders, not stand-in files written by the HTML test.
  const result = clips.length === 6 ? Promise.all(clips.map(clip =>
    new Promise(resolve => {
      let settled = false;
      const finish = ok => {
        if (settled) return;
        settled = true;
        resolve(ok);
      };
      clip.addEventListener('loadedmetadata', () => finish(
        clip.error === null &&
        clip.readyState >= HTMLMediaElement.HAVE_METADATA &&
        clip.duration >= 3.95 && clip.duration <= 4.05 &&
        clip.currentSrc.startsWith('file:')
      ), {once: true});
      clip.addEventListener('error', () => finish(false), {once: true});
      clip.preload = 'auto';
      clip.load();
    })
  )) : Promise.resolve([false]);
  const timeout = setTimeout(() => {
    document.documentElement.dataset.mixlabIntegratedCheck = 'timeout';
  }, 3000);
  result.then(flags => {
    clearTimeout(timeout);
    const ok = ratingsOk && flags.length === 6 && flags.every(Boolean);
    document.documentElement.dataset.mixlabIntegratedCheck = ok ? 'pass' : 'fail';
    document.documentElement.dataset.mixlabIntegratedRatings =
      ok ? btoa(payload) : '';
  });
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

        # The success gate must be a real decoder check, not just a count of
        # visible controls. Remove one of the verified ten WAVs: a NEW browser
        # profile must visibly mark the entire pack failed, not accept nine.
        missing = self.root / "trial-005-B.wav"
        missing.unlink()
        for scenario in ("missing", "corrupt"):
            if scenario == "corrupt":
                # Present but structurally undecodable audio must also fail.
                missing.write_bytes(b"RIFF" + b"\x00" * 36)
            new_command = [
                "--user-data-dir=" + str(self.root / f"pcm-chrome-negative-{scenario}")
                if arg.startswith("--user-data-dir=") else arg
                for arg in command
            ]
            try:
                bad = subprocess.run(new_command, capture_output=True, text=True,
                                     timeout=35, env=env)
            except subprocess.TimeoutExpired:
                self.fail("negative offline Chrome WAV check timed out")
            self.assertEqual(bad.returncode, 0, "Chromium negative media smoke crashed")
            bad_marker = re.search(r'<html\b[^>]*data-mixlab-audio-check="([^"]+)"',
                                   bad.stdout, flags=re.IGNORECASE)
            self.assertIsNotNone(bad_marker, "negative PCM decoder result missing")
            self.assertEqual(bad_marker.group(1), "fail",
                             "missing or undecodable audio was incorrectly accepted")


    def test_actual_engine_render_to_browser_to_evaluation_pipeline(self):
        """Original synthetic -> MixLab DSP -> browser -> frozen evaluation."""
        manifest_path = fixture(self.root / "procedural-library")
        receipt_path = benchmark(manifest_path, self.root / "rendered-pack", seed=42)
        pack_root = receipt_path.parent
        review = pack_root / "review"
        canonical_page = review / "index.html"

        controls = check_review_controls(canonical_page)
        self.assertEqual(controls["trial_count"], 3)
        quality = inspect_review_pack(
            review, require_generated_html=True, require_receipt=True
        )
        self.assertEqual(quality["trial_count"], 3)
        self.assertTrue(quality["official_generated_html_verified"])
        self.assertTrue(quality["review_page_audio_links_verified"])
        self.assertTrue(quality["public_receipt_pack_id_verified"])
        self.assertFalse(quality["answer_key_opened"])
        receipt, evidence, trials = verify_pack(pack_root)
        self.assertEqual(len(trials), 3)
        self.assertEqual(receipt["status"], "rendered-not-listener-validated")

        # Only the temporary test copy is instrumented. Real private proof,
        # renderer evidence, answer-key and the canonical page remain intact.
        browser_copy = self.root / "temporary-browser-review-copy"
        browser_copy.mkdir()
        for source in review.glob("trial-*.wav"):
            shutil.copyfile(source, browser_copy / source.name)
        instrumented = browser_copy / "index.html"
        text = canonical_page.read_text(encoding="utf-8")
        instrumented.write_text(
            text.replace("</html>",
                         "<script>" + _INTEGRATED_SCRIPT + "</script></html>"),
            encoding="utf-8"
        )
        command = [
            _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-extensions", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--virtual-time-budget=5000",
            "--user-data-dir=" + str(self.root / "pipeline-chrome-profile"),
            "--dump-dom", instrumented.as_uri()
        ]
        env = dict(os.environ)
        env["HOME"] = str(self.root)
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  timeout=40, env=env)
        except subprocess.TimeoutExpired:
            self.fail("bounded engine-to-browser smoke timed out")
        self.assertEqual(done.returncode, 0, "Chromium could not open offline render pack")
        marker = re.search(r'<html\b[^>]*data-mixlab-integrated-check="([^"]+)"',
                           done.stdout, flags=re.IGNORECASE)
        self.assertIsNotNone(marker, "browser synthetic pipeline marker missing")
        self.assertEqual(marker.group(1), "pass", "render/browser study pipeline failed")
        token = re.search(
            r'<html\b[^>]*data-mixlab-integrated-ratings="([^"]+)"',
            done.stdout, flags=re.IGNORECASE
        )
        self.assertIsNotNone(token, "browser synthetic ratings receipt missing")
        rating = json.loads(base64.b64decode(token.group(1), validate=True))
        self.assertEqual(rating["pack_id"], receipt["pack_id"])
        self.assertEqual([row["preference"] for row in rating["ratings"]],
                         ["A", "Tie", "Both unusable"])

        # A software-generated rating is not a real human vote. Confirm the
        # existing aggregator accepts the exact browser export while always
        # withholding any musical milestone/preference proof.
        synthetic_rating_path = self.root / "synthetic-browser-rating.json"
        synthetic_rating_path.write_text(json.dumps(rating), encoding="utf-8")
        aggregate_report = aggregate(pack_root, [synthetic_rating_path])
        self.assertEqual(aggregate_report["reviewers"], 1)
        self.assertEqual(aggregate_report["trials"], 3)
        self.assertEqual(sum(aggregate_report["counts"].values()), 3)
        self.assertFalse(aggregate_report["milestone_pass"])
        self.assertEqual(aggregate_report["status"],
                         "descriptive-only-requires-independent-human-review")

        # Rebuild the entire software-only experiment from the same manifest
        # and seeded assignment. Reproducible output/answer identities are
        # essential for review of a frozen benchmark, but synthetic seed use
        # is deliberately NOT a blind human listening protocol.
        second_receipt = benchmark(
            manifest_path, self.root / "replayed-rendered-pack", seed=42
        )
        second = json.loads(second_receipt.read_text(encoding="utf-8"))
        self.assertEqual(second["pack_id"], receipt["pack_id"])
        self.assertEqual(second["trial_count"], receipt["trial_count"])
        self.assertEqual(second["render_count"], receipt["render_count"])
        _, _, second_trials = verify_pack(second_receipt.parent)
        self.assertEqual(second_trials, trials)

    def test_browser_accepts_local_pcm_play_request(self):
        """Prove HTMLMediaElement.play accepts original WAV; not physical audio."""
        wav = self.root / "trial-001-A.wav"
        _synthetic_pcm_wav(wav)
        page = self.root / "playback-review.html"
        write_review(page, ["trial-001"], "a" * 64)
        original = page.read_text(encoding="utf-8")
        page.write_text(
            original.replace("</html>",
                             "<script>" + _PLAYBACK_SCRIPT + "</script></html>"),
            encoding="utf-8"
        )
        command = [
            _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-extensions", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--mute-audio",
            "--autoplay-policy=no-user-gesture-required",
            "--virtual-time-budget=5000",
            "--user-data-dir=" + str(self.root / "playback-chrome-profile"),
            "--dump-dom", page.as_uri(),
        ]
        env = dict(os.environ)
        env["HOME"] = str(self.root)
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  timeout=35, env=env)
        except subprocess.TimeoutExpired:
            self.fail("bounded synthetic browser playback timed out")
        self.assertEqual(done.returncode, 0, "Chromium playback process failed")
        marker = re.search(r'<html\b[^>]*data-mixlab-playback-check="([^"]+)"',
                           done.stdout, flags=re.IGNORECASE)
        self.assertIsNotNone(marker, "browser did not report playback outcome")
        stage = re.search(r'<html\b[^>]*data-mixlab-playback-stage="([^"]+)"',
                          done.stdout, flags=re.IGNORECASE)
        phase = stage.group(1) if stage else "no-stage"
        self.assertEqual(marker.group(1), "pass",
                         f"browser did not accept local PCM play request (phase: {phase})")

    def test_browser_decodes_full_synthetic_pcm_without_audio_hardware(self):
        """Full WebAudio PCM decode with a corrupt-data negative control."""
        raw_wav = self.root / "synthetic-full-decode.wav"
        _synthetic_pcm_wav(raw_wav, channels=2)
        good_pcm = raw_wav.read_bytes()

        def inspect(encoded, label):
            page = self.root / ("decode-" + label + ".html")
            script = _FULL_DECODE_SCRIPT.replace("__PCM_BASE64__", encoded)
            page.write_text("<!doctype html><html lang='en'><script>" + script +
                            "</script></html>", encoding="utf-8")
            env = dict(os.environ)
            env["HOME"] = str(self.root)
            # On overloaded hosted Chromium a --dump-dom snapshot may arrive
            # before the async decoder has emitted a DOM marker. Retry only
            # an INDETERMINATE (missing marker) with a new isolated profile.
            # A real 'fail' never retries and never becomes PASS.
            for attempt in range(2):
                args = [
                    _BROWSER, "--headless=new", "--no-sandbox", "--disable-gpu",
                    "--disable-dev-shm-usage", "--disable-background-networking",
                    "--disable-extensions", "--no-first-run",
                    "--no-default-browser-check", "--disable-sync",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--virtual-time-budget=8000",
                    "--user-data-dir=" + str(
                        self.root / f"decode-profile-{label}-{attempt}"),
                    "--dump-dom", page.as_uri(),
                ]
                try:
                    done = subprocess.run(
                        args, capture_output=True, text=True, timeout=35, env=env)
                except subprocess.TimeoutExpired:
                    self.fail("bounded Chromium offline decode timed out")
                self.assertEqual(
                    done.returncode, 0, "Chromium decode process failed")
                match = re.search(
                    r'<html\b[^>]*data-mixlab-full-decode-check="([^"]+)"',
                    done.stdout, flags=re.IGNORECASE
                )
                if match is not None:
                    return match.group(1)
            self.fail("browser PCM decoder marker missing after bounded retries")

        self.assertEqual(inspect(base64.b64encode(good_pcm).decode("ascii"),
                                 "valid"), "pass")
        self.assertEqual(inspect(base64.b64encode(b"not-a-wav").decode("ascii"),
                                 "invalid"), "fail")


if __name__ == "__main__":
    unittest.main()
