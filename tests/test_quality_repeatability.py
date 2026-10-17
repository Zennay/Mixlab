"""Synthetic-only tests for independent render PCM repeatability (ML-07).

No third-party packages, copyrighted recordings or live worker state.
"""
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

from mixlab.quality.repeatability import (
    CHUNK_FRAMES, MAX_BYTES, RepeatabilityError, verify_repeatability,
)


def make_wav(path: Path, samples: list[int], *, channels: int = 1, rate: int = 8000):
    data = array.array("h", samples)
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setframerate(rate)
        out.setsampwidth(2)
        out.writeframes(data.tobytes())


class RepeatabilityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.a = self.root / "private-A-track.wav"
        self.b = self.root / "private-B-track.wav"
        values = [((i * 97) % 24001) - 12000 for i in range(8192)]
        make_wav(self.a, values)
        make_wav(self.b, values)

    def test_identical_distinct_sources_pass(self):
        report = verify_repeatability(self.a, self.b)
        self.assertEqual(
            {"schema_version": 1, "repeatable_pcm": True,
             "independent_sources_verified": True,
             "format_and_frame_count_verified": True,
             "technical_review_required": False,
             "human_preference_test_required": True}, report
        )
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("hash", json.dumps(report).lower())
        self.assertNotIn("score", json.dumps(report).lower())

    def test_same_filename_or_hardlink_refused(self):
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.a)
        self.b.unlink()
        os.link(self.a, self.b)
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.b)

    def test_independent_pcm_mutation_is_not_repeatable(self):
        make_wav(self.b, [0] * 8192)
        result = verify_repeatability(self.a, self.b)
        self.assertFalse(result["repeatable_pcm"])
        self.assertTrue(result["technical_review_required"])

    def test_stereo_pair_passes_and_channel_swap_fails(self):
        a = [sample for i in range(5000) for sample in (i % 1000, -(i % 791))]
        make_wav(self.a, a, channels=2, rate=48000)
        make_wav(self.b, a, channels=2, rate=48000)
        self.assertTrue(verify_repeatability(self.a, self.b)["repeatable_pcm"])
        swapped = [sample for i in range(0, len(a), 2)
                   for sample in (a[i+1], a[i])]
        make_wav(self.b, swapped, channels=2, rate=48000)
        self.assertFalse(verify_repeatability(self.a, self.b)["repeatable_pcm"])

    def test_metadata_mismatch_refused_before_any_pcm(self):
        for kw in ({"rate": 16000}, {"channels": 2}):
            with self.subTest(kw=kw):
                make_wav(self.b, [0] * 8192, **kw)
                with patch.object(wave.Wave_read, "readframes",
                                  side_effect=AssertionError("PCM read before admission")):
                    with self.assertRaises(RepeatabilityError):
                        verify_repeatability(self.a, self.b)
        make_wav(self.b, [0] * 1024)
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.b)

    def test_stream_chunks_are_bounded(self):
        original = wave.Wave_read.readframes
        calls = []
        def monitored(reader, count):
            calls.append(count)
            return original(reader, count)
        with patch.object(wave.Wave_read, "readframes", monitored):
            self.assertTrue(verify_repeatability(self.a, self.b)["repeatable_pcm"])
        self.assertEqual(4, len(calls))  # two 4096-frame slices, both files
        self.assertTrue(all(1 <= count <= CHUNK_FRAMES for count in calls))

    def test_actual_m1_renderer_repeatability_across_transition_families(self):
        # Exercise the integrated MixLab engine, not only synthetic WAV writer.
        # Generated sine inputs are rights-safe and run locally in hosted CI.
        import math
        from mixlab.engine import FAMILY_NAMES, render, write_wav
        from mixlab.models import Recipe

        original_a = self.root / "render-input-A.wav"
        original_b = self.root / "render-input-B.wav"
        write_wav(original_a, 8000, [
            (0.22 * math.sin(i * .11), 0.13 * math.cos(i * .05))
            for i in range(8000)
        ])
        write_wav(original_b, 8000, [
            (0.18 * math.cos(i * .09), 0.10 * math.sin(i * .07))
            for i in range(8000)
        ])
        self.assertGreaterEqual(len(FAMILY_NAMES), 3)
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                first = self.root / (family + "-render-1.wav")
                second = self.root / (family + "-render-2.wav")
                recipe = Recipe(family=family, beats=1)
                render(original_a, original_b, first, recipe)
                render(original_a, original_b, second, recipe)
                result = verify_repeatability(first, second)
                self.assertTrue(result["repeatable_pcm"])
                self.assertFalse(result["technical_review_required"])
                self.assertNotIn(str(self.root), json.dumps(result))
        # A distinct valid render recipe should not pass as a repeat.
        other = self.root / "different-recipe.wav"
        render(original_a, original_b, other, Recipe(family="hard_cut", beats=1))
        baseline = self.root / "baseline-render-1.wav"
        self.assertTrue(baseline.exists())
        self.assertFalse(verify_repeatability(baseline, other)["repeatable_pcm"])

    def test_streaming_dsp_render_block_partition_invariance_all_families(self):
        # The current streaming renderer, not the legacy in-memory engine.
        # Exercise many PCM read partitions, including non-divisors of 4,000
        # frames, and compare every rendered frame through the privacy gate.
        import math
        from mixlab.dsp import render as streaming_render
        from mixlab.models import FAMILY_NAMES, Recipe

        source_a = self.root / "dsp-input-a.wav"
        source_b = self.root / "dsp-input-b.wav"
        left = [int(3900 * math.sin(i * .137)) for i in range(8000)]
        right = [int(2500 * math.cos(i * .109)) for i in range(8000)]
        make_wav(source_a, [v for i in range(8000)
                            for v in (left[i], right[i])], channels=2)
        make_wav(source_b, [v for i in range(8000)
                            for v in (right[i], -left[i])], channels=2)
        blocks = (7, 31, 257, 4096, 8192)
        self.assertGreaterEqual(len(FAMILY_NAMES), 3)
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                reference = None
                reference_digest = None
                reference_receipt = None
                for block in blocks:
                    destination = self.root / f"stream-{family}-{block}.wav"
                    receipt = streaming_render(source_a, source_b, destination,
                                               Recipe(family=family, beats=1),
                                               block_frames=block)
                    self.assertEqual(block, receipt["block_frames"])
                    self.assertEqual(4000, receipt["frames"])
                    self.assertEqual("reject_before_publication", receipt["clipping_policy"])
                    if reference is None:
                        reference = destination
                        reference_digest = receipt["output_sha256"]
                        reference_receipt = receipt
                    else:
                        verdict = verify_repeatability(
                            reference, destination,
                            receipts=(reference_receipt, receipt),
                        )
                        self.assertTrue(
                            verdict["repeatable_pcm"],
                            f"Streaming renderer block-size regression: {family}/{block}",
                        )
                        self.assertTrue(verdict["render_receipts_consistent"])
                        self.assertEqual(reference_digest, receipt["output_sha256"])

    def test_streaming_dsp_separate_process_same_recipe_is_identical(self):
        # Separate Python processes cannot accidentally share mutable module
        # state. Receipts never leave this private fixture directory.
        import math
        from mixlab.models import FAMILY_NAMES

        source_a = self.root / "isolate-input-a.wav"
        source_b = self.root / "isolate-input-b.wav"
        make_wav(source_a, [int(3300 * math.sin(i * .16)) for i in range(8000)])
        make_wav(source_b, [int(2900 * math.cos(i * .09)) for i in range(8000)])
        code = (
            "import sys; from mixlab.dsp import render; "
            "from mixlab.models import Recipe; "
            "render(sys.argv[1], sys.argv[2], sys.argv[3], "
            "Recipe(family=sys.argv[4], beats=1), block_frames=int(sys.argv[5]))"
        )
        project_root = Path(__file__).resolve().parents[1]
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                one = self.root / f"process-{family}-one.wav"
                two = self.root / f"process-{family}-two.wav"
                for path, block in ((one, 31), (two, 4096)):
                    result = subprocess.run(
                        [sys.executable, "-c", code, str(source_a), str(source_b),
                         str(path), family, str(block)],
                        cwd=project_root, capture_output=True, text=True,
                        timeout=30,
                    )
                    self.assertEqual(0, result.returncode,
                                     "Streaming renderer child failed")
                    self.assertEqual("", result.stdout)
                self.assertTrue(verify_repeatability(one, two)["repeatable_pcm"])
                self.assertNotIn(str(self.root),
                                 json.dumps(verify_repeatability(one, two)))

    def _render_fixture_with_receipts(self):
        import math
        from mixlab.dsp import render as streaming_render
        from mixlab.models import Recipe

        first_input = self.root / "receipt-input-a.wav"
        second_input = self.root / "receipt-input-b.wav"
        make_wav(first_input, [int(3000 * math.sin(i * .11))
                               for i in range(8000)])
        make_wav(second_input, [int(2500 * math.cos(i * .17))
                                for i in range(8000)])
        one = self.root / "receipt-output-a.wav"
        two = self.root / "receipt-output-b.wav"
        first_receipt = streaming_render(first_input, second_input, one,
                                         Recipe(beats=1), block_frames=7)
        second_receipt = streaming_render(first_input, second_input, two,
                                          Recipe(beats=1), block_frames=4096)
        return one, two, first_receipt, second_receipt

    def test_receipts_bind_full_output_bytes_across_different_dsp_blocks(self):
        one, two, first_receipt, second_receipt = self._render_fixture_with_receipts()
        self.assertNotEqual(first_receipt["block_frames"],
                            second_receipt["block_frames"])
        report = verify_repeatability(
            one, two, receipts=(first_receipt, second_receipt)
        )
        self.assertTrue(report["repeatable_pcm"])
        self.assertTrue(report["render_receipts_consistent"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("sha256", json.dumps(report))
        self.assertNotIn("source", json.dumps(report).replace(
            "independent_sources_verified", ""))

        # Metadata-only mutation leaves PCM equal but must break the receipt
        # SHA binding. Without receipts, PCM-only equality is intentionally
        # retained, since the two modes answer different questions.
        with two.open("ab") as dest:
            dest.write(b"private-trailer-not-a-valid-receipt")
        self.assertTrue(verify_repeatability(one, two)["repeatable_pcm"])
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(one, two, receipts=(first_receipt, second_receipt))

    def test_valid_riff_metadata_may_differ_without_changing_pcm(self):
        # A legal unknown RIFF chunk does not change playback PCM; the
        # PCM-only mode must not turn into a whole-container byte comparator.
        # Receipt-bound mode requires each *individual* updated WAV digest.
        import copy
        import hashlib
        import struct

        one, two, ra, rb = self._render_fixture_with_receipts()
        original = two.read_bytes()
        self.assertEqual(b"RIFF", original[:4])
        self.assertEqual(b"data", original[36:40])  # canonical PCM16 fixture
        junk = b"JUNK" + struct.pack("<I", 5) + b"noise" + b"\x00"
        modified = original[:36] + junk + original[36:]
        modified = modified[:4] + struct.pack("<I", len(modified) - 8) + modified[8:]
        two.write_bytes(modified)
        with wave.open(str(two), "rb") as reader:
            self.assertEqual(4000, reader.getnframes())
        self.assertTrue(verify_repeatability(one, two)["repeatable_pcm"])
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(one, two, receipts=(ra, rb))
        updated_receipt = copy.deepcopy(rb)
        updated_receipt["output_sha256"] = hashlib.sha256(modified).hexdigest()
        report = verify_repeatability(one, two, receipts=(ra, updated_receipt))
        self.assertTrue(report["repeatable_pcm"])
        self.assertTrue(report["render_receipts_consistent"])

    def test_receipt_recipe_input_and_output_tampering_fail_closed(self):
        import copy
        one, two, original_a, original_b = self._render_fixture_with_receipts()
        self.assertTrue(verify_repeatability(
            one, two, receipts=(original_a, original_b)
        )["render_receipts_consistent"])
        modifications = (
            lambda r: r["recipe"].__setitem__("beats", 2),
            lambda r: r["sources"][0].__setitem__("sha256", "0" * 64),
            lambda r: r.__setitem__("output_sha256", "f" * 64),
            lambda r: r.__setitem__("engine_version", "changed-version"),
            lambda r: r.__setitem__("sample_rate", 16000),
            lambda r: r.__setitem__("frames", 1234),
            lambda r: r.__setitem__("start_frames", {}),
            lambda r: r.__setitem__("sources", []),
        )
        for mutate in modifications:
            with self.subTest(modification=modifications.index(mutate)):
                tampered = copy.deepcopy(original_b)
                mutate(tampered)
                with self.assertRaisesRegex(
                    RepeatabilityError,
                    "^invalid, changed or incompatible source$"
                ):
                    verify_repeatability(one, two, receipts=(original_a, tampered))

    def test_receipt_malformed_and_oversized_metadata_is_rejected_privately(self):
        one, two, ra, rb = self._render_fixture_with_receipts()
        invalid = (
            (ra,),
            "not receipts",
            (ra, None),
            (ra, {"secret_path": str(self.root)}),
            (ra, dict(rb, dangerous_string="private" * 5000)),
            (ra, dict(rb, output_sha256="not-a-sha")),
            (ra, dict(rb, duration_seconds=float("nan"))),
        )
        for pair in invalid:
            with self.subTest(kind=type(pair).__name__):
                with self.assertRaisesRegex(
                    RepeatabilityError, "^invalid, changed or incompatible source$"
                ):
                    verify_repeatability(one, two, receipts=pair)
        self.assertTrue(verify_repeatability(one, two)["repeatable_pcm"])

    def test_full_two_million_frame_stereo_capacity_and_last_frame_integrity(self):
        # Exercise the actual 2M-frame/source ceiling, not only 8k-frame
        # fixtures. Generate two separate regular WAVs with bounded writes.
        frames = 2_000_000
        full = b"\x00\x00" * (4096 * 2)
        blocks, tail = divmod(frames, 4096)
        for path in (self.a, self.b):
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                for _ in range(blocks):
                    writer.writeframesraw(full)
                writer.writeframesraw(b"\x00" * (tail * 4))
        self.assertTrue(verify_repeatability(self.a, self.b)["repeatable_pcm"])
        with self.b.open("r+b") as f:
            f.seek(-4, os.SEEK_END)
            f.write(b"\x01\x00\x00\x00")
        self.assertFalse(verify_repeatability(self.a, self.b)["repeatable_pcm"])

    def test_short_pcm_is_not_silently_accepted(self):
        self.b.write_bytes(self.b.read_bytes()[:-128])
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.b)

    def test_malformed_or_missing_wav_is_refused_with_static_error(self):
        self.b.write_bytes(b"not a WAV")
        with self.assertRaisesRegex(RepeatabilityError, "^invalid, changed or incompatible source$"):
            verify_repeatability(self.a, self.b)
        self.b.unlink()
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.b)

    def test_symlink_and_fifo_fail_closed_without_blocking(self):
        self.b.unlink()
        os.symlink(self.a, self.b)
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.b)
        self.b.unlink()
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.b)
            with self.assertRaises(RepeatabilityError):
                verify_repeatability(self.a, self.b)

    def test_sparse_file_beyond_32m_is_refused_before_audio(self):
        with self.b.open("wb") as stream:
            stream.truncate(MAX_BYTES + 1)
        with patch.object(wave.Wave_read, "readframes",
                          side_effect=AssertionError("unexpected audio read")):
            with self.assertRaises(RepeatabilityError):
                verify_repeatability(self.a, self.b)

    def test_replace_original_name_during_read_is_refused(self):
        original = wave.Wave_read.readframes
        replaced = False
        def mutate(reader, count):
            nonlocal replaced
            if not replaced:
                replaced = True
                self.b.rename(self.root / "renamed.wav")
                make_wav(self.b, [0] * 8192)
            return original(reader, count)
        with patch.object(wave.Wave_read, "readframes", mutate):
            with self.assertRaises(RepeatabilityError):
                verify_repeatability(self.a, self.b)

    def test_unlink_during_read_is_refused(self):
        original = wave.Wave_read.readframes
        removed = False
        def mutate(reader, count):
            nonlocal removed
            if not removed:
                removed = True
                self.b.unlink()
            return original(reader, count)
        with patch.object(wave.Wave_read, "readframes", mutate):
            with self.assertRaises(RepeatabilityError):
                verify_repeatability(self.a, self.b)

    def test_changed_first_source_while_scanning_second_is_refused(self):
        original = wave.Wave_read.readframes
        count = 0
        def mutate(reader, frames):
            nonlocal count
            count += 1
            if count == 2:
                with self.a.open("r+b") as stream:
                    stream.seek(44)
                    stream.write(b"\x01\x02")
            return original(reader, frames)
        with patch.object(wave.Wave_read, "readframes", mutate):
            with self.assertRaises(RepeatabilityError):
                verify_repeatability(self.a, self.b)

    def test_cli_strict_and_success_output_do_not_expose_source(self):
        root = Path(__file__).resolve().parents[1]
        cmd = [sys.executable, "-m", "mixlab.quality.repeatability",
               str(self.a), str(self.b)]
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                                timeout=15)
        self.assertEqual(0, result.returncode)
        self.assertTrue(json.loads(result.stdout)["repeatable_pcm"])
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        make_wav(self.b, [0] * 8192)
        strict = subprocess.run(cmd + ["--strict"], cwd=root, capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(2, strict.returncode)
        self.assertFalse(json.loads(strict.stdout)["repeatable_pcm"])
        self.assertNotIn(str(self.root), strict.stdout + strict.stderr)

    def test_cli_invalid_and_help_are_static_redacted(self):
        root = Path(__file__).resolve().parents[1]
        cmd = [sys.executable, "-m", "mixlab.quality.repeatability"]
        help_run = subprocess.run(cmd + ["--help"], cwd=root, capture_output=True,
                                  text=True, timeout=15)
        self.assertEqual(0, help_run.returncode)
        self.assertIn("Usage:", help_run.stdout)
        invalid = subprocess.run(cmd + [str(self.a), str(self.root / "private-not-found.wav")],
                                 cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(3, invalid.returncode)
        self.assertEqual("", invalid.stdout)
        self.assertNotIn(str(self.root), invalid.stderr)

    def test_sources_remain_unchanged(self):
        before = self.a.read_bytes(), self.b.read_bytes()
        verify_repeatability(self.a, self.b)
        self.assertEqual(before, (self.a.read_bytes(), self.b.read_bytes()))


if __name__ == "__main__":
    unittest.main()
