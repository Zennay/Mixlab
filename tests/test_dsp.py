import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mixlab.engine import render as reference, write_wav, load_wav, measure
from mixlab.dsp import render
from mixlab.models import Recipe, FAMILY_NAMES

class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.a,self.b=self.root/"a.wav",self.root/"b.wav"
        write_wav(self.a,8000,[(.2*math.sin(i*.1),0.) for i in range(16000)])
        write_wav(self.b,8000,[(.12*math.cos(i*.07),0.) for i in range(16000)])

    def test_pcm_equivalent_to_reference_across_chunk_boundaries(self):
        for family in FAMILY_NAMES:
            recipe=Recipe(family=family,beats=2,a_start=.125,b_start=.25)
            old=self.root/(family+"-old.wav")
            reference(self.a,self.b,old,recipe)
            for block in (127,4096):
                new=self.root/(family+str(block)+".wav")
                result=render(self.a,self.b,new,recipe,block_frames=block)
                self.assertEqual(old.read_bytes(),new.read_bytes())
                _,frames=load_wav(new)
                self.assertEqual(measure(frames),result["post_pcm_metrics"])
                self.assertTrue(all(f[1]==0 for f in frames))

    def test_clipping_never_publishes_partial_candidate(self):
        write_wav(self.a,8000,[(.99,)]*8000)
        write_wav(self.b,8000,[(.99,)]*8000)
        out=self.root/"clip.wav"
        with self.assertRaisesRegex(ValueError,"clipping"):
            render(self.a,self.b,out,Recipe(beats=1,gain_db=0))
        self.assertFalse(out.exists())
        self.assertEqual(list(self.root.glob(".mixlab-render-*")),[])
        result=render(self.a,self.b,out,Recipe(beats=1,gain_db=-6))
        self.assertEqual(result["post_pcm_metrics"]["clipping_samples"],0)

    def test_no_source_or_existing_candidate_overwrite(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            render(self.a,self.b,self.a,Recipe(beats=1))
        out=self.root/"existing.wav"; out.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError,"exists"):
            render(self.a,self.b,out,Recipe(beats=1))
        self.assertEqual(out.read_bytes(),b"keep")

    def test_failure_removes_temporary_output(self):
        out=self.root/"fail.wav"
        with patch("mixlab.dsp.os.link",side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError): render(self.a,self.b,out,Recipe(beats=1))
        self.assertFalse(out.exists())
        self.assertEqual(list(self.root.glob(".mixlab-render-*")),[])

    def test_input_budget_and_block_validation(self):
        with self.assertRaisesRegex(ValueError,"short"):
            render(self.a,self.b,self.root/"bad.wav",Recipe(beats=8))
        for size in (0,True,65537):
            with self.assertRaises(ValueError):
                render(self.a,self.b,self.root/"bad.wav",Recipe(beats=1),block_frames=size)
