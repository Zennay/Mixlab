import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from mixlab.evaluation.study import (CANDIDATE_FAMILIES, camelot, camelot_distance, freeze, main,
                                     verify_study)

KEYS = ["C major", "G major", "A minor", "F# major", "D minor", "E minor", "B major", None,
        "C major", "A# minor", "F major", "C# major"]


def track(index, split="evaluation", bpm=124, key="__auto__"):
    key = KEYS[index % len(KEYS)] if key == "__auto__" else key
    return {"id": f"t{index:02d}", "sha256": hashlib.sha256(f"t{index}".encode()).hexdigest(),
            "bpm": bpm, "key": key, "key_source": "manual" if key else "unavailable",
            "split": split, "rights": "user-permitted"}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, tracks, name="candidates.json"):
        path = self.root / name
        path.write_text(json.dumps({"schema_version": 1, "tracks": tracks}))
        return path

    def library(self):
        return ([track(i) for i in range(12)] + [track(20 + i, split="development") for i in range(4)] +
                [track(40, bpm=128), track(41, bpm=128.5)])

    def test_camelot_wheel(self):
        self.assertEqual(camelot("C major"), (8, "B"))
        self.assertEqual(camelot("A minor"), (8, "A"))
        self.assertEqual(camelot("G major"), (9, "B"))
        self.assertEqual(camelot("F major"), (7, "B"))
        self.assertEqual(camelot("E minor"), (9, "A"))
        self.assertEqual(camelot("B major"), (1, "B"))
        self.assertEqual(camelot_distance("C major", "A minor"), 1)
        self.assertEqual(camelot_distance("C major", "G major"), 1)
        self.assertEqual(camelot_distance("B major", "E major"), 1)  # 1B / 12B wrap around
        self.assertEqual(camelot_distance("C major", "F# major"), 6)

    def test_freeze_is_reproducible_balanced_and_split_safe(self):
        path = self.write(self.library())
        first, second = freeze(path, 8, 7), freeze(path, 8, 7)
        self.assertEqual(first, second)
        self.assertNotEqual(first["study_id"], freeze(path, 8, 8)["study_id"])
        pairs = first["pairs"]
        self.assertEqual(len(pairs), 8)
        ids = {p["a"] for p in pairs} | {p["b"] for p in pairs}
        self.assertTrue(all(int(i[1:]) < 20 or int(i[1:]) >= 40 for i in ids))  # no development tracks
        self.assertNotIn("t41", ids)  # 0.4% tempo mismatch is excluded by default
        uses = {}
        for p in pairs:
            for t in (p["a"], p["b"]):
                uses[t] = uses.get(t, 0) + 1
        self.assertLessEqual(max(uses.values()), 2)
        counts = [sum(p["candidate_family"] == f for p in pairs) for f in CANDIDATE_FAMILIES]
        self.assertLessEqual(max(counts) - min(counts), 1)
        classes = [p["harmonic_class"] for p in pairs]
        self.assertGreaterEqual(classes.count("compatible"), 4)
        self.assertGreaterEqual(len(classes) - classes.count("compatible"), 3)
        self.assertTrue(all(p["renderable_without_stretch"] for p in pairs))
        target = self.root / "study.json"
        target.write_text(json.dumps(first))
        self.assertEqual(verify_study(target)["study_id"], first["study_id"])

    def test_tempo_tolerance_admits_labelled_stretch_pairs(self):
        # Two tempo groups of five; single use per track leaves only 4 same-tempo pairs.
        tracks = [track(i, bpm=120 + (i % 2) * .6) for i in range(10)]
        with self.assertRaises(ValueError):
            freeze(self.write(tracks), 5, 1, max_track_uses=1)
        study = freeze(self.write(tracks, "b.json"), 5, 1, tempo_tolerance_percent=1, max_track_uses=1)
        self.assertTrue(any(not p["renderable_without_stretch"] for p in study["pairs"]))

    def test_rejects_invalid_candidates(self):
        good = self.library()
        variants = {
            "duplicate-id": good + [good[0]],
            "same-recording": good + [dict(good[0], id="copy")],
            "unknown-rights": [dict(good[0], rights="unknown")] + good[1:],
            "key-source-mismatch": [dict(good[0], key_source="unavailable")] + good[1:],
            "bad-key": [dict(good[0], key="H major")] + good[1:],
            "bad-split": [dict(good[0], split="test")] + good[1:],
            "extra-field": [dict(good[0], path="/private/x.wav")] + good[1:],
            "bool-bpm": [dict(good[0], bpm=True)] + good[1:],
        }
        for label, tracks in variants.items():
            with self.subTest(label), self.assertRaises(ValueError):
                freeze(self.write(tracks, f"{label}.json"), 8, 1)
        path = self.write(good)
        for args in ((4, 1), (11, 1), (8, -1), (8, True), (8, 1.5)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                freeze(path, *args)

    def test_verify_detects_tampering(self):
        study = freeze(self.write(self.library()), 6, 3)
        edits = {
            "family": lambda s: s["pairs"][0].update(candidate_family="echo_exit"
                                                     if s["pairs"][0]["candidate_family"] != "echo_exit"
                                                     else "hard_cut"),
            "drop": lambda s: s["pairs"].pop(),
            "seed": lambda s: s.update(seed=s["seed"] + 1),
        }
        for label, edit in edits.items():
            tampered = json.loads(json.dumps(study))
            edit(tampered)
            target = self.root / f"{label}.json"
            target.write_text(json.dumps(tampered))
            with self.subTest(label), self.assertRaises(ValueError):
                verify_study(target)

    def test_cli_never_overwrites(self):
        candidates = self.write(self.library())
        output = self.root / "frozen.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["freeze", str(candidates), str(output), "--pairs", "6"])
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["pairs"], 6)
        self.assertIsInstance(json.loads(output.read_text())["seed"], int)
        with contextlib.redirect_stdout(io.StringIO()):
            main(["verify", str(output)])
        before = output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["freeze", str(candidates), str(output)])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
