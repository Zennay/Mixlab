"""Offline ML-02 regression: untrusted JSON recursion is a clean validation error."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mixlab.ingest import validate_library


class ManifestNestingAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "untrusted-manifest.json"

    def write(self, value):
        self.path.write_text(value, encoding="utf-8")

    def test_deep_array_and_object_fail_closed(self):
        for name, opening, closing in [
            ("nested-arrays", "[", "]"),
            ("nested-objects", '{"x":', "}"),
        ]:
            with self.subTest(name=name):
                # Syntactically valid JSON, only ~9KiB; too deep for CPython
                # decoder under ordinary interpreter recursion settings.
                self.write('{"schema_version":1,"extra":' +
                           opening * 1400 + "0" + closing * 1400 + "}")
                with self.assertRaisesRegex(ValueError, "nesting limit exceeded"):
                    validate_library(self.path)

    def test_cli_returns_controlled_error_without_traceback_or_path(self):
        self.write('{"schema_version":1,"extra":' + "[" * 1400 +
                   "0" + "]" * 1400 + "}")
        run = subprocess.run(
            [sys.executable, "-m", "mixlab.ingest", str(self.path)],
            capture_output=True, text=True, check=False, timeout=10
        )
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn("nesting limit exceeded", run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertNotIn(str(self.path), run.stderr)
        self.assertFalse(run.stdout)

    def test_shallow_manifest_still_uses_normal_schema_validation(self):
        self.write(json.dumps({"schema_version": 1, "tracks": []}))
        with self.assertRaisesRegex(ValueError, "Library must contain"):
            validate_library(self.path)


if __name__ == "__main__":
    unittest.main()
