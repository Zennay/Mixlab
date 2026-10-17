"""Synthetic, rights-free local DC-bias evidence (never real music)."""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

from mixlab.quality import local_dc


RATE = 8000
DURATION = 4


def _wav(path: Path, *, channels=1, rate=RATE, duration=DURATION, offsets=None, amplitude=700):
    frames = int(rate * duration)
    if offsets is None:
        offsets = [[0] * frames for _ in range(channels)]
    pcm = bytearray()
    for i in range(frames):
        sine = round(amplitude * math.sin(2 * math.pi * 440 * i / rate))
        for c in range(channels):
            pcm += struct.pack("<h", sine + offsets[c][i])
    with wave.open(str(path), "wb") as dest:
        dest.setnchannels(channels)
        dest.setsampwidth(2)
        dest.setframerate(rate)
        dest.writeframes(pcm)


def _offset_sections(levels, *, rate=RATE):
    return [v for level in levels for v in [level] * rate]


class LocalDCQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "baseline.wav"
        self.alt = Path(self.tmp.name) / "candidate.wav"

    def _batch_candidate(self, index: int, *, offset: int = 0, duration=4, rate=RATE) -> Path:
        path = Path(self.tmp.name) / f"choice-{index:03d}.wav"
        _wav(path, duration=duration, rate=rate,
             offsets=[[offset] * int(rate * duration)])
        return path

    def _append_riff_chunks(self, path: Path, chunks: bytes):
        original = bytearray(path.read_bytes())
        original.extend(chunks)
        struct.pack_into("<I", original, 4, len(original) - 8)
        path.write_bytes(original)

    def _assert_riff_rejected_before_pcm(self):
        # Both admissions must reject before opening the PCM stream.
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM already decoded")):
            with self.assertRaises(ValueError):
                local_dc.inspect(self.base, self.alt)
            with self.assertRaises(ValueError):
                local_dc.inspect_batch(self.base, [self.alt])

    def test_duplicate_data_chunk_rejected_even_when_total_size_valid(self):
        _wav(self.base)
        _wav(self.alt)
        self._append_riff_chunks(self.alt, b"data" + struct.pack("<I", 4) + b"abcd")
        self._assert_riff_rejected_before_pcm()

    def test_duplicate_fmt_chunk_rejected_even_when_total_size_valid(self):
        _wav(self.base)
        _wav(self.alt)
        # Known minimal PCM16 fmt chunk; physically accounted for in RIFF.
        extra_fmt = b"fmt " + struct.pack("<I", 16)
        extra_fmt += struct.pack("<HHIIHH", 1, 1, RATE, RATE * 2, 2, 16)
        self._append_riff_chunks(self.alt, extra_fmt)
        self._assert_riff_rejected_before_pcm()

    def test_overlong_trailing_chunk_rejected_even_when_outer_size_valid(self):
        _wav(self.base)
        _wav(self.alt)
        self._append_riff_chunks(self.alt, b"JUNK" + struct.pack("<I", 9000) + b"abc")
        self._assert_riff_rejected_before_pcm()

    def test_orphan_trailing_bytes_rejected_even_when_outer_size_valid(self):
        _wav(self.base)
        _wav(self.alt)
        self._append_riff_chunks(self.alt, b"DEAD")  # too short for a chunk header
        self._assert_riff_rejected_before_pcm()

    def test_missing_data_chunk_rejected_before_pcm(self):
        _wav(self.base)
        _wav(self.alt)
        payload = bytearray(self.alt.read_bytes())
        self.assertEqual(payload[36:40], b"data")
        payload[36:40] = b"JUNK"
        self.alt.write_bytes(payload)
        self._assert_riff_rejected_before_pcm()

    def test_frame_misaligned_data_chunk_rejected_before_pcm(self):
        _wav(self.base)
        _wav(self.alt)
        payload = bytearray(self.alt.read_bytes())
        frames_as_bytes = struct.unpack_from("<I", payload, 40)[0]
        # Valid RIFF framing, but PCM data now has one extra sample byte and
        # a required RIFF alignment pad. This is not a whole PCM16 frame.
        struct.pack_into("<I", payload, 40, frames_as_bytes + 1)
        payload.extend(b"\x01\x00")
        struct.pack_into("<I", payload, 4, len(payload) - 8)
        self.alt.write_bytes(payload)
        self._assert_riff_rejected_before_pcm()

    def test_exactly_1024_riff_chunk_headers_are_admitted(self):
        _wav(self.base)
        _wav(self.alt)
        # Canonical WAV has fmt+data; 1,022 optional empty chunks is exactly
        # the public 1,024-header cap. There must not be an off-by-one veto.
        self._append_riff_chunks(self.alt, (b"JUNK" + struct.pack("<I", 0)) * 1022)
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)
        self.assertIs(local_dc.inspect_batch(self.base, [self.alt])["warning"], False)

    def test_1025_riff_chunk_headers_rejected_before_pcm(self):
        _wav(self.base)
        _wav(self.alt)
        self._append_riff_chunks(self.alt, (b"JUNK" + struct.pack("<I", 0)) * 1023)
        self._assert_riff_rejected_before_pcm()

    def test_more_than_thousand_riff_chunks_rejected_with_bounded_headers(self):
        _wav(self.base)
        _wav(self.alt)
        self._append_riff_chunks(self.alt, (b"JUNK" + struct.pack("<I", 0)) * 1026)
        self._assert_riff_rejected_before_pcm()

    def test_valid_metadata_chunk_before_fmt_is_accepted(self):
        _wav(self.base)
        _wav(self.alt)
        payload = bytearray(self.alt.read_bytes())
        # Metadata can legally precede the fmt chunk. Keep all RIFF sizes
        # consistent and verify both read-only paths still scan the samples.
        payload[12:12] = b"JUNK" + struct.pack("<I", 4) + b"ABCD"
        struct.pack_into("<I", payload, 4, len(payload) - 8)
        self.alt.write_bytes(payload)
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)
        self.assertIs(local_dc.inspect_batch(self.base, [self.alt])["warning"], False)

    def test_data_before_fmt_chunk_rejected_before_any_pcm_decoding(self):
        _wav(self.base)
        _wav(self.alt)
        original = self.alt.read_bytes()
        self.assertEqual(original[12:16], b"fmt ")
        self.assertEqual(original[36:40], b"data")
        # RIFF outer length and both inner chunk sizes remain intact, but
        # their order becomes invalid: the PCM data precedes its format.
        swapped = original[:12] + original[36:] + original[12:36]
        self.alt.write_bytes(swapped)
        self._assert_riff_rejected_before_pcm()

    def test_odd_sized_valid_metadata_chunk_is_accepted(self):
        _wav(self.base)
        _wav(self.alt)
        # Exactly one odd-sized JUNK payload plus its required pad.
        self._append_riff_chunks(self.alt, b"JUNK" + struct.pack("<I", 3) + b"abc\x00")
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)
        self.assertIs(local_dc.inspect_batch(self.base, [self.alt])["warning"], False)

    def test_riff_unclaimed_trailing_data_rejected_before_decode(self):
        _wav(self.base)
        _wav(self.alt)
        with self.alt.open("ab") as f:
            f.write(b"PRIVATE-GARBAGE")
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM already decoded")):
            with self.assertRaisesRegex(ValueError, "RIFF size"):
                local_dc.inspect(self.base, self.alt)
            with self.assertRaisesRegex(ValueError, "RIFF size"):
                local_dc.inspect_batch(self.base, [self.alt])

    def test_forged_short_and_long_riff_size_rejected_before_decode(self):
        _wav(self.base)
        for adjustment in (-4, 4):
            _wav(self.alt)
            payload = bytearray(self.alt.read_bytes())
            original_length = struct.unpack_from("<I", payload, 4)[0]
            struct.pack_into("<I", payload, 4, original_length + adjustment)
            self.alt.write_bytes(payload)
            with mock.patch.object(local_dc, "_scan_private_pcm",
                                   side_effect=AssertionError("PCM already decoded")):
                with self.assertRaisesRegex(ValueError, "RIFF size"):
                    local_dc.inspect(self.base, self.alt)
                with self.assertRaisesRegex(ValueError, "RIFF size"):
                    local_dc.inspect_batch(self.base, [self.alt])

    def test_valid_extra_non_audio_riff_chunk_is_still_allowed(self):
        _wav(self.base)
        _wav(self.alt)
        # Non-audio chunk is part of the container when RIFF.size includes
        # its bytes, rather than being an unclaimed trailing suffix.
        with self.alt.open("ab") as f:
            f.write(b"JUNK" + struct.pack("<I", 4) + b"ABCD")
        content = bytearray(self.alt.read_bytes())
        struct.pack_into("<I", content, 4, len(content) - 8)
        self.alt.write_bytes(content)
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)
        self.assertIs(local_dc.inspect_batch(self.base, [self.alt])["warning"], False)

    def test_failed_riff_admission_emits_no_private_path_from_cli(self):
        _wav(self.base)
        _wav(self.alt)
        with self.alt.open("ab") as f:
            f.write(b"PRIVATE-GARBAGE")
        for extra in ([], ["--batch"]):
            cmd = [sys.executable, "-m", "mixlab.quality.local_dc",
                   str(self.base), str(self.alt), *extra]
            done = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
            self.assertEqual(done.returncode, 3)
            self.assertEqual(done.stdout, "")
            self.assertNotIn(str(self.tmp.name), done.stderr)

    def test_single_alias_rejected_before_any_pcm_decode(self):
        _wav(self.base)
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM decoded")):
            with self.assertRaisesRegex(ValueError, "distinct regular files"):
                local_dc.inspect(self.base, self.base)

    def test_single_hardlink_rejected_before_any_pcm_decode(self):
        _wav(self.base)
        os.link(self.base, self.alt)
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM decoded")):
            with self.assertRaisesRegex(ValueError, "distinct regular files"):
                local_dc.inspect(self.base, self.alt)

    def test_single_shape_mismatch_rejected_before_any_pcm_decode(self):
        _wav(self.base)
        _wav(self.alt, duration=2)
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM decoded")):
            with self.assertRaisesRegex(ValueError, "identical shape"):
                local_dc.inspect(self.base, self.alt)

    def test_single_corrupted_header_rejected_before_any_pcm_decode(self):
        _wav(self.base)
        self.alt.write_bytes(b"RIFF" + b"X" * 50)
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM decoded")):
            with self.assertRaises(ValueError):
                local_dc.inspect(self.base, self.alt)

    def test_single_source_replaced_after_admission_rejected(self):
        _wav(self.base)
        _wav(self.alt)
        original = local_dc._admit_batch
        def replace_after_admission(sources):
            receipt = original(sources)
            self.base.unlink()
            _wav(self.base)
            return receipt
        with mock.patch.object(local_dc, "_admit_batch", side_effect=replace_after_admission):
            with self.assertRaises(ValueError):
                local_dc.inspect(self.base, self.alt)

    def test_batch_real_eight_million_frame_aggregate_ceiling(self):
        # Eight independent 1M-frame PCM16 mono WAVs, no fabricated nframes.
        # This exercises the full 8M-frame admission and bounded scanner.
        sources = [self.base] + [
            Path(self.tmp.name) / f"bounded-{i:03d}.wav" for i in range(7)
        ]
        def create_real_wavs(frame_count):
            payload = bytes(frame_count * 2)
            for path in sources:
                with wave.open(str(path), "wb") as writer:
                    writer.setnchannels(1)
                    writer.setsampwidth(2)
                    writer.setframerate(8000)
                    writer.writeframes(payload)
        create_real_wavs(1_000_000)
        output = local_dc.inspect_batch(sources[0], sources[1:])
        self.assertEqual(output["candidate_count"], 7)
        self.assertEqual(output["frames"], 1_000_000)
        self.assertIs(output["warning"], False)
        create_real_wavs(1_000_001)
        with mock.patch.object(local_dc, "_scan_private_pcm",
                               side_effect=AssertionError("PCM decoded over limit")):
            with self.assertRaisesRegex(ValueError, "resource admission"):
                local_dc.inspect_batch(sources[0], sources[1:])

    def test_batch_two_candidates_are_anon_and_ordered(self):
        _wav(self.base)
        first = self._batch_candidate(1, offset=3400)
        second = self._batch_candidate(2)
        result = local_dc.inspect_batch(self.base, [first, second])
        self.assertEqual([r["candidate_id"] for r in result["candidates"]],
                         ["candidate-001", "candidate-002"])
        self.assertEqual([r["warning"] for r in result["candidates"]], [True, False])
        self.assertIs(result["warning"], True)
        self.assertNotIn(str(self.tmp.name), json.dumps(result))
        self.assertNotIn("_identity", result)

    def test_batch_single_candidate_parity_and_reproducible_thresholds(self):
        _wav(self.base)
        candidate = self._batch_candidate(1, offset=3400)
        single = local_dc.inspect(self.base, candidate)
        multi = local_dc.inspect_batch(self.base, [candidate])
        self.assertIs(multi["warning"], single["warning"])
        self.assertEqual(multi["baseline_bias_warning"], single["baseline_bias_warning"])
        self.assertEqual(multi["candidates"][0]["candidate_excess_bias_warning"],
                         single["candidate_excess_bias_warning"])
        self.assertEqual(multi["complete_windows"], single["complete_windows"])
        self.assertEqual(multi["thresholds"], single["thresholds"])
        self.assertEqual(multi, local_dc.inspect_batch(self.base, [candidate]))

    def test_batch_short_signal_never_reports_clear(self):
        _wav(self.base, duration=.5)
        candidate = self._batch_candidate(1, duration=.5)
        data = local_dc.inspect_batch(self.base, [candidate])
        self.assertIsNone(data["warning"])
        self.assertIsNone(data["candidates"][0]["warning"])

    def test_batch_scans_baseline_exactly_once(self):
        _wav(self.base)
        candidates = [self._batch_candidate(i) for i in range(3)]
        real = local_dc._scan_private_pcm
        seen = []
        def capture(path):
            seen.append(str(path))
            return real(path)
        with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=capture):
            local_dc.inspect_batch(self.base, candidates)
        self.assertEqual(seen, [str(self.base), *(str(path) for path in candidates)])

    def test_batch_eight_candidates_allowed_nine_rejected(self):
        _wav(self.base)
        candidates = [self._batch_candidate(i) for i in range(9)]
        result = local_dc.inspect_batch(self.base, candidates[:8])
        self.assertEqual(result["candidate_count"], 8)
        self.assertEqual(result["candidates"][-1]["candidate_id"], "candidate-008")
        with self.assertRaisesRegex(ValueError, "1..8"):
            local_dc.inspect_batch(self.base, candidates)

    def test_batch_requires_at_least_one_candidate(self):
        _wav(self.base)
        with self.assertRaises(ValueError):
            local_dc.inspect_batch(self.base, [])

    def test_batch_rejects_baseline_and_candidate_alias_before_pcm(self):
        _wav(self.base)
        with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=AssertionError("decoded")):
            with self.assertRaisesRegex(ValueError, "distinct regular files"):
                local_dc.inspect_batch(self.base, [self.base])

    def test_batch_rejects_two_candidate_hardlinks_before_pcm(self):
        _wav(self.base)
        first = self._batch_candidate(1)
        duplicate = Path(self.tmp.name) / "alias.wav"
        os.link(first, duplicate)
        with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=AssertionError("decoded")):
            with self.assertRaisesRegex(ValueError, "distinct regular files"):
                local_dc.inspect_batch(self.base, [first, duplicate])

    def test_batch_rejects_mismatched_frames_before_pcm(self):
        _wav(self.base)
        bad = self._batch_candidate(1, duration=2)
        with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=AssertionError("decoded")):
            with self.assertRaisesRegex(ValueError, "identical shape"):
                local_dc.inspect_batch(self.base, [bad])

    def test_batch_rejects_corrupt_wav_before_pcm(self):
        _wav(self.base)
        broken = Path(self.tmp.name) / "private-corrupt.wav"
        broken.write_bytes(b"RIFF" + b"X" * 50)
        with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=AssertionError("decoded")):
            with self.assertRaises(ValueError):
                local_dc.inspect_batch(self.base, [broken])

    def test_batch_total_pcm_frames_limit_before_decode(self):
        _wav(self.base)
        paths = [self._batch_candidate(i) for i in range(2)]
        with mock.patch.object(local_dc, "MAX_BATCH_FRAMES", 2 * RATE * DURATION):
            with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=AssertionError("decoded")):
                with self.assertRaisesRegex(ValueError, "resource admission"):
                    local_dc.inspect_batch(self.base, paths)

    def test_batch_physical_file_bytes_limit_before_decode(self):
        _wav(self.base)
        paths = [self._batch_candidate(i) for i in range(2)]
        with mock.patch.object(local_dc, "MAX_BATCH_BYTES", 120_000):
            with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=AssertionError("decoded")):
                with self.assertRaisesRegex(ValueError, "resource admission"):
                    local_dc.inspect_batch(self.base, paths)

    def test_batch_late_baseline_mutation_rejected_without_partial_json(self):
        _wav(self.base)
        paths = [self._batch_candidate(i) for i in range(2)]
        real = local_dc._scan_private_pcm
        count = 0
        def mutate(path):
            nonlocal count
            data = real(path)
            count += 1
            if count == 2:
                with open(self.base, "ab") as out:
                    out.write(b"CHANGED")
            return data
        with mock.patch.object(local_dc, "_scan_private_pcm", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "pair inspection"):
                local_dc.inspect_batch(self.base, paths)

    def test_batch_cli_strict_and_output_redaction(self):
        _wav(self.base)
        one = self._batch_candidate(1, offset=3400)
        two = self._batch_candidate(2)
        cmd = [sys.executable, "-m", "mixlab.quality.local_dc",
               str(self.base), str(one), str(two), "--batch", "--strict"]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual(done.stderr, "")
        payload = json.loads(done.stdout)
        self.assertEqual(payload["candidate_count"], 2)
        self.assertIs(payload["warning"], True)
        self.assertNotIn(str(self.tmp.name), done.stdout)

    def test_batch_cli_incomplete_args_redact_all_paths(self):
        _wav(self.base)
        candidate = self._batch_candidate(1)
        secret = str(Path(self.tmp.name) / "PRIVATE_BROKEN_CHOICE.wav")
        cmd = [sys.executable, "-m", "mixlab.quality.local_dc", str(self.base),
               str(candidate), secret, "--batch"]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout, "")
        self.assertNotIn(str(self.tmp.name), done.stderr)

    def test_batch_rejects_multiple_candidates_without_opt_in(self):
        _wav(self.base)
        paths = [self._batch_candidate(i) for i in range(2)]
        cmd = [sys.executable, "-m", "mixlab.quality.local_dc",
               str(self.base), *map(str, paths)]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout, "")

    def test_same_path_pair_rejected(self):
        _wav(self.base)
        with self.assertRaisesRegex(ValueError, "distinct regular files"):
            local_dc.inspect(self.base, self.base)

    @unittest.skipUnless(hasattr(os, "link"), "Hardlinks unavailable")
    def test_hardlink_pair_rejected(self):
        _wav(self.base)
        os.link(self.base, self.alt)
        with self.assertRaisesRegex(ValueError, "distinct regular files"):
            local_dc.inspect(self.base, self.alt)

    def test_independent_identical_byte_copies_remain_admissible(self):
        _wav(self.base)
        self.alt.write_bytes(self.base.read_bytes())
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)

    def test_one_second_exact_positive_threshold(self):
        _wav(self.base, duration=1)
        _wav(self.alt, duration=1, offsets=[[3400] * RATE])
        report = local_dc.inspect(self.base, self.alt)
        self.assertEqual(report["complete_windows"], 4)
        self.assertIs(report["candidate_excess_bias_warning"][0], True)

    def test_one_window_shorter_than_one_second_is_unknown(self):
        _wav(self.base, duration=.75)
        _wav(self.alt, duration=.75, offsets=[[3400] * (3 * RATE // 4)])
        self.assertIsNone(local_dc.inspect(self.base, self.alt)["warning"])

    def test_frame_mismatch_rejected(self):
        _wav(self.base, duration=1)
        _wav(self.alt, duration=2)
        with self.assertRaisesRegex(ValueError, "identical shape"):
            local_dc.inspect(self.base, self.alt)

    def test_upper_boundary_two_million_stereo_frames(self):
        # Rights-free raw constant PCM: test the real input limit, not a mocked
        # nframes or a small fixture with patched MAX_SOURCE_FRAMES.
        def write_constant(path, frames):
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(96000)
                chunk = struct.pack("<hh", 0, 0) * 4096
                complete, tail = divmod(frames, 4096)
                for _ in range(complete):
                    writer.writeframesraw(chunk)
                if tail:
                    writer.writeframesraw(chunk[:tail * 4])
                writer.writeframes(b"")
        write_constant(self.base, local_dc.MAX_SOURCE_FRAMES)
        write_constant(self.alt, local_dc.MAX_SOURCE_FRAMES)
        report = local_dc.inspect(self.base, self.alt)
        self.assertEqual(report["frames"], 2_000_000)
        self.assertEqual(report["channels"], 2)
        self.assertEqual(report["sample_rate"], 96000)
        self.assertIs(report["warning"], False)
        write_constant(self.alt, local_dc.MAX_SOURCE_FRAMES + 1)
        with self.assertRaisesRegex(ValueError, "frame/rate bounds"):
            local_dc.inspect(self.base, self.alt)

    def _misaligned_dc(self, *, rate=RATE, level=1100, seconds=1.0):
        frame_count = rate * DURATION
        offsets = [0] * frame_count
        # The offset starts half a 250-ms window late. Only three full
        # windows of the original phase see a low-level one-second shift.
        start = round(rate * .125)
        length = round(rate * seconds)
        offsets[start:start + length] = [level] * length
        return offsets

    def test_half_window_shift_recovers_weak_full_second_dc(self):
        _wav(self.base)
        _wav(self.alt, offsets=[self._misaligned_dc()])
        ref = local_dc._scan_private_pcm(self.base)
        candidate = local_dc._scan_private_pcm(self.alt)
        flags = [abs(x[0]) >= local_dc.DC_THRESHOLD and
                 abs(x[0] - y[0]) >= local_dc.RELATIVE_THRESHOLD
                 for x, y in zip(candidate["means"], ref["means"])]
        # Prove the defect existed: original aligned grid abstains.
        self.assertIsNone(local_dc._run_state(flags, enough_windows=True))
        result = local_dc.inspect(self.base, self.alt)
        self.assertIs(result["candidate_excess_bias_warning"][0], True)
        self.assertIs(result["warning"], True)
        self.assertEqual(result["window_phase_shift_ms"], 125)

    def test_half_window_negative_dc_is_equally_detected(self):
        _wav(self.base)
        _wav(self.alt, offsets=[self._misaligned_dc(level=-1100)])
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], True)

    def test_half_window_baseline_dc_is_reported(self):
        _wav(self.base, offsets=[self._misaligned_dc()])
        _wav(self.alt, offsets=[self._misaligned_dc()])
        r = local_dc.inspect(self.base, self.alt)
        self.assertIs(r["baseline_bias_warning"][0], True)
        self.assertIs(r["candidate_excess_bias_warning"][0], False)

    def test_half_window_only_one_stereo_channel_warns(self):
        _wav(self.base, channels=2)
        _wav(self.alt, channels=2, offsets=[
            self._misaligned_dc(), [0] * (RATE * DURATION),
        ])
        r = local_dc.inspect(self.base, self.alt)
        self.assertEqual(r["candidate_excess_bias_warning"], [True, False])

    def test_half_window_subsecond_bias_is_still_inconclusive(self):
        _wav(self.base)
        _wav(self.alt, offsets=[self._misaligned_dc(seconds=.875)])
        self.assertIsNone(local_dc.inspect(self.base, self.alt)["warning"])

    def test_half_window_shift_at_noninteger_sample_rate_window(self):
        rate = 11025
        _wav(self.base, rate=rate)
        _wav(self.alt, rate=rate, offsets=[self._misaligned_dc(rate=rate)])
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], True)

    def test_exactly_one_second_clean_audio_stays_clear(self):
        _wav(self.base, duration=1)
        _wav(self.alt, duration=1)
        r = local_dc.inspect(self.base, self.alt)
        self.assertIs(r["warning"], False)
        self.assertEqual(r["complete_windows"], 4)

    def test_misaligned_dc_batch_matches_standalone_warning(self):
        _wav(self.base)
        _wav(self.alt, offsets=[self._misaligned_dc()])
        extra = self._batch_candidate(22, offset=0)
        paired = local_dc.inspect(self.base, self.alt)
        batch = local_dc.inspect_batch(self.base, [self.alt, extra])
        self.assertEqual(batch["window_phase_shift_ms"], 125)
        self.assertEqual(batch["candidates"][0]["candidate_excess_bias_warning"],
                         paired["candidate_excess_bias_warning"])
        self.assertEqual([r["warning"] for r in batch["candidates"]], [True, False])

    def test_negative_sustained_dc_offset(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([-3400] * 4)])
        self.assertIs(local_dc.inspect(self.base, self.alt)["candidate_excess_bias_warning"][0], True)

    def test_large_gain_change_without_dc_is_not_bias(self):
        _wav(self.base, amplitude=700)
        _wav(self.alt, amplitude=10000)
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)

    def test_subthreshold_bias_does_not_flag(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([700] * 4)])
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)

    def test_comparison_preserves_private_file_bytes(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([3400] * 4)])
        original = [hashlib.sha256(p.read_bytes()).digest() for p in (self.base, self.alt)]
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], True)
        after = [hashlib.sha256(p.read_bytes()).digest() for p in (self.base, self.alt)]
        self.assertEqual(original, after)

    def test_post_scan_baseline_symlink_swap_is_rejected(self):
        _wav(self.base)
        _wav(self.alt)
        original = local_dc._scan_private_pcm
        scans = 0
        def swap_after_candidate(path):
            nonlocal scans
            result = original(path)
            scans += 1
            if scans == 2:
                self.base.unlink()
                self.base.symlink_to(self.alt)
            return result
        with mock.patch.object(local_dc, "_scan_private_pcm", swap_after_candidate):
            with self.assertRaisesRegex(ValueError, "pair inspection"):
                local_dc.inspect(self.base, self.alt)

    def test_non_pcm16_width_rejected(self):
        _wav(self.base)
        with wave.open(str(self.alt), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(1)
            out.setframerate(RATE)
            out.writeframes(b"\x80" * (RATE * DURATION))
        with self.assertRaisesRegex(ValueError, "PCM16"):
            local_dc.inspect(self.base, self.alt)

    def test_identical_sources_are_negative(self):
        _wav(self.base)
        _wav(self.alt)
        data = local_dc.inspect(self.base, self.alt)
        self.assertIs(data["warning"], False)
        self.assertEqual(data["baseline_bias_warning"], [False])
        self.assertEqual(data["candidate_excess_bias_warning"], [False])
        self.assertEqual(data["complete_windows"], 16)

    def test_positive_then_negative_offsets_cancel_globally_but_warn(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([3400, 3400, -3400, -3400])])
        data = local_dc.inspect(self.base, self.alt)
        self.assertIs(data["warning"], True)
        self.assertEqual(data["candidate_excess_bias_warning"], [True])

    def test_baseline_bad_also_warns(self):
        _wav(self.base, offsets=[_offset_sections([3400] * 4)])
        _wav(self.alt, offsets=[_offset_sections([3400] * 4)])
        data = local_dc.inspect(self.base, self.alt)
        self.assertIs(data["baseline_bias_warning"][0], True)
        self.assertIs(data["candidate_excess_bias_warning"][0], False)
        self.assertIs(data["warning"], True)

    def test_one_window_anomaly_abstains(self):
        _wav(self.base)
        offsets = [0] * (RATE * DURATION)
        offsets[RATE:RATE + RATE // 4] = [3400] * (RATE // 4)
        _wav(self.alt, offsets=[offsets])
        data = local_dc.inspect(self.base, self.alt)
        self.assertIsNone(data["candidate_excess_bias_warning"][0])
        self.assertIsNone(data["warning"])

    def test_stereo_one_channel_warns_other_does_not(self):
        _wav(self.base, channels=2)
        _wav(self.alt, channels=2,
             offsets=[_offset_sections([3400] * 4), [0] * (RATE * DURATION)])
        result = local_dc.inspect(self.base, self.alt)
        self.assertEqual(result["candidate_excess_bias_warning"], [True, False])

    def test_zero_length_and_truncated_private_inputs_rejected(self):
        _wav(self.base)
        self.alt.write_bytes(b"RIFF")
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)
        _wav(self.alt)
        payload = self.alt.read_bytes()
        self.alt.write_bytes(payload[:-14])
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_sample_rate_mismatch_rejected(self):
        _wav(self.base)
        _wav(self.alt, rate=11025)
        with self.assertRaisesRegex(ValueError, "identical shape"):
            local_dc.inspect(self.base, self.alt)

    def test_channel_mismatch_rejected(self):
        _wav(self.base)
        _wav(self.alt, channels=2)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_symlink_input_rejected(self):
        _wav(self.base)
        self.alt.symlink_to(self.base)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX specific")
    def test_fifo_is_rejected_without_blocking(self):
        _wav(self.base)
        os.mkfifo(self.alt)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_short_audio_abstains(self):
        _wav(self.base, duration=0.5)
        _wav(self.alt, duration=0.5)
        self.assertIsNone(local_dc.inspect(self.base, self.alt)["warning"])

    def test_cli_is_path_redacted_even_when_input_missing(self):
        _wav(self.base)
        private = Path(self.tmp.name) / "UNIQUE_PRIVATE_MARKER"
        command = [sys.executable, "-m", "mixlab.quality.local_dc", str(self.base), str(private)]
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout, "")
        self.assertNotIn(str(private), done.stderr)
        self.assertNotIn(str(self.base), done.stderr)

    def test_cli_does_not_echo_bad_option_values(self):
        private = str(Path(self.tmp.name) / "UNIQUE_PRIVATE_MARKER")
        done = subprocess.run([sys.executable, "-m", "mixlab.quality.local_dc",
                               "--invalid=" + private, "a", "b"],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 3)
        self.assertNotIn(private, done.stderr)

    def test_cli_strict_unknown_returns_two_and_anonymizes_output(self):
        _wav(self.base)
        offsets = [0] * (RATE * DURATION)
        offsets[RATE:RATE + RATE // 4] = [3400] * (RATE // 4)
        _wav(self.alt, offsets=[offsets])
        command = [sys.executable, "-m", "mixlab.quality.local_dc",
                   str(self.base), str(self.alt), "--strict"]
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 2, done.stderr)
        data = json.loads(done.stdout)
        self.assertIsNone(data["warning"])
        self.assertNotIn(str(self.base), done.stdout)
        self.assertNotIn(str(self.alt), done.stdout)

    def test_too_large_file_rejected_before_parsing(self):
        _wav(self.base)
        with open(self.alt, "wb") as handle:
            handle.truncate(local_dc.MAX_SOURCE_BYTES + 1)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_source_changes_after_scan_are_not_accepted(self):
        _wav(self.base)
        _wav(self.alt)
        original = local_dc._scan_private_pcm
        seen = 0
        def change_after_first_scan(path):
            nonlocal seen
            r = original(path)
            seen += 1
            if seen == 1:
                # A source that mutates while a separate source is scanned
                # must be checked again before publication, not assumed frozen.
                with open(self.base, "ab") as f:
                    f.write(b"CHANGED")
            return r
        with mock.patch.object(local_dc, "_scan_private_pcm", change_after_first_scan):
            with self.assertRaisesRegex(ValueError, "pair inspection"):
                local_dc.inspect(self.base, self.alt)
