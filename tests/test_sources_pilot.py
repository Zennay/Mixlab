from array import array
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
import wave
from mixlab.cli import digest
from mixlab.evaluation.pilot import fold, prepare, target_bpm
from mixlab.evaluation.study_pack import verify_study_pack
from mixlab.quality.pack import inspect_review_pack
from mixlab.sources.archive import admissible, license_of

RATE = 22050


def loop(path, bpm, seconds=45, phase=.11):
    """Kick on every beat, accented bar lines, and a sustained chord."""
    period = 60 / bpm
    pcm = array("h")
    for i in range(int(seconds * RATE)):
        t = i / RATE - phase
        beat = math.floor(t / period) if t >= 0 else -1
        local = t - beat * period
        v = .25 * math.sin(2 * math.pi * 220 * i / RATE) + .15 * math.sin(2 * math.pi * 277.2 * i / RATE)
        if beat >= 0:
            amp = .8 if beat % 4 == 0 else .35
            v += amp * math.exp(-local * 18) * math.sin(2 * math.pi * 60 * local)
        sample = int(9000 * v)
        pcm.extend((sample, sample))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2); out.setsampwidth(2); out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


class SourceRules(unittest.TestCase):
    def test_only_adaptation_friendly_cc_licenses(self):
        self.assertEqual(license_of("http://creativecommons.org/licenses/by-nc-sa/3.0/"), ("by-nc-sa", "3.0"))
        self.assertEqual(license_of("https://creativecommons.org/licenses/by/4.0/"), ("by", "4.0"))
        for url in ("http://creativecommons.org/licenses/by-nc-nd/3.0/", "http://creativecommons.org/licenses/by-nd/4.0/",
                    "http://creativecommons.org/licenses/sampling+/1.0/", "", None):
            with self.subTest(url=url):
                self.assertIsNone(license_of(url))

    def test_mixes_and_unlicensed_items_are_rejected(self):
        good = {"licenseurl": "https://creativecommons.org/licenses/by/4.0/", "creator": "x",
                "subject": ["house"], "title": "Track"}
        self.assertTrue(admissible(good))
        self.assertFalse(admissible(dict(good, subject=["house", "DJ set"])))
        self.assertFalse(admissible(dict(good, title="Summer Mix 2010")))
        self.assertFalse(admissible(dict(good, licenseurl="http://creativecommons.org/licenses/by-nd/3.0/")))
        self.assertFalse(admissible(dict(good, creator=None)))


class PilotTempo(unittest.TestCase):
    def test_octave_fold_and_even_grid(self):
        self.assertAlmostEqual(fold(63.), 126.)
        self.assertAlmostEqual(fold(252.), 126.)
        self.assertAlmostEqual(fold(124.6), 124.6)
        self.assertEqual(target_bpm(124.6), 124.)
        self.assertEqual(target_bpm(125.2), 126.)


@unittest.skipUnless(shutil.which("ffmpeg"), "pilot conform needs ffmpeg")
class PilotEndToEnd(unittest.TestCase):
    def test_machine_prepared_pack_passes_existing_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            (library / "excerpts").mkdir(parents=True)
            records = []
            for index, bpm in enumerate((119.4, 120.5, 120.2, 119.7, 121.6, 123.7, 124.3, 123.9)):
                wav = library / "excerpts" / f"ia-{index:03d}.wav"
                loop(wav, bpm, phase=.05 + .03 * index)
                records.append({"id": f"ia-{index:03d}", "excerpt": f"excerpts/{wav.name}",
                                "excerpt_sha256": digest(wav), "excerpt_start_seconds": 60.,
                                "excerpt_seconds": 45, "creator": f"artist {index}", "title": "loop",
                                "file": "loop.mp3", "license": "CC BY 4.0",
                                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                                "item_url": "https://archive.org/details/synthetic"})
            (library / "sources.json").write_text(json.dumps({"schema_version": 1, "tracks": records}))
            out = Path(temp) / "pilot"
            report = prepare(library, out, pairs=5, seed=3)
            self.assertEqual(len(report["pairs"]), 5)
            self.assertTrue(all(t["target_bpm"] in (120., 124., 122.) for t in report["tracks"]))
            self.assertTrue(all(abs(t["stretch_ratio"] - 1) <= .03 for t in report["tracks"]))
            self.assertEqual(verify_study_pack(out / "pack", out / "study.json"), report["study_id"])
            inspect_review_pack(out / "pack" / "review", require_generated_html=True, require_receipt=True)
            self.assertTrue(all("kick_alignment" in p and "kick_alignment_before" in p for p in report["pairs"]))
            manifest = json.loads((out / "library-aligned.json").read_text())
            self.assertTrue(all(set(p) == {"id", "a", "b", "a_start", "b_start", "bpm", "beats"}
                                for p in manifest["pairs"]))
            self.assertTrue(all("not human-verified" in t["provenance"] for t in manifest["tracks"]))


if __name__ == "__main__":
    unittest.main()
