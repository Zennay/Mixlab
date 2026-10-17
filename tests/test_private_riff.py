"""Private-WAV RIFF contract and early-failure synthetic regressions for ML-07.

Public listener packs have stricter metadata-free rules in quality.pack.
"""
from array import array
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mixlab.quality import compare_wavs, scan_wav


def make_wav(path, channels=2):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        # Construct samples without letting Python's array generator flatten.
        values = array("h", [v for i in range(4097)
                              for v in [int(2800 * ((i % 29) - 14) / 14)] * channels])
        if sys.byteorder != "little":
            values.byteswap()
        wav.writeframes(values.tobytes())


def patch_header(data, offset, changed):
    updated = bytearray(data)
    updated[offset:offset + len(changed)] = changed
    return bytes(updated)


class PrivateRiffQualityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.baseline = self.root / "private source baseline.wav"
        self.variant = self.root / "private source candidate.wav"
        make_wav(self.baseline)
        make_wav(self.variant)
        self.original = self.variant.read_bytes()

    def test_regular_mono_and_stereo_remain_valid(self):
        self.assertEqual(4097, scan_wav(self.baseline)["frames"])
        make_wav(self.variant, channels=1)
        self.assertEqual(4097, scan_wav(self.variant)["frames"])

    def test_private_metadata_chunks_are_accepted_and_never_come_out(self):
        # Preserve direct scan contract: public-review pack forbids metadata,
        # while private source WAVs can have user-entered harmless RIFF fields.
        junk = b"JUNK" + (8).to_bytes(4, "little") + b"secret00"
        with_metadata = self.original[:36] + junk + self.original[36:]
        with_metadata = patch_header(with_metadata, 4, (len(with_metadata) - 8).to_bytes(4, "little"))
        self.variant.write_bytes(with_metadata)
        report = compare_wavs(self.baseline, [self.variant])
        self.assertEqual("baseline", report["candidates"][0]["duplicate_pcm_of"])
        self.assertNotIn("secret", json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(with_metadata, self.variant.read_bytes())

    def test_private_trailing_bytes_preserve_exact_pcm_duplicate_contract(self):
        # Pre-existing ML-07 behavior intentionally ignores private, unbound
        # bytes appended outside RIFF and fingerprints only playback PCM.
        self.variant.write_bytes(self.original + b"non_audio_container_metadata")
        report = compare_wavs(self.baseline, [self.variant])
        self.assertEqual("baseline", report["candidates"][0]["duplicate_pcm_of"])

    def test_rejects_false_byte_rate_and_block_alignment_before_decode(self):
        changed_headers = [
            patch_header(self.original, 28, (8000).to_bytes(4, "little")),
            patch_header(self.original, 32, (2).to_bytes(2, "little")),
            patch_header(self.original, 32, bytes(2)),
            patch_header(self.original, 34, (24).to_bytes(2, "little")),
            patch_header(self.original, 20, (3).to_bytes(2, "little")),
        ]
        for mutated in changed_headers:
            with self.subTest(header=mutated[20:36]):
                self.variant.write_bytes(mutated)
                with patch("mixlab.quality.wave.open",
                           side_effect=AssertionError("PCM decode started")):
                    with self.assertRaises(ValueError):
                        scan_wav(self.variant)
        self.assertEqual(self.original, self.baseline.read_bytes())

    def test_rejects_extra_partial_stereo_frame_before_decode(self):
        mutated = bytearray(self.original + b"\x35\x7a")
        mutated[4:8] = (len(mutated) - 8).to_bytes(4, "little")
        mutated[40:44] = (len(mutated) - 44).to_bytes(4, "little")
        self.variant.write_bytes(mutated)
        # Python wave rounds the partial stereo frame down silently.
        with wave.open(str(self.variant), "rb") as reader:
            self.assertEqual(4097, reader.getnframes())
        with patch("mixlab.quality.wave.open",
                   side_effect=AssertionError("PCM decode started")):
            with self.assertRaisesRegex(ValueError, "alignment"):
                scan_wav(self.variant)

    def test_rejects_truncated_riff_extent_and_unknown_chunk_overflow(self):
        malformed = [
            patch_header(self.original, 4, (len(self.original) + 64).to_bytes(4, "little")),
            patch_header(self.original, 40, (len(self.original) + 1).to_bytes(4, "little")),
            patch_header(self.original, 0, b"RIFX"),
        ]
        for mutated in malformed:
            with self.subTest(mutated=mutated[:44]):
                self.variant.write_bytes(mutated)
                with self.assertRaises(ValueError):
                    scan_wav(self.variant)

    def test_rejects_duplicate_fmt_and_data_before_fmt(self):
        extra_fmt = self.original[12:36]
        duplicate = self.original[:36] + extra_fmt + self.original[36:]
        duplicate = patch_header(duplicate, 4, (len(duplicate) - 8).to_bytes(4, "little"))
        self.variant.write_bytes(duplicate)
        with self.assertRaisesRegex(ValueError, "repeated"):
            scan_wav(self.variant)
        reordered = self.original[:12] + self.original[36:]
        reordered += self.original[12:36]
        reordered = patch_header(reordered, 4, (len(reordered) - 8).to_bytes(4, "little"))
        self.variant.write_bytes(reordered)
        with self.assertRaisesRegex(ValueError, "alignment"):
            scan_wav(self.variant)

    def test_supported_fmt_extension_and_unreported_private_metadata(self):
        extension = self.original[:36] + b"\\x00\\x00" + self.original[36:]
        extension = patch_header(extension, 16, (18).to_bytes(4, "little"))
        extension = patch_header(extension, 4, (len(extension) - 8).to_bytes(4, "little"))
        self.variant.write_bytes(extension)
        self.assertEqual("baseline", compare_wavs(self.baseline, [self.variant])[
            "candidates"][0]["duplicate_pcm_of"])
        # A one-byte extension is invalid; with even pad it still has no cbSize.
        partial = self.original[:36] + b"\\x00\\x00" + self.original[36:]
        partial = patch_header(partial, 16, (17).to_bytes(4, "little"))
        partial = patch_header(partial, 4, (len(partial) - 8).to_bytes(4, "little"))
        self.variant.write_bytes(partial)
        with self.assertRaisesRegex(ValueError, "extension"):
            scan_wav(self.variant)
        # Two-byte ext field must agree with actual extra size.
        forged = patch_header(extension, 36, (2).to_bytes(2, "little"))
        self.variant.write_bytes(forged)
        with self.assertRaisesRegex(ValueError, "extension"):
            scan_wav(self.variant)

    def test_both_cli_modes_fail_sanitized_on_malformed_pcm_container(self):
        invalid = patch_header(self.original, 28, bytes(4))
        self.variant.write_bytes(invalid)
        for extra in ([], ["--fail-on-warnings"]):
            with self.subTest(extra=extra):
                result = subprocess.run(
                    [sys.executable, "-m", "mixlab.quality",
                     str(self.baseline), str(self.variant), *extra],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(3, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertNotIn(str(self.root), result.stderr)
                self.assertNotIn("private source", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
