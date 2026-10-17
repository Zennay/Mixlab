"""Synthetic security/immutability tests for the isolated ML-07 FD guard."""
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import wave

from mixlab.quality.fd_guard import (MAX_BYTES, admitted_pcm16, validate_private_pcm16,
                                    validate_private_ab_group, MAX_GROUP_FRAMES)


def make_wav(path, *, frames=200, channels=1, rate=8000, width=2):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(b"\x05\x01" * frames * channels if width == 2 else b"\x01" * frames * channels * width)


class PrivateFdGuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "private-secret-track.wav"
        make_wav(self.source)

    def assert_rejected(self, path):
        with self.assertRaisesRegex(ValueError, r"Private WAV admission rejected") as ctx:
            with admitted_pcm16(path) as reader:
                reader.readframes(10)
        self.assertNotIn(str(self.root), str(ctx.exception))
        self.assertNotIn("private-secret-track", str(ctx.exception))

    def test_regular_pcm16_mono_fully_reads_immutably(self):
        original = self.source.read_bytes()
        with admitted_pcm16(self.source) as reader:
            self.assertEqual((1, 2, 8000), (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()))
            self.assertEqual(200, reader.getnframes())
            self.assertEqual(400, len(reader.readframes(200)))
        self.assertEqual(original, self.source.read_bytes())

    def test_regular_stereo_accepted(self):
        make_wav(self.source, channels=2)
        with admitted_pcm16(self.source) as reader:
            self.assertEqual(800, len(reader.readframes(200)))

    def test_symlink_rejected_without_following(self):
        alias = self.root / "alias.wav"
        alias.symlink_to(self.source)
        self.assert_rejected(alias)

    def test_fifo_rejected_without_blocking(self):
        fifo = self.root / "private-secret-pipe.wav"
        os.mkfifo(fifo)
        self.assert_rejected(fifo)

    def test_directory_and_missing_path_rejected(self):
        self.assert_rejected(self.root)
        self.assert_rejected(self.root / "missing-private.wav")

    def test_sparse_oversize_rejected_before_wave_decoding(self):
        with open(self.source, "r+b") as file:
            file.truncate(MAX_BYTES + 1)
        self.assert_rejected(self.source)

    def test_exact_maximum_byte_size_is_admissible_if_header_valid(self):
        with open(self.source, "r+b") as file:
            file.truncate(MAX_BYTES)
        with admitted_pcm16(self.source) as reader:
            self.assertEqual(200, reader.getnframes())
            self.assertEqual(400, len(reader.readframes(200)))

    def test_metadata_before_data_with_valid_payload_is_admitted(self):
        # A WAVE container need not have the canonical 44-byte layout.
        # An odd-size JUNK chunk requires the RIFF padding byte.
        make_wav(self.source, channels=2)
        original = self.source.read_bytes()
        chunk = b"JUNK" + struct.pack("<I", 127) + b"z" * 127 + b"\x00"
        mixed = bytearray(original[:36] + chunk + original[36:])
        mixed[4:8] = struct.pack("<I", len(mixed) - 8)
        self.source.write_bytes(mixed)
        with admitted_pcm16(self.source) as reader:
            self.assertEqual(200, reader.getnframes())
            self.assertEqual(800, len(reader.readframes(200)))

    def test_bounded_pre_data_chunks_accept_exact_header_limit(self):
        from mixlab.quality.fd_guard import MAX_PRE_DATA_CHUNKS
        # 4094 JUNK + fmt + data = exactly 4096 supported headers.
        original = self.source.read_bytes()
        junk = b"JUNK\x00\x00\x00\x00" * (MAX_PRE_DATA_CHUNKS - 2)
        result = bytearray(original[:12] + junk + original[12:])
        result[4:8] = struct.pack("<I", len(result) - 8)
        self.source.write_bytes(result)
        self.assertTrue(validate_private_pcm16(self.source)["pcm16_payload_complete"])

    def test_pre_data_chunk_flood_fails_before_wave_parser(self):
        from mixlab.quality.fd_guard import MAX_PRE_DATA_CHUNKS
        original = self.source.read_bytes()
        junk = b"JUNK\x00\x00\x00\x00" * (MAX_PRE_DATA_CHUNKS - 1)
        result = bytearray(original[:12] + junk + original[12:])
        result[4:8] = struct.pack("<I", len(result) - 8)
        self.source.write_bytes(result)
        self.assert_rejected(self.source)

    def test_non_integral_declared_pcm_frame_is_rejected(self):
        # wave's getnframes floors data_bytes / frame_width. Guard must not
        # treat a trailing orphan PCM byte as a valid 200-frame WAV.
        original = bytearray(self.source.read_bytes())
        original[40:44] = struct.pack("<I", 401)
        original.extend(b"x\x00")  # extra sample byte + required RIFF pad
        original[4:8] = struct.pack("<I", len(original) - 8)
        self.source.write_bytes(original)
        self.assert_rejected(self.source)

    def test_riff_size_must_fit_the_physical_file(self):
        original = bytearray(self.source.read_bytes())
        original[4:8] = struct.pack("<I", len(original) + 200)
        self.source.write_bytes(original)
        self.assert_rejected(self.source)

    def test_padded_metadata_cannot_hide_truncated_declared_pcm(self):
        # Real PCM begins after JUNK: total file length still exceeds
        # (44 + declared payload), fooling a fixed-44-byte size gate.
        original = self.source.read_bytes()
        chunk = b"JUNK" + struct.pack("<I", 128) + b"z" * 128
        truncated = bytearray(original[:36] + chunk + original[36:-100])
        truncated[4:8] = struct.pack("<I", len(truncated) - 8)
        self.assertGreaterEqual(len(truncated), 44 + 200 * 2)
        self.source.write_bytes(truncated)
        self.assert_rejected(self.source)

    def test_truncated_claimed_pcm_payload_rejected(self):
        with open(self.source, "r+b") as file:
            file.truncate(44 + 20)
        self.assert_rejected(self.source)

    def test_24bit_format_rejected(self):
        make_wav(self.source, width=3)
        self.assert_rejected(self.source)

    def test_unsupported_sample_rate_rejected(self):
        make_wav(self.source, rate=1000)
        self.assert_rejected(self.source)

    def test_more_than_two_channels_rejected(self):
        make_wav(self.source, channels=3)
        self.assert_rejected(self.source)

    def test_zero_frames_rejected(self):
        make_wav(self.source, frames=0)
        self.assert_rejected(self.source)

    def test_real_maximum_two_million_stereo_frames_stream_without_full_copy(self):
        # Actual maximum payload, not merely a large WAV-header declaration.
        # Stream small synthetic blocks to keep generation/read memory bounded.
        block = b"\x00\x01\x00\xfe" * 4096
        with wave.open(str(self.source), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(96000)
            for _ in range(488):
                writer.writeframesraw(block)
            writer.writeframesraw(b"\x00\x01\x00\xfe" * 1152)
        with admitted_pcm16(self.source) as reader:
            self.assertEqual(2_000_000, reader.getnframes())
            frames_seen = 0
            while True:
                payload = reader.readframes(4096)
                if not payload:
                    break
                self.assertEqual(0, len(payload) % 4)
                frames_seen += len(payload) // 4
            self.assertEqual(2_000_000, frames_seen)
        # The new user-facing read-only preflight must also consume exactly
        # the 2M-frame stereo maximum within its fixed block budget.
        report = validate_private_pcm16(self.source)
        self.assertEqual(2_000_000, report["frames"])
        self.assertEqual(2, report["channels"])
        self.assertTrue(report["pcm16_payload_complete"])

    def test_more_than_two_million_frames_rejected_from_header(self):
        # A sparse extension avoids allocating >4 MiB sample arrays.
        with open(self.source, "r+b") as file:
            file.seek(40)
            file.write(struct.pack("<I", 2_000_001 * 2))
            file.truncate(44 + 2_000_001 * 2)
        self.assert_rejected(self.source)

    def test_same_inode_modified_while_open_rejected(self):
        with self.assertRaisesRegex(ValueError, "admission rejected"):
            with admitted_pcm16(self.source) as reader:
                reader.readframes(4)
                with open(self.source, "r+b") as file:
                    file.seek(44)
                    file.write(b"\x04")
                os.utime(self.source, ns=(1_500_000_000_000_000_000, 1_500_000_000_000_000_000))

    def test_path_rebound_to_another_regular_inode_rejected(self):
        replacement = self.root / "replacement.wav"
        make_wav(replacement)
        with self.assertRaisesRegex(ValueError, "admission rejected"):
            with admitted_pcm16(self.source) as reader:
                reader.readframes(4)
                os.replace(replacement, self.source)

    def test_path_swapped_to_symlink_while_reading_rejected(self):
        real_file = self.root / "real.wav"
        with self.assertRaisesRegex(ValueError, "admission rejected"):
            with admitted_pcm16(self.source) as reader:
                reader.readframes(4)
                self.source.rename(real_file)
                self.source.symlink_to(real_file)

    def test_malformed_short_fmt_chunk_is_sanitized(self):
        # wave._read_fmt_chunk can surface struct.error from unpacking a
        # declared fmt chunk that contains fewer than the mandatory bytes.
        # It must never bypass the bounded path-redacted admission contract.
        payload = (b"WAVE" + b"fmt " + struct.pack("<I", 2) + b"\x01\x00"
                   + b"data" + struct.pack("<I", 8) + b"x" * 8
                   + b"\x00" * 16)
        self.source.write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)
        self.assert_rejected(self.source)

    def test_corrupt_and_tiny_headers_rejected(self):
        self.source.write_bytes(b"not a valid WAV" + b"x" * 45)
        self.assert_rejected(self.source)
        self.source.write_bytes(b"RIFF")
        self.assert_rejected(self.source)

    def test_standalone_pcm_validator_consumes_all_declared_frames(self):
        original = self.source.read_bytes()
        with patch("mixlab.quality.fd_guard.os.open", wraps=os.open) as opened:
            report = validate_private_pcm16(self.source, block_frames=73)
        self.assertEqual(1, opened.call_count)
        self.assertEqual({"screen": "ml07-single-fd-pcm16-integrity-v1",
                          "sample_rate": 8000, "channels": 1, "frames": 200,
                          "pcm16_payload_complete": True,
                          "human_listening_required": True}, report)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertEqual(original, self.source.read_bytes())

    def test_standalone_pcm_validator_stereo_and_block_boundaries(self):
        make_wav(self.source, frames=8193, channels=2)
        report = validate_private_pcm16(self.source)
        self.assertEqual(2, report["channels"])
        self.assertEqual(8193, report["frames"])
        self.assertTrue(report["pcm16_payload_complete"])

    def test_standalone_validator_rejects_bad_block_admission(self):
        for requested in (True, 0, -1, 4097, 10.5, None, "10"):
            with self.subTest(block_frames=requested):
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    validate_private_pcm16(self.source, block_frames=requested)

    def test_full_stream_validator_rejects_truncation_mid_read(self):
        # Deterministic race: the source passes header admission, then the
        # underlying file is cut after the first block read.
        original_read = wave.Wave_read.readframes
        changed = [False]

        def truncate_after_first_read(reader, count):
            data = original_read(reader, count)
            if not changed[0]:
                changed[0] = True
                with open(self.source, "r+b") as stream:
                    stream.truncate(44 + 8)
            return data

        with patch.object(wave.Wave_read, "readframes", new=truncate_after_first_read):
            with self.assertRaisesRegex(ValueError, "details withheld") as result:
                validate_private_pcm16(self.source, block_frames=10)
        self.assertTrue(changed[0])
        self.assertNotIn(str(self.root), str(result.exception))

    def test_full_stream_validator_rejects_same_size_replacement_mid_read(self):
        # The old descriptor still reads valid PCM after the named path was
        # replaced. The successful read must not certify the *new* path.
        replacement = self.root / "fresh-private.wav"
        make_wav(replacement)
        original_read = wave.Wave_read.readframes
        changed = [False]

        def replace_after_first_read(reader, count):
            data = original_read(reader, count)
            if not changed[0]:
                changed[0] = True
                os.replace(replacement, self.source)
            return data

        with patch.object(wave.Wave_read, "readframes", new=replace_after_first_read):
            with self.assertRaisesRegex(ValueError, "details withheld") as result:
                validate_private_pcm16(self.source, block_frames=10)
        self.assertTrue(changed[0])
        self.assertNotIn(str(self.root), str(result.exception))

    def test_standalone_cli_redacts_path_and_is_deterministic(self):
        cmd = [sys.executable, "-m", "mixlab.quality.fd_guard", str(self.source)]
        first = subprocess.run(cmd, capture_output=True, text=True)
        second = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual(200, report["frames"])
        self.assertTrue(report["pcm16_payload_complete"])
        self.assertNotIn(str(self.root), first.stdout + first.stderr)

    def test_standalone_cli_redacts_missing_path_and_arguments(self):
        marker = "VERY_SECRET_LOCAL_MUSIC_FILENAME"
        for arguments, expected_status in (
            ([str(self.root / marker)], 3),
            ([str(self.source), "--unknown=" + marker], 2),
            ([str(self.source), marker], 2),
            ([], 2),
        ):
            with self.subTest(arguments=arguments):
                proc = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.fd_guard", *arguments],
                    capture_output=True, text=True,
                )
                self.assertEqual(expected_status, proc.returncode)
                self.assertFalse(proc.stdout)
                self.assertNotIn(marker, proc.stderr)
                self.assertNotIn(str(self.root), proc.stderr)

    def test_ab_group_validates_multiple_sources_anonymously_and_immutably(self):
        c1, c2 = self.root / "PRIVATE_CANDIDATE1.wav", self.root / "PRIVATE_CANDIDATE2.wav"
        make_wav(c1)
        make_wav(c2)
        files = [self.source, c1, c2]
        before = [p.read_bytes() for p in files]
        with patch("mixlab.quality.fd_guard.os.open", wraps=os.open) as opened:
            report = validate_private_ab_group(files)
        self.assertEqual(3, opened.call_count)  # no metadata second opens
        self.assertEqual({"screen": "ml07-single-fd-ab-group-integrity-v1",
                          "sample_rate": 8000, "channels": 1, "frames": 200,
                          "candidate_count": 2, "shape_comparable": True,
                          "pcm16_payloads_complete": True,
                          "human_listening_required": True}, report)
        self.assertEqual(before, [p.read_bytes() for p in files])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_ab_group_rejects_invalid_participant_inventory(self):
        for group in ([], [self.source], [self.source] * 9, None,
                      (self.source,), "not-a-list"):
            with self.subTest(group=str(type(group)) + ":" + str(len(group) if group else 0)):
                with self.assertRaisesRegex(ValueError, "details withheld"):
                    validate_private_ab_group(group)

    def test_ab_group_shape_mismatch_before_pcm_scan(self):
        candidate = self.root / "PRIVATE_DIFFERENT.wav"
        for kwargs in ({"frames": 201}, {"channels": 2}, {"rate": 16000}):
            with self.subTest(kwargs=kwargs):
                make_wav(candidate, **kwargs)
                with patch.object(wave.Wave_read, "readframes", side_effect=AssertionError(
                    "PCM read on header-shape mismatch"
                )) as intercepted:
                    with self.assertRaisesRegex(ValueError, "details withheld"):
                        validate_private_ab_group([self.source, candidate])
                    intercepted.assert_not_called()

    def test_ab_group_rejects_missing_symlink_fifo_and_corrupt_inputs(self):
        target = self.root / "UNKNOWN_SECRET_TRACK.wav"
        alias = self.root / "alias.wav"
        alias.symlink_to(self.source)
        fifo = self.root / "fifo-secret.wav"
        os.mkfifo(fifo)
        for source in (target, alias, fifo):
            with self.subTest(source=source.name):
                with self.assertRaisesRegex(ValueError, "details withheld") as error:
                    validate_private_ab_group([self.source, source])
                self.assertNotIn(str(self.root), str(error.exception))
        target.write_bytes(b"not a RIFF file" * 8)
        with self.assertRaisesRegex(ValueError, "details withheld"):
            validate_private_ab_group([self.source, target])

    def test_ab_group_rejects_identical_inode_even_with_distinct_path(self):
        alias = self.root / "PRIVATE_HARDLINK.wav"
        os.link(self.source, alias)
        for pair in ([self.source, self.source], [self.source, alias]):
            with self.subTest(same_file=pair[0] == pair[1]):
                with patch.object(wave.Wave_read, "readframes", side_effect=AssertionError(
                    "Audio read before duplicate inode admission"
                )) as intercepted:
                    with self.assertRaisesRegex(ValueError, "details withheld") as result:
                        validate_private_ab_group(pair)
                    intercepted.assert_not_called()
                    self.assertNotIn(str(self.root), str(result.exception))

    def test_ab_group_distinct_inodes_do_not_claim_different_audio(self):
        # Byte-identical, independently stored source files remain legal:
        # this FD guard is NOT PR #68's acoustic/exact-PCM reuse detector.
        copy = self.root / "private-byte-duplicate.wav"
        shutil.copyfile(self.source, copy)
        report = validate_private_ab_group([self.source, copy])
        self.assertTrue(report["shape_comparable"])
        self.assertNotIn("identical", json.dumps(report))

    def test_ab_group_stereo_identical_shape_admitted(self):
        make_wav(self.source, channels=2, frames=8193)
        other = self.root / "stereo-new.wav"
        make_wav(other, channels=2, frames=8193)
        report = validate_private_ab_group([self.source, other])
        self.assertEqual(2, report["channels"])
        self.assertEqual(8193, report["frames"])
        self.assertTrue(report["pcm16_payloads_complete"])

    def test_ab_group_aggregate_ceiling_checked_before_audio_reads(self):
        # One sparse 2M-frame file is sufficient to prove both 8M budget
        # and pre-I/O admission. Never allocate 20M PCM samples in Python.
        with open(self.source, "r+b") as source:
            source.seek(40)
            source.write(struct.pack("<I", 2_000_000 * 2))
            source.truncate(44 + 2_000_000 * 2)
        self.assertEqual(8_000_000, MAX_GROUP_FRAMES)
        copies = [self.source]
        for index in range(4):
            path = self.root / f"budget-candidate-{index}.wav"
            shutil.copyfile(self.source, path)
            copies.append(path)
        with patch.object(wave.Wave_read, "readframes", side_effect=AssertionError(
            "PCM work exceeded pre-admission budget"
        )) as intercepted:
            with self.assertRaisesRegex(ValueError, "details withheld"):
                validate_private_ab_group(copies)
            intercepted.assert_not_called()

    def test_ab_group_exact_eight_million_frames_admitted(self):
        with open(self.source, "r+b") as source:
            source.seek(4)
            source.write(struct.pack("<I", 36 + 2_000_000 * 2))
            source.seek(40)
            source.write(struct.pack("<I", 2_000_000 * 2))
            source.truncate(44 + 2_000_000 * 2)
        copies = [self.source]
        for index in range(3):
            path = self.root / f"exact-budget-{index}.wav"
            shutil.copyfile(self.source, path)
            copies.append(path)
        result = validate_private_ab_group(copies)
        self.assertEqual(3, result["candidate_count"])
        self.assertEqual(2_000_000, result["frames"])

    def test_ab_group_detects_last_candidate_mutation_while_reading(self):
        candidate = self.root / "private-A.wav"
        make_wav(candidate)
        original_read = wave.Wave_read.readframes
        changed = [False]
        def edit_when_read(reader, n):
            result = original_read(reader, n)
            if not changed[0]:
                changed[0] = True
                with open(candidate, "r+b") as file:
                    file.seek(44)
                    file.write(b"\x7e")
            return result
        with patch.object(wave.Wave_read, "readframes", new=edit_when_read):
            with self.assertRaisesRegex(ValueError, "details withheld"):
                validate_private_ab_group([self.source, candidate])
        self.assertTrue(changed[0])

    def test_ab_group_revalidates_baseline_during_later_candidate_scan(self):
        # All descriptors remain owned until the complete cohort exits. A
        # replaced earlier path must not be silently accepted at the end.
        candidate = self.root / "later.wav"
        replacement = self.root / "replacement.wav"
        make_wav(candidate)
        make_wav(replacement)
        real_read = wave.Wave_read.readframes
        calls = [0]

        def rebind_after_baseline(reader, n):
            raw = real_read(reader, n)
            calls[0] += 1
            if calls[0] == 2:
                os.replace(replacement, self.source)
            return raw

        with patch.object(wave.Wave_read, "readframes", new=rebind_after_baseline):
            with self.assertRaisesRegex(ValueError, "details withheld") as error:
                validate_private_ab_group([self.source, candidate])
        self.assertGreaterEqual(calls[0], 2)
        self.assertNotIn(str(self.root), str(error.exception))

    def test_ab_group_eight_participants_and_bounded_read_chunk(self):
        files = [self.source]
        for idx in range(7):
            file = self.root / f"c-{idx}.wav"
            make_wav(file, frames=8193)
            files.append(file)
        make_wav(self.source, frames=8193)
        original_read = wave.Wave_read.readframes
        counts = []

        def bounded_read(reader, count):
            counts.append(count)
            return original_read(reader, count)

        with patch.object(wave.Wave_read, "readframes", new=bounded_read):
            report = validate_private_ab_group(files)
        self.assertEqual(7, report["candidate_count"])
        self.assertTrue(counts)
        self.assertLessEqual(max(counts), 4096)
        self.assertEqual(8, len([v for v in counts if v == 4096]))

    def test_ab_group_cli_success_stable_and_no_private_path(self):
        candidate = self.root / "CANDIDATE_PRIVATE.wav"
        make_wav(candidate)
        cmd = [sys.executable, "-m", "mixlab.quality.fd_guard",
               "--ab-group", str(self.source), str(candidate)]
        first = subprocess.run(cmd, capture_output=True, text=True)
        second = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertTrue(json.loads(first.stdout)["shape_comparable"])
        self.assertNotIn("PRIVATE", first.stdout + first.stderr)
        self.assertNotIn(str(self.root), first.stdout + first.stderr)

    def test_ab_group_cli_errors_redacted(self):
        candidate = self.root / "OTHER_SUPER_PRIVATE.wav"
        make_wav(candidate, rate=16000)
        modes = (
            (["--ab-group", str(self.source), str(candidate)], 3),
            ([str(self.source), str(candidate)], 2),
            (["--ab-group", str(self.source)], 2),
            (["--ab-group", str(self.source), "SECRET_NOT_FOUND"], 3),
        )
        for args, expected in modes:
            with self.subTest(expected=expected, count=len(args)):
                proc = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality.fd_guard", *args],
                    capture_output=True, text=True,
                )
                self.assertEqual(expected, proc.returncode)
                self.assertFalse(proc.stdout)
                self.assertNotIn("PRIVATE", proc.stderr)
                self.assertNotIn("SECRET_NOT_FOUND", proc.stderr)
                self.assertNotIn(str(self.root), proc.stderr)

    def test_outputs_no_private_path_or_audio_and_no_writes(self):
        original = self.source.read_bytes()
        with admitted_pcm16(self.source) as reader:
            size = len(reader.readframes(10))
        self.assertEqual(20, size)
        self.assertEqual(original, self.source.read_bytes())
        self.assertNotIn(str(self.root), json.dumps({"bytes_read": size}))


if __name__ == "__main__":
    unittest.main()
