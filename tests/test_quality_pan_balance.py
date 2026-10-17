"""Rights-free deterministic tests for private stereo pan A/B screening."""
from __future__ import annotations

import json
import os
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

    def test_cli_parse_errors_never_echo_private_arguments(self):
        wav(self.a)
        wav(self.b)
        base = [sys.executable, "-m", "mixlab.quality.pan_balance"]
        invalid_argvs = [
            [],
            [str(self.a)],
            [str(self.a), str(self.b), "--unexpected=" + str(self.root / "SECRET.WAV")],
        ]
        for argv in invalid_argvs:
            with self.subTest(argv_length=len(argv)):
                result = subprocess.run(base + argv, text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(str(self.root), result.stdout + result.stderr)
                self.assertNotIn("SECRET", result.stdout + result.stderr)
                self.assertIn("rejected private arguments", result.stderr)

    def test_ancestor_directory_symlink_refused_before_pcm(self):
        real = self.root / "real_album"
        real.mkdir()
        baseline = real / "baseline.wav"
        candidate = real / "candidate.wav"
        wav(baseline)
        wav(candidate)
        alias = self.root / "untrusted_album"
        alias.symlink_to(real, target_is_directory=True)
        with mock.patch.object(pan_balance.struct, "iter_unpack",
                               side_effect=AssertionError("private PCM decoded")):
            with self.assertRaises((OSError, ValueError)):
                pan_balance.inspect(alias / "baseline.wav", candidate)

    def test_ancestor_symlink_then_dotdot_rejected_without_normalizing(self):
        real = self.root / "real_album"
        real.mkdir()
        nested = real / "nested"
        nested.mkdir()
        baseline = real / "baseline.wav"
        wav(baseline)
        wav(self.b)
        alias = self.root / "alias_nested"
        alias.symlink_to(nested, target_is_directory=True)
        # This path would reach a valid, nonsymlink final WAV on Linux.
        suspect = alias / ".." / "baseline.wav"
        with mock.patch.object(pan_balance.struct, "iter_unpack",
                               side_effect=AssertionError("private PCM decoded")):
            with self.assertRaises((OSError, ValueError)):
                pan_balance.inspect(suspect, self.b)

    def test_parent_directory_replaced_by_symlink_midscan_is_refused(self):
        album = self.root / "active_album"
        album.mkdir()
        original_a = album / "baseline.wav"
        original_b = album / "candidate.wav"
        wav(original_a)
        wav(original_b)
        moved = self.root / "moved_album"
        original_unchanged = pan_balance._unchanged
        swapped = False

        def swap_then_check(record):
            nonlocal swapped
            if not swapped:
                swapped = True
                album.rename(moved)
                album.symlink_to(moved, target_is_directory=True)
            return original_unchanged(record)

        with mock.patch.object(pan_balance, "_unchanged", side_effect=swap_then_check):
            with self.assertRaises((OSError, ValueError)):
                pan_balance.inspect(original_a, original_b)

    def test_path_bounds_fail_before_opening_any_directory(self):
        wav(self.b)
        overdeep = self.root.joinpath(*(["nested"] * 70), "baseline.wav")
        huge = self.root / ("p" * 4080) / "baseline.wav"
        for suspect in (overdeep, huge):
            with self.subTest(path_kind="deep" if suspect == overdeep else "long"):
                with mock.patch.object(pan_balance.os, "open",
                                       side_effect=AssertionError("opened before path limits")):
                    with self.assertRaises(ValueError):
                        pan_balance.inspect(suspect, self.b)

    def test_valid_non_symlink_lexical_dotdot_and_relative_input(self):
        album = self.root / "safe_album"
        album.mkdir()
        nested = album / "nested"
        nested.mkdir()
        source = album / "baseline.wav"
        wav(source)
        wav(self.b)
        # Valid parent traversal must still work, without resolving away
        # dangerous symlink components before validation.
        lexical = nested / ".." / "baseline.wav"
        relative = Path(os.path.relpath(lexical, Path.cwd()))
        result = pan_balance.inspect(relative, self.b)
        self.assertEqual(result["evidence_status"], "no_sustained_pan_bias_detected")
        self.assertFalse(result["stereo_pan_confound_review"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX named pipes")
    def test_fifo_refused_without_blocking_or_reading_private_pcm(self):
        wav(self.a)
        os.mkfifo(self.b)
        with mock.patch.object(pan_balance.struct, "iter_unpack",
                               side_effect=AssertionError("PCM decoded")):
            with self.assertRaises(ValueError):
                pan_balance.inspect(self.a, self.b)

    @unittest.skipUnless(Path("/proc/self/fd").is_dir(), "requires Linux procfs")
    def test_repeated_parent_symlink_rejection_leaks_no_fds(self):
        album = self.root / "source_album"
        album.mkdir()
        real = album / "original.wav"
        wav(real)
        wav(self.b)
        alias = self.root / "unsafe_alias"
        alias.symlink_to(album, target_is_directory=True)
        initial = len(os.listdir("/proc/self/fd"))
        for _ in range(32):
            with self.assertRaises((OSError, ValueError)):
                pan_balance.inspect(alias / "original.wav", self.b)
        self.assertEqual(len(os.listdir("/proc/self/fd")), initial)

    def test_strict_cli_review_exit_codes_do_not_claim_insufficient_audio_clean(self):
        wav(self.a)
        base = [sys.executable, "-m", "mixlab.quality.pan_balance",
                str(self.a), str(self.b)]
        # Safe identical pan, despite changed global gain.
        wav(self.b, left=2000, right=2000)
        clean = subprocess.run(base + ["--fail-on-review"],
                               capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(json.loads(clean.stdout)["evidence_status"],
                         "no_sustained_pan_bias_detected")
        # Measured sustained pan defect: nonzero only with the opt-in flag.
        wav(self.b, left=8000, right=2000)
        reviewed = subprocess.run(base + ["--fail-on-review"],
                                  capture_output=True, text=True)
        self.assertEqual(reviewed.returncode, 3)
        self.assertTrue(json.loads(reviewed.stdout)["stereo_pan_confound_review"])
        default = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(default.returncode, 0)
        # An insufficient sample must not silently become an acceptance.
        wav(self.a, frames=6000)
        wav(self.b, frames=6000)
        unknown = subprocess.run(base + ["--fail-on-review"],
                                 capture_output=True, text=True)
        self.assertEqual(unknown.returncode, 3)
        self.assertIsNone(json.loads(unknown.stdout)["stereo_pan_confound_review"])
        # Corrupt or missing private audio: code 2, never reveal source paths.
        self.b.unlink()
        invalid = subprocess.run(base + ["--fail-on-review"],
                                 capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        for receipt in (clean, reviewed, default, unknown, invalid):
            self.assertNotIn(str(self.root), receipt.stdout + receipt.stderr)

    def test_group_two_candidates_scanned_anonymously_against_one_baseline(self):
        wav(self.a)
        wav(self.b, left=8000, right=2000)
        other = self.root / "third private clip.wav"
        wav(other, left=2000, right=2000)
        result = pan_balance.inspect_batch(self.a, [self.b, other])
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["total_source_frames"], 3 * 8000)
        self.assertEqual([r["candidate_id"] for r in result["candidates"]],
                         ["candidate-01", "candidate-02"])
        self.assertTrue(result["candidates"][0]["metrics"]["stereo_pan_confound_review"])
        self.assertFalse(result["candidates"][1]["metrics"]["stereo_pan_confound_review"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(pan_balance.inspect_batch(self.a, [self.b])["candidate_count"], 1)

    def test_group_prevalidates_every_shape_before_reading_first_pcm_sample(self):
        wav(self.a)
        wav(self.b)
        other = self.root / "late malformed.wav"
        wav(other, rate=16000)
        with mock.patch.object(pan_balance.struct, "iter_unpack",
                               side_effect=AssertionError("Decoded before group preflight")):
            with self.assertRaises(ValueError):
                pan_balance.inspect_batch(self.a, [self.b, other])

    def test_group_rejects_duplicate_candidate_before_pcm(self):
        wav(self.a)
        wav(self.b)
        alias = self.root / "duplicated hardlink.wav"
        alias.hardlink_to(self.b)
        with mock.patch.object(pan_balance.struct, "iter_unpack",
                               side_effect=AssertionError("Decoded before group alias check")):
            with self.assertRaises(ValueError):
                pan_balance.inspect_batch(self.a, [self.b, alias])

    def test_group_candidate_count_and_total_frames_bound_before_decode(self):
        wav(self.a, frames=2_000_000)
        others = []
        for n in range(4):
            candidate = self.root / f"private group-{n}.wav"
            wav(candidate, frames=2_000_000)
            others.append(candidate)
        with mock.patch.object(pan_balance.struct, "iter_unpack",
                               side_effect=AssertionError("Decoded over-budget audio")):
            with self.assertRaises(ValueError):
                pan_balance.inspect_batch(self.a, others)
        with mock.patch.object(pan_balance, "_admit",
                               side_effect=AssertionError("Admitted too many candidates")):
            with self.assertRaises(ValueError):
                pan_balance.inspect_batch(self.a, ["private.wav"] * 8)

    def test_group_rechecks_first_candidate_after_later_render_scan(self):
        wav(self.a)
        wav(self.b)
        other = self.root / "last.wav"
        wav(other)
        orig = pan_balance._measure_open_pair
        counter = 0

        def mutate_previous_after_second(*args):
            nonlocal counter
            result = orig(*args)
            counter += 1
            if counter == 2:
                wav(self.b, left=5000)
            return result

        with mock.patch.object(pan_balance, "_measure_open_pair",
                               side_effect=mutate_previous_after_second):
            with self.assertRaises(ValueError):
                pan_balance.inspect_batch(self.a, [self.b, other])

    def test_group_cli_strict_mode_returns_three_for_any_review_or_abstention(self):
        wav(self.a)
        wav(self.b)
        third = self.root / "third.wav"
        wav(third)
        base = [sys.executable, "-m", "mixlab.quality.pan_balance",
                str(self.a), str(self.b), str(third), "--fail-on-review"]
        clean = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(json.loads(clean.stdout)["candidate_count"], 2)
        wav(third, left=8000, right=2000)
        warning = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(warning.returncode, 3)
        self.assertEqual(json.loads(warning.stdout)["candidates"][1]["candidate_id"],
                         "candidate-02")
        wav(third, frames=6000)
        bad = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        for output in (clean, warning, bad):
            self.assertNotIn(str(self.root), output.stdout + output.stderr)

    def test_exact_one_second_at_fractional_quarter_window_rates_is_decisive(self):
        # Four 250-ms windows need alternating frame widths (e.g. 11025 Hz
        # yields 2756, 2757, 2756, 2756). Flooring each width loses frames
        # and falsely abstains on exactly one second of audio.
        for rate in (8001, 11025, 16001, 22050, 44101):
            with self.subTest(rate=rate, case="clean"):
                wav(self.a, frames=rate, rate=rate)
                wav(self.b, frames=rate, rate=rate)
                report = pan_balance.inspect(self.a, self.b)
                self.assertEqual(report["evidence_status"], "no_sustained_pan_bias_detected")
                self.assertFalse(report["stereo_pan_confound_review"])
                self.assertEqual(report["longest_continuous_active_ms"], 1000)
            with self.subTest(rate=rate, case="persistent-pan"):
                wav(self.b, frames=rate, rate=rate, left=8000, right=2000)
                report = pan_balance.inspect(self.a, self.b)
                self.assertEqual(report["evidence_status"], "review_pan_balance")
                self.assertTrue(report["stereo_pan_confound_review"])
                self.assertEqual(report["longest_sustained_shift_ms"], 1000)
            with self.subTest(rate=rate, case="one-frame-short"):
                wav(self.a, frames=rate - 1, rate=rate)
                wav(self.b, frames=rate - 1, rate=rate, left=8000, right=2000)
                report = pan_balance.inspect(self.a, self.b)
                self.assertEqual(report["evidence_status"], "insufficient_active_audio")
                self.assertIsNone(report["stereo_pan_confound_review"])

    def test_fractional_sample_rate_group_matches_individual_results(self):
        rate = 11025
        wav(self.a, frames=rate, rate=rate)
        wav(self.b, frames=rate, rate=rate, left=8000, right=2000)
        third = self.root / "odd-rate third.wav"
        wav(third, frames=rate, rate=rate)
        report = pan_balance.inspect_batch(self.a, [self.b, third])
        self.assertTrue(report["candidates"][0]["metrics"]["stereo_pan_confound_review"])
        self.assertFalse(report["candidates"][1]["metrics"]["stereo_pan_confound_review"])
        self.assertEqual(report["candidates"][0]["metrics"], pan_balance.inspect(self.a, self.b))
        self.assertEqual(report["candidates"][1]["metrics"], pan_balance.inspect(self.a, third))

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
