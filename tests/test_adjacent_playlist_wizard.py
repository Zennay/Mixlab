"""Real synthetic local wizard route; no licensed music or guessed metadata."""
import json
from pathlib import Path
import tempfile
import unittest
import wave

from mixlab.ingest import validate_library
from mixlab.session import _manual_cues_present

from mixlab.project_wizard import create_manifest


class AdjacentPlaylistWizardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "permitted-synthetic"
        self.root.mkdir()
        for label in ("alpha", "beta", "gamma"):
            # Generate playable *synthetic* PCM16 so canonical downstream
            # consumer validation proves this is a real product handoff.
            with wave.open(str(self.root / f"{label}.wav"), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\x00\x00" * (8000 * 8 + len(label)))

    def build(self, choices, *, playlist=True, name="playlist.json"):
        answers = iter(choices)
        calls = []
        destination = self.root / name
        def read(prompt):
            calls.append(prompt)
            return next(answers)
        result = create_manifest(
            self.root, destination, read=read, write=lambda _: None,
            adjacent_playlist=playlist,
        )
        return result, calls

    def test_adjacent_playlist_preserves_explicit_song_order_and_source_custody(self):
        # Sorted library is alpha,beta,gamma; selected route is gamma→alpha→beta.
        answers = ["3,1,2"]
        answers += ["120", "0", "synthetic", "Generated local synthetic"] * 3
        answers += ["8", "0", "0"] * 2
        result, prompts = self.build(answers)
        data = json.loads(result.read_text())
        self.assertEqual(
            [track["path"] for track in data["tracks"]],
            ["gamma.wav", "alpha.wav", "beta.wav"],
        )
        self.assertEqual(
            [(pair["a"], pair["b"]) for pair in data["pairs"]],
            [("track-001", "track-002"), ("track-002", "track-003")],
        )
        self.assertEqual(len(data["pairs"]), 2)
        self.assertEqual(len([p for p in prompts if "track number" in p.lower()]), 0)
        self.assertEqual(len([p for p in prompts if "beat count" in p.lower()]), 2)
        self.assertEqual(data["purpose"], "development-pilot")
        # The manifest is accepted by the canonical consumers, not merely
        # syntactically well-formed private JSON.
        _, validated = validate_library(result)
        self.assertEqual(len(validated), 3)
        _manual_cues_present(data)
        self.assertEqual(set(t["rights"] for t in data["tracks"]), {"synthetic"})

    def test_incompatible_verified_bpm_refused_without_manifest(self):
        answers = ["1,2"]
        answers += ["120", "", "synthetic", "synthetic A"]
        answers += ["123", "", "synthetic", "synthetic B"]
        with self.assertRaisesRegex(ValueError, "different verified BPM"):
            self.build(answers, name="reject.json")
        self.assertFalse((self.root / "reject.json").exists())

    def test_more_than_ten_adjacent_pairs_refuses_without_overwriting(self):
        for index in range(9):
            (self.root / f"extra-{index:02d}.wav").write_bytes(b"synthetic")
        with self.assertRaisesRegex(ValueError, "at most 11 songs"):
            self.build([",".join(str(i) for i in range(1, 13))], name="too-many.json")
        self.assertFalse((self.root / "too-many.json").exists())

    def test_manual_pair_wizard_remains_supported(self):
        answers = ["1,2"] + ["120", "", "synthetic", "synthetic origin"] * 2
        answers += ["1", "2", "1", "16", "0", "0"]
        result, prompts = self.build(answers, playlist=False, name="manual.json")
        data = json.loads(result.read_text())
        self.assertEqual(len(data["pairs"]), 1)
        self.assertEqual((data["pairs"][0]["a"], data["pairs"][0]["b"]),
                         ("track-002", "track-001"))
        self.assertTrue(any("Outgoing track number" in p for p in prompts))

    def test_nonboolean_direct_api_mode_is_denied(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.build(["1,2"], playlist="true", name="invalid-flag.json")
        self.assertFalse((self.root / "invalid-flag.json").exists())


if __name__ == "__main__":
    unittest.main()
