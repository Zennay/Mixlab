"""Synthetic, rights-free regression tests for independent ML-07 bitdepth screening."""
import array
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import bitdepth


def samples(frames=8000, *, collapse=False, channels=2, quiet=False, right_only=False):
    values = array.array("h")
    for i in range(frames):
        # Non-periodic low bits; deliberately no recordings or copyrighted music.
        high = (2600 + ((i * 1103 + (i // 7) * 719) % 17000)) * (-1 if i % 3 else 1)
        for ch in range(channels):
            number = (0 if quiet else high + ch * 19)
            if collapse and (not right_only or ch == 1):
                number = (number // 256) * 256
            values.append(number)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def wav(path, data, *, rate=8000, channels=2, width=2):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(data)


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "private-base.wav"
        self.good = self.root / "private-good.wav"
        self.bad = self.root / "private-bad.wav"
        wav(self.base, samples())
        wav(self.good, samples())
        wav(self.bad, samples(collapse=True))

    def test_clean_stereo_ab_is_conclusive_without_false_warning(self):
        data = bitdepth.inspect_ab(self.base, [self.good])
        self.assertFalse(data["candidates"][0]["coarse_resolution_review"])
        self.assertEqual([False, False], data["candidates"][0]["per_channel_review"])
        self.assertEqual(2, data["channels"])
        self.assertTrue(all(ch["evidenced"] for ch in data["baseline_channel_metrics"]))
        self.assertNotIn(str(self.root), json.dumps(data))
        self.assertNotIn("private", json.dumps(data))

    def test_8bit_left_justified_candidate_is_flagged_both_channels(self):
        data = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertIs(data["candidates"][0]["coarse_resolution_review"], True)
        self.assertEqual([True, True], data["candidates"][0]["per_channel_review"])
        self.assertEqual(1.0, data["candidates"][0]["candidate_channel_metrics"][0]["low_byte_zero_fraction"])

    def test_exact_integer_thresholds_cannot_round_into_false_positive(self):
        # Both reported six-decimal fractions can appear to meet the gate,
        # even though the raw integer counts remain strictly below/above.
        clean_base = {"eligible_samples": 2_000_000, "low_byte_zero_samples": 0}
        almost_candidate = {"eligible_samples": 1_999_999, "low_byte_zero_samples": 1_989_999}
        self.assertEqual(0.995, round(almost_candidate["low_byte_zero_samples"] / almost_candidate["eligible_samples"], 6))
        self.assertFalse(bitdepth._coarse_loss(clean_base, almost_candidate))
        just_over_base = {"eligible_samples": 1_999_999, "low_byte_zero_samples": 700_000}
        clear_candidate = {"eligible_samples": 2_000_000, "low_byte_zero_samples": 1_990_000}
        self.assertEqual(0.35, round(just_over_base["low_byte_zero_samples"] / just_over_base["eligible_samples"], 6))
        self.assertFalse(bitdepth._coarse_loss(just_over_base, clear_candidate))
        threshold_base = {"eligible_samples": 2_000_000, "low_byte_zero_samples": 700_000}
        self.assertTrue(bitdepth._coarse_loss(threshold_base, clear_candidate))

    def test_constant_nonzero_low_byte_quantization_lattice_is_reviewed(self):
        # An 8-bit-shifted signal with a fixed PCM offset has low byte 37,
        # not zero, but still contains only 256-level quantization steps.
        original = array.array("h")
        original.frombytes(samples())
        shifted = array.array("h", ((value // 256) * 256 + 37 for value in original))
        if sys.byteorder != "little":
            shifted.byteswap()
        wav(self.bad, shifted.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])["candidates"][0]
        self.assertEqual([True, True], result["per_channel_review"])

    def test_only_right_channel_has_nonzero_offset_lattice(self):
        original = array.array("h")
        original.frombytes(samples())
        for index in range(1, len(original), 2):
            original[index] = original[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            original.byteswap()
        wav(self.bad, original.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])["candidates"][0]
        self.assertEqual([False, True], result["per_channel_review"])

    def test_smooth_fixed_offset_without_quantization_stays_clear(self):
        original = array.array("h")
        original.frombytes(samples())
        shifted = array.array("h", (value + 37 for value in original))
        if sys.byteorder != "little":
            shifted.byteswap()
        wav(self.bad, shifted.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])["candidates"][0]
        self.assertEqual([False, False], result["per_channel_review"])

    def test_twelve_bit_quantization_inside_pcm16_is_detected(self):
        # 12-bit effective precision: four LSBs are locked to an offset,
        # while the byte-level residue still varies over sixteen values.
        original = array.array("h")
        original.frombytes(samples())
        shifted = array.array("h", ((value // 16) * 16 + 3 for value in original))
        if sys.byteorder != "little":
            shifted.byteswap()
        wav(self.bad, shifted.tobytes())
        report = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([True, True], report["candidates"][0]["per_channel_review"])

    def test_fourteen_bit_quantization_inside_pcm16_is_detected(self):
        # 14-bit content hidden in 16-bit container leaves only 4 residue
        # values; a fixed two-bit remainder is a candidate-specific failure.
        original = array.array("h")
        original.frombytes(samples())
        shifted = array.array("h", ((value // 4) * 4 + 1 for value in original))
        if sys.byteorder != "little":
            shifted.byteswap()
        wav(self.bad, shifted.tobytes())
        report = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([True, True], report["candidates"][0]["per_channel_review"])

    def test_already_fourteen_bit_baseline_requires_inconclusive_result(self):
        original = array.array("h")
        original.frombytes(samples())
        low_precision = array.array("h", ((value // 4) * 4 + 1 for value in original))
        if sys.byteorder != "little":
            low_precision.byteswap()
        wav(self.base, low_precision.tobytes())
        wav(self.good, low_precision.tobytes())
        report = bitdepth.inspect_ab(self.base, [self.good])
        self.assertEqual([None, None], report["candidates"][0]["per_channel_review"])

    def test_twelve_bit_degradation_still_detected_from_fourteen_bit_reference(self):
        original = array.array("h")
        original.frombytes(samples())
        base_14 = array.array("h", ((value // 4) * 4 + 1 for value in original))
        candidate_12 = array.array("h", ((value // 16) * 16 + 3 for value in original))
        if sys.byteorder != "little":
            base_14.byteswap()
            candidate_12.byteswap()
        wav(self.base, base_14.tobytes())
        wav(self.bad, candidate_12.tobytes())
        report = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([True, True], report["candidates"][0]["per_channel_review"])

    def test_single_channel_regression_detected(self):
        wav(self.bad, samples(collapse=True, right_only=True))
        result = bitdepth.inspect_ab(self.base, [self.bad])["candidates"][0]
        self.assertEqual([False, True], result["per_channel_review"])
        self.assertTrue(result["coarse_resolution_review"])

    def test_regional_quantization_four_window_is_not_hidden_by_clean_majority(self):
        # Exactly 400ms of the middle of a 1s WAV loses 8 LSBs.
        # Whole-file dominant-residue fraction is only about 40%, below 99.5%.
        values = array.array("h")
        values.frombytes(samples())
        for frame in range(2400, 5600):
            for channel in (0, 1):
                index = 2 * frame + channel
                values[index] = values[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            values.byteswap()
        wav(self.bad, values.tobytes())
        report = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([True, True], report["candidates"][0]["per_channel_review"])
        self.assertEqual(3, self.cli(self.base, self.bad, "--strict").returncode)

    def test_three_consecutive_quantized_windows_are_not_persistent(self):
        values = array.array("h")
        values.frombytes(samples())
        for frame in range(2400, 4800):
            for channel in (0, 1):
                index = 2 * frame + channel
                values[index] = values[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            values.byteswap()
        wav(self.bad, values.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([False, False], result["candidates"][0]["per_channel_review"])

    def test_four_separated_one_window_artifacts_are_not_consecutive(self):
        values = array.array("h")
        values.frombytes(samples())
        for frame in range(8000):
            if frame // 800 in (0, 2, 4, 6):
                for channel in (0, 1):
                    index = 2 * frame + channel
                    values[index] = values[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            values.byteswap()
        wav(self.bad, values.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([False, False], result["candidates"][0]["per_channel_review"])

    def test_locally_damaged_baseline_cannot_certify_a_matching_candidate(self):
        # Whole-file baseline diversity can hide a persistent 400ms local
        # loss of 8-bit precision. Equal candidates must NOT be certified.
        values = array.array("h")
        values.frombytes(samples())
        for frame in range(2400, 5600):
            for channel in (0, 1):
                index = 2 * frame + channel
                values[index] = values[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            values.byteswap()
        wav(self.base, values.tobytes())
        wav(self.good, values.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.good])
        self.assertEqual([None, None], result["candidates"][0]["per_channel_review"])
        self.assertIsNone(result["candidates"][0]["coarse_resolution_review"])
        self.assertEqual(3, self.cli(self.base, self.good, "--strict").returncode)

    def test_four_window_local_damage_in_right_channel_only(self):
        values = array.array("h")
        values.frombytes(samples())
        for frame in range(2400, 5600):
            index = 2 * frame + 1
            values[index] = values[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            values.byteswap()
        wav(self.bad, values.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([False, True], result["candidates"][0]["per_channel_review"])

    def test_batch_earlier_good_never_covers_later_bad(self):
        data = bitdepth.inspect_ab(self.base, [self.good, self.bad])
        self.assertEqual([False, True], [r["coarse_resolution_review"] for r in data["candidates"]])

    def test_mono_supported(self):
        wav(self.base, samples(channels=1), channels=1)
        wav(self.bad, samples(collapse=True, channels=1), channels=1)
        data = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual(1, data["channels"])
        self.assertEqual([True], data["candidates"][0]["per_channel_review"])

    def test_coarsened_baseline_cannot_become_a_false_clean_ab_pair(self):
        # If the reference itself has only 8-bit steps, there is no
        # trustworthy high-resolution baseline for a "clean" judgement.
        wav(self.base, samples(collapse=True))
        wav(self.good, samples(collapse=True))
        first = bitdepth.inspect_ab(self.base, [self.good])["candidates"][0]
        self.assertEqual([None, None], first["per_channel_review"])
        self.assertIsNone(first["coarse_resolution_review"])
        wav(self.good, samples())
        second = bitdepth.inspect_ab(self.base, [self.good])["candidates"][0]
        self.assertEqual([None, None], second["per_channel_review"])
        self.assertIsNone(second["coarse_resolution_review"])
        self.assertEqual(3, self.cli(self.base, self.good, "--strict").returncode)

    def test_partial_coarsened_baseline_abstains_only_on_affected_channel(self):
        wav(self.base, samples(collapse=True, right_only=True))
        result = bitdepth.inspect_ab(self.base, [self.good])["candidates"][0]
        self.assertEqual([False, None], result["per_channel_review"])
        self.assertIsNone(result["coarse_resolution_review"])


    def test_disjoint_active_100ms_intervals_never_make_a_clean_ab_claim(self):
        # Both files independently contain a full second of valid PCM16,
        # yet none of their audible frames coincide. Aggregate statistics
        # are identical and must not be interpreted as comparative evidence.
        chunk = samples(frames=8000)
        silence = b"\x00\x00" * 2 * 8000
        wav(self.base, chunk + silence)
        wav(self.good, silence + chunk)
        report = bitdepth.inspect_ab(self.base, [self.good])
        self.assertTrue(all(c["evidenced"] for c in report["baseline_channel_metrics"]))
        self.assertEqual([None, None], report["candidates"][0]["per_channel_review"])
        self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])
        self.assertEqual(3, self.cli(self.base, self.good, "--strict").returncode)

    def test_disjoint_coarse_candidate_cannot_claim_bitdepth_defect(self):
        # A quantised candidate is silent wherever the reference is active.
        # No A/B evidence exists to attribute precision loss to processing.
        chunk = samples(frames=8000)
        coarse = samples(frames=8000, collapse=True)
        silence = b"\x00\x00" * 2 * 8000
        wav(self.base, chunk + silence)
        wav(self.bad, silence + coarse)
        report = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([None, None], report["candidates"][0]["per_channel_review"])
        self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])

    def test_stereo_right_disjoint_from_baseline_abstains_without_full_clean(self):
        # Both left channels align, but the right candidate channel plays
        # only in the second second, with its reference on the first.
        block = array.array("h")
        block.frombytes(samples(frames=8000))
        values = array.array("h")
        for frame in range(8000):
            values.extend((block[frame * 2], 0))
        for frame in range(8000):
            values.extend((0, block[frame * 2 + 1]))
        if sys.byteorder != "little":
            values.byteswap()
        left_only_then_right = values.tobytes()
        silence = b"\x00\x00" * 2 * 8000
        wav(self.base, samples(frames=8000) + silence)
        wav(self.good, left_only_then_right)
        report = bitdepth.inspect_ab(self.base, [self.good])
        self.assertEqual([False, None], report["candidates"][0]["per_channel_review"])
        self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])

    def test_disjoint_later_candidate_makes_strict_batch_inconclusive(self):
        # A first valid candidate cannot hide a later non-overlapping one.
        chunk = samples(frames=8000)
        silence = b"\x00\x00" * 2 * 8000
        wav(self.base, chunk + silence)
        wav(self.good, chunk + silence)
        wav(self.bad, silence + chunk)
        result = bitdepth.inspect_ab(self.base, [self.good, self.bad])
        self.assertEqual([False, None], [
            item["coarse_resolution_review"] for item in result["candidates"]])
        cmd = self.cli(self.base, self.good, self.bad, "--strict")
        self.assertEqual(3, cmd.returncode)
        self.assertNotIn(str(self.root), cmd.stdout + cmd.stderr)

    def test_partial_overlap_with_missing_audible_tail_stays_inconclusive(self):
        # There are five perfectly aligned high-level 100ms windows, but
        # five more are present only in the baseline. Whole-file metrics
        # must not claim clean quality for a partially missing render.
        rate = 96000
        first = samples(frames=rate // 2, channels=1)
        last = samples(frames=rate // 2, channels=1)
        wav(self.base, first + last, rate=rate, channels=1)
        wav(self.good, first + b"\x00\x00" * (rate // 2),
            rate=rate, channels=1)
        report = bitdepth.inspect_ab(self.base, [self.good])
        self.assertTrue(report["baseline_channel_metrics"][0]["evidenced"])
        self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])

    def test_one_short_matched_window_does_not_fabricate_evidence(self):
        # Both files have independent valid audio elsewhere but only three
        # consecutive shared active windows. Never call them comparable.
        segment = samples(frames=8000, channels=1)
        silence = b"\x00\x00" * 8000
        wav(self.base, segment + silence, channels=1)
        shifted = b"\x00\x00" * (800 * 7) + segment + b"\x00\x00" * (800 * 3)
        wav(self.good, shifted, channels=1)
        report = bitdepth.inspect_ab(self.base, [self.good])
        self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])

    def test_disjoint_window_intersection_across_fractional_rates(self):
        # The 100ms boundaries vary when samplerate % 10 != 0. Prove that
        # disjoint and matched one-second intervals remain distinguishable,
        # without assuming an exact integral samples-per-window.
        for rate in (8000, 11025, 44101, 96000):
            with self.subTest(rate=rate):
                chunk = samples(frames=rate, channels=1)
                silence = b"\x00\x00" * rate
                wav(self.base, chunk + silence, rate=rate, channels=1)
                wav(self.good, silence + chunk, rate=rate, channels=1)
                disjoint = bitdepth.inspect_ab(self.base, [self.good])
                self.assertIsNone(disjoint["candidates"][0]["coarse_resolution_review"])
                wav(self.good, chunk + silence, rate=rate, channels=1)
                matched = bitdepth.inspect_ab(self.base, [self.good])
                self.assertIs(matched["candidates"][0]["coarse_resolution_review"], False)

    def test_half_window_time_division_does_not_count_as_simultaneous_pcm(self):
        # Each WAV is active for exactly HALF of each 100ms window, so
        # per-window occupancy and even matching time-window index sets pass.
        # Yet A plays in frames 0..399 and B in 400..799 within EVERY window.
        # There is not a single frame of simultaneous audible A/B evidence.
        frames = 16000
        base = array.array("h")
        base.frombytes(samples(frames=frames))
        cand = array.array("h", base)
        for frame in range(frames):
            for channel in range(2):
                index = 2 * frame + channel
                if frame % 800 < 400:
                    cand[index] = 0
                else:
                    base[index] = 0
        if sys.byteorder != "little":
            base.byteswap()
            cand.byteswap()
        wav(self.base, base.tobytes())
        wav(self.good, cand.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.good])
        self.assertEqual([None, None], result["candidates"][0]["per_channel_review"])
        self.assertIsNone(result["candidates"][0]["coarse_resolution_review"])

    def test_half_window_time_division_cannot_falsely_flag_coarse_damage(self):
        frames = 16000
        base = array.array("h")
        base.frombytes(samples(frames=frames))
        cand = array.array("h")
        cand.frombytes(samples(frames=frames, collapse=True))
        for frame in range(frames):
            for channel in range(2):
                index = 2 * frame + channel
                if frame % 800 < 400:
                    cand[index] = 0
                else:
                    base[index] = 0
        if sys.byteorder != "little":
            base.byteswap()
            cand.byteswap()
        wav(self.base, base.tobytes())
        wav(self.bad, cand.tobytes())
        result = bitdepth.inspect_ab(self.base, [self.bad])
        self.assertEqual([None, None], result["candidates"][0]["per_channel_review"])
        self.assertIsNone(result["candidates"][0]["coarse_resolution_review"])

    def test_low_energy_abstains_without_claiming_a_clean_pair(self):
        wav(self.good, samples(quiet=True))
        data = bitdepth.inspect_ab(self.base, [self.good])
        self.assertIsNone(data["candidates"][0]["coarse_resolution_review"])
        self.assertEqual([None, None], data["candidates"][0]["per_channel_review"])

    def test_short_excerpt_abstains(self):
        wav(self.base, samples(frames=500))
        wav(self.good, samples(frames=500))
        self.assertIsNone(bitdepth.inspect_ab(self.base, [self.good])["candidates"][0]["coarse_resolution_review"])

    def test_short_burst_does_not_satisfy_four_windows(self):
        # At 96 kHz, 4096 high-level samples meet the total-sample requirement,
        # but span only ONE 100ms bucket; the temporal-coverage guard must abstain.
        frame = samples(frames=4096, channels=1) + b"\x00\x00" * (9600 - 4096)
        wav(self.base, frame, channels=1, rate=96000)
        wav(self.good, frame, channels=1, rate=96000)
        report = bitdepth.inspect_ab(self.base, [self.good])
        self.assertEqual(4096, report["baseline_channel_metrics"][0]["eligible_samples"])
        self.assertEqual(1, report["baseline_channel_metrics"][0]["active_windows"])
        self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])

    def test_many_sparse_pulses_cannot_fake_continuous_active_evidence(self):
        # Each of 12 windows has 20ms of high-level audio followed by 80ms
        # silence at 96kHz. More than 4096 samples across >=4 buckets must
        # NOT produce a definitive false/true for either A/B variant.
        active = 1920
        frames_per_window = 9600
        zero = b"\x00\x00" * (frames_per_window - active)
        sparse = (samples(frames=active, channels=1) + zero) * 12
        sparse_coarse = (samples(frames=active, channels=1, collapse=True) + zero) * 12
        wav(self.base, sparse, rate=96000, channels=1)
        wav(self.good, sparse, rate=96000, channels=1)
        wav(self.bad, sparse_coarse, rate=96000, channels=1)
        result = bitdepth.inspect_ab(self.base, [self.good, self.bad])
        self.assertGreater(result["baseline_channel_metrics"][0]["eligible_samples"], 4096)
        self.assertEqual([None, None], [
            row["coarse_resolution_review"] for row in result["candidates"]
        ])

    def test_noncontiguous_dense_windows_cannot_claim_sustained_evidence(self):
        # Two isolated three-window islands meet the previous global
        # >=4-window requirement but never form four continuous windows.
        active = samples(frames=9600, channels=1) * 3
        gap = b"\x00\x00" * (9600 * 4)
        excerpt = active + gap + active
        wav(self.base, excerpt, rate=96000, channels=1)
        wav(self.good, excerpt, rate=96000, channels=1)
        result = bitdepth.inspect_ab(self.base, [self.good])
        self.assertEqual(6, result["baseline_channel_metrics"][0]["active_windows"])
        self.assertIsNone(result["candidates"][0]["coarse_resolution_review"])

    def test_exact_full_hundred_ms_windows_at_fractional_rates(self):
        # All rational boundaries remain exact without dropping a frame.
        # One frame short of a full fourth window may NOT be conclusive.
        for rate in (11025, 16001, 44101, 96000):
            nframes = (4 * rate + 9) // 10
            with self.subTest(rate=rate, mode="exact"):
                full = samples(frames=nframes, channels=1)
                wav(self.base, full, rate=rate, channels=1)
                wav(self.good, full, rate=rate, channels=1)
                report = bitdepth.inspect_ab(self.base, [self.good])
                self.assertEqual(4, report["baseline_channel_metrics"][0]["longest_sustained_window_run"])
                self.assertIs(report["candidates"][0]["coarse_resolution_review"], False)
            with self.subTest(rate=rate, mode="one_frame_short"):
                short = samples(frames=nframes - 1, channels=1)
                wav(self.base, short, rate=rate, channels=1)
                wav(self.good, short, rate=rate, channels=1)
                report = bitdepth.inspect_ab(self.base, [self.good])
                self.assertLess(report["baseline_channel_metrics"][0]["longest_sustained_window_run"], 4)
                self.assertIsNone(report["candidates"][0]["coarse_resolution_review"])

    def test_exact_half_occupancy_gate_vs_one_frame_less(self):
        # At 96kHz a 100ms bucket contains exactly 9600 frames. Half may
        # qualify technically; 4799/9600 must abstain in all four buckets.
        for active in (4800, 4799):
            with self.subTest(active=active):
                segment = samples(frames=active, channels=1)
                coarse_segment = samples(frames=active, collapse=True, channels=1)
                quiet = b"\x00\x00" * (9600 - active)
                wav(self.base, (segment + quiet) * 4, rate=96000, channels=1)
                wav(self.bad, (coarse_segment + quiet) * 4, rate=96000, channels=1)
                report = bitdepth.inspect_ab(self.base, [self.bad])
                expected = True if active == 4800 else None
                self.assertIs(report["candidates"][0]["coarse_resolution_review"], expected)

    def test_mismatched_duration_rate_channels_and_width_rejected(self):
        for kwargs in ({"rate": 8001}, {"channels": 1}, {"width": 1}):
            with self.subTest(kwargs=kwargs):
                if "channels" in kwargs:
                    data = samples(channels=1)
                elif "width" in kwargs:
                    data = b"\x01" * 16000
                else:
                    data = samples()
                wav(self.good, data, **kwargs)
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    bitdepth.inspect_ab(self.base, [self.good])

    def test_symlinks_and_symlinked_parent_fail_closed(self):
        symlink = self.root / "private-link.wav"
        symlink.symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            bitdepth.inspect_ab(symlink, [self.good])
        parent = self.root / "private-dir-link"
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            bitdepth.inspect_ab(parent / self.base.name, [self.good])

    def test_same_inode_hardlink_and_repeated_path_rejected(self):
        with self.assertRaises(ValueError):
            bitdepth.inspect_ab(self.base, [self.base])
        duplicate = self.root / "hardlink.wav"
        os.link(self.base, duplicate)
        with self.assertRaises(ValueError):
            bitdepth.inspect_ab(self.base, [duplicate])

    def test_parent_directory_swap_cannot_open_a_private_external_inode(self):
        # Reproduce a TOCTOU: the checked parent is a real directory, but it
        # becomes a symlink to a different directory just as the file opens.
        # O_NOFOLLOW on the *final basename* alone does not protect parents.
        allowed = self.root / "allowed"
        outside = self.root / "outside-private"
        displaced = self.root / "allowed-displaced"
        allowed.mkdir()
        outside.mkdir()
        source = allowed / "raced.wav"
        secret = outside / "raced.wav"
        wav(source, samples())
        wav(secret, samples(collapse=True))
        private_identity = (secret.stat().st_dev, secret.stat().st_ino)
        opened_private = []
        original_open = os.open
        swapped = False

        def swap_just_before_file_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if os.fspath(path).endswith("raced.wav") and not swapped:
                allowed.rename(displaced)
                allowed.symlink_to(outside, target_is_directory=True)
                swapped = True
            fd = original_open(path, flags, *args, **kwargs)
            if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == private_identity:
                opened_private.append(True)
            return fd

        try:
            with patch.object(bitdepth.os, "open", side_effect=swap_just_before_file_open):
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    bitdepth.inspect_ab(source, [self.good])
        finally:
            if allowed.is_symlink():
                allowed.unlink()
            if displaced.exists():
                displaced.rename(allowed)
        self.assertTrue(swapped, "The swap must execute for this to prove anything")
        self.assertFalse(opened_private, "Race crossed the inspected parent into a private inode")

    def test_parent_symlink_appearing_before_directory_open_is_not_followed(self):
        allowed = self.root / "allowed-early"
        outside = self.root / "outside-early"
        displaced = self.root / "allowed-early-moved"
        allowed.mkdir()
        outside.mkdir()
        wav(allowed / "raced.wav", samples())
        secret = outside / "raced.wav"
        wav(secret, samples(collapse=True))
        external = (secret.stat().st_dev, secret.stat().st_ino)
        original_open = os.open
        opened_private = []
        swapped = False

        def swap_before_parent_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and (
                os.fspath(path) == "allowed-early"
                or os.fspath(path).endswith("allowed-early/raced.wav")
            ):
                allowed.rename(displaced)
                allowed.symlink_to(outside, target_is_directory=True)
                swapped = True
            fd = original_open(path, flags, *args, **kwargs)
            if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == external:
                opened_private.append(True)
            return fd

        try:
            with patch.object(bitdepth.os, "open", side_effect=swap_before_parent_open):
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    bitdepth.inspect_ab(allowed / "raced.wav", [self.good])
        finally:
            if allowed.is_symlink():
                allowed.unlink()
            if displaced.exists():
                displaced.rename(allowed)
        self.assertTrue(swapped)
        self.assertFalse(opened_private, "Directory traversal must not follow an exchanged parent")

    @unittest.skipUnless(Path("/proc/self/fd").exists(), "Linux FD accounting")
    def test_repeated_nested_nofollow_rejection_and_success_do_not_leak_fds(self):
        nested = self.root / "a" / "b" / "c"
        nested.mkdir(parents=True)
        target = nested / "private.wav"
        wav(target, samples())
        link = self.root / "nested-link"
        link.symlink_to(self.root / "a", target_is_directory=True)
        checked = link / "b" / "c" / "private.wav"
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(16):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(checked, [self.good])
            result = bitdepth.inspect_ab(target, [self.good])
            self.assertIs(result["candidates"][0]["coarse_resolution_review"], False)
        after = len(os.listdir("/proc/self/fd"))
        self.assertEqual(before, after)

    def test_nofollow_walk_opens_each_path_component_relative_to_dirfd(self):
        parent = self.root / "one" / "two" / "three"
        parent.mkdir(parents=True)
        source = parent / "nested.wav"
        wav(source, samples())
        seen = []
        original_open = os.open

        def record_component(path, flags, *args, **kwargs):
            seen.append((os.fspath(path), flags, kwargs.get("dir_fd")))
            return original_open(path, flags, *args, **kwargs)

        with patch.object(bitdepth.os, "open", side_effect=record_component):
            result = bitdepth.inspect_ab(source, [self.good])
        self.assertIs(result["candidates"][0]["coarse_resolution_review"], False)
        self.assertTrue(any(p == "nested.wav" and dir_fd is not None for p, _, dir_fd in seen))
        self.assertTrue(any(p == "one" and dir_fd is not None and flags & os.O_NOFOLLOW and flags & os.O_DIRECTORY
                            for p, flags, dir_fd in seen))
        self.assertTrue(any(p == "two" and dir_fd is not None and flags & os.O_NOFOLLOW and flags & os.O_DIRECTORY
                            for p, flags, dir_fd in seen))
        self.assertTrue(any(p == "three" and dir_fd is not None and flags & os.O_NOFOLLOW and flags & os.O_DIRECTORY
                            for p, flags, dir_fd in seen))

    def test_parent_directory_replaced_with_same_inode_hardlink_is_rejected(self):
        # A different parent can expose the *same file inode* via hardlink.
        # Final basename fstat/lstat checks alone still look unchanged, so
        # identity of every ancestor directory is part of the admission gate.
        permitted = self.root / "permitted-parent"
        replacement = self.root / "replacement-parent"
        displaced = self.root / "permitted-parent-displaced"
        permitted.mkdir()
        replacement.mkdir()
        original = permitted / "private.wav"
        substitute = replacement / "private.wav"
        wav(original, samples())
        os.link(original, substitute)
        old_scan = bitdepth._scan
        moved = False

        def swap_parent_after_pcm_read(source):
            nonlocal moved
            result = old_scan(source)
            if not moved:
                permitted.rename(displaced)
                replacement.rename(permitted)
                moved = True
            return result

        try:
            with patch.object(bitdepth, "_scan", side_effect=swap_parent_after_pcm_read):
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    bitdepth.inspect_ab(original, [self.good])
        finally:
            if moved:
                permitted.rename(replacement)
                displaced.rename(permitted)
        self.assertTrue(moved, "The parent replacement must actually occur")

    def test_pathlike_is_resolved_once_before_lexical_and_inode_admission(self):
        # A PathLike can legally return different names on repeated calls.
        # Never validate one string and open a different private string.
        class FlippingPath:
            def __init__(self, allowed, private):
                self.allowed = allowed
                self.private = private
                self.calls = 0

            def __fspath__(self):
                self.calls += 1
                return str(self.allowed if self.calls == 1 else self.private)

        object_path = FlippingPath(self.base, self.bad)
        result = bitdepth.inspect_ab(object_path, [self.good])
        self.assertEqual(1, object_path.calls)
        self.assertIs(result["candidates"][0]["coarse_resolution_review"], False)

    def test_pathlike_cannot_expose_private_exception_on_second_resolution(self):
        class OneSafeResolution:
            def __init__(self, filename):
                self.filename = filename
                self.calls = 0

            def __fspath__(self):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("PRIVATE_TRACK_NAME")
                return str(self.filename)

        object_path = OneSafeResolution(self.base)
        report = bitdepth.inspect_ab(object_path, [self.good])
        self.assertIs(report["candidates"][0]["coarse_resolution_review"], False)
        self.assertEqual(1, object_path.calls)

    def test_pathlike_single_resolution_failure_never_leaks_private_exception(self):
        class UntrustedPath:
            def __fspath__(self):
                raise RuntimeError("PRIVATE_TRACK_FILENAME_DO_NOT_LOG")

        with self.assertRaises(ValueError) as context:
            bitdepth.inspect_ab(UntrustedPath(), [self.good])
        self.assertNotIn("PRIVATE_TRACK_FILENAME", str(context.exception))
        self.assertIn("details withheld", str(context.exception))

    def test_non_regular_and_missing_sources_do_not_leak_path(self):
        for path in [self.root / "not-found-private.wav", self.root]:
            with self.assertRaises(ValueError) as ctx:
                bitdepth.inspect_ab(self.base, [path])
            self.assertNotIn(str(path), str(ctx.exception))
            self.assertNotIn(str(self.root), str(ctx.exception))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_fifo_never_blocks(self):
        fifo = self.root / "never-open-private.fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            bitdepth.inspect_ab(self.base, [fifo])

    def test_path_replacement_midscan_rejected_without_partial_report(self):
        original = bitdepth._scan
        called = 0
        def replace_after_first_scan(source):
            nonlocal called
            result = original(source)
            called += 1
            if called == 1:
                replacement = self.root / "other.wav"
                wav(replacement, samples())
                os.replace(replacement, self.good)
            return result
        with patch.object(bitdepth, "_scan", side_effect=replace_after_first_scan):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(self.base, [self.good])

    def test_mutation_in_earlier_source_during_later_scan_rejected(self):
        original = bitdepth._scan
        called = 0
        def mutate_earlier_source(source):
            nonlocal called
            result = original(source)
            called += 1
            if called == 2:
                with open(self.base, "ab") as handle:
                    handle.write(b"later mutation")
            return result
        with patch.object(bitdepth, "_scan", side_effect=mutate_earlier_source):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(self.base, [self.good])

    def test_invalid_candidate_count_and_string_rejected(self):
        for candidates in ([], str(self.good), [self.good] * 8):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(self.base, candidates)

    def test_unbounded_candidate_iterator_is_stopped_before_source_admission(self):
        def candidate_stream():
            for _ in range(8):
                yield self.good
            raise AssertionError("unbounded candidate stream was consumed")
        with patch.object(bitdepth, "_open_source",
                          side_effect=AssertionError("source open before count validation")):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(self.base, candidate_stream())

    def test_iterator_failure_does_not_leak_private_details(self):
        def broken_candidates():
            yield self.good
            raise RuntimeError("private-track-name-from-iterator")
        with self.assertRaises(ValueError) as context:
            bitdepth.inspect_ab(self.base, broken_candidates())
        self.assertNotIn("private-track-name", str(context.exception))
        self.assertIn("details withheld", str(context.exception))

    def test_aggregate_admission_rejects_before_read(self):
        with patch.object(bitdepth, "_scan", side_effect=AssertionError("PCM read started")):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                bitdepth.inspect_ab(self.base, [self.good] * 7)
        # Same inode is rejected even earlier: either way, no PCM is read.

    def test_public_api_errors_and_result_never_leak_private_path(self):
        with self.assertRaises(ValueError) as ctx:
            bitdepth.inspect_ab(self.base, [self.root / "secret-not-found.wav"])
        self.assertNotIn("secret", str(ctx.exception))
        self.assertNotIn(str(self.root), str(ctx.exception))
        self.assertNotIn(self.base.name, json.dumps(bitdepth.inspect_ab(self.base, [self.bad])))

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "mixlab.quality.bitdepth", *map(str, args)],
            capture_output=True, text=True, timeout=15,
        )

    def test_actual_m1_renderer_families_preserve_pcm_resolution_and_private_files(self):
        from hashlib import sha256
        from mixlab.engine import FAMILY_NAMES, render
        from mixlab.models import Recipe

        baseline = self.root / "private-render-baseline.wav"
        render(self.base, self.good, baseline, Recipe(family="baseline", beats=2))
        seen = set()
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                candidate = self.root / ("private-render-family-" + family + ".wav")
                render(self.base, self.good, candidate, Recipe(family=family, beats=2))
                before = [sha256(p.read_bytes()).hexdigest() for p in (baseline, candidate)]
                review = bitdepth.inspect_ab(baseline, [candidate])
                self.assertIs(review["candidates"][0]["coarse_resolution_review"], False)
                self.assertEqual([False, False], review["candidates"][0]["per_channel_review"])
                self.assertNotIn(str(self.root), json.dumps(review))
                self.assertEqual(before, [sha256(p.read_bytes()).hexdigest()
                                          for p in (baseline, candidate)])
                seen.add(family)
        self.assertEqual(set(FAMILY_NAMES), seen)

    def test_actual_m1_output_with_injected_shifted_8bit_fault_is_detected(self):
        from mixlab.engine import render
        from mixlab.models import Recipe
        baseline = self.root / "private-engine-baseline.wav"
        clean_candidate = self.root / "private-engine-clean.wav"
        broken_candidate = self.root / "private-engine-broken.wav"
        render(self.base, self.good, baseline, Recipe(family="baseline", beats=2))
        render(self.base, self.good, clean_candidate, Recipe(family="hard_cut", beats=2))
        with wave.open(str(clean_candidate), "rb") as src:
            raw = src.readframes(src.getnframes())
            props = src.getparams()
        values = array.array("h")
        values.frombytes(raw)
        for index in range(len(values)):
            values[index] = values[index] // 256 * 256 + 37
        if sys.byteorder != "little":
            values.byteswap()
        with wave.open(str(broken_candidate), "wb") as dst:
            dst.setparams(props)
            dst.writeframes(values.tobytes())
        report = bitdepth.inspect_ab(baseline, [clean_candidate, broken_candidate])
        self.assertEqual([False, True], [
            row["coarse_resolution_review"] for row in report["candidates"]
        ])
        run = self.cli(baseline, clean_candidate, broken_candidate, "--strict")
        self.assertEqual(3, run.returncode)
        self.assertNotIn(str(self.root), run.stdout + run.stderr)

    def test_cli_clean_suspect_and_invalid_exit_codes(self):
        self.assertEqual(0, self.cli(self.base, self.good, "--strict").returncode)
        suspect = self.cli(self.base, self.bad, "--strict")
        self.assertEqual(3, suspect.returncode)
        self.assertTrue(json.loads(suspect.stdout)["candidates"][0]["coarse_resolution_review"])
        invalid = self.cli(self.base, self.root / "secret-does-not-exist.wav")
        self.assertEqual(2, invalid.returncode)
        self.assertNotIn("secret", invalid.stdout + invalid.stderr)
        self.assertNotIn(str(self.root), invalid.stdout + invalid.stderr)

    def test_cli_abstention_is_exit3_under_strict(self):
        wav(self.good, samples(quiet=True))
        run = self.cli(self.base, self.good, "--strict")
        self.assertEqual(3, run.returncode)
        self.assertIsNone(json.loads(run.stdout)["candidates"][0]["coarse_resolution_review"])

    def test_cli_parser_redacts_unknown_option_and_private_value(self):
        bad = self.cli(self.base, self.good, "--private-filename=secret")
        self.assertEqual(2, bad.returncode)
        self.assertNotIn("secret", bad.stdout + bad.stderr)


if __name__ == "__main__":
    unittest.main()
