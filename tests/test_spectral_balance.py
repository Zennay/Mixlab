"""Deterministic synthetic-only tests for the isolated ML-07 spectral proxy."""
from array import array
import json
import math
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.spectral import compare_spectral_balance, scan_spectral_proxy
import mixlab.quality.spectral as spectral


def make_wav(path, *, freq=100, gain=8000, rate=48000, channels=1, duration=0.25, width=2):
    frames = round(rate * duration)
    if width == 2:
        samples = array("h")
        for i in range(frames):
            sample = int(gain * math.sin(2 * math.pi * freq * i / rate))
            samples.extend([sample] * channels)
        if sys.byteorder != "little":
            samples.byteswap()
        raw = samples.tobytes()
    else:
        raw = bytes([128] * frames * channels)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(raw)


def make_segmented_wav(path, freqs, *, rate=48000, channels=1, gain=8000):
    # Exactly eight aligned intervals; transitions deliberately synthetic.
    frames_per_span = 6000
    samples = array("h")
    for segment, freq in enumerate(freqs):
        for offset in range(frames_per_span):
            frame = segment * frames_per_span + offset
            amplitude = int(gain * math.sin(2 * math.pi * freq * frame / rate))
            samples.extend([amplitude] * channels)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())


def make_stereo_split_wav(path, *, left_hz, right_hz, gain=8000, rate=48000):
    samples = array("h")
    for index in range(12000):
        samples.extend((
            int(gain * math.sin(2 * math.pi * left_hz * index / rate)),
            int(gain * math.sin(2 * math.pi * right_hz * index / rate)),
        ))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())


class SpectralBalanceTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.dir = Path(root.name)
        self.base = self.dir / "secret_base.wav"
        self.other = self.dir / "secret_candidate.wav"
        make_wav(self.base)
        make_wav(self.other)

    def report(self, **kwargs):
        return compare_spectral_balance(self.base, [self.other], **kwargs)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "mixlab.quality.spectral", *map(str, args)],
            text=True, capture_output=True, timeout=15
        )

    def test_independent_low_mid_high_sine_frequency_order(self):
        # Blind-to-implementation signal oracle: first-order proxies should
        # respond to deliberately distinct synthetic tone regions.
        ratios = []
        for frequency in (40, 600, 8000):
            make_wav(self.base, freq=frequency, rate=48000, duration=0.5)
            report = scan_spectral_proxy(self.base)
            ratios.append((
                report["lowpass_180_ratio"],
                report["midpass_180_2500_ratio"],
                report["highpass_2500_ratio"],
            ))
        self.assertGreater(ratios[0][0], ratios[1][0])
        self.assertGreater(ratios[1][0], ratios[2][0])
        self.assertGreater(ratios[1][1], ratios[0][1])
        self.assertGreater(ratios[1][1], ratios[2][1])
        self.assertLess(ratios[0][2], ratios[1][2])
        self.assertLess(ratios[1][2], ratios[2][2])

    def test_streaming_read_block_size_does_not_change_public_results(self):
        make_segmented_wav(self.base, [40, 200, 600, 1000, 2500, 4000, 6000, 8000])
        make_segmented_wav(self.other, [40, 200, 600, 1000, 2500, 4000, 6000, 8000])
        reference = self.report()
        for block in (1, 257, 4096, 8191):
            with self.subTest(block=block), patch.object(spectral, "READ_FRAMES", block):
                self.assertEqual(reference, self.report())
                self.assertEqual(reference["baseline"], scan_spectral_proxy(self.base))

    def test_public_scan_api_redacts_inode_timestamps_and_private_envelopes(self):
        public = scan_spectral_proxy(self.base)
        self.assertEqual({"sample_rate", "channels", "frames", "rms_dbfs",
                          "lowpass_180_ratio", "midpass_180_2500_ratio",
                          "highpass_2500_ratio"}, set(public))
        serialized = json.dumps(public, allow_nan=False)
        self.assertNotIn(str(self.dir), serialized)
        self.assertNotIn("_source", serialized)
        self.assertNotIn("_channels", serialized)
        self.assertNotIn("_spans", serialized)
        self.assertNotIn("inode", serialized)
        self.assertNotIn("mtime", serialized)
        self.assertNotIn("ctime", serialized)
        self.assertEqual(public, self.report()["baseline"])

    def test_public_scan_metrics_are_safe_at_chunk_and_sample_rate_edges(self):
        for rate in (8000, 44100, 96000):
            for frames in (1, 4095, 4096, 4097, 9003):
                with self.subTest(rate=rate, frames=frames):
                    make_wav(self.base, rate=rate, duration=frames / rate)
                    make_wav(self.other, rate=rate, duration=frames / rate)
                    public = scan_spectral_proxy(self.base)
                    self.assertEqual(frames, public["frames"])
                    self.assertEqual(rate, public["sample_rate"])
                    self.assertEqual(public, self.report()["baseline"])
                    self.assertEqual([], [
                        key for key in public if key.startswith("_")
                    ])
                    json.dumps(self.report(), allow_nan=False)

    def test_pcm16_extrema_have_finite_safe_public_ratios(self):
        samples = array("h", [-32768, 32767, 0, -32768, 32767] * 2000)
        if sys.byteorder != "little":
            samples.byteswap()
        for path in (self.base, self.other):
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(samples.tobytes())
        report = self.report()
        self.assertEqual(report["baseline"], report["candidates"][0]["metrics"])
        for field in ("lowpass_180_ratio", "midpass_180_2500_ratio", "highpass_2500_ratio"):
            self.assertTrue(math.isfinite(report["baseline"][field]))
        json.dumps(report, allow_nan=False)

    def test_equal_pcm_has_equal_proxies_and_no_warning(self):
        before = self.base.read_bytes(), self.other.read_bytes()
        result = self.report()
        row = result["candidates"][0]
        self.assertEqual([], row["warnings"])
        self.assertAlmostEqual(0, row["low_proxy_delta_db"], places=6)
        self.assertAlmostEqual(0, row["high_proxy_delta_db"], places=6)
        self.assertTrue(result["human_preference_test_required"])
        self.assertEqual(before, (self.base.read_bytes(), self.other.read_bytes()))
        self.assertNotIn(str(self.dir), json.dumps(result))

    def test_equal_rms_low_to_high_sine_flags_both_band_proxies(self):
        make_wav(self.other, freq=5000)
        result = self.report()
        row = result["candidates"][0]
        self.assertLess(row["low_proxy_delta_db"], -6)
        self.assertGreater(row["high_proxy_delta_db"], 6)
        self.assertIn("low_spectral_balance_shift_inspect", row["warnings"])
        self.assertIn("high_spectral_balance_shift_inspect", row["warnings"])
        self.assertAlmostEqual(
            result["baseline"]["rms_dbfs"], row["metrics"]["rms_dbfs"], delta=0.1
        )

    def test_midrange_loss_triggers_even_with_matched_pcm_rms(self):
        make_wav(self.base, freq=1000)
        make_wav(self.other, freq=30)
        result = self.report()
        row = result["candidates"][0]
        self.assertAlmostEqual(result["baseline"]["rms_dbfs"], row["metrics"]["rms_dbfs"], delta=0.2)
        self.assertLess(row["mid_proxy_delta_db"], -6)
        self.assertIn("mid_spectral_balance_shift_inspect", row["warnings"])
        self.assertIsNotNone(result["baseline"]["midpass_180_2500_ratio"])
        self.assertNotIn(str(self.base), json.dumps(result))

    def test_gain_only_keeps_spectral_ratios_but_flags_volume_bias(self):
        make_wav(self.other, gain=6000)
        row = self.report()["candidates"][0]
        self.assertIn("rms_level_mismatch_inspect_not_lufs", row["warnings"])
        self.assertLess(row["rms_delta_db_vs_baseline"], -1.5)
        self.assertFalse(any("spectral_balance_shift" in item for item in row["warnings"]))
        self.assertAlmostEqual(row["low_proxy_delta_db"], 0, delta=0.02)
        self.assertAlmostEqual(row["high_proxy_delta_db"], 0, delta=0.02)
        self.assertAlmostEqual(row["mid_proxy_delta_db"], 0, delta=0.02)

    def test_small_gain_change_is_not_a_technical_rms_confound(self):
        make_wav(self.other, gain=7500)
        row = self.report()["candidates"][0]
        self.assertAlmostEqual(row["rms_delta_db_vs_baseline"], -0.56, delta=0.03)
        self.assertNotIn("rms_level_mismatch_inspect_not_lufs", row["warnings"])

    def test_positive_gain_confound_is_symmetric_and_cli_strict(self):
        make_wav(self.other, gain=12000)
        report = self.report()
        row = report["candidates"][0]
        self.assertGreater(row["rms_delta_db_vs_baseline"], 1.5)
        self.assertIn("rms_level_mismatch_inspect_not_lufs", row["warnings"])
        strict = self.cli(self.base, self.other, "--fail-on-warnings")
        self.assertEqual(2, strict.returncode, strict.stderr)
        self.assertNotIn(str(self.dir), strict.stdout + strict.stderr)
        reverse = compare_spectral_balance(self.other, [self.base])
        self.assertAlmostEqual(
            row["rms_delta_db_vs_baseline"],
            -reverse["candidates"][0]["rms_delta_db_vs_baseline"],
            delta=0.001
        )
        self.assertIn("rms_level_mismatch_inspect_not_lufs", reverse["candidates"][0]["warnings"])

    def test_rms_confound_threshold_is_decided_on_unrounded_signal_energy(self):
        # 9500/8000 is below +1.5 dB; 9530/8000 is above.
        # This is independent of the different spectrogram 6 dB threshold.
        make_wav(self.other, gain=9500)
        lower = self.report()["candidates"][0]
        self.assertLess(lower["rms_delta_db_vs_baseline"], 1.5)
        self.assertNotIn("rms_level_mismatch_inspect_not_lufs", lower["warnings"])
        make_wav(self.other, gain=9530)
        upper = self.report()["candidates"][0]
        self.assertGreater(upper["rms_delta_db_vs_baseline"], 1.5)
        self.assertIn("rms_level_mismatch_inspect_not_lufs", upper["warnings"])

    def test_55db_audibility_gate_consistent_across_sample_rates(self):
        # A 90-LSB sine has > -55dBFS RMS, 80 LSB falls below it.
        for rate in (8000, 48000, 96000):
            with self.subTest(rate=rate):
                make_wav(self.base, gain=90, rate=rate)
                make_wav(self.other, gain=80, rate=rate)
                report = self.report()
                row = report["candidates"][0]
                self.assertEqual(1.0, row["temporal_audibility_mismatch_fraction"])
                self.assertIn("temporal_audibility_alignment_inspect", row["warnings"])
                self.assertIn("insufficient_audible_energy_for_spectral_comparison", row["warnings"])
                self.assertIsNone(row["rms_delta_db_vs_baseline"])
                self.assertNotIn(str(self.dir), json.dumps(report))

    def test_silent_level_delta_is_undefined_not_fabricated(self):
        make_wav(self.other, gain=0)
        row = self.report()["candidates"][0]
        self.assertIsNone(row["rms_delta_db_vs_baseline"])
        self.assertIn("insufficient_audible_energy_for_spectral_comparison", row["warnings"])


    def test_stereo_and_channel_order_are_symmetric(self):
        make_wav(self.base, freq=400, channels=2)
        make_wav(self.other, freq=400, channels=2)
        row = self.report()["candidates"][0]
        self.assertEqual(2, row["metrics"]["channels"])
        self.assertEqual([], row["warnings"])
        make_wav(self.other, freq=4000, channels=2)
        row = self.report()["candidates"][0]
        self.assertIn("high_spectral_balance_shift_inspect", row["warnings"])

    def test_stereo_near_silent_channel_is_not_false_clean(self):
        make_wav(self.base, freq=1000, channels=2)
        make_stereo_split_wav(self.other, left_hz=0, right_hz=1000)
        row = self.report()["candidates"][0]
        self.assertIn("stereo_channel_near_silence_inspect", row["warnings"])
        self.assertNotIn(str(self.other), json.dumps(row))
        # Reversal must also warn: a broken baseline invalidates a blind
        # comparison even when the candidate's two channels are healthy.
        make_stereo_split_wav(self.base, left_hz=0, right_hz=1000)
        make_wav(self.other, freq=1000, channels=2)
        self.assertIn("stereo_channel_near_silence_inspect", self.report()["candidates"][0]["warnings"])

    def test_identical_one_channel_loss_is_still_inspect_not_clean(self):
        make_stereo_split_wav(self.base, left_hz=0, right_hz=1000)
        make_stereo_split_wav(self.other, left_hz=0, right_hz=1000)
        row = self.report()["candidates"][0]
        self.assertIn("stereo_channel_near_silence_inspect", row["warnings"])
        strict = self.cli(self.base, self.other, "--fail-on-warnings")
        self.assertEqual(2, strict.returncode, strict.stderr)
        self.assertNotIn(str(self.dir), strict.stdout + strict.stderr)

    def test_regular_stereo_and_mono_do_not_get_channel_silence_warning(self):
        row = self.report()["candidates"][0]
        self.assertNotIn("stereo_channel_near_silence_inspect", row["warnings"])
        make_wav(self.base, freq=1000, channels=2)
        make_wav(self.other, freq=1000, channels=2)
        self.assertNotIn("stereo_channel_near_silence_inspect", self.report()["candidates"][0]["warnings"])

    def test_channel_swapped_stereo_can_hide_all_global_spectral_changes(self):
        make_stereo_split_wav(self.base, left_hz=100, right_hz=5000)
        make_stereo_split_wav(self.other, left_hz=5000, right_hz=100)
        report = self.report()
        row = report["candidates"][0]
        # Overall stereo energies are the same despite different placement.
        for name in ("low", "mid", "high"):
            self.assertAlmostEqual(0.0, row[name + "_proxy_delta_db"], delta=0.01)
        self.assertTrue(row["stereo_channel_low_spectral_shift_risk"])
        self.assertTrue(row["stereo_channel_high_spectral_shift_risk"])
        self.assertIn("stereo_channel_low_spectral_shift_inspect", row["warnings"])
        self.assertIn("stereo_channel_high_spectral_shift_inspect", row["warnings"])
        anonymous = json.dumps(report)
        self.assertNotIn(str(self.dir), anonymous)
        self.assertNotIn("_channels", anonymous)
        self.assertNotIn("left_hz", anonymous)

    def test_stereo_gain_change_does_not_create_channel_spectral_alarm(self):
        make_stereo_split_wav(self.base, left_hz=100, right_hz=5000)
        make_stereo_split_wav(self.other, left_hz=100, right_hz=5000, gain=6000)
        row = self.report()["candidates"][0]
        for name in ("low", "mid", "high"):
            self.assertFalse(row["stereo_channel_" + name + "_spectral_shift_risk"])
        self.assertFalse(any("stereo_channel_" in item for item in row["warnings"]))

    def test_mono_report_has_no_implied_stereo_channel_evidence(self):
        row = self.report()["candidates"][0]
        for name in ("low", "mid", "high"):
            self.assertNotIn("stereo_channel_" + name + "_spectral_shift_risk", row)

    def test_two_candidates_get_only_opaque_ids(self):
        third = self.dir / "SECRET_THIRD.wav"
        make_wav(third, freq=5000)
        report = compare_spectral_balance(self.base, [self.other, third])
        self.assertEqual(["candidate-01", "candidate-02"],
                         [x["id"] for x in report["candidates"]])
        out = json.dumps(report)
        for item in (str(self.dir), self.base.name, self.other.name, third.name):
            self.assertNotIn(item, out)

    def test_same_inode_baseline_and_hardlink_candidates_flag_blind_noop(self):
        alias = self.dir / "PRIVATE_HARDLINK.wav"
        os.link(self.base, alias)
        report = compare_spectral_balance(self.base, [self.base, alias])
        for row in report["candidates"]:
            self.assertIn("same_input_file_inspect_for_blind_noop", row["warnings"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.dir), serialized)
        self.assertNotIn("PRIVATE_HARDLINK", serialized)
        self.assertNotIn("_source_key", serialized)
        strict = self.cli(self.base, alias, "--fail-on-warnings")
        self.assertEqual(2, strict.returncode, strict.stderr)
        self.assertIn("same_input_file_inspect_for_blind_noop", strict.stdout)
        self.assertNotIn(str(self.dir), strict.stdout + strict.stderr)

    def test_concurrent_candidate_path_replacement_fails_closed(self):
        # Baseline uses three 4096-frame reads. Replace the candidate name
        # during its first read; its existing FD still points to OLD PCM.
        replacement = self.dir / "new_private.wav"
        make_wav(replacement, freq=5000)
        original = wave.Wave_read.readframes
        reads = []

        def replace_during_read(reader, count):
            reads.append(count)
            if len(reads) == 4:
                os.replace(replacement, self.other)
            return original(reader, count)

        with patch.object(wave.Wave_read, "readframes", replace_during_read):
            with self.assertRaisesRegex(ValueError, "changed while being inspected"):
                self.report()
        self.assertEqual(6, len(reads))
        self.assertEqual(12000, scan_spectral_proxy(self.other)["frames"])

    def test_concurrent_candidate_unlink_fails_closed(self):
        original = wave.Wave_read.readframes
        reads = []

        def unlink_during_read(reader, count):
            reads.append(count)
            if len(reads) == 4:
                self.other.unlink()
            return original(reader, count)

        with patch.object(wave.Wave_read, "readframes", unlink_during_read):
            with self.assertRaisesRegex(ValueError, "changed while being inspected"):
                self.report()
        self.assertEqual(6, len(reads))
        self.assertFalse(self.other.exists())

    def test_baseline_mutated_after_its_scan_rejects_entire_report(self):
        original = wave.Wave_read.readframes
        reads = []

        def mutate_early_baseline(reader, count):
            reads.append(count)
            # The fourth read is the first candidate's PCM block.
            if len(reads) == 4:
                replacement = self.dir / "REPLACEMENT_PRIVATE.wav"
                make_wav(replacement, freq=5000)
                os.replace(replacement, self.base)
            return original(reader, count)

        with patch.object(wave.Wave_read, "readframes", mutate_early_baseline):
            with self.assertRaisesRegex(ValueError, "A/B input changed"):
                self.report()
        self.assertEqual(6, len(reads))

    def test_first_candidate_mutated_during_second_candidate_is_rejected(self):
        third = self.dir / "PRIVATE_THIRD.wav"
        make_wav(third)
        original = wave.Wave_read.readframes
        reads = []

        def mutate_early_candidate(reader, count):
            reads.append(count)
            # First candidate completed at read six; the first PCM block
            # of candidate two replaces its earlier sibling's pathname.
            if len(reads) == 7:
                replacement = self.dir / "REPLACEMENT_PRIVATE.wav"
                make_wav(replacement, freq=5000)
                os.replace(replacement, self.other)
            return original(reader, count)

        with patch.object(wave.Wave_read, "readframes", mutate_early_candidate):
            with self.assertRaisesRegex(ValueError, "A/B input changed"):
                compare_spectral_balance(self.base, [self.other, third])
        self.assertEqual(9, len(reads))

    def test_final_snapshot_rejects_delayed_symlink_substitution(self):
        other_backup = self.dir / "PRIVATE_OLD.wav"
        original = wave.Wave_read.readframes
        reads = []

        def substitute_finished_baseline(reader, count):
            reads.append(count)
            if len(reads) == 4:
                self.base.rename(other_backup)
                self.base.symlink_to(other_backup)
            return original(reader, count)

        with patch.object(wave.Wave_read, "readframes", substitute_finished_baseline):
            with self.assertRaisesRegex(ValueError, "A/B input changed"):
                self.report()

    def test_silence_is_never_misrepresented_as_comparable(self):
        make_wav(self.other, gain=0)
        row = self.report()["candidates"][0]
        self.assertIn("insufficient_audible_energy_for_spectral_comparison", row["warnings"])
        self.assertIsNone(row["low_proxy_delta_db"])
        self.assertIsNone(row["high_proxy_delta_db"])
        make_wav(self.base, gain=0)
        self.assertTrue(self.report()["candidates"][0]["warnings"])

    def test_format_mismatches_fail_closed(self):
        for kwargs in ({"rate": 44100}, {"channels": 2}, {"duration": 0.3}):
            make_wav(self.other, **kwargs)
            with self.assertRaises(ValueError):
                self.report()
        make_wav(self.other, width=1)
        with self.assertRaises(ValueError):
            self.report()

    def test_mismatched_candidate_header_is_rejected_before_pcm_decoding(self):
        expected = (48000, 1, 12000)
        original = wave.Wave_read.readframes
        for kwargs in ({"rate": 44100}, {"channels": 2}, {"duration": 0.3}):
            with self.subTest(kwargs=kwargs):
                make_wav(self.other, **kwargs)
                baseline_reads = []

                def reject_candidate_pcm(reader, nframes):
                    fmt = (reader.getframerate(), reader.getnchannels(), reader.getnframes())
                    if fmt != expected:
                        raise AssertionError("mismatched candidate PCM was decoded")
                    baseline_reads.append(nframes)
                    return original(reader, nframes)

                with patch.object(wave.Wave_read, "readframes", reject_candidate_pcm):
                    with self.assertRaises(ValueError):
                        self.report()
                self.assertTrue(baseline_reads)
        with patch.object(wave.Wave_read, "readframes", side_effect=AssertionError("PCM decoded")):
            with self.assertRaises(ValueError):
                scan_spectral_proxy(self.base, expected_format=(48000, 2, 12000))

    def test_reject_unbounded_and_malformed_thresholds(self):
        for value in (float("nan"), float("inf"), -1, 0, 25, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.report(threshold_db=value)
        with self.assertRaises(ValueError):
            compare_spectral_balance(self.base, [])
        with self.assertRaises(ValueError):
            compare_spectral_balance(self.base, [self.other] * 9)

    def test_nonregular_inputs_and_truncated_audio_do_not_block(self):
        fifo = self.dir / "SECRET_FIFO"
        if hasattr(os, "mkfifo"):
            os.mkfifo(fifo)
            with self.assertRaises((ValueError, OSError)):
                scan_spectral_proxy(fifo)
        symlink = self.dir / "SECRET_SYMLINK"
        symlink.symlink_to(self.base)
        with self.assertRaises((ValueError, OSError)):
            scan_spectral_proxy(symlink)
        make_wav(self.other)
        self.other.write_bytes(self.other.read_bytes()[:-2])
        with self.assertRaises((ValueError, wave.Error)):
            self.report()

    def test_per_source_frame_budget_is_checked_before_pcm_reads(self):
        with self.assertRaises(ValueError):
            scan_spectral_proxy(self.base, max_frames=11999)
        for budget in (0, True, -1, 2_000_001):
            with self.assertRaises(ValueError):
                scan_spectral_proxy(self.base, max_frames=budget)

    def test_aggregate_frame_budget_is_enforced_before_extra_pcm(self):
        before = self.base.read_bytes(), self.other.read_bytes()
        calls = []
        original = wave.Wave_read.readframes

        def traced(source, count):
            calls.append(count)
            return original(source, count)

        # 12000 baseline + 12000 first candidate leave one frame;
        # the next candidate must fail at header admission, not PCM scan.
        with patch.object(spectral, "MAX_AGGREGATE_FRAMES", 24001):
            with patch.object(wave.Wave_read, "readframes", traced):
                with self.assertRaises(ValueError):
                    compare_spectral_balance(self.base, [self.other, self.other])
        self.assertEqual(6, len(calls))
        self.assertEqual(before, (self.base.read_bytes(), self.other.read_bytes()))

    def test_swapped_spectral_halves_are_detected_despite_matched_global_ratios(self):
        base_frequencies = [100] * 4 + [5000] * 4
        make_segmented_wav(self.base, base_frequencies)
        make_segmented_wav(self.other, base_frequencies[::-1])
        report = self.report()
        row = report["candidates"][0]
        # A whole-file signature is nearly the same even though the segments
        # have been swapped: this is a *temporal* A/B confound.
        self.assertLess(abs(row["low_proxy_delta_db"]), 6)
        self.assertLess(abs(row["high_proxy_delta_db"]), 6)
        self.assertGreaterEqual(row["temporal_low_proxy_mismatch_fraction"], 0.25)
        self.assertGreaterEqual(row["temporal_high_proxy_mismatch_fraction"], 0.25)
        self.assertIn("low_temporal_spectral_shift_inspect", row["warnings"])
        self.assertIn("high_temporal_spectral_shift_inspect", row["warnings"])
        serialized = json.dumps(report)
        self.assertNotIn("spectral_spans", serialized)
        self.assertNotIn("_spans", serialized)
        self.assertNotIn(str(self.dir), serialized)

    def test_temporal_midrange_rearrangement_is_flagged(self):
        make_segmented_wav(self.base, [1000] * 4 + [30] * 4)
        make_segmented_wav(self.other, [30] * 4 + [1000] * 4)
        row = self.report()["candidates"][0]
        self.assertGreaterEqual(row["temporal_mid_proxy_mismatch_fraction"], 0.25)
        self.assertIn("mid_temporal_spectral_shift_inspect", row["warnings"])
        self.assertIsInstance(row["temporal_mid_proxy_mismatch_fraction"], float)

    def test_disjoint_audio_halves_do_not_appear_spectrally_comparable(self):
        make_segmented_wav(self.base, [100] * 4 + [0] * 4)
        make_segmented_wav(self.other, [0] * 4 + [100] * 4)
        report = self.report()
        row = report["candidates"][0]
        self.assertAlmostEqual(0, row["low_proxy_delta_db"], delta=0.5)
        self.assertEqual(1.0, row["temporal_audibility_mismatch_fraction"])
        self.assertIn("temporal_audibility_alignment_inspect", row["warnings"])
        self.assertIn("insufficient_temporal_spectral_coverage_inspect", row["warnings"])
        for band in ("low", "mid", "high"):
            self.assertIsNone(row["temporal_" + band + "_proxy_mismatch_fraction"])
        self.assertNotIn("_spans", json.dumps(report))
        self.assertNotIn(str(self.dir), json.dumps(report))

    def test_equal_aligned_partial_silence_has_enough_coverage(self):
        make_segmented_wav(self.base, [100] * 4 + [0] * 4)
        make_segmented_wav(self.other, [100] * 4 + [0] * 4)
        row = self.report()["candidates"][0]
        self.assertEqual(0.0, row["temporal_audibility_mismatch_fraction"])
        self.assertNotIn("temporal_audibility_alignment_inspect", row["warnings"])
        self.assertNotIn("insufficient_temporal_spectral_coverage_inspect", row["warnings"])
        self.assertEqual(0.0, row["temporal_low_proxy_mismatch_fraction"])

    def test_sparse_same_span_audio_cannot_claim_temporal_spectral_proof(self):
        make_segmented_wav(self.base, [100] + [0] * 7)
        make_segmented_wav(self.other, [100] + [0] * 7)
        row = self.report()["candidates"][0]
        self.assertEqual(0.0, row["temporal_audibility_mismatch_fraction"])
        self.assertIn("insufficient_temporal_spectral_coverage_inspect", row["warnings"])
        for band in ("low", "mid", "high"):
            self.assertIsNone(row["temporal_" + band + "_proxy_mismatch_fraction"])

    def test_one_changed_audible_span_reports_alignment_not_coordinates(self):
        make_segmented_wav(self.base, [100] * 5 + [0] * 3, channels=2)
        make_segmented_wav(self.other, [100] * 4 + [0] * 4, channels=2)
        report = self.report()
        row = report["candidates"][0]
        self.assertEqual(0.125, row["temporal_audibility_mismatch_fraction"])
        self.assertIn("temporal_audibility_alignment_inspect", row["warnings"])
        self.assertNotIn("insufficient_temporal_spectral_coverage_inspect", row["warnings"])
        self.assertNotIn("span_energy", json.dumps(report))
        strict = self.cli(self.base, self.other, "--fail-on-warnings")
        self.assertEqual(2, strict.returncode, strict.stderr)
        self.assertNotIn(str(self.dir), strict.stdout + strict.stderr)

    def test_one_short_spectral_change_does_not_trigger_persistent_bias(self):
        make_segmented_wav(self.base, [100] * 8)
        make_segmented_wav(self.other, [5000] + [100] * 7)
        row = self.report()["candidates"][0]
        self.assertLess(row["temporal_low_proxy_mismatch_fraction"], 0.25)
        self.assertNotIn("low_temporal_spectral_shift_inspect", row["warnings"])
        self.assertNotIn("high_temporal_spectral_shift_inspect", row["warnings"])

    def test_temporal_proxy_is_gain_invariant_and_works_on_stereo(self):
        make_segmented_wav(self.base, [200, 250, 300, 350] * 2, channels=2)
        make_segmented_wav(self.other, [200, 250, 300, 350] * 2, channels=2, gain=6000)
        row = self.report()["candidates"][0]
        self.assertEqual(0.0, row["temporal_low_proxy_mismatch_fraction"])
        self.assertEqual(0.0, row["temporal_high_proxy_mismatch_fraction"])
        self.assertEqual(0.0, row["temporal_mid_proxy_mismatch_fraction"])
        self.assertNotIn("low_temporal_spectral_shift_inspect", row["warnings"])

    def test_silent_segments_have_no_fake_zero_db_temporal_evidence(self):
        make_wav(self.other, gain=0)
        row = self.report()["candidates"][0]
        self.assertIsNone(row["temporal_low_proxy_mismatch_fraction"])
        self.assertIsNone(row["temporal_high_proxy_mismatch_fraction"])
        self.assertIsNone(row["temporal_mid_proxy_mismatch_fraction"])
        self.assertIn("insufficient_audible_energy_for_spectral_comparison", row["warnings"])

    def test_cli_output_status_and_argument_privacy(self):
        clean = self.cli(self.base, self.other)
        self.assertEqual(0, clean.returncode, clean.stderr)
        report = json.loads(clean.stdout)
        self.assertEqual([], report["candidates"][0]["warnings"])
        for secret in (str(self.base), str(self.other), str(self.dir)):
            self.assertNotIn(secret, clean.stdout + clean.stderr)
        make_wav(self.other, freq=5000)
        flagged = self.cli(self.base, self.other, "--fail-on-warnings")
        self.assertEqual(2, flagged.returncode, flagged.stderr)
        self.assertTrue(json.loads(flagged.stdout)["candidates"][0]["warnings"])
        canary = "/private/PRIVATE_CANARY_VALUE"
        for params, code in (
            ((self.base, self.other, "--threshold-db", canary), 2),
            ((self.base, self.other, "--unknown=" + canary), 2),
            ((self.base, self.other, "--threshold-db", "nan"), 3),
            ((self.base, canary), 3),
        ):
            response = self.cli(*params)
            self.assertEqual(code, response.returncode, response.stderr)
            self.assertNotIn(canary, response.stdout + response.stderr)
            self.assertEqual("", response.stdout)


if __name__ == "__main__":
    unittest.main()
