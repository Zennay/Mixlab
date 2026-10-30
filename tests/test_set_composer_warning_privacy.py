"""Real Composer CLI JSON route with fictional local content and optional failures."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from mixlab import set_composer


class ComposerPrivacyTests(unittest.TestCase):
    def test_complete_wav_survives_and_two_optional_warnings_hide_error_text(self):
        marker = "FICTIONAL-DO-NOT-LOG-TOKEN"
        private_path = "/private/dj/source/" + marker
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "chosen.wav")
            def fake_render(*args):
                with wave.open(str(target), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(b"\x00\x00" * 12)
                return target
            output = io.StringIO()
            with patch.object(sys, "argv", ["set_composer", "render", "/synthetic/session",
                                            "/synthetic/choices.json", str(target),
                                            "--portable-mp3", str(Path(directory, "portable.mp3"))]), \
                 patch("mixlab.set_composer.render_composition", side_effect=fake_render), \
                 patch("mixlab.set_player.publish_player", side_effect=OSError(private_path)), \
                 patch("mixlab.set_delivery.export_portable", side_effect=ValueError(private_path)), \
                 contextlib.redirect_stdout(output):
                set_composer.main()
            result = json.loads(output.getvalue())
            self.assertTrue(target.is_file(), "completed local WAV must survive optional failures")
            self.assertEqual(result["continuous_set"], str(target))
            self.assertIn("player_warning", result)
            self.assertIn("portable_warning", result)
            self.assertNotIn(marker, json.dumps(result))
            self.assertNotIn("/private/dj", json.dumps(result))
            self.assertFalse(result["human_preference_proven"])
            self.assertFalse(result["automatic_beatmatching"])


if __name__ == "__main__":
    unittest.main()
