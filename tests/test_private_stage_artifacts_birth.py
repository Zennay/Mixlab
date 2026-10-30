"""Synthetic manual DJ selection must not use write-then-chmod evidence."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from mixlab.models import FAMILY_NAMES
from mixlab.private_transition_selection import export_choice


class PrivateEvidenceBirthTests(unittest.TestCase):
    def test_real_export_uses_exclusive_private_receipt_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gallery = root / "fictional-gallery"
            gallery.mkdir()
            source_bytes = b"synthetic-only-not-a-real-WAV" * 8
            digest = hashlib.sha256(source_bytes).hexdigest()
            for family in FAMILY_NAMES:
                (gallery / f"{family}.wav").write_bytes(source_bytes)
            receipt = {
                "schema_version": 1, "kind": "mixlab-private-manual-transition-gallery",
                "status": "rendered-not-listener-validated", "rights_status": "unverified",
                "renders": [{"family": family, "audio": f"{family}.wav", "audio_sha256": digest}
                            for family in FAMILY_NAMES],
            }
            receipt_bytes = json.dumps(receipt).encode()
            (gallery / "receipt.json").write_bytes(receipt_bytes)
            choice = {
                "schema_version": 1, "kind": "mixlab-private-dj-choice",
                "human_choice_not_blind_study": True,
                "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "selected_family": FAMILY_NAMES[0], "note": "synthetic only",
            }
            choice_file = root / "private-choice.json"
            choice_file.write_text(json.dumps(choice))
            output = root / "chosen.wav"
            # A write-then-chmod publisher creates world-readable bytes under
            # umask 000. All source-evidence writes must use private O_EXCL.
            old_umask = os.umask(0)
            try:
                with patch.object(Path, "write_text", side_effect=AssertionError(
                    "no write-then-chmod evidence publication"
                )):
                    audio, sidecar = export_choice(gallery, choice_file, output)
            finally:
                os.umask(old_umask)
            self.assertEqual(audio.read_bytes(), source_bytes)
            self.assertEqual(stat.S_IMODE(audio.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)
            record = json.loads(sidecar.read_bytes())
            self.assertEqual(record["selected_wav_sha256"], digest)
            self.assertIs(record["source_permission_verified"], False)
            self.assertIs(record["human_blind_preference_verified"], False)


if __name__ == "__main__":
    unittest.main()
