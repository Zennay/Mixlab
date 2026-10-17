import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from mixlab.analysis import analyze_cached
from mixlab.analysis.key import KEYS, PITCH_CLASSES, ChromaKeyProvider, camelot, estimate, key_score
from mixlab.engine import write_wav


def progression(path, key, rate=8000, seconds=6., drums=0., cents=0., channels=2):
    """I-IV-V-I (major) or i-iv-V-i with raised leading tone (minor), three harmonics."""
    tonic = PITCH_CLASSES.index(key.split()[0])
    third = 3 if key.endswith("minor") else 4
    chords = [(0, third, 7), (5, 5 + third, 12), (7, 11, 14), (0, third, 7)]
    rng = random.Random(4)
    frames = []
    for i in range(round(rate * seconds)):
        t = i / rate
        chord = chords[min(3, int(4 * t / seconds))]
        v = 0.
        for k, interval in enumerate(chord + (chord[0] - 12,)):
            f = 220 * 2 ** ((tonic + interval - 9 - (12 if k == 3 else 0)) / 12 + cents / 1200)
            v += sum(.08 / h * math.sin(2 * math.pi * f * h * t) for h in (1, 2, 3))
        v += drums * (math.sin(2 * math.pi * 55 * t) * math.exp(-(t % .5) * 30)
                      + rng.gauss(0, .3) * math.exp(-((t + .25) % .5) * 60))
        frames.append((v,) * channels)
    write_wav(path, rate, frames)
    return path


class KeyHelpersTests(unittest.TestCase):
    def test_camelot_wheel(self):
        expected = {"C major": "8B", "A minor": "8A", "G major": "9B", "E minor": "9A",
                    "B major": "1B", "G# minor": "1A", "F major": "7B", "D minor": "7A"}
        for key, code in expected.items():
            self.assertEqual(camelot(key), code)
        self.assertEqual(len({camelot(k) for k in KEYS}), 24)

    def test_mirex_weights(self):
        self.assertEqual(key_score("C major", "C major"), 1.)
        self.assertEqual(key_score("C major", "G major"), .5)
        self.assertEqual(key_score("A minor", "D minor"), .5)
        self.assertEqual(key_score("C major", "A minor"), .3)
        self.assertEqual(key_score("A minor", "C major"), .3)
        self.assertEqual(key_score("C major", "C minor"), .2)
        self.assertEqual(key_score("C major", "F# major"), 0.)
        self.assertEqual(key_score("C major", None), 0.)
        for bad in ("H major", "C dorian", "C", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                key_score(bad, "C major")


class ChromaKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_all_24_synthetic_keys(self):
        # Synthetic triads verify mechanics only; real-audio accuracy is unmeasured.
        for key in KEYS:
            with self.subTest(key=key):
                result = estimate(progression(self.root / "k.wav", key))
                self.assertEqual(result["key"], key, result["candidates"])
                self.assertIsNone(result["abstain_reason"])
                (self.root / "k.wav").unlink()

    def test_drums_resampling_mono_and_detuning(self):
        cases = [("E minor", dict(rate=44100, drums=.5)), ("A# major", dict(rate=48000, drums=.5, channels=1)),
                 ("D major", dict(rate=22050, cents=40))]
        for key, options in cases:
            with self.subTest(key=key, **options):
                self.assertEqual(estimate(progression(self.root / f"{key[0]}.wav", key, seconds=4., **options))["key"], key)

    def test_abstains_without_tonal_evidence(self):
        rng = random.Random(9)
        signals = {"noise": [(rng.gauss(0, .2),) * 2 for _ in range(8000 * 5)],
                   "clicks": [(.6 * math.exp(-(i / 8000 % .5) * 80),) * 2 for i in range(8000 * 5)],
                   "silence": [(0., 0.)] * (8000 * 5),
                   "short": [(.3 * math.sin(i * .2),) * 2 for i in range(4000)]}
        for name, frames in signals.items():
            with self.subTest(name=name):
                write_wav(self.root / f"{name}.wav", 8000, frames)
                result = estimate(self.root / f"{name}.wav")
                self.assertIsNone(result["key"])
                self.assertTrue(result["abstain_reason"])

    def test_provider_labels_heuristic_and_caches(self):
        wav = progression(self.root / "a.wav", "F# minor")
        analysis = ChromaKeyProvider().analyze(wav)
        self.assertEqual(analysis.key, "F# minor")
        self.assertEqual(analysis.key_source, "measured-heuristic")
        self.assertEqual(analysis.timing_source, "unavailable")
        self.assertIsNone(analysis.bpm)
        self.assertGreater(analysis.key_confidence, 0)
        self.assertEqual(analysis.key_candidates[0][0], "F# minor")
        cache = self.root / "cache"
        first = analyze_cached(wav, cache, ChromaKeyProvider())
        self.assertEqual(first, analyze_cached(wav, cache, ChromaKeyProvider()))
        self.assertNotIn(str(self.root), next(cache.glob("*.json")).read_text())
        write_wav(self.root / "n.wav", 8000, [(0., 0.)] * 40000)
        silent = ChromaKeyProvider().analyze(self.root / "n.wav")
        self.assertIsNone(silent.key)
        self.assertEqual(silent.key_source, "unavailable")
        self.assertEqual(silent.key_confidence, 0.)

    def test_cli_provider_choice(self):
        wav = progression(self.root / "b.wav", "C major", seconds=4.)
        run = subprocess.run([sys.executable, "-m", "mixlab.analysis", str(wav), "--cache", str(self.root / "c"),
                              "--provider", "chroma-key"], capture_output=True, text=True, timeout=120,
                             cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["key"], "C major")


if __name__ == "__main__":
    unittest.main()
