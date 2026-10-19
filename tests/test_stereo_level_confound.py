"""Stereo per-channel level confounds despite matched whole-file RMS.

All WAVs are synthetic. Strong channel imbalances must not masquerade as a
well level-matched blind A/B, even if overall/window RMS is unchanged.
"""
from array import array
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs


def wav(path, frames, *, channels=2):
    samples = array("h", (s for frame in frames for s in frame))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(samples.tobytes())


class StereoChannelLevelConfoundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="PRIVATE_mixlab_channel-level-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "SECRET_base.wav"
        self.candidate = self.root / "SECRET_candidate.wav"
        self.tone = [int(5000 * math.sin(i * .19 + .15)) for i in range(8000)]
        wav(self.base, [(x, x) for x in self.tone])

    def report(self):
        outcome = compare_wavs(self.base, [self.candidate])
        raw = json.dumps(outcome)
        self.assertNotIn("SECRET_", raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("channel_envelope", raw)
        return outcome["candidates"][0]

    def test_equal_global_and_short_window_rms_can_mask_channel_loss(self):
        # Pythagorean scaling approximately preserves (L^2+R^2)/2.
        # Candidate right channel loses ~17 dB vs baseline.
        shifted = [(int(x * 1.4), int(x * .2)) for x in self.tone]
        wav(self.candidate, shifted)
        row = self.report()
        self.assertTrue(row["level_comparable_for_blind_ab"])
        self.assertFalse(row["short_window_level_mismatch_risk"])
        self.assertTrue(row["stereo_channel_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])
        self.assertIn("stereo_channel_level_mismatch_inspect_not_lufs", row["warnings"])
        self.assertTrue(row["requires_human_review"])

    def test_channel_loss_on_left_or_right_is_symmetric(self):
        for weak in (0, 1):
            with self.subTest(weak_channel=weak):
                frames = [(int(x * .2), int(x * 1.4)) if weak == 0
                          else (int(x * 1.4), int(x * .2))
                          for x in self.tone]
                wav(self.candidate, frames)
                self.assertTrue(self.report()["stereo_channel_level_confound_risk"])

    def test_moderate_per_channel_difference_is_not_reported(self):
        wav(self.candidate, [(int(x * 1.05), int(x * .95)) for x in self.tone])
        row = self.report()
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertTrue(row["rms_and_window_level_preflight_pass"])

    def test_silent_channel_vs_active_channel_fails(self):
        wav(self.candidate, [(int(x * 1.4), 0) for x in self.tone])
        row = self.report()
        self.assertTrue(row["stereo_channel_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_both_files_fully_silent_do_not_invent_channel_mismatch(self):
        silence = [(0, 0)] * len(self.tone)
        wav(self.base, silence)
        wav(self.candidate, silence)
        row = self.report()
        self.assertFalse(row["stereo_channel_level_confound_risk"])
        self.assertFalse(row["rms_and_window_level_preflight_pass"])

    def test_mono_does_not_claim_stereo_channel_mismatch(self):
        mono = [(x,) for x in self.tone]
        wav(self.base, mono, channels=1)
        wav(self.candidate, [(int(x * .9),) for x in self.tone], channels=1)
        row = self.report()
        self.assertFalse(row["stereo_channel_level_confound_risk"])


if __name__ == "__main__":
    unittest.main()
