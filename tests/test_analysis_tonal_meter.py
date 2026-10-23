from array import array
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
import wave
from mixlab.analysis import ManualProvider
from mixlab.analysis.meter import AccentMeterProvider, main as meter_main
from mixlab.analysis.tonal import (KEYS, MAJOR, MINOR, ChromaKeyProvider, key_report,
                                   key_score, key_scores, main as key_main)

RATE = 8000


def write(path, values, channels=1):
    pcm = array("h", (max(-32767, min(32767, round(v))) for v in values))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels); out.setsampwidth(2); out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


def midi_hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def triad(root, minor=False):
    return [root, root + (3 if minor else 4), root + 7, root + 12]


def cadence(tonic, minor):
    """i/I - iv/IV - V - i/I with a harmonic-minor leading tone."""
    return [triad(tonic, minor), triad(tonic + 5, minor), triad(tonic + 7), triad(tonic, minor)]


def chords(path, progression, stereo=False, seconds=2., repeats=2):
    out = []
    for _ in range(repeats):
        for chord in progression:
            freqs = [midi_hz(m) for m in chord]
            for i in range(int(RATE * seconds)):
                t = i / RATE
                envelope = min(1, t * 20) * math.exp(-t * .6)
                v = 9000 * envelope * sum(sum(math.sin(2 * math.pi * f * h * t) / h for h in (1, 2, 3))
                                          for f in freqs) / len(freqs)
                out.extend((v, -v) if stereo else (v,))
    write(path, out, 2 if stereo else 1)


