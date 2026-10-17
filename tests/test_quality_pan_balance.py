"""Rights-free deterministic tests for private stereo pan A/B screening."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest import mock

from mixlab.quality import pan_balance


def wav(path, *, frames=8000, rate=8000, channels=2, left=4000, right=4000):
    sample = struct.pack("<hh", left, right) if channels == 2 else struct.pack("<h", left)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(sample * frames)


class PanBalanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / "private baseline source.wav"
        self.b = self.root / "private candidate source.wav"

    def test_persistent_stereo_pan_drift_flags_without_source_paths(self):
        wav(self.a)
        wav(self.b, left=8000, right=2000)
        result = pan_balance.inspect(self.a, self.b)
        self.assertTrue(result["stereo_pan_confound_review"])
        self.assertEqual(result["evidence_status"], "review_pan_balance")
        self.assertEqual(result["longest_sustained_shift_ms"], 1000)
        self.assertAlmostEqual(result["max_pan_balance_delta_db"], 12.041, places=2)
        self.assertEqual(result["active_windows"], 4)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_common_gain_does_not_create_pan_confound(self):
        wav(self.a, left=2000, right=2000)
        wav(self.b, left=6000, right=6000)
        result = pan_balance.inspect(self.a, self.b)
        self.assertFalse(result["stereo_pan_confound_review"])
        self.assertEqual(result["evidence_status"], "no_sustained_pan_bias_detected")
        self.assertEqual(result["max_pan_balance_delta_db"], 0)

    def test_balanced_channel_energy_not_a_loudness_or_music_score(self):
        wav(self.a, left=16000, right=4000)
        wav(self.b, left=8000, right=2000)
        self.assertFalse(pan_balance.inspect(self.a, self.b)["stereo_pan_confound_review"])

    def test_inactive_channel_abstains_from_claiming_pan(self):
        wav(self.a)
        wav(self.b, left=8000, right=10)
        result = pan_balance.inspect(self.a, self.b)
        self.assertIsNone(result["max_pan_balance_delta_db"])
        self.assertIsNone(result["stereo_pan_confound_review"])
        self.assertEqual(result["evidence_status"], "insufficient_active_audio")

    def test_subsecond_shift_cannot_pass_one_second_persistence_gate(self):
        wav(self.a, frames=6000)
        wav(self.b, frames=6000, left=8000, right=2000)
        result = pan_balance.inspect(self.a, self.b)
        self.assertIsNone(result["stereo_pan_confound_review"])
        self.assertEqual(result["evidence_status"], "insufficient_active_audio")
        self.assertEqual(result["longest_sustained_shift_ms"], 750)

    def test_partial_active_blocks_do_not_count_as_one_second_of_evidence(self):
        # 4 windows of valid stereo, but with one near-silent window between
        # active regions; no continuous audible second can be inferred.
        wav(self.a, frames=8000)
        with wave.open(str(self.b), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(struct.pack("<hh", 8000, 2000) * 4000)
            out.writeframes(struct.pack("<hh", 0, 0) * 2000)
            out.writeframes(struct.pack("<hh", 8000, 2000) * 2000)
        report = pan_balance.inspect(self.a, self.b)
        self.assertIsNone(report["stereo_pan_confound_review"])
        self.assertEqual(report["evidence_status"], "insufficient_active_audio")
        self.assertEqual(report["longest_continuous_active_ms"], 500)

    def test_rate_frame_and_stereo_mismatch_rejected_before_pcm_read(self):
        for key in ("rate", "frames", "channels"):
            with self.subTest(key=key):
                wav(self.a)
                kwargs = {"rate": 16000} if key == "rate" else (
                    {"frames": 16000} if key == "frames" else {"channels": 1})
                wav(self.b, **kwargs)
                with mock.patch.object(pan_balance.struct, "iter_unpack",
                                       side_effect=AssertionError("PCM decoded too early")):
                    with self.assertRaises(ValueError):
                        pan_balance.inspect(self.a, self.b)

    def test_self_and_hardlink_refused(self):
        wav(self.a)
        with self.assertRaises(ValueError):
            pan_balance.inspect(self.a, self.a)
        self.b.hardlink_to(self.a)
        with self.assertRaises(ValueError):
            pan_balance.inspect(self.a, self.b)

    def test_last_component_symlink_refused(self):
        wav(self.a)
        self.b.symlink_to(self.a)
        with self.assertRaises((OSError, ValueError)):
            pan_balance.inspect(self.a, self.b)

    def test_incomplete_pcm_and_invalid_riff_length_rejected(self):
        wav(self.a)
        wav(self.b)
        with self.b.open("r+b") as handle:
            handle.truncate(self.b.stat().st_size - 4)
        with self.assertRaises(ValueError):
            pan_balance.inspect(self.a, self.b)
        wav(self.b)
        with self.b.open("r+b") as handle:
            handle.seek(4)
            handle.write(struct.pack("<I", 0))
        with self.assertRaises(ValueError):
            pan_balance.inspect(self.a, self.b)

    def test_private_file_mutation_during_read_rejected(self):
        wav(self.a)
        wav(self.b)
        original = pan_balance._unchanged
        changed = False
        def mutate_once(record):
            nonlocal changed
            if not changed:
                changed = True
                wav(self.a, left=7000)
            original(record)
        with mock.patch.object(pan_balance, "_unchanged", side_effect=mutate_once):
            with self.assertRaises(ValueError):
                pan_balance.inspect(self.a, self.b)

    def test_cli_json_and_sanitized_error(self):
        wav(self.a)
        wav(self.b)
        cmd = [sys.executable, "-m", "mixlab.quality.pan_balance",
               str(self.a), str(self.b)]
        ok = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertFalse(json.loads(ok.stdout)["stereo_pan_confound_review"])
        self.b.unlink()
        bad = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn(str(self.root), bad.stdout + bad.stderr)
        self.assertNotIn(self.b.name, bad.stdout + bad.stderr)

    def test_upper_two_million_frame_stereo_source_budget(self):
        # Exactly 2M frames per source, 8 MiB stereo data per file; no sound upload.
        wav(self.a, frames=2_000_000, rate=48000)
        wav(self.b, frames=2_000_000, rate=48000, left=8000, right=2000)
        result = pan_balance.inspect(self.a, self.b)
        self.assertTrue(result["stereo_pan_confound_review"])
        self.assertEqual(result["format"]["frames"], 2_000_000)
        self.assertGreater(result["active_windows"], 100)


if __name__ == "__main__":
    unittest.main()
