"""Synthetic optional-export failures must never disclose private exception text."""
import unittest
from pathlib import Path
from unittest.mock import patch

from mixlab.instant_set import render_instant_set


class OptionalExportPrivacy(unittest.TestCase):
    def test_private_player_and_delivery_failures_are_safe(self):
        sentinel = "FICTIONAL-BEARER-TOKEN-NEVER-PUBLISH"
        secret = "private/example-person/music/" + sentinel
        with patch("mixlab.instant_set._choose_transitions", return_value=(Path("/synthetic"), ["pair-001:bass_swap"])), \
             patch("mixlab.instant_set.export_set", return_value=Path("/synthetic/set.wav")), \
             patch("mixlab.instant_set.publish_player", side_effect=OSError(secret)), \
             patch("mixlab.delivery.export_delivery", side_effect=ValueError(secret)):
            result = render_instant_set("/synthetic", "/synthetic/set.wav", delivery="/synthetic/release.mp3")
        self.assertIn("Completed WAV exists", result["player_warning"])
        self.assertIn("Completed PCM16 WAV exists", result["delivery_warning"])
        for field in ("player_warning", "delivery_warning"):
            self.assertNotIn(sentinel, result[field])
            self.assertNotIn("private/example-person", result[field])
        self.assertFalse(result["human_preference_proven"])
        self.assertFalse(result["automatic_track_discovery"])


if __name__ == "__main__":
    unittest.main()
