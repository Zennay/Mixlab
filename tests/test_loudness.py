import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from mixlab.cli import benchmark, fixture
from mixlab.engine import write_wav
from mixlab.evaluation import aggregate, verify_pack
from mixlab.loudness import apply_gain, k_weighting, match_group, measure


def sine(path, rate=16000, seconds=1.2, amp=.1, channels=2, freq=997., silence=0.):
    frames = [(0.,) * channels] * round(silence * rate)
    frames += [(amp * math.sin(2 * math.pi * freq * i / rate),) * channels for i in range(round(seconds * rate))]
    write_wav(path, rate, frames)
    return path


class LoudnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_48k_coefficients_match_bs1770_table(self):
        shelf, highpass = k_weighting(48000)
        published = ((1.53512485958697, -2.69169618940638, 1.19839281085285, -1.69065929318241, .73248077421585),
                     (1., -2., 1., -1.99004745483398, .99007225036621))
        for ours, spec in zip(shelf + highpass, published[0] + published[1]):
            self.assertAlmostEqual(ours, spec, places=12)

    def test_reference_sines(self):
        # BS.1770: a 997 Hz sine at amplitude A in both stereo channels reads 20*log10(A) LUFS;
        # in a single (mono) channel it is 3.01 LU lower.
        for rate in (44100, 48000):
            stereo = measure(sine(self.root / f"s{rate}.wav", rate=rate, amp=.1, seconds=.8))
            mono = measure(sine(self.root / f"m{rate}.wav", rate=rate, amp=.5, channels=1, seconds=.8))
            self.assertAlmostEqual(stereo["integrated_lufs"], -20., delta=.02)
            self.assertAlmostEqual(mono["integrated_lufs"], -9.03, delta=.02)
            self.assertEqual(stereo["method"], "itu-r-bs.1770-4-integrated-sample-peak")

    def test_gates_ignore_silence_and_quiet_passages(self):
        plain = measure(sine(self.root / "plain.wav", seconds=3.))["integrated_lufs"]
        padded = measure(sine(self.root / "padded.wav", seconds=3., silence=2.))["integrated_lufs"]
        # Only the few 400 ms blocks straddling the onset pass the gates; an ungated
        # mean over 2 s silence + 3 s tone would read 10*log10(3/5) = -2.2 LU lower.
        self.assertAlmostEqual(plain, padded, delta=.3)
        self.assertGreater(padded, plain + 10 * math.log10(3 / 5) + 1.5)
        rate = 16000
        rng = random.Random(3)
        frames = [(rng.gauss(0, .2 if i < 3 * rate else .002),) * 2 for i in range(6 * rate)]
        write_wav(self.root / "loud-quiet.wav", rate, frames)
        write_wav(self.root / "loud.wav", rate, frames[:3 * rate])
        # The -40 dB tail falls below the relative gate and must not dilute the result.
        mixed, loud = (measure(self.root / name)["integrated_lufs"] for name in ("loud-quiet.wav", "loud.wav"))
        self.assertAlmostEqual(mixed, loud, delta=.3)
        self.assertGreater(mixed, loud + 10 * math.log10(1 / 2) + 2.)

    def test_silence_and_short_clips_have_no_loudness(self):
        write_wav(self.root / "silent.wav", 8000, [(0., 0.)] * 8000)
        self.assertIsNone(measure(self.root / "silent.wav")["integrated_lufs"])
        short = measure(sine(self.root / "short.wav", seconds=.3))
        self.assertIsNone(short["integrated_lufs"])
        self.assertEqual(short["gating_blocks"], 0)

    def test_rejects_unsupported_input(self):
        (self.root / "junk.wav").write_bytes(b"RIFF0000WAVE")
        with self.assertRaises(ValueError):
            measure(self.root / "junk.wav")
        (self.root / "link.wav").symlink_to(sine(self.root / "target.wav"))
        with self.assertRaisesRegex(ValueError, "regular"):
            measure(self.root / "link.wav")

    def test_apply_gain_attenuates_only_and_never_overwrites(self):
        source = sine(self.root / "src.wav", amp=.5)
        out = self.root / "out.wav"
        apply_gain(source, out, -6.)
        self.assertAlmostEqual(measure(out)["integrated_lufs"], measure(source)["integrated_lufs"] - 6, delta=.01)
        with self.assertRaisesRegex(ValueError, "exists"):
            apply_gain(source, out, -1.)
        for bad in (.5, float("nan"), True, -61):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                apply_gain(source, self.root / "bad.wav", bad)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["out.wav", "src.wav"])

    def test_match_group_equalizes_to_quietest(self):
        paths = {"quiet": sine(self.root / "q.wav", amp=.1), "loud": sine(self.root / "l.wav", amp=.4),
                 "bassy": sine(self.root / "b.wav", amp=.3, freq=60.)}
        out = self.root / "matched"
        out.mkdir()
        result = match_group(paths, out)
        target = result["target_lufs"]
        self.assertAlmostEqual(target, -20., delta=.05)
        self.assertEqual(result["members"]["quiet"]["gain_db"], 0.)
        for member in result["members"].values():
            self.assertLessEqual(member["gain_db"], 0)
            self.assertAlmostEqual(member["after"]["integrated_lufs"], target, delta=.1)

    def test_match_group_rejects_silence_and_format_mismatch(self):
        write_wav(self.root / "silent.wav", 16000, [(0., 0.)] * 19200)
        with self.assertRaisesRegex(ValueError, "silent"):
            match_group({"a": sine(self.root / "a.wav"), "b": self.root / "silent.wav"}, self.root)
        with self.assertRaisesRegex(ValueError, "share"):
            match_group({"a": self.root / "a.wav", "c": sine(self.root / "c.wav", seconds=2.)}, self.root)

    @unittest.skipUnless(hasattr(__import__("os"), "mkfifo"), "POSIX FIFO required")
    def test_fifo_is_refused_quickly_not_hung(self):
        import os
        fifo = self.root / "PRIVATE-pipe.wav"
        os.mkfifo(fifo)
        code = ("import sys; from mixlab.loudness import measure\n"
                "try:\n    measure(sys.argv[1])\nexcept ValueError:\n    sys.exit(3)\nsys.exit(0)")
        # Without O_NONBLOCK a read-only open of a writer-less FIFO blocks forever.
        run = subprocess.run([sys.executable, "-c", code, str(fifo)], capture_output=True, text=True,
                             timeout=20, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(run.returncode, 3, run.stderr)

    def test_symlinked_parent_directory_is_refused(self):
        real = self.root / "real"
        real.mkdir()
        sine(real / "x.wav")
        (self.root / "alias").symlink_to(real, target_is_directory=True)
        self.assertIsNotNone(measure(real / "x.wav")["integrated_lufs"])
        with self.assertRaisesRegex(ValueError, "symlinks"):
            measure(self.root / "alias" / "x.wav")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            apply_gain(self.root / "alias" / "x.wav", self.root / "out.wav", -1.)
        self.assertFalse((self.root / "out.wav").exists())

    def test_apply_gain_refuses_bytes_other_than_measured(self):
        source = sine(self.root / "src.wav")
        with self.assertRaisesRegex(ValueError, "changed"):
            apply_gain(source, self.root / "out.wav", -1., expected_sha256="0" * 64)
        self.assertFalse((self.root / "out.wav").exists())
        self.assertEqual([p.name for p in self.root.iterdir()], ["src.wav"])

    def test_match_group_detects_source_swapped_after_measurement(self):
        # Same loudness, different audible content: matching by LUFS alone would pass.
        paths = {"a": sine(self.root / "a.wav", amp=.1), "b": sine(self.root / "b.wav", amp=.2)}
        decoy = sine(self.root / "decoy.wav", amp=.2, freq=1001.)
        self.assertAlmostEqual(measure(decoy)["integrated_lufs"], measure(paths["b"])["integrated_lufs"], delta=.05)
        original = measure
        def measure_then_swap(path):
            result = original(path)
            if Path(path) == paths["b"]:
                Path(decoy).replace(paths["b"])
            return result
        out = self.root / "matched"
        out.mkdir()
        with mock.patch("mixlab.loudness.measure", side_effect=measure_then_swap), \
                self.assertRaisesRegex(ValueError, "changed"):
            match_group(paths, out)
        self.assertFalse((out / "b-matched.wav").exists())

    def test_cli_does_not_disclose_private_paths(self):
        secret = self.root / "PRIVATE-client-wedding-set" / "do-not-log.wav"
        bad = self.root / "PRIVATE-corrupt-upload.wav"
        bad.write_bytes(b"not a wav")
        for target in (secret, bad):
            with self.subTest(target=target.name):
                run = subprocess.run([sys.executable, "-m", "mixlab", "loudness", str(target)],
                                     capture_output=True, text=True, timeout=60,
                                     cwd=Path(__file__).resolve().parents[1])
                self.assertEqual(run.returncode, 2)
                for stream in (run.stdout, run.stderr):
                    self.assertNotIn("PRIVATE", stream)
                    self.assertNotIn(str(self.root), stream)
                self.assertIn("input 1", run.stderr)
        ok = subprocess.run([sys.executable, "-m", "mixlab", "loudness", str(sine(self.root / "ok.wav"))],
                            capture_output=True, text=True, timeout=60, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(ok.returncode, 0)
        self.assertNotIn("sha256", ok.stdout)
        self.assertNotIn(str(self.root), ok.stdout)


class PackLoudnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        manifest = fixture(cls.root / "library")
        cls.pack = cls.root / "pack"
        benchmark(manifest, cls.pack, seed=5)
        cls.raw = cls.root / "raw-pack"
        benchmark(manifest, cls.raw, seed=5, loudness_match=False)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_review_files_are_loudness_matched_and_bound(self):
        receipt, evidence, trials = verify_pack(self.pack)
        self.assertEqual(evidence["loudness_matching"], "bs1770-4-attenuate-to-quietest-per-pair")
        raw = [measure(p)["integrated_lufs"] for p in sorted((self.raw / "review").glob("*.wav"))]
        matched = [measure(p)["integrated_lufs"] for p in sorted((self.pack / "review").glob("*.wav"))]
        self.assertGreater(max(raw) - min(raw), .3)
        self.assertLessEqual(max(matched) - min(matched), .1)
        for row in evidence["renders"]:
            if row["loudness"]["gain_db"]:
                self.assertNotEqual(row["render_sha256"], row["output_sha256"])
            self.assertLessEqual(row["loudness"]["gain_db"], 0)
        self.assertNotIn("not loudness-normalized", evidence["limitations"])

    def test_aggregation_flags_unmatched_packs_only(self):
        def vote(pack):
            receipt, _, trials = verify_pack(pack)
            path = self.root / f"{pack.name}-vote.json"
            path.write_text(json.dumps({"schema_version": 1, "pack_id": receipt["pack_id"], "reviewer": "l1",
                                        "ratings": [{"trial": t, "preference": "Tie"} for t in trials]}))
            return path
        matched = aggregate(self.pack, [vote(self.pack)])
        self.assertFalse(any("integrated_loudness_mismatch" in c["warnings"] for c in matched["audio_confounds"]))
        # The synthetic fixture's raw spread is below the 0.5 LU default; tighten it so
        # unmatched packs are flagged while matched packs (identical targets) are not.
        with mock.patch("mixlab.evaluation.LOUDNESS_TOLERANCE_LU", .1):
            raw = aggregate(self.raw, [vote(self.raw)])
            self.assertFalse(aggregate(self.pack, [vote(self.pack)])["audio_confounds"])
        self.assertTrue(any("integrated_loudness_mismatch" in c["warnings"] for c in raw["audio_confounds"]))


if __name__ == "__main__":
    unittest.main()
