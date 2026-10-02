import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.engine import FAMILY_NAMES, load_wav, measure, render, write_wav
from mixlab.models import Recipe, Segment, Track, TransitionCandidate


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b = self.root / "a.wav", self.root / "b.wav"
        self.sr = 8000
        self.frames = [(0.2 * math.sin(i * 0.1), 0.0) for i in range(8000)]
        write_wav(self.a, self.sr, self.frames)
        write_wav(self.b, self.sr, [(0.1 * math.cos(i * 0.15), 0.0) for i in range(8000)])

    def test_all_families_deterministic_equal_duration_gain_and_stereo_independence(self):
        metadata = []
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                one, two = self.root / (family + "1.wav"), self.root / (family + "2.wav")
                recipe = Recipe(family=family, beats=1)
                m1 = render(self.a, self.b, one, recipe)
                m2 = render(self.a, self.b, two, recipe)
                self.assertEqual(one.read_bytes(), two.read_bytes())
                self.assertEqual(m1["output_sha256"], m2["output_sha256"])
                _, result = load_wav(one)
                self.assertTrue(all(frame[1] == 0 for frame in result))
                self.assertGreater(m1["metrics"]["rms"], 0)
                metadata.append(m1)
        self.assertEqual({m["frames"] for m in metadata}, {4000})
        self.assertEqual(len({m["gain_linear"] for m in metadata}), 1)

    def test_manual_offsets_and_endpoints(self):
        _, af = load_wav(self.a)
        _, bf = load_wav(self.b)
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                output = self.root / (family + ".wav")
                meta = render(self.a, self.b, output,
                              Recipe(family=family, beats=1, a_start=0.125, b_start=0.25))
                _, result = load_wav(output)
                gain = meta["gain_linear"]
                self.assertAlmostEqual(result[0][0], af[1000][0] * gain, delta=1 / 32768)
                self.assertAlmostEqual(result[-1][0], bf[2000 + 3999][0] * gain, delta=1 / 32768)
                self.assertEqual(meta["start_frames"], {"a": 1000, "b": 2000})

    def test_mono_and_channel_mismatch(self):
        mono = self.root / "mono.wav"
        write_wav(mono, self.sr, [(0.1,)] * 8000)
        output = self.root / "out.wav"
        self.assertEqual(render(mono, mono, output, Recipe(beats=1))["channels"], 1)
        with self.assertRaisesRegex(ValueError, "identical"):
            render(self.a, mono, self.root / "mismatch.wav", Recipe(beats=1))

    def test_rate_mismatch_and_short_clips(self):
        other = self.root / "other.wav"
        write_wav(other, 16000, self.frames)
        with self.assertRaisesRegex(ValueError, "identical"):
            render(self.a, other, self.root / "out.wav", Recipe(beats=1))
        with self.assertRaisesRegex(ValueError, "too short"):
            render(self.a, self.b, self.root / "out.wav", Recipe(beats=8))

    def test_invalid_recipes_and_no_implicit_tempo_conversion(self):
        for values in ({"family": "magic"}, {"bpm": 0}, {"bpm": float("nan")},
                       {"beats": 0}, {"beats": 1.5}, {"beats": True},
                       {"a_start": -1}, {"b_start": float("inf")},
                       {"gain_db": 1}, {"a_bpm": 121}, {"b_bpm": float("nan")}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Recipe(**values)

    def test_unsupported_and_malformed_wav(self):
        invalid = self.root / "invalid.wav"
        invalid.write_bytes(b"not-a-wave")
        with self.assertRaises(ValueError):
            load_wav(invalid)
        for width, channels in ((1, 1), (3, 2), (2, 3)):
            with wave.open(str(invalid), "wb") as output:
                output.setparams((channels, width, self.sr, 0, "NONE", "not compressed"))
                output.writeframes(bytes(100 * channels * width))
            with self.assertRaisesRegex(ValueError, "PCM16"):
                load_wav(invalid)
        invalid.write_bytes(self.a.read_bytes()[:-20])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            load_wav(invalid)

    def test_source_overwrite_rejected(self):
        before = self.a.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            render(self.a, self.b, self.a, Recipe(beats=1))
        self.assertEqual(self.a.read_bytes(), before)

    def test_existing_candidate_is_preserved(self):
        output = self.root / "candidate.wav"
        output.write_bytes(b"existing result")
        with self.assertRaisesRegex(ValueError, "already exists"):
            render(self.a, self.b, output, Recipe(beats=1))
        self.assertEqual(output.read_bytes(), b"existing result")

    def test_input_resource_bounds(self):
        with patch("mixlab.engine.MAX_INPUT_FRAMES", 100):
            with self.assertRaisesRegex(ValueError, "frames"):
                load_wav(self.a)
        with patch("mixlab.engine.MAX_INPUT_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "input limit"):
                load_wav(self.a)

    def test_stereo_channels_process_independently(self):
        # Compare right-channel DSP against the same signal processed as mono.
        stereo_a, stereo_b = self.root / "sa.wav", self.root / "sb.wav"
        mono_a, mono_b = self.root / "ma.wav", self.root / "mb.wav"
        right_a = [(0.15 * math.sin(i * 0.13),) for i in range(8000)]
        right_b = [(0.12 * math.cos(i * 0.07),) for i in range(8000)]
        write_wav(mono_a, self.sr, right_a)
        write_wav(mono_b, self.sr, right_b)
        write_wav(stereo_a, self.sr, [(0.3, f[0]) for f in right_a])
        write_wav(stereo_b, self.sr, [(-0.2, f[0]) for f in right_b])
        for family in FAMILY_NAMES:
            with self.subTest(family=family):
                so, mo = self.root / (family + "-stereo.wav"), self.root / (family + "-mono.wav")
                recipe = Recipe(family=family, beats=1)
                render(stereo_a, stereo_b, so, recipe)
                render(mono_a, mono_b, mo, recipe)
                _, stereo = load_wav(so)
                _, mono = load_wav(mo)
                self.assertEqual([f[1] for f in stereo], [f[0] for f in mono])

    def test_write_rejects_invalid_frames(self):
        for frames in ([], [(0.0, 0.0, 0.0)], [(0.0,), (0.0, 0.0)], [(float("nan"),)]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                write_wav(self.root / "bad.wav", self.sr, frames)

    def test_metrics_known_values(self):
        metrics = measure([(0.5, 0.0), (-0.5, 0.0)])
        self.assertEqual(metrics["peak"], 0.5)
        self.assertEqual(metrics["dc_per_channel"], [0.0, 0.0])
        self.assertEqual(metrics["max_sample_jump"], 1.0)
        self.assertEqual(metrics["clipping_samples"], 0)
        self.assertAlmostEqual(metrics["rms"], math.sqrt(0.125))
        self.assertEqual(measure([(1.2,), (-1.1,)])["clipping_samples"], 2)

    def test_schema_preserves_rights_and_provenance(self):
        track = Track("a", "clip.wav", bpm=120, rights_status="owned",
                      provenance={"origin": "synthetic"})
        self.assertEqual(track.provenance["origin"], "synthetic")
        candidate = TransitionCandidate("c", "a", "b", Recipe(), "out.wav")
        self.assertEqual(candidate.to_dict()["recipe"]["family"], "baseline")
        self.assertEqual(candidate.rights_status, "unknown")
        with self.assertRaises(ValueError):
            Track("a", "clip.wav", rights_status="assumed")
        with self.assertRaises(ValueError):
            Segment("a", 0, 8, alignment_source="automatic")


if __name__ == "__main__":
    unittest.main()
