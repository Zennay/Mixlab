import copy
import json
from pathlib import Path
import tempfile
import unittest
from mixlab.cli import fixture, benchmark
from mixlab.evaluation import aggregate, verify_pack

class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        manifest=fixture(cls.root/"library")
        cls.pack=cls.root/"pack"
        benchmark(manifest,cls.pack,seed=42)
        cls.receipt,cls.evidence,cls.trials=verify_pack(cls.pack)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def vote(self,reviewer="listener-01",choice="Tie"):
        return {"schema_version":1,"pack_id":self.receipt["pack_id"],"reviewer":reviewer,
                "ratings":[{"trial":t,"preference":choice} for t in self.trials]}

    def save(self,name,vote):
        path=self.root/name
        path.write_text(json.dumps(vote))
        return path

    def test_ties_and_unusable_have_explicit_denominators(self):
        result=aggregate(self.pack,[self.save("v1.json",self.vote()),
                                   self.save("v2.json",self.vote("listener-02","Both unusable"))])
        self.assertEqual(result["reviewers"],2)
        self.assertEqual(result["counts"]["ties"],3)
        self.assertEqual(result["counts"]["both_unusable"],3)
        self.assertIsNone(result["candidate_preference_fraction"])
        self.assertFalse(result["milestone_pass"])
        self.assertNotIn(str(self.root),json.dumps(result))

    def test_answer_key_resolves_candidate_preferences(self):
        vote=self.vote()
        for rating in vote["ratings"]:
            trial=self.trials[rating["trial"]]
            rating["preference"]="B" if trial["A"]=="baseline" else "A"
        result=aggregate(self.pack,[self.save("candidate.json",vote)])
        self.assertEqual(result["counts"]["candidate"],3)
        self.assertEqual(result["candidate_preference_fraction"],1.)
        self.assertFalse(result["milestone_pass"])

    def test_duplicate_incomplete_foreign_and_wrong_pack_rejected(self):
        invalid=[]
        v=self.vote(); v["ratings"].pop(); invalid.append(v)
        v=self.vote(); v["ratings"].append(v["ratings"][0]); invalid.append(v)
        v=self.vote(); v["pack_id"]="x"*64; invalid.append(v)
        v=self.vote(); v["ratings"][0]["trial"]="unknown"; invalid.append(v)
        v=self.vote(); v["ratings"][0]["preference"]="great"; invalid.append(v)
        for i,v in enumerate(invalid):
            with self.subTest(i=i), self.assertRaises(ValueError):
                aggregate(self.pack,[self.save(f"bad{i}.json",v)])
        with self.assertRaisesRegex(ValueError,"Duplicate reviewer"):
            aggregate(self.pack,[self.save("one.json",self.vote()),
                                 self.save("two.json",self.vote("LISTENER-01"))])

    def test_mutated_audio_is_rejected_and_restored(self):
        audio=self.pack/"review/trial-001-A.wav"
        original=audio.read_bytes()
        try:
            audio.write_bytes(original[:-2]+b"\x00\x00")
            with self.assertRaisesRegex(ValueError,"changed"):
                verify_pack(self.pack)
        finally: audio.write_bytes(original)

    def test_answer_key_mutation_is_rejected_and_restored(self):
        path=self.pack/"private/answer-key.json"
        original=path.read_text()
        try:
            key=json.loads(original)
            key[0]["A"],key[0]["B"]=key[0]["B"],key[0]["A"]
            path.write_text(json.dumps(key))
            with self.assertRaisesRegex(ValueError,"identity"):
                verify_pack(self.pack)
        finally: path.write_text(original)
