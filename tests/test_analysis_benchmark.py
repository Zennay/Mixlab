import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from mixlab.analysis.benchmark import evaluate, load_references, main
from tests.test_analysis_tonal_meter import cadence, chords, song


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class AnalysisBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.beats, cls.downbeats = song(cls.root / "loop.wav", bpm=120, bars=16, offset_beats=1)
        chords(cls.root / "tonal.wav", cadence(45, True))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def items(self):
        return [{"id": "loop-1", "path": "loop.wav", "sha256": sha(self.root / "loop.wav"),
                 "bpm": 120, "first_beat": self.beats[0], "downbeats": self.downbeats,
                 "annotator": "synthetic-fixture"},
                {"id": "tonal-1", "path": "tonal.wav", "sha256": sha(self.root / "tonal.wav"),
                 "bpm": 120, "key": "A minor", "annotator": "synthetic-fixture"}]

    def write(self, items, name="refs.json"):
        target = self.root / name
        target.write_text(json.dumps({"schema_version": 1, "items": items}))
        return target

    def test_reports_beat_downbeat_and_key_scores(self):
        result = evaluate(self.write(self.items()))
        summary = result["summary"]
        self.assertEqual(summary["items"], 2)
        self.assertEqual(summary["downbeat_items"], 1)
        # The grid runs to the clip end; one unannotated trailing bar costs precision.
        self.assertGreater(summary["downbeat_f1_mean_answered_reference_grid"], .95)
        self.assertEqual(summary["downbeat_abstention_rate_reference_grid"], 0.)
        self.assertEqual(summary["key"]["exact_accuracy"], 1.)
        self.assertIn("not listener preference", summary["evidence_boundary"])
        rows = {row["id"]: row for row in result["items"]}
        self.assertEqual(rows["tonal-1"]["estimated_key"], "A minor")
        self.assertNotIn("downbeat_f1_reference_grid", rows["tonal-1"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_rejects_unsafe_or_inconsistent_references(self):
        good = self.items()
        variants = {
            "traversal": [dict(good[0], path="../loop.wav")],
            "absolute": [dict(good[0], path=str(self.root / "loop.wav"))],
            "duplicate": [good[0], dict(good[1], id="loop-1")],
            "bad-key": [dict(good[1], key="H major")],
            "extra": [dict(good[0], notes="x")],
            "no-annotator": [dict(good[0], annotator=" ")],
            "unordered": [dict(good[0], downbeats=[2., 1.])],
            "bool-bpm": [dict(good[0], bpm=True)],
            "bad-id": [dict(good[0], id="../x")],
            "empty": [],
        }
        for label, items in variants.items():
            with self.subTest(label), self.assertRaises(ValueError):
                load_references(self.write(items, f"{label}.json"))
        with self.assertRaises(ValueError):
            evaluate(self.write([dict(good[1], sha256="0" * 64)], "mismatch.json"))

    def test_cli_exit_codes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main([str(self.write(self.items()[1:], "cli.json"))])
        self.assertEqual(json.loads(output.getvalue())["summary"]["key"]["items"], 1)
        with contextlib.redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit) as caught:
            main([str(self.root / "missing.json")])
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn(str(self.root), error.getvalue())


if __name__ == "__main__":
    unittest.main()