def song(path, bpm=128, bars=24, offset_beats=1, lead=.25, accent=True, phrase=8):
    """Kick-accented downbeats, hats on every beat, I-IV-V-I bars, 8-bar sections."""
    period = 60 / bpm
    total_beats = offset_beats + bars * 4
    pcm = [0.] * int((lead + total_beats * period + .5) * RATE)
    section_a = cadence(48, False)
    section_b = cadence(45, True)
    for beat in range(total_beats):
        index = beat - offset_beats
        bar = index // 4 if index >= 0 else 0
        section = (bar // phrase) % 2
        loud = 1. if section == 0 else .55
        chord = (section_a if section == 0 else section_b)[bar % 4]
        downbeat = accent and index >= 0 and index % 4 == 0
        start = int((lead + beat * period) * RATE)
        for n in range(int(period * RATE)):
            if start + n >= len(pcm):
                break
            t = n / RATE
            v = .35 * math.exp(-t * 60) * math.sin(2 * math.pi * 1500 * t) * ((n * 7919) % 13 - 6) / 6
            if downbeat:
                v += .7 * math.exp(-t * 12) * math.sin(2 * math.pi * (55 + 60 * math.exp(-t * 30)) * t)
            else:
                v += .25 * math.exp(-t * 25) * math.sin(2 * math.pi * 80 * t)
            v += loud * .12 * sum(math.sin(2 * math.pi * midi_hz(m) * t) for m in chord[:3])
            pcm[start + n] += v
    write(path, (9000 * v for v in pcm))
    beats = [round(lead + b * period, 6) for b in range(total_beats)]
    downbeats = [beats[offset_beats + 4 * k] for k in range(bars)]
    return beats, downbeats


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.wav = Path(self.temp.name) / "clip.wav"

    def test_profiles_identify_all_twenty_four_keys(self):
        for index, name in enumerate(KEYS):
            template = MAJOR if index < 12 else MINOR
            tonic = index % 12
            profile = [template[(pc - tonic) % 12] for pc in range(12)]
            scores = key_scores(profile)
            self.assertEqual(max(range(24), key=scores.__getitem__), index, name)

    def test_major_and_minor_cadences_across_transpositions(self):
        cases = [(48, False, "C major"), (54, False, "F# major"), (45, True, "A minor"),
                 (51, True, "D# minor"), (53, False, "F major")]
        for tonic, minor, expected in cases:
            with self.subTest(expected=expected):
                chords(self.wav, cadence(tonic, minor))
                result = ChromaKeyProvider().analyze(self.wav)
                self.assertEqual(result.key, expected)
                self.assertEqual(result.key_source, "measured-heuristic")
                self.assertGreaterEqual(result.margin, .04)
                self.assertEqual(len(result.pitch_class_profile), 12)

    def test_opposite_polarity_stereo_uses_channel_average_honestly(self):
        # Exact L/R cancellation removes all mono content; abstain, do not guess.
        chords(self.wav, cadence(48, False), stereo=True)
        result = ChromaKeyProvider().analyze(self.wav)
        self.assertIsNone(result.key)
        self.assertEqual(result.key_source, "unavailable")

    def test_abstains_on_silence_noise_and_clicks(self):
        seed = 12345
        noise = []
        for _ in range(RATE * 12):
            seed = (1103515245 * seed + 12345) % 2 ** 31
            noise.append((seed / 2 ** 31 - .5) * 16000)
        clicks = [12000 * math.exp(-((i / RATE) % .5) * 80) for i in range(RATE * 12)]
        for label, values in (("silence", [0] * RATE * 12), ("noise", noise), ("clicks", clicks)):
            with self.subTest(label):
                write(self.wav, values)
                result = ChromaKeyProvider().analyze(self.wav)
                self.assertIsNone(result.key)
                self.assertEqual(result.key_source, "unavailable")
                self.assertTrue(any("manual" in w or "insufficient" in w for w in result.warnings))

    def test_weighted_key_score_and_report(self):
        self.assertEqual(key_score("C major", "C major"), 1.)
        self.assertEqual(key_score("C major", "G major"), .5)
        self.assertEqual(key_score("C major", "F major"), .5)
        self.assertEqual(key_score("C major", "A minor"), .3)
        self.assertEqual(key_score("A minor", "C major"), .3)
        self.assertEqual(key_score("C major", "C minor"), .2)
        self.assertEqual(key_score("C major", "F# major"), 0.)
        self.assertEqual(key_score("C major", None), 0.)
        with self.assertRaises(ValueError):
            key_score("H major", "C major")
        with self.assertRaises(ValueError):
            key_score("C major", "c")
        report = key_report([("C major", "C major"), ("A minor", None), ("D major", "A major"),
                             ("E minor", "G major")])
        self.assertEqual(report["items"], 4)
        self.assertEqual(report["answered"], 3)
        self.assertAlmostEqual(report["abstention_rate"], .25)
        self.assertAlmostEqual(report["exact_accuracy"], .25)
        self.assertAlmostEqual(report["weighted_score"], (1 + 0 + .5 + .3) / 4)
        self.assertAlmostEqual(report["weighted_score_answered"], 1.8 / 3)
        with self.assertRaises(ValueError):
            key_report([])

    def test_cli_emits_json_and_rejects_invalid_input(self):
        chords(self.wav, cadence(45, True))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            key_main([str(self.wav)])
        document = json.loads(output.getvalue())
        self.assertEqual(document["key"], "A minor")
        self.assertEqual(document["provider"], "chroma-key")
        bad = Path(self.temp.name) / "bad.wav"
        bad.write_bytes(b"not a wav")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            key_main([str(bad)])
        self.assertEqual(caught.exception.code, 2)


class MeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.fixtures = {}
        for name, options in {"offset1": dict(offset_beats=1), "offset3": dict(offset_beats=3),
                              "slow": dict(offset_beats=2, bpm=100),
                              "flat": dict(accent=False, bars=12),
                              "no-sections": dict(phrase=1000)}.items():
            path = root / f"{name}.wav"
            cls.fixtures[name] = (path,) + song(path, **options)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_downbeat_phase_and_phrases_are_measured(self):
        for name in ("offset1", "offset3", "slow"):
            with self.subTest(name):
                path, beats, truth = self.fixtures[name]
                result = AccentMeterProvider().analyze(path, beats)
                self.assertEqual(list(result.downbeats_seconds), truth)
                self.assertEqual(result.timing_source, "measured-heuristic")
                self.assertGreaterEqual(result.downbeat_consistency, .6)
                self.assertEqual(list(result.phrase_starts_seconds), truth[::8])
                self.assertTrue(set(result.phrase_starts_seconds) <= set(result.downbeats_seconds))

    def test_uniform_accents_abstain_instead_of_counting_fours(self):
        path, beats, _ = self.fixtures["flat"]
        result = AccentMeterProvider().analyze(path, beats)
        self.assertEqual(result.downbeats_seconds, ())
        self.assertEqual(result.phrase_starts_seconds, ())
        self.assertIn("manual downbeats required", result.warnings[0])

    def test_phrases_abstain_without_section_change(self):
        path, beats, truth = self.fixtures["no-sections"]
        result = AccentMeterProvider().analyze(path, beats)
        self.assertEqual(list(result.downbeats_seconds), truth)
        self.assertEqual(result.phrase_starts_seconds, ())

    def test_too_few_beats_abstain(self):
        path, beats, _ = self.fixtures["offset1"]
        result = AccentMeterProvider().analyze(path, beats[:12])
        self.assertEqual(result.downbeats_seconds, ())
        self.assertIn("too few beats", result.warnings[0])
        result = AccentMeterProvider().analyze(path, beats[:40])
        self.assertEqual(result.phrase_starts_seconds, ())

    def test_invalid_beats_and_settings_rejected(self):
        path, beats, _ = self.fixtures["offset1"]
        for bad in ([1., .5] + beats, [True] + beats[1:], [-1.] + beats, beats + [10_000.],
                    iter(beats), "0.5", [float("nan")] + beats):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                AccentMeterProvider().analyze(path, bad)
        for args in ((1, 8), (4, 1), (True, 8), (4.0, 8), (4, 64)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                AccentMeterProvider(*args)

    def test_proposals_round_trip_into_manual_verification(self):
        # A human can confirm the proposal; ManualProvider validates it on-grid.
        path, beats, truth = self.fixtures["offset1"]
        proposal = AccentMeterProvider().analyze(path, beats)
        manual = ManualProvider(128, beats[0], downbeats=list(proposal.downbeats_seconds),
                                phrases=list(proposal.phrase_starts_seconds), key="C major",
                                annotator="synthetic-test").analyze(path)
        self.assertEqual(manual.timing_source, "manual")
        self.assertEqual(list(manual.downbeats_seconds), truth)

    def test_cli_with_declared_grid(self):
        path, beats, truth = self.fixtures["slow"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            meter_main([str(path), "--bpm", "100", "--first-beat", str(beats[0])])
        document = json.loads(output.getvalue())
        # The declared grid extends to the clip end, so it may hold one more bar.
        self.assertEqual(document["downbeats_seconds"][:len(truth)], truth)
        self.assertEqual(document["provider"], "accent-meter")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            meter_main([str(path), "--bpm", "100", "--beats-per-bar", "9"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
