"""ML-03: bounded, fail-closed private analysis cache acceptance (synthetic audio)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main, mock
import wave

from mixlab.analysis import CACHE_MAX_BYTES, ManualProvider, analyze_cached


class CacheReceiptTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="mixlab-cache-receipt-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic.wav"
        # Pure synthetic silence: no external samples, rights, models or network.
        with wave.open(str(self.source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8000)
        self.directory = self.root / "features"
        self.provider = ManualProvider(120, first_beat=0, annotator="synthetic")
        self.original = analyze_cached(self.source, self.directory, self.provider)
        files = list(self.directory.glob("*.json"))
        self.assertEqual(1, len(files))
        self.entry = files[0]

    def document(self):
        return json.loads(self.entry.read_text(encoding="utf-8"))

    def put(self, item):
        self.entry.write_text(json.dumps(item, sort_keys=True), encoding="utf-8")

    def resign(self, item):
        # Recomputed public checksums cannot defeat independent source/provider checks.
        encoded = json.dumps(item["analysis"], sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        item["analysis_sha256"] = hashlib.sha256(encoded).hexdigest()

    def read(self):
        return analyze_cached(self.source, self.directory, self.provider)

    def test_cache_hit_reuses_valid_analysis_without_recomputing(self):
        before = self.entry.read_bytes()
        with mock.patch.object(self.provider, "analyze", side_effect=AssertionError("reran")):
            self.assertEqual(self.original, self.read())
        self.assertEqual(before, self.entry.read_bytes())
        self.assertEqual(2, self.document()["cache_identity"]["schema"])

    def test_unexpected_changed_bpm_detected_by_receipt_hash(self):
        payload = self.document()
        payload["analysis"]["bpm"] = 123
        self.put(payload)
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.read()

    def test_forged_matching_digest_does_not_override_source_binding(self):
        payload = self.document()
        payload["analysis"]["source_sha256"] = "a" * 64
        self.resign(payload)
        self.put(payload)
        with self.assertRaisesRegex(ValueError, "source/provider"):
            self.read()

    def test_forged_matching_digest_does_not_override_provider_version(self):
        payload = self.document()
        payload["analysis"]["provider_version"] = "manual-fake"
        self.resign(payload)
        self.put(payload)
        with self.assertRaisesRegex(ValueError, "source/provider"):
            self.read()

    def test_forged_matching_digest_does_not_allow_boolean_confidence(self):
        payload = self.document()
        payload["analysis"]["tempo_confidence"] = True
        self.resign(payload)
        self.put(payload)
        with self.assertRaisesRegex(ValueError, "confidence"):
            self.read()

    def test_forged_matching_digest_does_not_allow_bad_beatgrid(self):
        payload = self.document()
        payload["analysis"]["beats_seconds"] = [0, 0]
        self.resign(payload)
        self.put(payload)
        with self.assertRaisesRegex(ValueError, "beatgrid"):
            self.read()

    def test_duplicate_json_keys_fail_closed(self):
        raw = self.entry.read_text(encoding="utf-8")
        self.entry.write_text(raw.replace('"analysis":', '"analysis": {}, "analysis":', 1),
                              encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.read()

    def test_nonfinite_json_literal_is_rejected(self):
        raw = self.entry.read_text(encoding="utf-8")
        self.entry.write_text(raw.replace('"tempo_confidence": 0.0',
                                          '"tempo_confidence": NaN', 1), encoding="utf-8")
        self.assertIn("NaN", self.entry.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            self.read()

    def test_missing_or_extra_schema_keys_fail_closed(self):
        for mutate in (lambda d: d.pop("analysis_sha256"),
                       lambda d: d.update({"extra": "untrusted"})):
            with self.subTest(mutate=repr(mutate)):
                snapshot = self.entry.read_bytes()
                try:
                    payload = self.document()
                    mutate(payload)
                    self.put(payload)
                    with self.assertRaisesRegex(ValueError, "receipt"):
                        self.read()
                finally:
                    self.entry.write_bytes(snapshot)

    def test_oversize_entry_rejected_before_json_parse(self):
        self.entry.write_bytes(b" " * (CACHE_MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "size budget"):
            self.read()

    def test_zero_byte_entry_rejected(self):
        self.entry.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "size budget"):
            self.read()

    def test_symlink_entry_is_not_followed(self):
        original = self.entry.read_bytes()
        target = self.root / "shadow.json"
        target.write_bytes(original)
        self.entry.unlink()
        self.entry.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.read()
        self.assertEqual(original, target.read_bytes())

    def test_directory_entry_rejected(self):
        self.entry.unlink()
        self.entry.mkdir()
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.read()

    def test_fifo_entry_rejected_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("POSIX mkfifo only")
        self.entry.unlink()
        os.mkfifo(self.entry)
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.read()

    def test_invalid_utf8_rejected_without_filename_leak(self):
        self.entry.write_bytes(b"\xff\xfe\xfd")
        with self.assertRaisesRegex(ValueError, "Invalid analysis cache document") as captured:
            self.read()
        self.assertNotIn(str(self.root), str(captured.exception))

    def test_cache_hit_rechecks_source_integrity(self):
        with mock.patch("mixlab.analysis.digest", side_effect=[
            self.original["source_sha256"], "d" * 64
        ]):
            with self.assertRaisesRegex(ValueError, "Source changed"):
                self.read()


if __name__ == "__main__":
    main()
