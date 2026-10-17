from array import array
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mixlab.dsp.tempo import capabilities, prepare, render_pair, tempo_ratio
from mixlab.engine import write_wav, load_wav
from mixlab.models import Recipe

class TempoContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.source=self.root/"tone.wav"
        write_wav(self.source,16000,[(.15*math.sin(2*math.pi*440*i/16000),) for i in range(16000*4)])

    def test_ratio_limits(self):
        for source,target in ((100,120),(120,100),(True,120),(120,float("nan"))):
            with self.assertRaises(ValueError): tempo_ratio(source,target)
        self.assertEqual(tempo_ratio(120,126),1.05)

    def test_missing_backend_fails_without_publishing(self):
        out=self.root/"out.wav"
        with patch("mixlab.dsp.tempo.capabilities",return_value={"available":False,"reason":"test"}):
            with self.assertRaisesRegex(ValueError,"unavailable"):
                prepare(self.source,out,source_bpm=120,target_bpm=126)
        self.assertFalse(out.exists())

    def test_protect_original_and_existing_output(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            prepare(self.source,self.source,source_bpm=120,target_bpm=126)
        with self.assertRaisesRegex(ValueError,"overwrite"):
            render_pair(self.source,self.source,self.source,Recipe(beats=2),a_bpm=120,b_bpm=120)

    def test_equal_tempo_identity_needs_no_backend(self):
        with patch("mixlab.dsp.tempo.capabilities",side_effect=AssertionError("not needed")):
            result=render_pair(self.source,self.source,self.root/"mix.wav",Recipe(beats=2),a_bpm=120,b_bpm=120)
        self.assertEqual(result["tempo_transforms"][0]["backend"],"identity")
        self.assertEqual(result["frames"],16000)

    def test_invalid_backend_audio_is_not_published(self):
        before=self.source.read_bytes()
        for case in ("duration", "nonfinite"):
            out=self.root/(case+".wav")
            def invalid_audio(command, **kwargs):
                frames=4 if case=="duration" else round(64000/1.05)
                values=array("f",[float("nan") if case=="nonfinite" else .1])*frames
                Path(command[-1]).write_bytes(values.tobytes())
            backend={"available":True,"executable":"test-ffmpeg","version":"test"}
            with patch("mixlab.dsp.tempo.capabilities",return_value=backend), \
                 patch("mixlab.dsp.tempo.subprocess.run",side_effect=invalid_audio):
                with self.assertRaises(ValueError):
                    prepare(self.source,out,source_bpm=120,target_bpm=126)
            self.assertFalse(out.exists())
            self.assertEqual(list(self.root.glob(".mixlab-*")),[])
            self.assertEqual(self.source.read_bytes(),before)

class TempoBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend=capabilities()
        if not backend["available"]:
            if os.environ.get("MIXLAB_REQUIRE_RUBBERBAND") == "1":
                raise RuntimeError("VPS proof requires installed Rubber Band backend")
            raise unittest.SkipTest("optional FFmpeg Rubber Band backend absent")

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.a=self.root/"a.wav"; self.b=self.root/"b.wav"
        rate=16000
        write_wav(self.a,rate,[(.15*math.sin(2*math.pi*440*i/rate),0.) for i in range(rate*8)])
        write_wav(self.b,rate,[(.15*math.sin(2*math.pi*660*i/rate),0.) for i in range(rate*8)])

    def test_actual_pitch_preserved_and_duration_changed(self):
        for target in (114,126):
            output=self.root/f"prepared-{target}.wav"
            result=prepare(self.a,output,source_bpm=120,target_bpm=target)
            rate,frames=load_wav(output)
            self.assertAlmostEqual(len(frames)/rate,8*120/target,delta=.05)
            middle=[f[0] for f in frames[rate:rate*5]]
            crossings=sum(a<=0<b for a,b in zip(middle,middle[1:]))
            frequency=crossings/(len(middle)/rate)
            self.assertAlmostEqual(frequency,440,delta=2)
            self.assertTrue(all(f[1]==0 for f in frames))
            self.assertLess(result["peak_before_pcm"],.9)

    def test_actual_mismatched_pair_renders(self):
        out=self.root/"pair.wav"
        result=render_pair(self.a,self.b,out,Recipe(bpm=122,beats=8,a_start=.5,b_start=.5),
                           a_bpm=120,b_bpm=124)
        self.assertEqual(result["frames"],round(8*60/122*16000))
        self.assertEqual(result["post_pcm_metrics"]["clipping_samples"],0)
        self.assertEqual(len(result["tempo_transforms"]),2)
        self.assertNotIn(".mixlab-pair-",str(result))
        self.assertEqual(list(self.root.glob(".mixlab-*")),[])

    def test_pulse_timing_after_stretch(self):
        pulse=self.root/"pulse.wav"
        rate=16000
        samples=[]
        for i in range(rate*8):
            t=i/rate
            phase=(t-.5)%.5
            value=.3*math.sin(2*math.pi*1000*t)*math.exp(-phase*100) if t>=.5 else 0.
            samples.append((value,))
        write_wav(pulse,rate,samples)
        out=self.root/"pulse-fast.wav"
        prepare(pulse,out,source_bpm=120,target_bpm=126)
        _,frames=load_wav(out)
        for n in range(2,12):
            expected=(.5+n*.5)/1.05
            center=round(expected*rate)
            window=frames[center-1600:center+1600]
            energy=[sum(f[0]**2 for f in window[i:i+160]) for i in range(0,len(window),160)]
            observed=(center-1600+energy.index(max(energy))*160)/rate
            self.assertAlmostEqual(observed,expected,delta=.06)
