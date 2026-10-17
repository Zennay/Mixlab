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
            tone_hz = 221 if mode in ("alternate", "alternate-opposed") else 200
            v = round(8000 * math.sin(2 * math.pi * tone_hz * i / rate))
            w = round(7000 * math.sin(2 * math.pi * 260 * i / rate))
            if mode == "silent":
                left = right = 0
            elif mode in ("opposed", "alternate-opposed"):
                left, right = v, -v
            elif mode == "polarity":
                left = right = -v
            elif mode == "stereo":
                left, right = v, w
            elif mode == "stereo-swapped":
                left, right = w, v
            elif mode == "loud-normal":
                left = right = v * 2
            elif mode == "window-level-shift":
                # 400ms 12dB attenuation, compensated later to match
                # whole-clip RMS. Canonical short-window QA must HOLD.
                scale = 0.25 if i < 3200 else math.sqrt(11800 / 8800)
                left = right = round(v * scale)
            elif mode == "onset-100ms-late":
                # Timing confound under canonical 75ms prominent-onset limit.
                left = right = (0 if i < rate // 10 else v)
            elif mode == "tail-210ms-quiet":
                # Canonical >=200ms A/B trailing-silence confound.
                left = right = (0 if i >= frames - round(rate * .21) else v)
            elif mode == "interior-60ms-silence":
                left = right = (0 if frames // 2 <= i < frames // 2 + rate * 60 // 1000 else v)
            elif mode == "interior-60ms-right-dropout":
                left = v
                right = (0 if frames // 2 <= i < frames // 2 + rate * 60 // 1000 else v)
            elif mode == "single-impulse":
                # Detectable >=8192-LSB isolated impulse, but <16384 jump
                # from the adjacent sine frames to isolate this one gate.
                left = right = 14000 if i == 4000 else v
            elif mode == "flat-top":
                left = right = 25000 if 4000 <= i < 4007 else v
            elif mode == "large-jump":
                left = right = 28000 if i == 4000 else v
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
        # Independently rendered, equal-level clean stereo signal.
        _wave(self.candidate, mode="alternate")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "no_new_sustained_mono_cancellation_detected")
        self.assertFalse(result["milestone_pass"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("source_sha", json.dumps(result))

    def test_exact_duplicate_pcm_is_not_an_independent_blind_ab(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="normal")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "non_independent_ab_audio")
        self.assertFalse(result["milestone_pass"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_duplicate_candidate_rejected_without_downgrading_first_independent(self):
        _wave(self.base, mode="normal")
        independent = self.root / "independent.wav"
        copied = self.root / "same-as-independent.wav"
        _wave(independent, mode="alternate")
        _wave(copied, mode="alternate")
        result = inspect(str(self.base), [str(independent), str(copied)])
        self.assertEqual([row["status"] for row in result["candidates"]], [
            "no_new_sustained_mono_cancellation_detected",
            "non_independent_ab_audio",
        ])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_different_wav_container_cannot_hide_identical_pcm(self):
        _wave(self.base, mode="normal")
        plain = self.base.read_bytes()
        # A private JUNK chunk changes the WAV bytes but not decoded PCM16.
        # The public listening-pack gate separately rejects such metadata.
        payload = b"PRIVATE-INFO"  # no original media; synthetic only
        if len(payload) % 2:
            payload += b"!"
        junk = b"JUNK" + struct.pack("<I", len(payload)) + payload
        altered = (plain[:4] + struct.pack("<I", len(plain) - 8 + len(junk))
                   + plain[8:36] + junk + plain[36:])
        self.candidate.write_bytes(altered)
        self.assertNotEqual(self.base.read_bytes(), self.candidate.read_bytes())
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "non_independent_ab_audio")
        self.assertNotIn("PRIVATE-INFO", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_same_inode_hardlink_cannot_count_as_new_ab_audio(self):
        _wave(self.base, mode="normal")
        os.link(self.base, self.candidate)
        report = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(report["candidates"][0]["status"], "non_independent_ab_audio")
        self.assertNotIn(str(self.base), json.dumps(report))

    def test_noop_candidate_cli_returns_hold_without_filename(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="normal")
        proc = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.relative_mono",
             "--baseline", str(self.base), "--candidate", str(self.candidate)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(proc.stderr, "")
        self.assertNotIn(str(self.root), proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["candidates"][0]["status"],
                         "non_independent_ab_audio")

    def test_channel_swap_is_not_independent_transition(self):
        _wave(self.base, mode="stereo")
        _wave(self.candidate, mode="stereo-swapped")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "non_independent_ab_audio")
        self.assertFalse(result["milestone_pass"])

    def test_swapped_second_candidate_is_held_without_rejecting_first(self):
        _wave(self.base, mode="alternate")
        first = self.root / "first-new-stereo.wav"
        second = self.root / "swapped-first-stereo.wav"
        _wave(first, mode="stereo")
        _wave(second, mode="stereo-swapped")
        report = inspect(str(self.base), [str(first), str(second)])
        self.assertEqual(
            [row["status"] for row in report["candidates"]],
            ["no_new_sustained_mono_cancellation_detected", "non_independent_ab_audio"],
        )
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_inverted_second_candidate_is_held_without_rejecting_first(self):
        _wave(self.base, mode="alternate")
        first = self.root / "first-new.wav"
        second = self.root / "inverted-first.wav"
        _wave(first, mode="normal")
        _wave(second, mode="polarity")
        report = inspect(str(self.base), [str(first), str(second)])
        self.assertEqual(
            [row["status"] for row in report["candidates"]],
            ["no_new_sustained_mono_cancellation_detected", "non_independent_ab_audio"],
        )
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_polarity_inverted_audio_is_not_independent_transition(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="polarity")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "non_independent_ab_audio")
        self.assertFalse(result["milestone_pass"])

    def test_candidate_only_antiphase_detected(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "candidate_introduces_mono_cancellation")
        self.assertGreaterEqual(result["candidates"][0]["added_risky_window_fraction"], .25)

    def test_level_mismatch_must_not_issue_clean_relative_ab_verdict(self):
        # Same stereo phase but 6dB difference: this is not a fair
        # listener comparison, even though neither WAV loses in mono.
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="loud-normal")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "rms_level_confound")
        self.assertFalse(result["milestone_pass"])

    def test_unambiguously_short_or_silent_pair_skips_extra_pcm_scan(self):
        # Only strong prior evidence (short duration or full digital
        # silence) may skip the aligned scan. Level-only confounds cannot:
        # a sparse level mismatch might additionally lack joint frames.
        for mode, frames in (("normal", 4000), ("silent", 12000)):
            with self.subTest(mode=mode, frames=frames):
                _wave(self.base, mode=mode, frames=frames)
                _wave(self.candidate, mode=mode, frames=frames)
                with patch("mixlab.quality.relative_mono._paired_phase_fractions",
                           side_effect=AssertionError("unneeded second PCM read")):
                    result = inspect(str(self.base), [str(self.candidate)])
                self.assertEqual(result["candidates"][0]["status"],
                                 "insufficient_stereo_evidence")

    def test_sparse_loudness_confound_does_not_hide_missing_shared_frames(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="sparse-opposed")
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"],
                         "insufficient_stereo_evidence")

    def test_global_rms_match_does_not_hide_persistent_local_level_confound(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="window-level-shift")
        from mixlab.quality import compare_wavs
        report = compare_wavs(self.base, [self.candidate])
        self.assertTrue(report["candidates"][0]["level_comparable_for_blind_ab"])
        self.assertTrue(report["candidates"][0]["short_window_level_mismatch_risk"])
        screened = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(screened["candidates"][0]["status"],
                         "ab_timing_or_dynamics_confound")
        self.assertFalse(screened["milestone_pass"])

    def test_equal_duration_audio_with_prominent_onset_100ms_late_is_hold(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="onset-100ms-late")
        from mixlab.quality import compare_wavs
        report = compare_wavs(self.base, [self.candidate])
        self.assertTrue(report["candidates"][0]["level_comparable_for_blind_ab"])
        self.assertTrue(report["candidates"][0]["prominent_onset_mismatch_risk"])
        screened = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(screened["candidates"][0]["status"],
                         "ab_timing_or_dynamics_confound")
        self.assertFalse(screened["milestone_pass"])

    def test_audible_trailing_edge_mismatch_is_not_clean_mono_ab(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="tail-210ms-quiet")
        from mixlab.quality import compare_wavs
        canonical = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertTrue(canonical["edge_silence_mismatch_risk"])
        self.assertFalse(canonical["prominent_onset_mismatch_risk"])
        checked = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(checked["candidates"][0]["status"],
                         "ab_timing_or_dynamics_confound")
        self.assertNotIn(str(self.root), json.dumps(checked))

    def test_blind_ab_batch_holds_only_confounded_candidate(self):
        _wave(self.base, mode="normal")
        healthy = self.root / "independent.wav"
        confounded = self.root / "shifted.wav"
        _wave(healthy, mode="alternate")
        _wave(confounded, mode="window-level-shift")
        result = inspect(str(self.base), [str(healthy), str(confounded)])
        self.assertEqual([x["status"] for x in result["candidates"]], [
            "no_new_sustained_mono_cancellation_detected",
            "ab_timing_or_dynamics_confound",
        ])
        self.assertTrue(result["human_preference_test_required"])
        self.assertFalse(result["milestone_pass"])

    def test_short_interior_stereo_silence_is_not_a_clean_candidate(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="interior-60ms-silence")
        from mixlab.quality import compare_wavs
        canonical = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertTrue(canonical["metrics"]["short_interior_pcm_dropout_risk"])
        self.assertTrue(canonical["level_comparable_for_blind_ab"])
        report = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(report["candidates"][0]["status"], "ab_audio_integrity_confound")
        self.assertFalse(report["milestone_pass"])

    def test_short_one_channel_dropout_is_not_a_clean_candidate(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="interior-60ms-right-dropout")
        from mixlab.quality import compare_wavs
        canonical = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertTrue(canonical["metrics"]["short_interior_stereo_channel_dropout_risk"])
        self.assertTrue(canonical["level_comparable_for_blind_ab"])
        report = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(report["candidates"][0]["status"], "ab_audio_integrity_confound")
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_isolated_pcm_impulse_requires_review(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="single-impulse")
        from mixlab.quality import compare_wavs
        canonical = compare_wavs(self.base, [self.candidate])["candidates"][0]
        self.assertTrue(canonical["metrics"]["isolated_sample_impulse_risk"])
        self.assertFalse(canonical["metrics"]["severe_sample_discontinuity_risk"])
        report = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(report["candidates"][0]["status"], "ab_audio_integrity_confound")
        self.assertFalse(report["milestone_pass"])

    def test_baseline_audio_glitch_is_not_a_clean_comparison_either(self):
        _wave(self.base, mode="single-impulse")
        _wave(self.candidate, mode="alternate")
        from mixlab.quality import compare_wavs
        canonical = compare_wavs(self.base, [self.candidate])
        self.assertTrue(canonical["baseline"]["isolated_sample_impulse_risk"])
        checked = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(checked["candidates"][0]["status"], "ab_audio_integrity_confound")
        self.assertFalse(checked["milestone_pass"])
        self.assertNotIn(str(self.root), json.dumps(checked))

    def test_sustained_flat_top_requires_audio_integrity_review(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="flat-top")
        from mixlab.quality import compare_wavs
        metrics = compare_wavs(self.base, [self.candidate])["candidates"][0]["metrics"]
        self.assertTrue(metrics["high_flat_top_plateau_risk"])
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "ab_audio_integrity_confound")
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_large_pcm_discontinuity_requires_audio_integrity_review(self):
        _wave(self.base, mode="normal")
        _wave(self.candidate, mode="large-jump")
        from mixlab.quality import compare_wavs
        metrics = compare_wavs(self.base, [self.candidate])["candidates"][0]["metrics"]
        self.assertTrue(metrics["severe_sample_discontinuity_risk"])
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"], "ab_audio_integrity_confound")
        self.assertFalse(result["milestone_pass"])

    def test_baseline_already_inverted_requires_review_not_false_clean(self):
        _wave(self.base, mode="opposed")
        _wave(self.candidate, mode="alternate-opposed")
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
        _wave(clean, mode="alternate")
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

    def test_exact_two_million_frame_limit_stays_bounded_and_abstains(self):
        # Maximum admitted stereo payload is exactly 8MB per file. Exercise
        # the entire paired reader with low-information synthetic silence.
        # Neither the quality verdict nor program output may turn green.
        silent = bytes(2_000_000 * 4)
        for path in (self.base, self.candidate):
            with wave.open(str(path), "wb") as out:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(96000)
                out.writeframes(silent)
        result = inspect(str(self.base), [str(self.candidate)])
        self.assertEqual(result["candidates"][0]["status"],
                         "insufficient_stereo_evidence")
        self.assertFalse(result["milestone_pass"])
        self.assertNotIn(str(self.root), json.dumps(result))

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

    def test_invalid_cli_arguments_never_echo_private_sources(self):
        # argparse normally includes unrecognized positional arguments
        # verbatim in stderr, accidentally disclosing reviewer source paths.
        private_path = str(self.root / "confidential-artist-and-title.wav")
        for tail in (["--unknown", private_path], [private_path]):
            with self.subTest(extra=tail):
                proc = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.relative_mono",
                     "--baseline", "private-baseline.wav",
                     "--candidate", "private-candidate.wav", *tail],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertNotIn(private_path, proc.stdout + proc.stderr)
                self.assertEqual(proc.stderr, "")
                self.assertEqual(json.loads(proc.stdout)["status"], "invalid_private_pcm")

    def test_missing_cli_operands_fail_closed_without_path_disclosure(self):
        secret = str(self.root / "private-review-source.wav")
        for args in (
            ["--baseline", secret],
            ["--baseline", secret, "--candidate"],
            ["--candidate", secret],
        ):
            with self.subTest(arguments=args):
                proc = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.relative_mono", *args],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stderr, "")
                self.assertNotIn(secret, proc.stdout + proc.stderr)
                self.assertFalse(json.loads(proc.stdout)["milestone_pass"])

    def test_mixed_cli_batch_with_loud_candidate_must_hold(self):
        _wave(self.base, mode="normal")
        clean = self.root / "clean.wav"
        loud = self.root / "too-loud.wav"
        _wave(clean, mode="alternate")
        _wave(loud, mode="loud-normal")
        result = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.relative_mono",
             "--baseline", str(self.base),
             "--candidate", str(clean), "--candidate", str(loud)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertEqual([x["status"] for x in json.loads(result.stdout)["candidates"]],
                         ["no_new_sustained_mono_cancellation_detected", "rms_level_confound"])

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
