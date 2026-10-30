"""Synthetic M1 user-route checks: optional exporter failures never disclose local exception text."""
import re
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from mixlab.event_publish import publish_event
from mixlab.playlist_approval import KIND as APPROVAL_KIND


class PrivateExportWarningTests(unittest.TestCase):
    def test_complete_event_keeps_wav_and_redacts_four_optional_error_routes(self):
        secret = "FICTIONAL-NOT-AN-ACTUAL-SECRET"
        private_error = "/private/DJ/folder/" + secret
        with tempfile.TemporaryDirectory() as root:
            music = Path(root, "music")
            music.mkdir()
            plan, approval = music / "plan.json", music / "approved.json"
            plan.write_text("{}", encoding="utf-8")
            approval.write_text("{}", encoding="utf-8")
            destination = Path(root, "event-one")
            def produce_approved_studio(*args, **kwargs):
                wav = kwargs["full_set_wav"]
                with wave.open(str(wav), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(8000)
                    stream.writeframes(b"\x00\x00" * 8)
                return {"warnings": [], "instant_complete_set": {
                    "continuous_set": str(wav), "offline_player": None,
                    "transitions": ["pair-001:bass_swap"]}}
            with patch("mixlab.event_publish._read_json", return_value=({"kind": APPROVAL_KIND, "beats": 16}, None)), \
                 patch("mixlab.event_publish.load_approval"), \
                 patch("mixlab.event_publish.build_playlist_studio", side_effect=produce_approved_studio), \
                 patch("mixlab.event_publish.create_runbook", side_effect=OSError(private_error)), \
                 patch("mixlab.event_publish.create_rehearsal", side_effect=ValueError(private_error)), \
                 patch("mixlab.event_publish.create_dashboard", side_effect=KeyError(private_error)), \
                 patch("mixlab.event_publish.export_bundle", side_effect=OSError(private_error)):
                result = publish_event(music, plan, approval, destination, bundle=True, write=lambda _: None)
            self.assertTrue(result["ready"])
            self.assertTrue(Path(result["full_set_wav"]).is_file())
            self.assertEqual(len(result["warnings"]), 4)
            self.assertTrue(all("unavailable" in w for w in result["warnings"]))
            self.assertNotIn(secret, repr(result["warnings"]))
            self.assertNotIn("/private/DJ", repr(result["warnings"]))
            self.assertFalse(result["human_preference_proven"])

    def test_adjacent_private_studio_routes_no_longer_append_raw_exceptions(self):
        root = Path(__file__).resolve().parents[1] / "mixlab"
        for name in ("playlist_studio.py", "idea_pipeline.py", "idea_board.py", "event_publish.py", "delivery.py"):
            with self.subTest(module=name):
                source = (root / name).read_text(encoding="utf-8")
                # These are bounded optional-return warning paths, not mandatory
                # admission failures where the caller needs a trace for local debugging.
                self.assertIsNone(re.search(r'(?:warnings\.append|\["player_warning"\])[^\n]*str\(exc\)', source))
                self.assertNotIn("optional full-set export failed: \" + str(exc)", source)


if __name__ == "__main__":
    unittest.main()
