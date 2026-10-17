"""Independent ML-07 relative stereo-to-mono regression tests.

Generate private synthetic PCM16 only; no copyrighted or external audio.
"""
import contextlib
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.relative_mono import assess, inspect


def _wave(path: Path, *, mode: str, frames: int = 12000, rate: int = 8000) -> None:
    # Equal-power stereo variants: normal correlated L/R, opposed L/-R,
    # silent and short clips. All are fresh 16-bit signed PCM.
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        buf = bytearray()
        for i in range(frames):
            v = round(8000 * math.sin(2 * math.pi * 200 * i / rate))
            if mode == "silent":
                left = right = 0
            elif mode == "opposed":
                left, right = v, -v
            elif mode == "late-opposed":
                left, right = (v, -v) if i >= frames // 2 else (v, v)
            else:
                left = right = v
            buf.extend(struct.pack("<hh", left, right))
        out.writeframes(buf)


class RelativeMonoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "base.wav"
        self.candidate = self.root / "candidate.wav"

    def test_clean_stereo_passes_without_musical_claim(self):
        _wave(self.base, mode="normal")
        # Different number of frames forbidden; use same duration.
        _wave(self.candidate, mode="normal")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "no_new_sustained_mono_cancellation_detected")
        self.assertFalse(result["milestone_pass"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("source_sha", json.dumps(result))

    def test_candidate_only_antiphase_detected(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "candidate_introduces_mono_cancellation")
        self.assertGreaterEqual(result["candidates"][0]["added_risky_window_fraction"], .25)

    def test_baseline_already_inverted_requires_review_not_false_clean(self):
        _wave(self.base, mode="opposed")
        _wave(self.candidate, mode="opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "baseline_already_has_mono_cancellation")

    def test_partial_antiphase_risk_detected(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="late-opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "candidate_introduces_mono_cancellation")

    def test_missing_evidence_abstains(self):
        for mode, frames in [("silent", 12000), ("normal", 4000)]:
            with self.subTest(mode=mode, frames=frames):
                _wave(self.base, mode=mode, frames=frames)
                _wave(self.candidate, mode=mode, frames=frames)
                result = inspect(str(self.base), [str(self.candidate)])
                self.assertEqual(result["candidates"][0]["status"], "insufficient_stereo_evidence")

    def test_mismatched_frames_do_not_get_positive_claim(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="opposed", frames=12001)
        with self.assertRaisesRegex(ValueError, "frames"):
            inspect(str(self.base), [str(self.candidate)])

    def test_rejects_candidate_batch_over_limit_before_source_read(self):
        with self.assertRaisesRegex(ValueError, "1..4"):
            inspect("unreadable", ["unreadable"] * 5)
        with self.assertRaisesRegex(ValueError, "1..4"):
            inspect("unreadable", [])

    def test_fake_report_status_cannot_claim_milestone(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="normal")
        from mixlab.quality import compare_wavs
        raw = compare_wavs(self.base, [self.candidate])
        checked = assess(raw)
        self.assertFalse(checked["milestone_pass"])
        self.assertTrue(checked["human_preference_test_required"])

    def test_cli_redacts_private_filename_and_uses_strict_exit(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="opposed")
        run = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.relative_mono",
             "--baseline", str(self.base), "--candidate", str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(run.returncode, 3, run.stderr)
        self.assertNotIn(str(self.root), run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["candidates"][0]["status"],
                         "candidate_introduces_mono_cancellation")
        bad = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.relative_mono",
             "--baseline", str(self.root / "private-token.wav"),
             "--candidate", str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(bad.returncode, 2, bad.stderr)
        self.assertNotIn(str(self.root), bad.stdout + bad.stderr)


if __name__ == "__main__":
    unittest.main()
