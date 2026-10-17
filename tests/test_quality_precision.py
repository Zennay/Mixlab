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
        coarse_offset=0, coarse_regions=(), coarse_region_offsets=None,
        channel_coarse_regions=None, coarse_jitter=0):
    state = seed
    samples = array("h")
    for frame in range(frames):
        for channel in range(channels):
            state = (1103515245 * state + 12345) & 0x7fffffff
            value = ((state >> 8) & 0xffff) - 32768
            if silence or channel in quiet_channels:
                value = 0
            elif channel in coarse and (
                    not (channel_coarse_regions or {}).get(channel, coarse_regions)
                    or min(7, (frame * 8) // frames) in
                    (channel_coarse_regions or {}).get(channel, coarse_regions)):
                region = min(7, (frame * 8) // frames)
                offset = (coarse_region_offsets or {}).get(region, coarse_offset)
                value = ((value // coarse_step) * coarse_step + offset
                         + (coarse_jitter if frame % 2 else 0))
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

    def test_detects_one_lsb_adjacent_phase_jitter(self):
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_step=32,
            coarse_offset=3, coarse_jitter=1)
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_adjacent_jitter_in_only_one_stereo_channel(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(1,), coarse_step=16,
            coarse_offset=3, coarse_jitter=1)
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_half_step_two_residues_do_not_exceed_detection_resolution(self):
        # Alternating 3/11 modulo 16 is *actually* an 8-sample grid;
        # adjacency must be restricted or the detector mislabels it.
        wav(self.a)
        wav(self.b, coarse=(0,), coarse_step=16,
            coarse_offset=3, coarse_jitter=8)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_baseline_also_has_adjacent_phase_grid_is_not_a_regression(self):
        wav(self.a, coarse=(0,), coarse_step=32,
            coarse_offset=3, coarse_jitter=1)
        wav(self.b, coarse=(0,), coarse_step=32,
            coarse_offset=5, coarse_jitter=1)
        self.assertIs(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"], False)

    def test_adjacent_phase_jitter_in_separate_stereo_regions(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1), coarse_step=32,
            coarse_offset=5, coarse_jitter=1,
            channel_coarse_regions={0: (0,), 1: (6,)})
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

    def test_one_adjacent_phase_window_in_both_channels_is_not_persistent(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1), coarse_step=32,
            coarse_offset=3, coarse_jitter=1, coarse_regions=(4,))
        outcome = compare_precision(self.a, self.b)
        self.assertIsNone(outcome["candidate_precision_loss_inspect"])
        self.assertEqual(outcome["warnings"], [])

    def test_adjacent_phase_detection_is_chunk_independent(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0,), coarse_step=32,
            coarse_offset=7, coarse_jitter=1)
        self.assertEqual(compare_precision(self.a, self.b, chunk_frames=1),
                         compare_precision(self.a, self.b, chunk_frames=4096))
        self.assertTrue(compare_precision(self.a, self.b)["candidate_precision_loss_inspect"])

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

    def test_migrating_stereo_loss_in_two_distinct_regions_is_flagged(self):
        # Before this fix each channel has only one affected region, so
        # evaluating per-channel persistence produced an inconclusive null.
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1),
            channel_coarse_regions={0: (0,), 1: (7,)},
            coarse_offset=7)
        result = compare_precision(self.a, self.b)
        self.assertIs(result["candidate_precision_loss_inspect"], True)
        self.assertEqual(result["warnings"], ["candidate_low_bit_precision_loss_inspect"])

    def test_one_region_in_both_channels_does_not_count_twice(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1), coarse_regions=(3,))
        result = compare_precision(self.a, self.b)
        self.assertIsNone(result["candidate_precision_loss_inspect"])
        self.assertEqual(result["warnings"], [])

    def test_migrating_stereo_loss_unchanged_by_streaming_chunk_size(self):
        wav(self.a, channels=2)
        wav(self.b, channels=2, coarse=(0, 1),
            channel_coarse_regions={0: (1,), 1: (6,)},
            coarse_offset=13)
        small = compare_precision(self.a, self.b, chunk_frames=1)
        large = compare_precision(self.a, self.b, chunk_frames=4096)
        self.assertEqual(small, large)
        self.assertIs(small["candidate_precision_loss_inspect"], True)

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


class BatchPrecisionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "PRIVATE-baseline.wav"
        self.c1 = self.root / "PRIVATE-one.wav"
        self.c2 = self.root / "PRIVATE-two.wav"
        self.c3 = self.root / "PRIVATE-three.wav"
        wav(self.base)
        wav(self.c1, seed=2)
        wav(self.c2, coarse=(0,), coarse_offset=3)
        wav(self.c3, silence=True)

    def test_three_candidates_preserve_anonymous_order_and_tri_state(self):
        result = precision.compare_precision_batch(
            self.base, [self.c1, self.c2, self.c3])
        self.assertEqual(result["status"], "technical-inspection-only")
        self.assertEqual([r["candidate_id"] for r in result["candidates"]],
                         ["candidate-001", "candidate-002", "candidate-003"])
        self.assertEqual([r["candidate_precision_loss_inspect"]
                          for r in result["candidates"]], [False, True, None])
        self.assertEqual([r["warnings"] for r in result["candidates"]],
                         [[], ["candidate_low_bit_precision_loss_inspect"], []])
        payload = json.dumps(result)
        self.assertNotIn(str(self.root), payload)
        self.assertNotIn("PRIVATE", payload)
        self.assertNotIn("_source_identity", payload)

    def test_batch_catches_migrating_stereo_defect_with_neutral_output(self):
        wav(self.base, channels=2)
        wav(self.c1, channels=2, seed=2)
        wav(self.c2, channels=2, coarse=(0, 1),
            channel_coarse_regions={0: (0,), 1: (6,)})
        result = precision.compare_precision_batch(self.base, [self.c1, self.c2])
        self.assertEqual(
            [entry["candidate_precision_loss_inspect"] for entry in result["candidates"]],
            [False, True])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_batch_strict_warns_on_cross_stereo_jitter_without_leaking_paths(self):
        wav(self.base, channels=2)
        wav(self.c1, channels=2, seed=4)
        wav(self.c2, channels=2, coarse=(0, 1), coarse_step=32,
            coarse_offset=5, coarse_jitter=1,
            channel_coarse_regions={0: (1,), 1: (5,)})
        rows = precision.compare_precision_batch(self.base, [self.c1, self.c2])
        self.assertEqual(
            [r["candidate_precision_loss_inspect"] for r in rows["candidates"]],
            [False, True])
        cmd = [sys.executable, "-m", "mixlab.quality.precision",
               str(self.base), str(self.c1), str(self.c2), "--batch",
               "--fail-on-warnings", "--require-conclusive"]
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout), rows)

    def test_single_candidate_batch_matches_single_pair_verdict(self):
        one = precision.compare_precision(self.base, self.c2)
        batch = precision.compare_precision_batch(self.base, (self.c2,))
        self.assertEqual(batch["candidates"][0]["candidate_precision_loss_inspect"],
                         one["candidate_precision_loss_inspect"])
        self.assertEqual(batch["candidates"][0]["warnings"], one["warnings"])

    def test_baseline_is_scanned_exactly_once_for_multiple_candidates(self):
        original = precision._scan
        inputs = []
        def counted(path, **kwargs):
            inputs.append(Path(path))
            return original(path, **kwargs)
        with patch.object(precision, "_scan", side_effect=counted):
            precision.compare_precision_batch(self.base, [self.c1, self.c2, self.c3])
        self.assertEqual(inputs, [self.base, self.c1, self.c2, self.c3])

    def test_all_eight_candidates_fit_when_aggregate_frames_fit(self):
        paths = [self.c1, self.c2, self.c3]
        for index in range(4, 9):
            path = self.root / f"PRIVATE-extra-{index}.wav"
            wav(path, seed=index + 3)
            paths.append(path)
        result = precision.compare_precision_batch(self.base, paths)
        self.assertEqual(len(result["candidates"]), 8)
        self.assertEqual(result["candidates"][-1]["candidate_id"], "candidate-008")

    def test_wrong_candidate_collection_and_count_fail_before_scan(self):
        with patch.object(precision, "_scan", side_effect=AssertionError("scan entered")):
            for candidates in ([], [self.c1] * 9, str(self.c1), None, iter([self.c1])):
                with self.subTest(kind=str(type(candidates))):
                    with self.assertRaises(ValueError):
                        precision.compare_precision_batch(self.base, candidates)

    def test_exact_eight_million_frame_stereo_budget_real_pcm(self):
        # Actual (non-sparse) boundary workload: 4 sources x 2M stereo
        # frames. Tests both admission equality and bounded streaming.
        wav(self.base, channels=2, frames=2_000_000)
        wav(self.c1, channels=2, frames=2_000_000, seed=2)
        wav(self.c2, channels=2, frames=2_000_000, coarse=(1,))
        wav(self.c3, channels=2, frames=2_000_000, seed=4)
        result = precision.compare_precision_batch(
            self.base, [self.c1, self.c2, self.c3])
        self.assertEqual([x["candidate_precision_loss_inspect"]
                          for x in result["candidates"]], [False, True, False])

    def test_aggregate_frame_budget_rejects_from_metadata_before_audio_scan(self):
        import struct
        # Tiny header lies about its PCM payload. The 5*2M-frame request
        # must fail at aggregate admission BEFORE opening any scan buffers.
        sources = [self.root / f"huge-{i}.wav" for i in range(5)]
        for source in sources:
            nbytes = 2_000_000 * 2 * 2
            source.write_bytes(
                b"RIFF" + struct.pack("<I", 36 + nbytes) + b"WAVE"
                + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, 48000,
                                         48000 * 4, 4, 16)
                + b"data" + struct.pack("<I", nbytes))
        with patch.object(precision, "_scan", side_effect=AssertionError("scan entered")):
            with self.assertRaisesRegex(ValueError, "aggregate PCM frame"):
                precision.compare_precision_batch(sources[0], sources[1:])

    def test_aggregate_byte_budget_rejects_large_non_audio_riff_padding(self):
        # Sparse-size WAVs with tiny declared PCM can still carry huge
        # metadata/data padding: refuse the entire set before any PCM scan.
        files = [self.base, self.c1, self.c2, self.c3]
        fifth = self.root / "PRIVATE-extra-padded.wav"
        wav(fifth, seed=5)
        files.append(fifth)
        for source in files:
            with source.open("r+b") as out:
                out.truncate(32 * 1024 * 1024)
        with patch.object(precision, "_scan", side_effect=AssertionError("scan entered")):
            with self.assertRaisesRegex(ValueError, "aggregate WAV byte budget"):
                precision.compare_precision_batch(files[0], files[1:])

    def test_rejects_hardlink_and_repeated_baseline_without_scanning(self):
        alias = self.root / "hardlink.wav"
        os.link(self.c1, alias)
        with patch.object(precision, "_scan", side_effect=AssertionError("scan entered")):
            for group in ([self.c1, alias], [self.base], [self.c1, self.c1]):
                with self.subTest(group=len(group)):
                    with self.assertRaisesRegex(ValueError, "duplicate A/B"):
                        precision.compare_precision_batch(self.base, group)

    def test_mismatch_rejected_before_expensive_scan(self):
        wav(self.c1, rate=44100)
        with patch.object(precision, "_scan", side_effect=AssertionError("scan entered")):
            with self.assertRaisesRegex(ValueError, "incomparable"):
                precision.compare_precision_batch(self.base, [self.c1])

    def test_source_replaced_between_batch_admission_and_scan_is_rejected(self):
        original = precision._preadmit_wav
        touched = False
        incoming = self.root / "different-inode.wav"
        wav(incoming, seed=2)

        def replace_after_admission(path):
            nonlocal touched
            receipt = original(path)
            if Path(path) == self.c3 and not touched:
                # Simulate a concurrent writer swapping a previously admitted
                # candidate before the PCM scan begins. Identical frame format.
                os.replace(incoming, self.c1)
                touched = True
            return receipt

        with patch.object(precision, "_preadmit_wav", side_effect=replace_after_admission):
            with self.assertRaisesRegex(ValueError, "after admission"):
                precision.compare_precision_batch(self.base, [self.c1, self.c2, self.c3])
        self.assertTrue(touched)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink metadata admission")
    def test_batch_symlink_fails_without_scanning_or_partial_output(self):
        link = self.root / "PRIVATE-symlink.wav"
        link.symlink_to(self.c2)
        with patch.object(precision, "_scan", side_effect=AssertionError("scan entered")):
            with self.assertRaises((OSError, ValueError)):
                precision.compare_precision_batch(self.base, [self.c1, link])

    def test_baseline_edit_during_later_candidate_invalidates_entire_batch(self):
        original = precision._scan
        def replace_midway(path, **kwargs):
            data = original(path, **kwargs)
            if Path(path) == self.c2:
                wav(self.base, seed=88)
            return data
        with patch.object(precision, "_scan", side_effect=replace_midway):
            with self.assertRaisesRegex(ValueError, "replaced or modified"):
                precision.compare_precision_batch(self.base, [self.c1, self.c2, self.c3])

    def test_candidate_changed_after_prior_scan_rejects_without_partial_result(self):
        original = precision._scan
        def edit_midway(path, **kwargs):
            data = original(path, **kwargs)
            if Path(path) == self.c3:
                wav(self.c1, seed=77)
            return data
        with patch.object(precision, "_scan", side_effect=edit_midway):
            with self.assertRaisesRegex(ValueError, "replaced or modified"):
                precision.compare_precision_batch(self.base, [self.c1, self.c2, self.c3])

    def test_chunk_variation_is_deterministic_for_batch(self):
        paths = [self.c1, self.c2, self.c3]
        a = precision.compare_precision_batch(self.base, paths, chunk_frames=1)
        b = precision.compare_precision_batch(self.base, paths, chunk_frames=4096)
        self.assertEqual(a, b)

    def test_batch_cli_gate_and_neutral_json(self):
        base = [sys.executable, "-m", "mixlab.quality.precision",
                str(self.base), str(self.c1), str(self.c2), str(self.c3), "--batch"]
        for suffix, expected in (([], 0), (["--fail-on-warnings"], 2),
                                 (["--require-conclusive"], 2),
                                 (["--fail-on-warnings", "--require-conclusive"], 2)):
            with self.subTest(flags=suffix):
                proc = subprocess.run(base + suffix, text=True, capture_output=True, timeout=20)
                self.assertEqual(proc.returncode, expected, proc.stderr)
                self.assertEqual(len(json.loads(proc.stdout)["candidates"]), 3)
                self.assertNotIn(str(self.root), proc.stdout + proc.stderr)

    def test_extra_candidates_without_batch_flag_fail_closed(self):
        cmd = [sys.executable, "-m", "mixlab.quality.precision",
               str(self.base), str(self.c1), str(self.c2)]
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
        self.assertEqual(proc.returncode, 3)
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)

    def test_malformed_fmt_chunk_errors_are_redacted_for_single_and_batch(self):
        import struct
        bad = self.root / "PRIVATE-secret-malformed-fmt.wav"
        # RIFF is recognizable, but fmt declares only 2 bytes where PCM
        # requires 16; CPython's wave parser may raise struct.error.
        fmt = b"fmt " + struct.pack("<I", 2) + b"\x01\x00"
        data = b"data" + struct.pack("<I", 2) + b"\x00\x00"
        bad.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(fmt) + len(data))
                        + b"WAVE" + fmt + data)
        commands = [
            [sys.executable, "-m", "mixlab.quality.precision",
             str(self.base), str(bad)],
            [sys.executable, "-m", "mixlab.quality.precision",
             str(self.base), str(self.c1), str(bad), "--batch"],
        ]
        for cmd in commands:
            with self.subTest(batch="--batch" in cmd):
                proc = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
                self.assertEqual(proc.returncode, 3)
                self.assertEqual(proc.stdout, "")
                self.assertNotIn("PRIVATE", proc.stderr)
                self.assertNotIn(str(self.root), proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

    def test_batch_invalid_file_does_not_publish_partial_results(self):
        missing = self.root / "PRIVATE-secret-not-found.wav"
        cmd = [sys.executable, "-m", "mixlab.quality.precision",
               str(self.base), str(self.c1), str(missing), "--batch"]
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(proc.stdout, "")
        self.assertNotIn("PRIVATE", proc.stderr)


if __name__ == "__main__":
    unittest.main()
