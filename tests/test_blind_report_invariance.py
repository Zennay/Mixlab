"""Blind-review report invariance under private names and WAV metadata.

A reviewer must not be able to infer answer keys or source identities merely
because files are renamed or harmless private RIFF metadata changes.
Only synthetic locally generated PCM16 is used.
"""
from array import array
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs


def create_wav(path, frames):
    samples = array("h", (v for pair in frames for v in pair))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(8000)
        target.writeframes(samples.tobytes())


def add_metadata(path, before, after):
    original = path.read_bytes()
    def tag(name, data):
        return name + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) & 1 else b"")
    pre = tag(b"JUNK", before)
    post = tag(b"LIST", after)
    payload = original[8:12] + pre + original[12:] + post
    path.write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)


class BlindReportInvarianceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ml07-private-blind-report-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.base = self.root / "SECRET_BASELINE_artist_A.wav"
        self.same = self.root / "SECRET_VARIANT_artist_B.wav"
        self.changed = self.root / "SECRET_VARIANT_artist_C.wav"
        rng = random.Random(17723)
        frames = [(rng.randrange(-15000, 15001), rng.randrange(-14000, 14001))
                  for _ in range(5031)]
        different = [(int(l * 0.78), int(r * 0.84)) for l, r in frames]
        create_wav(self.base, frames)
        create_wav(self.same, frames)
        create_wav(self.changed, different)

    def test_metadata_and_private_renaming_cannot_change_report_values(self):
        original = compare_wavs(self.base, [self.same, self.changed])
        self.assertEqual("baseline", original["candidates"][0]["duplicate_pcm_of"])
        before = [p.read_bytes() for p in (self.base, self.same, self.changed)]
        for idx, path in enumerate((self.base, self.same, self.changed)):
            add_metadata(path, bytes([idx + 1]) * (3 + idx),
                         b"private-artist-metadata" + bytes([idx]))
        self.assertNotEqual(before[0], self.base.read_bytes())
        metadata_report = compare_wavs(self.base, [self.same, self.changed])
        self.assertEqual(original, metadata_report)

        renamed = [
            self.root / "DO_NOT_DISCLOSE__headliner_X.wav",
            self.root / "DO_NOT_DISCLOSE__answer_key_Y.wav",
            self.root / "DO_NOT_DISCLOSE__answer_key_Z.wav",
        ]
        for src, dst in zip((self.base, self.same, self.changed), renamed):
            src.rename(dst)
        renamed_report = compare_wavs(renamed[0], renamed[1:])
        self.assertEqual(original, renamed_report)
        serialized = json.dumps(renamed_report, sort_keys=True)
        for sensitive in ("SECRET_", "DO_NOT_DISCLOSE", "private-artist",
                          str(self.root), "sha256", "st_ino", "mtime"):
            self.assertNotIn(sensitive, serialized)
        self.assertEqual(["candidate-01", "candidate-02"],
                         [row["candidate_id"] for row in renamed_report["candidates"]])

    def test_identical_repeated_candidate_uses_opaque_first_identifier(self):
        prior = self.root / "SECRET_prior.wav"
        repeated = self.root / "SECRET_repeat.wav"
        repeated.write_bytes(self.changed.read_bytes())
        prior.write_bytes(self.changed.read_bytes())
        report = compare_wavs(self.base, [prior, self.same, repeated])
        rows = report["candidates"]
        self.assertIsNone(rows[0]["duplicate_pcm_of"])
        self.assertEqual("baseline", rows[1]["duplicate_pcm_of"])
        self.assertEqual("candidate-01", rows[2]["duplicate_pcm_of"])
        self.assertIn("duplicate_candidate_pcm_inspect", rows[2]["warnings"])
        self.assertNotIn("SECRET_", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
