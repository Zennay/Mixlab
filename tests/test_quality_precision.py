"""Synthetic, rights-safe validation for candidate PCM16 precision regression."""
from __future__ import annotations

from array import array
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import precision

from mixlab.quality.precision import compare_precision, _scan, MAX_BYTES


def wav(path: Path, *, channels=1, frames=12000, coarse=(), silence=False,
        seed=1, rate=48000, quiet_channels=(), coarse_step=256,
        coarse_offset=0, coarse_regions=(), coarse_region_offsets=None):
    state = seed
    samples = array("h")
    for frame in range(frames):
        for channel in range(channels):
            state = (1103515245 * state + 12345) & 0x7fffffff
            value = ((state >> 8) & 0xffff) - 32768
            if silence or channel in quiet_channels:
                value = 0
            elif channel in coarse and (not coarse_regions or
                    min(7, (frame * 8) // frames) in coarse_regions):
                region = min(7, (frame * 8) // frames)
                offset = (coarse_region_offsets or {}).get(region, coarse_offset)
                value = (value // coarse_step) * coarse_step + offset
            samples.append(value)
    # Fixtures are little-endian PCM16, independent of test host byte order.
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


class PrecisionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / "private BASE.wav"
        self.b = self.root / "private CAND.wav"

    def test_detects_monophonic_8bit_grid_loss(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        result = compare_precision(self.a, self.b)
        self.assertTrue(result["candidate_precision_loss_inspect"])
        self.assertEqual(result["warnings"], ["candidate_low_bit_precision_loss_inspect"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_detects_offset_8_bit_quantizer(self):
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_offset=7)
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_detects_11_and_12_bit_equivalent_quantization(self):
        wav(self.a)
        for step, offset in ((32, 3), (16, 5), (128, 9)):
            with self.subTest(step=step):
                wav(self.b, coarse=(0,), coarse_step=step, coarse_offset=offset)
                self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_baseline_equally_12_bit_coarse_is_not_a_precision_loss(self):
        wav(self.a, coarse=(0,), coarse_step=16, coarse_offset=3)
        wav(self.b, coarse=(0,), coarse_step=16, coarse_offset=5)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_eight_sample_step_is_below_conservative_detection_resolution(self):
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_step=8, coarse_offset=3)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_detects_offset_10_bit_quantizer(self):
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_step=64, coarse_offset=17)
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_baseline_coarse_with_different_offset_does_not_create_false_positive(self):
        wav(self.a, coarse=(0,), coarse_offset=5)
        wav(self.b, coarse=(0,), coarse_offset=7)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_two_separated_quantized_regions_are_detected(self):
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_offset=7, coarse_regions=(0, 6))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_one_quantized_region_does_not_establish_persistent_loss(self):
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_regions=(7,))
        self.assertIsNone(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_regional_offset_loss_is_chunk_independent(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(1,), coarse_offset=9,
            coarse_regions=(1, 5))
        self.assertEqual(compare_precision(self.a, self.b, chunk_frames=1),
                         compare_precision(self.a, self.b, chunk_frames=4096))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_distinct_quantizer_phases_in_different_regions(self):
        # Neither global residue histogram nor a fixed-zero-grid test can
        # explain this two-region confound: local phase differs by region.
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_regions=(0, 7),
            coarse_region_offsets={0: 7, 7: 23})
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_short_regions_without_enough_evidence_abstain(self):
        wav(self.a, frames=4000)
        wav(self.b, frames=4000)
        self.assertIsNone(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_baseline_modified_after_its_scan_is_rejected(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        original_scan = precision._scan
        calls = 0

        def intervening_edit(path, **kwargs):
            nonlocal calls
            receipt = original_scan(path, **kwargs)
            calls += 1
            if calls == 1:
                # Same PCM length and same inode, but different source bytes.
                wav(self.a, seed=42)
            return receipt

        with patch.object(precision, "_scan", side_effect=intervening_edit):
            with self.assertRaisesRegex(ValueError, "replaced or modified"):
                compare_precision(self.a, self.b)
        self.assertEqual(calls, 2)

    def test_baseline_replaced_after_its_scan_is_rejected(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        original_scan = precision._scan
        replaced = self.root / "replacement.wav"
        wav(replaced)

        def intervening_replace(path, **kwargs):
            receipt = original_scan(path, **kwargs)
            if Path(path) == self.a:
                # Identical bytes, different inode; still an invalid freeze.
                os.replace(replaced, self.a)
            return receipt

        with patch.object(precision, "_scan", side_effect=intervening_replace):
            with self.assertRaisesRegex(ValueError, "replaced or modified"):
                compare_precision(self.a, self.b)

    def test_candidate_modified_after_scan_is_rejected(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        original_scan = precision._scan

        def intervening_edit(path, **kwargs):
            receipt = original_scan(path, **kwargs)
            if Path(path) == self.b:
                wav(self.b, coarse=(0,), seed=45)
            return receipt

        with patch.object(precision, "_scan", side_effect=intervening_edit):
            with self.assertRaisesRegex(ValueError, "replaced or modified"):
                compare_precision(self.a, self.b)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink final path")
    def test_baseline_replaced_with_symlink_after_scan_is_rejected(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        original_scan = precision._scan
        old = self.root / "old-baseline.wav"

        def intervening_symlink(path, **kwargs):
            receipt = original_scan(path, **kwargs)
            if Path(path) == self.a:
                os.replace(self.a, old)
                self.a.symlink_to(old)
            return receipt

        with patch.object(precision, "_scan", side_effect=intervening_symlink):
            with self.assertRaisesRegex(ValueError, "replaced or modified"):
                compare_precision(self.a, self.b)

    def test_detection_never_mutates_private_inputs(self):
        import hashlib
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0,), coarse_offset=11)
        before = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                  for file in self.root.iterdir()}
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])
        after = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                 for file in self.root.iterdir()}
        self.assertEqual(before, after)

    def test_detects_loss_in_only_one_stereo_channel(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(1,))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_detects_loss_in_both_stereo_channels(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_no_false_positive_for_full_resolution_audio(self):
        wav(self.a, seed=1)
        wav(self.b, seed=2)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_no_false_positive_for_identical_input(self):
        wav(self.a)
        self.assertIs(compare_precision(self.a, self.a)["candidate_precision_loss_inspect"], False)

    def test_coarse_baseline_is_not_falsely_treated_as_high_resolution(self):
        wav(self.a, coarse=(0,))
        wav(self.b, coarse=(0,), seed=2)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_insufficient_silent_signal_abstains(self):
        wav(self.a)
        wav(self.b, silence=True)
        result = compare_precision(self.a, self.b)
        self.assertIsNone(result["candidate_precision_loss_inspect"])
        self.assertEqual(result["warnings"], [])

    def test_one_uninformative_stereo_channel_never_gives_false_clean(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, quiet_channels=(1,))
        self.assertIsNone(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_clear_precision_loss_is_not_hidden_by_uninformative_stereo_channel(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0,), quiet_channels=(1,))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_synthetic_full_length_stereo_admission_at_frame_cap(self):
        # Maximum frame count remains bounded and supported; fixtures are
        # generated without any third-party copyrighted source material.
        wav(self.a, channels=2, frames=2_000_000)
        wav(self.b, channels=2, frames=2_000_000, coarse=(1,))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_read_chunk_size_does_not_change_detection(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0,))
        self.assertEqual(compare_precision(self.a, self.b, chunk_frames=1),
                         compare_precision(self.a, self.b, chunk_frames=4096))
        with self.assertRaises(ValueError):
            _scan(self.a, chunk_frames=0)

    def test_mismatched_channels_and_sample_rate_are_rejected(self):
        wav(self.a)
        wav(self.b, channels=2)
        with self.assertRaises(ValueError):
            compare_precision(self.a, self.b)
        wav(self.b, rate=44100)
        with self.assertRaises(ValueError):
            compare_precision(self.a, self.b)

    def test_mismatched_frame_count_is_rejected(self):
        wav(self.a)
        wav(self.b, frames=8000)
        with self.assertRaises(ValueError):
            compare_precision(self.a, self.b)

    def test_truncated_pcm_is_rejected(self):
        wav(self.a)
        wav(self.b)
        with self.b.open("r+b") as f:
            f.truncate(1000)
        with self.assertRaises((ValueError, EOFError)):
            compare_precision(self.a, self.b)

    def test_oversize_rejected_before_scan(self):
        with self.a.open("wb") as f:
            f.truncate(MAX_BYTES + 1)
        with self.assertRaises(ValueError):
            _scan(self.a)

    @unittest.skipUnless(os.name == "posix", "POSIX no-follow/fifo guard")
    def test_symlink_and_fifo_are_rejected(self):
        wav(self.a)
        self.b.symlink_to(self.a)
        with self.assertRaises((OSError, ValueError)):
            _scan(self.b)
        self.b.unlink()
        os.mkfifo(self.b)
        with self.assertRaises((OSError, ValueError)):
            _scan(self.b)

    def test_cli_optional_warning_gate_preserves_anonymous_json(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        base = [sys.executable, "-m", "mixlab.quality.precision", str(self.a), str(self.b)]
        default = subprocess.run(base, text=True, capture_output=True, timeout=20)
        warning_gate = subprocess.run(
            base + ["--fail-on-warnings"], text=True, capture_output=True, timeout=20)
        conclusive_gate = subprocess.run(
            base + ["--require-conclusive"], text=True, capture_output=True, timeout=20)
        self.assertEqual([default.returncode, warning_gate.returncode,
                          conclusive_gate.returncode], [0, 2, 0])
        self.assertEqual(json.loads(default.stdout), json.loads(warning_gate.stdout))
        self.assertEqual(json.loads(default.stdout), json.loads(conclusive_gate.stdout))
        self.assertNotIn(str(self.root), warning_gate.stdout + warning_gate.stderr)

    def test_cli_inconclusive_gate_and_combined_strict_mode(self):
        wav(self.a)
        wav(self.b, silence=True)
        base = [sys.executable, "-m", "mixlab.quality.precision", str(self.a), str(self.b)]
        cases = [([], 0), (["--fail-on-warnings"], 0),
                 (["--require-conclusive"], 2),
                 (["--fail-on-warnings", "--require-conclusive"], 2)]
        for args, expected in cases:
            with self.subTest(args=args):
                proc = subprocess.run(base + args, text=True, capture_output=True, timeout=20)
                self.assertEqual(proc.returncode, expected, proc.stderr)
                data = json.loads(proc.stdout)
                self.assertIsNone(data["candidate_precision_loss_inspect"])
                self.assertNotIn(str(self.root), proc.stdout + proc.stderr)

        wav(self.b, seed=2)
        clean = subprocess.run(
            base + ["--fail-on-warnings", "--require-conclusive"],
            text=True, capture_output=True, timeout=20)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertIs(json.loads(clean.stdout)["candidate_precision_loss_inspect"], False)

    def test_cli_argument_errors_do_not_echo_sensitive_option_values(self):
        wav(self.a)
        wav(self.b)
        private = self.root / "private-token-SECRET.wav"
        base = [sys.executable, "-m", "mixlab.quality.precision",
                str(self.a), str(self.b)]
        malformed = [
            base + [f"--require-conclusive={private}"],
            base + [f"--fail-on-warnings={private}"],
            base + [f"--unrecognized={private}"],
            [sys.executable, "-m", "mixlab.quality.precision", str(private)],
        ]
        for cmd in malformed:
            with self.subTest(cmd=cmd[-1].split("=")[0]):
                proc = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
                self.assertEqual(proc.returncode, 3)
                self.assertNotIn(str(self.root), proc.stdout + proc.stderr)
                self.assertNotIn("SECRET", proc.stdout + proc.stderr)

    def test_cli_valid_json_and_no_private_path_leak_on_failure(self):
        wav(self.a)
        wav(self.b, coarse=(0,))
        cmd = [sys.executable, "-m", "mixlab.quality.precision",
               str(self.a), str(self.b)]
        good = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)["candidate_precision_loss_inspect"])
        missing = self.root / "private-secret-never-print.wav"
        for badcmd in ([*cmd[:-1], str(missing)], [*cmd, str(missing)]):
            bad = subprocess.run(badcmd, text=True, capture_output=True, timeout=20)
            self.assertEqual(bad.returncode, 3)
            self.assertNotIn(str(self.root), bad.stdout + bad.stderr)
            self.assertNotIn(missing.name, bad.stdout + bad.stderr)


if __name__ == "__main__":
    unittest.main()
