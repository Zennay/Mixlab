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
             "distinct_output_files_verified": True,
             "independent_render_executions_proven": False,
             "format_and_frame_count_verified": True,
             "technical_review_required": False,
             "human_preference_test_required": True}, report
        )
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("hash", json.dumps(report).lower())
        self.assertNotIn("score", json.dumps(report).lower())
        self.assertFalse(report["independent_render_executions_proven"])

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

    def test_two_equally_invalid_receipts_are_not_mistaken_for_consistency(self):
        import copy
        one, two, ra, rb = self._render_fixture_with_receipts()
        mutations = (
            lambda r: r.__setitem__("duration_seconds", 0),
            lambda r: r.__setitem__("gain_linear", -1),
            lambda r: r["start_frames"].__setitem__("a", -1),
            lambda r: r["start_frames"].__setitem__("b", True),
            lambda r: r["recipe"].__setitem__("bpm", 0),
            lambda r: r["recipe"].__setitem__("beats", -2),
            lambda r: r["recipe"].__setitem__("family", ""),
            lambda r: r.__setitem__("tempo_source", ""),
            lambda r: r.__setitem__("alignment_source", None),
        )
        for mutate in mutations:
            with self.subTest(case=mutations.index(mutate)):
                left = copy.deepcopy(ra)
                right = copy.deepcopy(rb)
                mutate(left)
                mutate(right)
                with self.assertRaisesRegex(
                    RepeatabilityError, "^invalid, changed or incompatible source$"
                ):
                    verify_repeatability(one, two, receipts=(left, right))
        self.assertTrue(verify_repeatability(
            one, two, receipts=(ra, rb)
        )["render_receipts_consistent"])

    def test_two_matching_but_physically_inconsistent_receipts_fail_closed(self):
        # Two separately stored files and two internally matching statements
        # do not prove a valid render contract. Validate frame/tempo,
        # duration, gain and cue offsets against the *actual* output shape.
        import copy
        one, two, ra, rb = self._render_fixture_with_receipts()
        updates = (
            lambda r: r.__setitem__("duration_seconds", r["duration_seconds"] + 1),
            lambda r: r.__setitem__("gain_linear", r["gain_linear"] * .8),
            lambda r: r["start_frames"].__setitem__("a", 1),
            lambda r: r["start_frames"].__setitem__("b", 1),
            lambda r: r["recipe"].__setitem__("bpm", 130),
            lambda r: r["recipe"].__setitem__("beats", 2),
            lambda r: r["recipe"].__setitem__("gain_db", -12),
            lambda r: r["recipe"].__setitem__("a_start", .15),
            lambda r: r["recipe"].__setitem__("b_start", .25),
        )
        for index, mutate in enumerate(updates):
            with self.subTest(case=index):
                a, b = copy.deepcopy(ra), copy.deepcopy(rb)
                mutate(a)
                mutate(b)
                with self.assertRaisesRegex(
                    RepeatabilityError, "^invalid, changed or incompatible source$"
                ):
                    verify_repeatability(one, two, receipts=(a, b))
        self.assertTrue(verify_repeatability(one, two, receipts=(ra, rb))[
            "render_receipts_consistent"
        ])

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

    def test_two_equal_receipts_cannot_spoof_typed_wav_metadata_or_family(self):
        # Python considers bool == 1 and integral floats == ints. A signed
        # renderer receipt must retain exact JSON schema types, even when
        # both receipts carry the same wrong metadata.
        import copy
        one, two, original_a, original_b = self._render_fixture_with_receipts()
        mutate_both = (
            lambda r: r.__setitem__("schema_version", True),
            lambda r: r.__setitem__("schema_version", 1.0),
            lambda r: r.__setitem__("channels", True),
            lambda r: r.__setitem__("channels", 1.0),
            lambda r: r.__setitem__("sample_rate", 8000.0),
            lambda r: r.__setitem__("frames", 4000.0),
            lambda r: r["recipe"].__setitem__("family", "invented_unregistered_dsp"),
        )
        for index, mutation in enumerate(mutate_both):
            with self.subTest(case=index):
                left, right = copy.deepcopy(original_a), copy.deepcopy(original_b)
                mutation(left)
                mutation(right)
                with self.assertRaisesRegex(
                    RepeatabilityError, "^invalid, changed or incompatible source$"
                ):
                    verify_repeatability(one, two, receipts=(left, right))
        self.assertTrue(verify_repeatability(
            one, two, receipts=(original_a, original_b)
        )["render_receipts_consistent"])

    def test_invalid_receipt_is_rejected_before_any_private_pcm_read(self):
        # A contradictory or typed-spoofed metadata declaration must never
        # cause the quality gate to consume private PCM, even transiently.
        # Both public outputs and exceptions remain path-agnostic.
        import copy
        one, two, ra, rb = self._render_fixture_with_receipts()
        invalid_pairs = []
        for field, value in (("schema_version", True),
                             ("sample_rate", 8000.0),
                             ("frames", 4000.0),
                             ("channels", True),
                             ("duration_seconds", 123)):
            a, b = copy.deepcopy(ra), copy.deepcopy(rb)
            a[field] = value
            b[field] = value
            invalid_pairs.append((a, b))
        for field, value in (("family", "not_a_family"),
                             ("beats", 2)):
            a, b = copy.deepcopy(ra), copy.deepcopy(rb)
            a["recipe"][field] = value
            b["recipe"][field] = value
            invalid_pairs.append((a, b))
        with patch.object(wave.Wave_read, "readframes",
                          side_effect=AssertionError("private PCM was read")), patch(
            "mixlab.quality.repeatability._digest_open_file",
            side_effect=AssertionError("private file was hashed")
        ):
            for index, pair in enumerate(invalid_pairs):
                with self.subTest(case=index):
                    with self.assertRaisesRegex(
                        RepeatabilityError, "^invalid, changed or incompatible source$"
                    ):
                        verify_repeatability(one, two, receipts=pair)

    def test_two_matching_overlong_recipes_cannot_bypass_m1_120s_limit(self):
        # Recipe.__post_init__ rejects 128s (64 beats at 30 BPM); the
        # verifier must not accept two equally invalid, self-declared M1
        # receipts simply because both WAVs physically have 128s of PCM.
        import hashlib
        import struct
        from mixlab.models import Recipe

        rate, frames = 8000, 64 * 60 * 8000 // 30
        self.assertEqual(1_024_000, frames)
        with self.assertRaises(ValueError):
            Recipe(family="baseline", bpm=30, beats=64, gain_db=0)

        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + frames * 2,
            b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16,
            b"data", frames * 2,
        )
        for path in (self.a, self.b):
            with path.open("wb") as stream:
                stream.write(header)
                stream.truncate(44 + frames * 2)
        with self.a.open("rb") as stream:
            sha_a = hashlib.file_digest(stream, "sha256").hexdigest()
        with self.b.open("rb") as stream:
            sha_b = hashlib.file_digest(stream, "sha256").hexdigest()
        receipt = {
            "schema_version": 1,
            "engine_version": "synthetic-duration-guard-v1",
            "recipe": {
                "family": "baseline", "bpm": 30, "beats": 64,
                "a_start": 0.0, "b_start": 0.0, "gain_db": 0,
                "a_bpm": None, "b_bpm": None,
            },
            "sample_rate": rate, "channels": 1, "frames": frames,
            "duration_seconds": 128, "gain_linear": 1,
            "start_frames": {"a": 0, "b": 0},
            "alignment_source": "synthetic-only",
            "tempo_source": "synthetic-only",
            "sources": [{"sha256": "a" * 64}, {"sha256": "b" * 64}],
        }
        # Out-of-contract 128s admission must refuse before any private PCM.
        with patch.object(wave.Wave_read, "readframes",
                          side_effect=AssertionError("private PCM read too early")):
            with self.assertRaisesRegex(
                RepeatabilityError, "^invalid, changed or incompatible source$"
            ):
                verify_repeatability(
                    self.a, self.b,
                    receipts=(dict(receipt, output_sha256=sha_a),
                              dict(receipt, output_sha256=sha_b)),
                )

        # The legal exact boundary of 120s (64 beats at 32 BPM) remains
        # accepted; no arbitrary <120s restriction or silent regression.
        frames = 120 * rate
        self.assertEqual(960_000, frames)
        self.assertEqual(120, 64 * 60 / 32)
        self.assertIsInstance(Recipe(family="baseline", bpm=32, beats=64,
                                     gain_db=0), Recipe)
        for path in (self.a, self.b):
            with path.open("r+b") as stream:
                stream.seek(4)
                stream.write(struct.pack("<I", 36 + frames * 2))
                stream.seek(40)
                stream.write(struct.pack("<I", frames * 2))
                stream.truncate(44 + frames * 2)
        with self.a.open("rb") as stream:
            sha_a = hashlib.file_digest(stream, "sha256").hexdigest()
        with self.b.open("rb") as stream:
            sha_b = hashlib.file_digest(stream, "sha256").hexdigest()
        receipt["recipe"]["bpm"] = 32
        receipt["frames"] = frames
        receipt["duration_seconds"] = 120
        verdict = verify_repeatability(
            self.a, self.b,
            receipts=(dict(receipt, output_sha256=sha_a),
                      dict(receipt, output_sha256=sha_b)),
        )
        self.assertTrue(verdict["repeatable_pcm"])
        self.assertTrue(verdict["render_receipts_consistent"])

    def test_untrusted_receipt_size_and_nesting_are_rejected_before_serialization(self):
        # JSON serialization *before* checking the 16KiB cap can allocate
        # arbitrarily large data on hostile private metadata. The validator
        # must first bound strings, collection nodes, depth and cycles.
        import copy
        one, two, ra, rb = self._render_fixture_with_receipts()
        cyclic = {}
        cyclic["again"] = cyclic
        too_deep = {}
        pointer = too_deep
        for i in range(25):
            child = {}
            pointer["item"] = child
            pointer = child
        oversized = (
            dict(rb, comment="private" * 400000),
            dict(rb, extras={str(i): i for i in range(250)}),
            dict(rb, extras=too_deep),
            dict(rb, extras=cyclic),
        )
        for index, bad in enumerate(oversized):
            with self.subTest(kind=index), patch(
                "mixlab.quality.repeatability.json.dumps",
                side_effect=AssertionError("serialization before admission")
            ):
                with self.assertRaisesRegex(
                    RepeatabilityError, "^invalid, changed or incompatible source$"
                ):
                    verify_repeatability(one, two, receipts=(bad, ra))
        self.assertTrue(verify_repeatability(
            one, two, receipts=(ra, rb)
        )["render_receipts_consistent"])

    def test_legacy_and_streaming_dsp_pcm_parity_for_shared_m1_recipes(self):
        # Migration guard: current bounded streaming DSP should preserve the
        # old in-memory renderer's PCM on the mutually supported PCM16 cases.
        # Each renderer's engine_version differs, so this checks *PCM only*:
        # the optional private receipt mode correctly refuses version drift.
        import math
        from mixlab.engine import render as legacy_render
        from mixlab.dsp import render as streaming_render
        from mixlab.models import FAMILY_NAMES, Recipe

        for rate in (8000, 16000):
            with self.subTest(rate=rate):
                size = rate
                signal_a = self.root / f"parity-a-{rate}.wav"
                signal_b = self.root / f"parity-b-{rate}.wav"
                make_wav(signal_a, [
                    value for i in range(size)
                    for value in (int(2300 * math.sin(i * .093)),
                                  int(3100 * math.cos(i * .071)))
                ], channels=2, rate=rate)
                make_wav(signal_b, [
                    value for i in range(size)
                    for value in (int(2200 * math.cos(i * .081)),
                                  int(2600 * math.sin(i * .119)))
                ], channels=2, rate=rate)
                for family in FAMILY_NAMES:
                    with self.subTest(family=family):
                        recipe = Recipe(family=family, beats=1, gain_db=-3,
                                        a_start=0.05, b_start=0.10)
                        first = self.root / f"legacy-{rate}-{family}.wav"
                        second = self.root / f"stream-{rate}-{family}.wav"
                        legacy = legacy_render(signal_a, signal_b, first, recipe)
                        streamed = streaming_render(signal_a, signal_b, second,
                                                    recipe, block_frames=31)
                        self.assertEqual(legacy["frames"], streamed["frames"])
                        self.assertEqual(legacy["output_sha256"],
                                         streamed["output_sha256"])
                        self.assertTrue(verify_repeatability(first, second)["repeatable_pcm"])
                        with self.assertRaises(RepeatabilityError):
                            verify_repeatability(
                                first, second, receipts=(legacy, streamed)
                            )  # Different engine versions are not one receipt contract.

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

        # Also exercise the *receipt-bound* full-capacity path rather than
        # measuring memory only for the bare PCM comparator. These declared
        # input hashes are synthetic fixture claims, not provenance evidence.
        import hashlib
        with self.a.open("rb") as raw_a:
            output_a = hashlib.file_digest(raw_a, "sha256").hexdigest()
        with self.b.open("rb") as raw_b:
            output_b = hashlib.file_digest(raw_b, "sha256").hexdigest()
        fixture = {
            "schema_version": 1,
            "engine_version": "synthetic-capacity-check-v1",
            "recipe": {"family": "baseline", "bpm": 92.16, "beats": 64,
                       "a_start": 0.0, "b_start": 0.0, "gain_db": 0.0,
                       "a_bpm": None, "b_bpm": None},
            "sample_rate": 48000,
            "channels": 2,
            "frames": frames,
            "duration_seconds": frames / 48000,
            "gain_linear": 1,
            "start_frames": {"a": 0, "b": 0},
            "alignment_source": "synthetic-only",
            "tempo_source": "synthetic-only",
            "sources": [{"sha256": "a" * 64}, {"sha256": "b" * 64}],
        }
        receipt_a = dict(fixture, output_sha256=output_a)
        receipt_b = dict(fixture, output_sha256=output_b)
        before = verify_repeatability(self.a, self.b,
                                      receipts=(receipt_a, receipt_b))
        self.assertTrue(before["repeatable_pcm"])
        self.assertTrue(before["render_receipts_consistent"])

        with self.b.open("r+b") as f:
            f.seek(-4, os.SEEK_END)
            f.write(b"\x01\x00\x00\x00")
        self.assertFalse(verify_repeatability(self.a, self.b)["repeatable_pcm"])
        # A stale digest is an admission error, not a usable A/B verdict.
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, self.b,
                                 receipts=(receipt_a, receipt_b))
        with self.b.open("rb") as raw_b:
            updated_b = hashlib.file_digest(raw_b, "sha256").hexdigest()
        updated_receipt = dict(receipt_b, output_sha256=updated_b)
        after = verify_repeatability(self.a, self.b,
                                     receipts=(receipt_a, updated_receipt))
        self.assertFalse(after["repeatable_pcm"])
        self.assertTrue(after["technical_review_required"])
        self.assertTrue(after["render_receipts_consistent"])

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

    def test_parent_directory_symlink_cannot_redirect_private_wav(self):
        # O_NOFOLLOW on the final WAV basename does NOT prevent traversing
        # symlinked parent directories. No private PCM read is allowed until
        # every pathname component has been admitted.
        parent = self.root / "source-directory"
        parent.mkdir()
        intended = parent / "copied-render.wav"
        intended.write_bytes(self.b.read_bytes())
        alias = self.root / "redirected-directory"
        alias.symlink_to(parent, target_is_directory=True)
        with patch.object(
            wave.Wave_read, "readframes",
            side_effect=AssertionError("private PCM read before safe path admission")
        ):
            with self.assertRaisesRegex(
                RepeatabilityError, "^invalid, changed or incompatible source$"
            ):
                verify_repeatability(self.a, alias / intended.name)

        nested = self.root / "nested"
        nested.mkdir()
        middle = nested / "alias"
        middle.symlink_to(parent, target_is_directory=True)
        with self.assertRaises(RepeatabilityError):
            verify_repeatability(self.a, middle / intended.name)

        # Same file under its genuine, symlink-free directory remains valid.
        self.assertTrue(
            verify_repeatability(self.a, intended)["repeatable_pcm"]
        )

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
