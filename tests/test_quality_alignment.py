"""Synthetic regression suite for optional ML-07 temporal-envelope confound QA."""
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.alignment import compare_envelopes


def make_wav(path, samples, *, rate=8000, channels=1, width=2):
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(width)
        dst.setframerate(rate)
        if width == 2:
            pcm = array("h", samples)
            if sys.byteorder != "little":
                pcm.byteswap()
            dst.writeframes(pcm.tobytes())
        else:
            dst.writeframes(bytes(samples))


def pattern():
    # Continuous, non-silent floor: first-prominent/onset and >200ms silence
    # heuristics alone cannot identify this A/B timing confound.
    points = (0.10, 0.27, 0.49, 0.85, 1.14, 1.49, 1.81)
    beats = [int(p * 8000) for p in points]
    return [25000 if any(k <= i < k + 120 for k in beats) else 2000
            for i in range(16000)]


def regional_pattern():
    """Nonperiodic transient accents every 500ms, constant non-silent floor."""
    out = [2000] * 32000
    for segment in range(8):
        for onset in (640 + (segment % 3) * 160,
                      2240 + (segment % 2) * 120):
            start = segment * 4000 + onset
            out[start:start + 120] = [25000] * 120
    return out


def second_half_delayed(samples, *, shift_frames=640):
    """Keep the first 2s unchanged and delay only the remaining 2s."""
    out = samples[:16000]
    for start in range(16000, 32000, 4000):
        piece = samples[start:start + 4000]
        out += [2000] * shift_frames + piece[:4000 - shift_frames]
    return out


class EnvelopeAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name) / "baseline.wav"
        self.other = Path(self.folder.name) / "candidate.wav"
        self.samples = pattern()
        make_wav(self.base, self.samples)
        make_wav(self.other, self.samples)

    def row(self):
        return compare_envelopes(self.base, [self.other])["candidates"][0]

    def test_exact_time_alignment_is_not_flagged(self):
        self.assertIs(self.row()["temporal_envelope_shift_risk"], False)
        self.assertEqual([], self.row()["warnings"])

    def test_continuous_audio_80ms_shift_detected_without_exporting_lag(self):
        offset = 640
        make_wav(self.other, self.samples[-offset:] + self.samples[:-offset])
        row = self.row()
        self.assertIs(row["temporal_envelope_shift_risk"], True)
        self.assertEqual(
            ["microtiming_envelope_shift_inspect_not_beat_alignment"], row["warnings"])
        public = json.dumps(compare_envelopes(self.base, [self.other]))
        self.assertNotIn("640", public)
        self.assertNotIn(str(self.folder.name), public)
        self.assertNotIn("sha256", public)
        self.assertNotIn("envelope_bins", public)

    def test_simple_common_gain_does_not_invent_a_shift(self):
        make_wav(self.other, [round(x * 0.8) for x in self.samples])
        self.assertIs(self.row()["temporal_envelope_shift_risk"], False)

    def test_unstructured_constant_signal_abstains_instead_of_false_clean(self):
        flat = [2000] * len(self.samples)
        make_wav(self.base, flat)
        make_wav(self.other, flat)
        row = self.row()
        self.assertIsNone(row["temporal_envelope_shift_risk"])
        self.assertIn("microtiming_alignment_inconclusive_inspect", row["warnings"])
        self.assertIn("regional_timing_alignment_inconclusive_inspect", row["warnings"])

    def test_too_short_audio_abstains(self):
        make_wav(self.base, self.samples[:2400])
        make_wav(self.other, self.samples[:2400])
        self.assertIsNone(self.row()["temporal_envelope_shift_risk"])

    def test_different_frame_counts_fail_closed_before_scan(self):
        make_wav(self.other, self.samples[:-1])
        with self.assertRaises(ValueError):
            self.row()

    def test_different_channel_count_fails_closed(self):
        make_wav(self.other, [v for x in self.samples for v in (x, x)], channels=2)
        with self.assertRaises(ValueError):
            self.row()

    def test_invalid_pcm_width_fails_closed(self):
        make_wav(self.other, [128] * len(self.samples), width=1)
        with self.assertRaises(ValueError):
            self.row()

    def test_symlink_is_rejected(self):
        self.other.unlink()
        self.other.symlink_to(self.base)
        with self.assertRaises(OSError):
            self.row()

    @unittest.skipUnless(hasattr(__import__("os"), "mkfifo"), "FIFO requires POSIX")
    def test_fifo_rejected_without_waiting_for_writer(self):
        import os
        self.other.unlink()
        os.mkfifo(self.other)
        with self.assertRaises(ValueError):
            self.row()

    def test_max_eight_candidates_and_aggregate_budget(self):
        self.assertEqual(8, len(compare_envelopes(self.base, [self.other] * 8)["candidates"]))
        with self.assertRaises(ValueError):
            compare_envelopes(self.base, [self.other] * 9)

    def test_sources_are_unchanged(self):
        before = self.base.read_bytes(), self.other.read_bytes()
        compare_envelopes(self.base, [self.other])
        self.assertEqual(before, (self.base.read_bytes(), self.other.read_bytes()))

    def test_cli_paths_are_private_in_success_and_invalid_arguments(self):
        secret = "PRIVATE_AUDIO_TRACK_FILENAME"
        path = Path(self.folder.name) / (secret + ".wav")
        make_wav(path, self.samples)
        ok = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                             str(self.base), str(path)],
                            capture_output=True, text=True, timeout=20)
        self.assertEqual(0, ok.returncode)
        self.assertNotIn(secret, ok.stdout + ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["human_listening_required"])
        bad = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                              str(self.base), str(path), "--" + secret],
                             capture_output=True, text=True, timeout=20)
        self.assertEqual(2, bad.returncode)
        self.assertNotIn(secret, bad.stdout + bad.stderr)

    def test_cli_argument_error_uses_real_linebreak_not_raw_escape(self):
        private = "CANARY_200MS_SECRET"
        proc = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                               str(self.base), str(self.other),
                               "--" + private],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.endswith("\n"))
        self.assertNotIn(r"\n", proc.stderr)
        self.assertNotIn(private, proc.stderr + proc.stdout)

    def test_cli_fail_on_warnings_is_bounded_and_redacted(self):
        offset = 640
        make_wav(self.other, self.samples[-offset:] + self.samples[:-offset])
        proc = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                               str(self.base), str(self.other), "--fail-on-warnings"],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(2, proc.returncode)
        self.assertNotIn(self.folder.name, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["candidates"][0]["warnings"])

    def test_cli_rejects_unreadable_path_without_disclosure(self):
        secret = "secret_source_filename"
        proc = subprocess.run([sys.executable, "-m", "mixlab.quality.alignment",
                               str(self.base), str(Path(self.folder.name) / secret)],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(3, proc.returncode)
        self.assertNotIn(secret, proc.stdout + proc.stderr)



    def test_stereo_opposite_direction_shift_detected(self):
        stereo = [sample for x in self.samples for sample in (x, round(x * 0.7))]
        offset = 80 * 8 * 2  # 80 ms * 8 kHz, interleaved stereo samples
        make_wav(self.base, stereo, channels=2)
        make_wav(self.other, stereo[offset:] + stereo[:offset], channels=2)
        self.assertIs(self.row()["temporal_envelope_shift_risk"], True)

    def test_multiple_candidates_do_not_share_alignment_state(self):
        shift = 640
        make_wav(self.other, self.samples[-shift:] + self.samples[:-shift])
        rows = compare_envelopes(self.base, [self.other, self.base])["candidates"]
        self.assertEqual(["candidate-01", "candidate-02"], [r["id"] for r in rows])
        self.assertIs(rows[0]["temporal_envelope_shift_risk"], True)
        self.assertIs(rows[1]["temporal_envelope_shift_risk"], False)

    def test_rate_mismatch_rejected_before_comparison(self):
        make_wav(self.other, self.samples, rate=16000)
        with self.assertRaises(ValueError):
            self.row()

    def test_truncated_riff_audio_does_not_silently_pass(self):
        data = self.other.read_bytes()
        self.other.write_bytes(data[:-32])
        with self.assertRaises(ValueError):
            self.row()

    def test_aggregate_budget_rejects_a_later_candidate(self):
        from unittest.mock import patch
        # Simulate a smaller global limit without creating large media.
        with patch("mixlab.quality.alignment.MAX_TOTAL_FRAMES", 2 * len(self.samples)):
            with self.assertRaises(ValueError):
                compare_envelopes(self.base, [self.other, self.other])

    def test_invalid_baseline_symlink_rejected(self):
        alias = Path(self.folder.name) / "alias.wav"
        alias.symlink_to(self.base)
        with self.assertRaises(OSError):
            compare_envelopes(alias, [self.other])


    def test_real_two_million_frame_limit_without_loading_all_pcm(self):
        # Full advertised admission boundary, not just mocked source limits.
        # Constant non-silent PCM is deliberately uninformative (risk=None).
        block = array("h", [2000] * 4096)
        if sys.byteorder != "little":
            block.byteswap()
        for path in (self.base, self.other):
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                for _ in range(2_000_000 // 4096):
                    out.writeframesraw(block.tobytes())
                tail = array("h", [2000] * (2_000_000 % 4096))
                if sys.byteorder != "little":
                    tail.byteswap()
                out.writeframesraw(tail.tobytes())
        result = compare_envelopes(self.base, [self.other])
        self.assertIsNone(result["candidates"][0]["temporal_envelope_shift_risk"])


    def test_regional_drift_catches_only_later_timing_offset(self):
        reference = regional_pattern()
        make_wav(self.base, reference)
        make_wav(self.other, second_half_delayed(reference))
        row = self.row()
        self.assertIs(row["regional_timing_shift_risk"], True)
        self.assertIn("regional_timing_shift_inspect_not_tempo_estimate",
                      row["warnings"])
        report = json.dumps(compare_envelopes(self.base, [self.other]))
        self.assertNotIn(str(self.folder.name), report)
        self.assertNotIn("lag_ms", report)
        self.assertNotIn("segment_index", report)
        self.assertNotIn("correlation", report)

    def test_regional_drift_is_symmetric_in_source_order(self):
        reference = regional_pattern()
        candidate = second_half_delayed(reference)
        make_wav(self.base, reference)
        make_wav(self.other, candidate)
        before = self.row()
        make_wav(self.base, candidate)
        make_wav(self.other, reference)
        after = self.row()
        self.assertIs(before["regional_timing_shift_risk"], True)
        self.assertIs(after["regional_timing_shift_risk"], True)

    def test_regional_clean_when_same_rhythm_under_uniform_gain(self):
        samples = regional_pattern()
        make_wav(self.base, samples)
        make_wav(self.other, [round(x * .85) for x in samples])
        row = self.row()
        self.assertIs(row["regional_timing_shift_risk"], False)
        self.assertNotIn("regional_timing_shift_inspect_not_tempo_estimate",
                         row["warnings"])

    def test_global_shift_is_not_mislabeled_as_regional_drift(self):
        samples = regional_pattern()
        offset = 640
        make_wav(self.base, samples)
        make_wav(self.other, samples[-offset:] + samples[:-offset])
        row = self.row()
        self.assertIsNot(row["regional_timing_shift_risk"], True)

    def test_single_shifted_region_is_not_called_persistent_drift(self):
        samples = regional_pattern()
        altered = samples.copy()
        start = 16000
        altered[start:start + 4000] = [2000] * 640 + samples[start:start + 3360]
        make_wav(self.base, samples)
        make_wav(self.other, altered)
        self.assertIsNot(self.row()["regional_timing_shift_risk"], True)

    def test_regions_unchanged_on_multiple_private_candidates(self):
        samples = regional_pattern()
        make_wav(self.base, samples)
        make_wav(self.other, second_half_delayed(samples))
        row1, row2 = compare_envelopes(self.base,
                                       [self.other, self.base])["candidates"]
        self.assertIs(row1["regional_timing_shift_risk"], True)
        self.assertIs(row2["regional_timing_shift_risk"], False)


    def test_result_independent_of_read_chunk_sizes(self):
        from unittest.mock import patch
        samples = regional_pattern()
        make_wav(self.base, samples)
        make_wav(self.other, second_half_delayed(samples))
        ref = compare_envelopes(self.base, [self.other])
        for chunk in (1, 257, 4096, 8191):
            with self.subTest(chunk=chunk):
                with patch("mixlab.quality.alignment.READ_BLOCK_FRAMES", chunk):
                    self.assertEqual(ref, compare_envelopes(self.base, [self.other]))

    def test_stereo_region_drift_detected_after_a_clean_opening(self):
        samples = regional_pattern()
        stereo = [sample for x in samples for sample in (x, round(x * 0.5))]
        shifted = second_half_delayed(samples)
        other = [sample for x in shifted for sample in (x, round(x * 0.5))]
        make_wav(self.base, stereo, channels=2)
        make_wav(self.other, other, channels=2)
        self.assertIs(self.row()["regional_timing_shift_risk"], True)

    def test_short_or_flat_audio_cannot_claim_regional_clean(self):
        make_wav(self.base, self.samples[:2400])
        make_wav(self.other, self.samples[:2400])
        self.assertIsNone(self.row()["regional_timing_shift_risk"])
        long_flat = [2000] * 32000
        make_wav(self.base, long_flat)
        make_wav(self.other, long_flat)
        self.assertIsNone(self.row()["regional_timing_shift_risk"])

if __name__ == "__main__":
    unittest.main()
