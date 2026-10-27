import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from mixlab.cli import digest, dump
from mixlab.evaluation.candidates import build_candidates, main
from mixlab.evaluation.study import freeze, write_exclusive
from tests.test_analysis_tonal_meter import cadence, chords

# (tonic midi, minor) per track; t5 is the development-only track.
TONICS = [(48, False), (55, False), (45, True), (50, True), (53, False), (52, True)]


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        library = cls.root / "library"
        library.mkdir()
        tracks = []
        for index, (tonic, minor) in enumerate(TONICS):
            name = f"t{index}.wav"
            chords(library / name, cadence(tonic, minor), seconds=1.5, repeats=1)
            tracks.append({"id": f"t{index}", "path": name, "sha256": digest(library / name),
                           "bpm": 120., "rights": "synthetic",
                           "provenance": "MixLab synthetic candidate fixture"})
        cls.manifest = library / "library.json"
        dump(cls.manifest, {"schema_version": 1, "purpose": "synthetic-smoke-only", "tracks": tracks,
                            "pairs": [{"id": "p", "a": "t0", "b": "t1", "a_start": 0., "b_start": 0.,
                                       "bpm": 120., "beats": 4}]})
        cls.split = cls.write("split.json", {"schema_version": 1, "development": ["t5"],
                                             "evaluation": ["t0", "t1", "t2", "t3", "t4"]})

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def write(cls, name, document):
        path = cls.root / name
        path.write_text(json.dumps(document))
        return path

    def test_manual_keys_win_and_measurement_labels_its_source(self):
        manual = self.write("keys.json", {"schema_version": 1, "keys": {"t0": "C major"}})
        document = build_candidates(self.manifest, self.split, manual, measure_keys=True)
        rows = {row["id"]: row for row in document["tracks"]}
        self.assertEqual(rows["t0"]["key"], "C major")
        self.assertEqual(rows["t0"]["key_source"], "manual")
        self.assertEqual(rows["t2"]["key"], "A minor")
        self.assertEqual(rows["t2"]["key_source"], "measured-heuristic")
        self.assertEqual(rows["t5"]["split"], "development")
        for row in rows.values():
            self.assertEqual((row["key"] is None), row["key_source"] == "unavailable")

    def test_without_measurement_keys_are_unavailable(self):
        document = build_candidates(self.manifest, self.split)
        self.assertEqual({row["key_source"] for row in document["tracks"]}, {"unavailable"})

    def test_output_feeds_the_frozen_study(self):
        candidates = self.root / "candidates-for-study.json"
        if not candidates.exists():
            write_exclusive(candidates, build_candidates(self.manifest, self.split, measure_keys=True))
        study = freeze(candidates, 5, 1)
        ids = {p["a"] for p in study["pairs"]} | {p["b"] for p in study["pairs"]}
        self.assertNotIn("t5", ids)
        self.assertEqual(len(study["pairs"]), 5)

    def test_rejects_incomplete_or_inconsistent_inputs(self):
        variants = {
            "missing-track": {"schema_version": 1, "development": [], "evaluation": ["t0", "t1", "t2", "t3", "t4"]},
            "twice": {"schema_version": 1, "development": ["t5", "t0"], "evaluation": ["t0", "t1", "t2", "t3", "t4"]},
            "unknown": {"schema_version": 1, "development": ["t5", "zz"], "evaluation": ["t0", "t1", "t2", "t3", "t4"]},
            "no-eval": {"schema_version": 1, "development": ["t0", "t1", "t2", "t3", "t4", "t5"], "evaluation": []},
            "extra-field": {"schema_version": 1, "development": ["t5"], "evaluation": ["t0", "t1", "t2", "t3", "t4"], "x": []},
        }
        for label, document in variants.items():
            with self.subTest(label), self.assertRaises(ValueError):
                build_candidates(self.manifest, self.write(f"{label}.json", document))
        for label, keys in {"bad-key": {"t0": "H major"}, "foreign": {"zz": "C major"}}.items():
            with self.subTest(label), self.assertRaises(ValueError):
                build_candidates(self.manifest, self.split,
                                 self.write(f"{label}.json", {"schema_version": 1, "keys": keys}))

    def test_cli_writes_once_and_hides_private_paths(self):
        output = self.root / "cli-candidates.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main([str(self.manifest), str(self.split), str(output)])
        self.assertEqual(json.loads(stdout.getvalue())["evaluation"], 5)
        before = output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main([str(self.manifest), str(self.split), str(output)])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.read_bytes(), before)
        blocker = self.root / "SECRET-TOKEN-c4nd"
        blocker.write_text("x")
        result = subprocess.run([sys.executable, "-m", "mixlab.evaluation.candidates", str(self.manifest),
                                 str(self.split), str(blocker / "out.json")], capture_output=True, text=True,
                                timeout=60, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SECRET-TOKEN-c4nd", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
