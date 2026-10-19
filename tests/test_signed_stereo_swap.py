"""ML-07 regression: signed stereo swaps must not masquerade as new blind audio.

All fixtures are synthetic PCM16. Neither blind answers nor track paths are
returned by the detector; intentional channel transforms require human review.
"""
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs, scan_wav


def write_audio(path, frames, *, channels=2, rate=8000):
    data = array("h", [sample for frame in frames for sample in frame])
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(data.tobytes())


def stereo_signal():
    # Distinct independent channels, across several 4096-frame read blocks.
    return [(int(4900 * math.sin(i * 0.13 + 0.3)),
             int(3600 * math.sin(i * 0.19 + 0.9)))
            for i in range(9000)]


def signed_swap(frames, kind):
    if kind == "negate_after_swap_left":
        return [(-r, l) for l, r in frames]
    if kind == "negate_after_swap_right":
        return [(r, -l) for l, r in frames]
    if kind == "negate_after_swap_both":
        return [(-r, -l) for l, r in frames]
    raise AssertionError(kind)


KINDS = ("negate_after_swap_left", "negate_after_swap_right",
         "negate_after_swap_both")


class SignedStereoSwapQualityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "secret-internal-artist-baseline.wav"
        self.variant = self.root / "secret-internal-artist-candidate.wav"
        self.frames = stereo_signal()
        write_audio(self.source, self.frames)

    def test_all_signed_stereo_swaps_detect_exact_prior_baseline(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                write_audio(self.variant, signed_swap(self.frames, kind))
                old_data = self.variant.read_bytes()
                report = compare_wavs(self.source, [self.variant])
                candidate = report["candidates"][0]
                self.assertEqual("baseline", candidate["signed_stereo_swap_pcm_of"])
                self.assertIn("signed_stereo_swap_pcm_inspect_for_reused_audio",
                              candidate["warnings"])
                self.assertIsNone(candidate["duplicate_pcm_of"])
                self.assertTrue(candidate["requires_human_review"])
                self.assertTrue(report["human_preference_test_required"])
                self.assertEqual(old_data, self.variant.read_bytes())
                self.assertNotIn(str(self.root), json.dumps(report))
                self.assertNotIn("secret-internal-artist", json.dumps(report))
                self.assertNotIn("sha256", json.dumps(report))

    def test_distinct_earlier_candidate_can_be_recognized_without_side_leak(self):
        previous = self.root / "secret-internal-artist-earlier.wav"
        independent = [(int(l * .8), int(r * .65)) for l, r in self.frames]
        write_audio(previous, independent)
        write_audio(self.variant, signed_swap(independent, KINDS[0]))
        rows = compare_wavs(self.source, [previous, self.variant])["candidates"]
        self.assertIsNone(rows[0]["signed_stereo_swap_pcm_of"])
        self.assertEqual("candidate-01", rows[1]["signed_stereo_swap_pcm_of"])
        self.assertNotIn(previous.name, json.dumps(rows))
        self.assertNotIn(self.variant.name, json.dumps(rows))

    def test_one_changed_pcm_sample_does_not_produce_false_exact_match(self):
        data = signed_swap(self.frames, KINDS[1])
        left, right = data[4200]
        data[4200] = (left + 1, right)
        write_audio(self.variant, data)
        row = compare_wavs(self.source, [self.variant])["candidates"][0]
        self.assertIsNone(row["signed_stereo_swap_pcm_of"])
        self.assertNotIn("signed_stereo_swap_pcm_inspect_for_reused_audio",
                         row["warnings"])

    def test_pcm16_minimum_guard_keeps_legal_transform(self):
        data = list(self.frames)
        data[4096] = (-32768, data[4096][1])
        write_audio(self.source, data)
        # The transform (-R,L) does not negate the minimum in source L.
        write_audio(self.variant, signed_swap(data, KINDS[0]))
        row = compare_wavs(self.source, [self.variant])["candidates"][0]
        self.assertEqual("baseline", row["signed_stereo_swap_pcm_of"])
        # -32768 in R cannot be negated; don't pretend -32768 -> +32767
        # is an exact sign transformation.
        data[4097] = (data[4097][0], -32768)
        write_audio(self.source, data)
        almost = []
        for left, right in data:
            almost.append((-right if right > -32768 else 32767, left))
        write_audio(self.variant, almost)
        row = compare_wavs(self.source, [self.variant])["candidates"][0]
        self.assertIsNone(row["signed_stereo_swap_pcm_of"])

    def test_exact_pcm_duplicate_and_mono_remain_separate(self):
        write_audio(self.variant, self.frames)
        row = compare_wavs(self.source, [self.variant])["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertIsNone(row["signed_stereo_swap_pcm_of"])
        mono = self.root / "secret-internal-artist-mono.wav"
        write_audio(mono, [(l,) for l, _ in self.frames], channels=1)
        self.assertEqual(1, scan_wav(mono)["channels"])
        mono_row = compare_wavs(mono, [mono])["candidates"][0]
        self.assertIsNone(mono_row["signed_stereo_swap_pcm_of"])
        self.assertEqual("baseline", mono_row["duplicate_pcm_of"])

    def test_strict_cli_warning_is_pathless_and_preserves_pcm_bytes(self):
        write_audio(self.variant, signed_swap(self.frames, KINDS[2]))
        before = self.variant.read_bytes()
        command = [sys.executable, "-m", "mixlab.quality",
                   str(self.source), str(self.variant), "--fail-on-warnings"]
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=30, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(2, completed.returncode)
        self.assertFalse(completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("baseline", report["candidates"][0]["signed_stereo_swap_pcm_of"])
        self.assertNotIn("secret-internal-artist", completed.stdout)
        self.assertNotIn(str(self.root), completed.stdout)
        self.assertEqual(before, self.variant.read_bytes())


if __name__ == "__main__":
    unittest.main()
