"""Independent ML-07 relative stereo-to-mono regression tests.

Generate private synthetic PCM16 only; no copyrighted or external audio.
"""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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
            elif mode == "even":
                left = right = v if i % 2 == 0 else 0
            elif mode == "odd-opposed":
                left, right = (v, -v) if i % 2 else (0, 0)
            elif mode == "sparse-opposed":
                left, right = (v, -v) if i % 5 == 0 else (0, 0)
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

    def test_disjoint_sample_activity_must_abstain_not_claim_phase_harm(self):
        # Both files have non-silent *100ms* windows and adequate whole-file
        # RMS; no individual frame is jointly audible. Fraction-only checks
        # incorrectly claim candidate-specific mono damage here.
        _wave(self.base, mode="even")
        _wave(self.candidate, mode="odd-opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(
            result["candidates"][0]["status"], "insufficient_stereo_evidence"
        )

    def test_sparse_candidate_common_time_abstains(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="sparse-opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(
            result["candidates"][0]["status"], "insufficient_stereo_evidence"
        )

    def test_mixed_batch_never_promotes_disjoint_candidate(self):
        _wave(self.base, mode="normal")
        clean = self.root / "clean.wav"
        sparse = self.root / "sparse.wav"
        antiphase = self.root / "antiphase.wav"
        _wave(clean, mode="normal")
        _wave(sparse, mode="sparse-opposed")
        _wave(antiphase, mode="opposed")
        result = inspect(str(self.base), [str(clean), str(sparse), str(antiphase)])
        self.assertEqual([row["status"] for row in result["candidates"]], [
            "no_new_sustained_mono_cancellation_detected",
            "insufficient_stereo_evidence",
            "candidate_introduces_mono_cancellation",
        ])
        self.assertEqual([row["candidate_id"] for row in result["candidates"]],
                         ["candidate-01", "candidate-02", "candidate-03"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertFalse(result["milestone_pass"])

    def test_fractional_sample_rate_and_96khz_synchronous_windows(self):
        for sample_rate in (11025, 96000):
            with self.subTest(sample_rate=sample_rate):
                count = sample_rate * 12 // 10
                _wave(self.base, mode="normal", frames=count, rate=sample_rate)
                _wave(self.candidate, mode="opposed", frames=count, rate=sample_rate)
                report = inspect(str(self.base), [str(self.candidate)])
                self.assertEqual(report["candidates"][0]["status"],
                                 "candidate_introduces_mono_cancellation")

    def test_file_mutation_between_streaming_passes_is_rejected(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="normal")
        from mixlab.quality import relative_mono
        actual = relative_mono._paired_phase_fractions

        def changed_after_canonical_scan(base, candidate):
            with open(self.candidate, "r+b") as out:
                out.seek(44)
                out.write(b"\x01\x00\x02\x00")
                out.flush()
                os.fsync(out.fileno())
            return actual(base, candidate)

        with patch("mixlab.quality.relative_mono._paired_phase_fractions",
                   side_effect=changed_after_canonical_scan):
            with self.assertRaisesRegex(ValueError, "changed"):
                inspect(str(self.base), [str(self.candidate)])

    def test_excessive_declared_frame_count_rejected_before_paired_read(self):
        with wave.open(str(self.base), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(b"\x00\x00\x00\x00" * 2_000_001)
        _wave(self.candidate, mode="normal")
        with self.assertRaises(ValueError):
            inspect(str(self.base), [str(self.candidate)])

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

    def test_malformed_wav_decoder_error_is_redacted(self):
        _wave(self.candidate, mode="normal")
        self.base.write_bytes(b"not-a-wave" + str(self.root).encode())
        run = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.relative_mono",
             "--baseline", str(self.base), "--candidate", str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stderr, "")
        self.assertNotIn(str(self.root), run.stdout)
        self.assertEqual(json.loads(run.stdout)["status"], "invalid_private_pcm")

    def test_pcm8_is_not_misreported_as_safe(self):
        with wave.open(str(self.base), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(1)
            out.setframerate(8000)
            out.writeframes(bytes([128, 128]) * 12000)
        _wave(self.candidate, mode="normal")
        run = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.relative_mono",
             "--baseline", str(self.base), "--candidate", str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(run.returncode, 2)
        self.assertNotIn(str(self.root), run.stdout + run.stderr)


    def test_leaf_and_ancestor_symlink_paths_are_rejected(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="normal")
        leaf_link = self.root / "link.wav"
        leaf_link.symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "regular"):
            inspect(str(leaf_link), [str(self.candidate)])
        linked_parent = self.root / "linked-dir"
        linked_parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory"):
            inspect(str(linked_parent / "base.wav"), [str(self.candidate)])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO admission test")
    def test_fifo_rejected_without_opening_or_hanging(self):
        _wave(self.base, mode="normal")
        fifo = self.root / "pretend-audio.wav"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "regular"):
            inspect(str(self.base), [str(fifo)])

    def test_out_of_budget_file_rejected_before_decoding(self):
        _wave(self.base, mode="normal")
        large = self.root / "too-large.wav"
        with open(large, "wb") as stream:
            stream.truncate(32 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "bounded regular"):
            inspect(str(self.base), [str(large)])


if __name__ == "__main__":
    unittest.main()
