import contextlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from mixlab.cli import digest, dump
from mixlab.engine import write_wav
from mixlab.evaluation import aggregate, verify_pack
from mixlab.evaluation.study import freeze, write_exclusive
from mixlab.evaluation.study_pack import build, main, verify_study_pack
from mixlab.quality.pack import inspect_review_pack

KEYS = ["C major", "G major", "A minor", "F# major", "D minor", "E minor"]


class StudyPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        library = cls.root / "library"
        library.mkdir()
        tracks, candidates = [], []
        for index, key in enumerate(KEYS):
            name = f"t{index}.wav"
            frequency = 110 * 2 ** (index / 12)
            write_wav(library / name, 8000, [(.2 * math.sin(2 * math.pi * frequency * i / 8000),)
                                             for i in range(8000 * 5)])
            sha = digest(library / name)
            tracks.append({"id": f"t{index}", "path": name, "sha256": sha, "bpm": 120.,
                           "rights": "synthetic", "provenance": "MixLab synthetic study fixture"})
            candidates.append({"id": f"t{index}", "sha256": sha, "bpm": 120., "key": key,
                               "key_source": "manual", "split": "evaluation", "rights": "synthetic"})
        candidate_path = cls.root / "candidates.json"
        candidate_path.write_text(json.dumps({"schema_version": 1, "tracks": candidates}))
        cls.study_doc = freeze(candidate_path, 5, 11)
        cls.study = cls.root / "study.json"
        write_exclusive(cls.study, cls.study_doc)
        # A human aligns exactly the frozen pairs afterwards (manifest holds <= 10 pairs).
        pairs = [{"id": f"{p['a']}-{p['b']}", "a": p["a"], "b": p["b"], "a_start": 1.,
                  "b_start": 0., "bpm": 120., "beats": 4} for p in cls.study_doc["pairs"]]
        cls.manifest = library / "library.json"
        dump(cls.manifest, {"schema_version": 1, "purpose": "synthetic-smoke-only",
                            "tracks": tracks, "pairs": pairs})
        cls.pack = cls.root / "pack"
        build(cls.manifest, cls.study, cls.pack, seed=3)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_one_trial_per_frozen_pair_with_preselected_family(self):
        receipt, evidence, trials = verify_pack(self.pack)
        self.assertEqual(receipt["trial_count"], 5)
        self.assertEqual(receipt["render_count"], 10)
        self.assertNotIn("study_id", receipt)  # public receipt keeps the canonical fields
        self.assertEqual(evidence["study_id"], self.study_doc["study_id"])
        for number, entry in enumerate(self.study_doc["pairs"], 1):
            trial = trials[f"trial-{number:03d}"]
            self.assertEqual({trial["A"], trial["B"]}, {"baseline", entry["candidate_family"]})
        self.assertEqual(sorted(p.name for p in (self.pack / "review").iterdir())[-1], "trial-005-B.wav")

    def test_public_review_preflight_accepts_the_pack(self):
        report = inspect_review_pack(self.pack / "review", require_generated_html=True,
                                     require_receipt=True)
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_pinned_study_binds_pack_content(self):
        self.assertEqual(verify_study_pack(self.pack, self.study), self.study_doc["study_id"])
        # A forged study_id that matches another genuine study is rejected.
        other = self.root / "other-study.json"
        if not other.exists():
            write_exclusive(other, freeze(self.root / "candidates.json", 5, 12))
        with self.assertRaises(ValueError):
            verify_study_pack(self.pack, other)
        other_pairs = [(p["a"], p["b"], p["candidate_family"]) for p in json.loads(other.read_text())["pairs"]]
        self.assertNotEqual(other_pairs, [(p["a"], p["b"], p["candidate_family"])
                                          for p in self.study_doc["pairs"]])
        # Rewriting the private study_id to the other study's id does not help either.
        evidence_path = self.pack / "private" / "evidence.json"
        original = evidence_path.read_text()
        try:
            evidence = json.loads(original)
            evidence["study_id"] = json.loads(other.read_text())["study_id"]
            evidence_path.write_text(json.dumps(evidence))
            with self.assertRaises(ValueError):
                verify_study_pack(self.pack, other)
        finally:
            evidence_path.write_text(original)

    def test_existing_aggregation_accepts_the_pack(self):
        _, _, trials = verify_pack(self.pack)
        paths = []
        for reviewer in ("listener-01", "listener-02", "listener-03"):
            vote = {"schema_version": 1, "pack_id": json.loads((self.pack / "receipt.json").read_text())["pack_id"],
                    "reviewer": reviewer,
                    "ratings": [{"trial": t, "preference": "B" if row["A"] == "baseline" else "A"}
                                for t, row in trials.items()]}
            path = self.root / f"{reviewer}.json"
            path.write_text(json.dumps(vote))
            paths.append(path)
        result = aggregate(self.pack, paths)
        self.assertEqual(result["reviewers"], 3)
        self.assertEqual(result["counts"]["candidate"], 15)
        self.assertFalse(result["milestone_pass"])

    def test_refuses_missing_alignment_changed_source_or_existing_output(self):
        manifest = json.loads(self.manifest.read_text())
        first = self.study_doc["pairs"][0]
        manifest["pairs"] = [p for p in manifest["pairs"] if (p["a"], p["b"]) != (first["a"], first["b"])]
        partial = self.manifest.parent / "partial.json"
        dump(partial, manifest)
        with self.assertRaises(ValueError):
            build(partial, self.study, self.root / "out-partial")
        self.assertFalse((self.root / "out-partial").exists())
        tampered = json.loads(self.study.read_text())
        tampered["pairs"][0]["a_sha256"] = "0" * 64
        bad = self.root / "tampered-study.json"
        bad.write_text(json.dumps(tampered))
        with self.assertRaises(ValueError):
            build(self.manifest, bad, self.root / "out-tampered")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main([str(self.manifest), str(self.study), str(self.pack)])
        self.assertEqual(caught.exception.code, 2)

    def test_failed_render_leaves_no_partial_pack(self):
        import mixlab.evaluation.study_pack as study_pack
        calls = []
        real = study_pack.render

        def failing(*args, **kwargs):
            calls.append(1)
            if len(calls) == 4:
                raise ValueError("synthetic render failure")
            return real(*args, **kwargs)
        target = self.root / "out-failed"
        with mock.patch.object(study_pack, "render", failing), self.assertRaises(ValueError):
            build(self.manifest, self.study, target, seed=1)
        self.assertEqual(len(calls), 4)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob(".mixlab-staging-*")), [])

    def test_cli_errors_never_echo_private_paths(self):
        secret = self.root / "SECRET-TOKEN-7f3a" / "private-library.json"
        blocker = self.root / "SECRET-TOKEN-7f3a-file"
        blocker.write_text("not a directory")
        commands = [
            # Parent is a regular file: the OS error names the private destination.
            ["mixlab.evaluation.study_pack", str(self.manifest), str(self.study), str(blocker / "pack")],
            ["mixlab.evaluation.study_pack", str(secret), str(self.study), str(self.root / "o1")],
            ["mixlab.evaluation.study_pack", str(self.manifest), str(secret), str(self.root / "o2")],
            ["mixlab.evaluation.study", "freeze", str(secret), str(self.root / "o3.json"), "--seed", "1"],
            ["mixlab.evaluation.study", "verify", str(secret)],
        ]
        for command in commands:
            with self.subTest(command=command[0:2]):
                result = subprocess.run([sys.executable, "-m", *command], capture_output=True, text=True,
                                        cwd=Path(__file__).resolve().parents[1], timeout=60)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("SECRET-TOKEN-7f3a", result.stdout + result.stderr)
                self.assertNotIn(str(self.root), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
