from array import array
import math
from pathlib import Path
import random
import tempfile
import unittest
import wave
from mixlab.analysis import beat_errors
from mixlab.analysis.kick import KickGridProvider

RATE = 22050


def club(path, bpm=124.3, seconds=40, phase=.21, kick=True, jitter=0., seed=1):
    """Kick per beat, offbeat hats, a moving bass line and a pad."""
    rng = random.Random(seed)
    period = 60 / bpm
    hits = []
    t = phase
    while t < seconds:
        hits.append(t + (rng.uniform(-jitter, jitter) if jitter else 0.))
        t += period
    pcm = array("h", [0]) * int(seconds * RATE)
    signal = [0.] * len(pcm)
    for i in range(len(signal)):
        x = i / RATE
        signal[i] = (.12 * math.sin(2 * math.pi * 220 * x) + .08 * math.sin(2 * math.pi * 330 * x)
                     + .25 * math.sin(2 * math.pi * (55 if int(x / (2 * period)) % 2 else 73.4) * x))
    noise = random.Random(seed + 1)
    for n, h in enumerate(hits):
        start = int(h * RATE)
        if kick:
            for k in range(int(.18 * RATE)):
                if start + k < len(signal):
                    local = k / RATE
                    signal[start + k] += .9 * math.exp(-local * 22) * math.sin(2 * math.pi * (50 + 90 * math.exp(-local * 40)) * local)
        hat = int((h + period / 2) * RATE)
        for k in range(int(.03 * RATE)):
            if hat + k < len(signal):
                signal[hat + k] += .3 * math.exp(-k / RATE * 150) * noise.uniform(-1, 1)
    for i, v in enumerate(signal):
        pcm[i] = max(-32767, min(32767, int(14000 * v)))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(RATE)
        out.writeframes(pcm.tobytes())
    return hits


class KickGridTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.wav = Path(self.temp.name) / "clip.wav"

    def test_precise_tempo_and_phase_on_full_mix(self):
        for bpm in (102.5, 124.3, 137.9):
            with self.subTest(bpm=bpm):
                hits = club(self.wav, bpm=bpm)
                result = KickGridProvider().analyze(self.wav)
                self.assertIsNotNone(result.bpm)
                self.assertAlmostEqual(result.bpm, bpm, delta=bpm * .0005)
                self.assertEqual(result.timing_source, "measured-heuristic")
                self.assertGreater(beat_errors([round(h, 6) for h in hits if h < 40], result.beats_seconds,
                                               tolerance=.03)["f1"], .95)

    def test_abstains_without_kick_or_with_irregular_kicks(self):
        club(self.wav, kick=False)
        self.assertIsNone(KickGridProvider().analyze(self.wav).bpm)
        club(self.wav, jitter=.06, seed=4)
        self.assertIsNone(KickGridProvider().analyze(self.wav).bpm)

    def test_tempo_range_validation(self):
        for args in ((40, 100), (100, 230), (90, 200), (140, 100)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                KickGridProvider(*args)


if __name__ == "__main__":
    unittest.main()
