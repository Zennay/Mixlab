from array import array
import math
from pathlib import Path
import tempfile
import unittest
import wave
from mixlab.analysis import EnergyOnsetProvider, ManualProvider, analyze_cached, beat_errors

def clicks(path, bpm=120, phase=.18, duration=12, stereo=False, silent=False):
    rate=8000
    pcm=array("h")
    for i in range(round(duration*rate)):
        t=i/rate-phase
        pulse = int(12000*math.exp(-(t % (60/bpm))*80)) if t >= 0 and not silent else 0
        pcm.append(pulse)
        if stereo: pcm.append(-pulse)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2 if stereo else 1); out.setsampwidth(2); out.setframerate(rate)
        out.writeframes(pcm.tobytes())

class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.wav=self.root/"input.wav"

    def test_regular_tempo_and_phase(self):
        for bpm in (90,120,150):
            with self.subTest(bpm=bpm):
                clicks(self.wav,bpm=bpm)
                result=EnergyOnsetProvider().analyze(self.wav)
                self.assertIsNotNone(result.bpm)
                self.assertAlmostEqual(result.bpm,bpm,delta=1.)
                truth=[.18+n*60/bpm for n in range(math.ceil((12-.18)*bpm/60))]
                self.assertGreater(beat_errors(truth,result.beats_seconds)["f1"],.95)
                self.assertEqual(result.downbeats_seconds,())
                self.assertIsNone(result.key)

    def test_opposite_stereo_is_not_silence(self):
        clicks(self.wav,stereo=True)
        self.assertIsNotNone(EnergyOnsetProvider().analyze(self.wav).bpm)

    def test_silence_abstains(self):
        clicks(self.wav,silent=True)
        result=EnergyOnsetProvider().analyze(self.wav)
        self.assertIsNone(result.bpm); self.assertEqual(result.beats_seconds,())

    def test_manual_confidence_and_annotation_bounds(self):
        clicks(self.wav)
        provider=ManualProvider(120,0,downbeats=(0,2,4),phrases=(0,4),key="A minor",annotator="dj")
        result=provider.analyze(self.wav)
        self.assertEqual(result.timing_source,"manual")
        self.assertEqual(result.key_source,"manual")
        self.assertEqual(result.tempo_confidence,0)
        for opts in ({"downbeats":(99,)},{"downbeats":(.33,)},{"phrases":(2,)}):
            with self.assertRaises(ValueError):
                ManualProvider(120,annotator="dj",**opts).analyze(self.wav)

    def test_cache_is_source_and_provider_config_addressed(self):
        clicks(self.wav)
        cache=self.root/"features"
        p=ManualProvider(120,annotator="dj")
        first=analyze_cached(self.wav,cache,p)
        self.assertEqual(first,analyze_cached(self.wav,cache,p))
        analyze_cached(self.wav,cache,ManualProvider(121,annotator="dj"))
        clicks(self.wav,bpm=90)
        analyze_cached(self.wav,cache,p)
        self.assertEqual(len(list(cache.glob("*.json"))),3)
        self.assertNotIn(str(self.wav),next(cache.glob("*.json")).read_text())

    def test_reference_metrics_penalize_extra_beats(self):
        score=beat_errors([0.,1.,2.],[0.,.5,1.,1.5,2.])
        self.assertEqual(score["recall"],1.)
        self.assertAlmostEqual(score["precision"],.6)
        with self.assertRaises(ValueError): beat_errors([0,1],[0,0,1])

    def test_short_audio_abstains(self):
        clicks(self.wav,duration=2)
        self.assertIsNone(EnergyOnsetProvider().analyze(self.wav).bpm)
