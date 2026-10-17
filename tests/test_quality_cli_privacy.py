"""Native CLI error privacy regression; synthetic PCM, no real music or upload."""
from __future__ import annotations

from array import array
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave


class PrivateQualityCLIErrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mixlab-cli-private-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.secret = "PRIVATE_TRACK_NAME_CREDS_93a1"
        self.base = self.root / ("base-" + self.secret + ".wav")
        self.candidate = self.root / ("candidate-" + self.secret + ".wav")
        for file in (self.base, self.candidate):
            with wave.open(str(file), "wb") as dst:
                dst.setnchannels(1)
                dst.setsampwidth(2)
                dst.setframerate(8000)
                dst.writeframes(array("h", [2400, -2400] * 400).tobytes())

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "mixlab.quality", *map(str, args)],
            capture_output=True, text=True, timeout=12, cwd=Path(__file__).resolve().parents[1],
        )

    def assert_redacted(self, process, *, exit_code):
        self.assertEqual(process.returncode, exit_code, process.stderr[:120])
        self.assertEqual(process.stdout, "")
        self.assertNotIn(self.secret, process.stderr)
        self.assertNotIn(str(self.root), process.stderr)
        self.assertNotIn("Traceback", process.stderr)
        self.assertLessEqual(len(process.stderr), 110)
        self.assertTrue(process.stderr.endswith("\n"), repr(process.stderr))
        self.assertIn("details withheld", process.stderr)

    def test_unknown_option_and_extra_sensitive_operand_do_not_echo_paths(self):
        for args in (
            (self.base, self.candidate, "--" + self.secret),
            (self.base, self.candidate, "--fail-on-warnings=" + self.secret),
            ("--" + self.secret, self.base, self.candidate),
        ):
            with self.subTest(case=str(args[-1])[-18:]):
                self.assert_redacted(self.run_cli(*args), exit_code=2)

    def test_invalid_numeric_values_do_not_echo_arguments(self):
        for option in ("--window-ms", "--loudness-tolerance-db"):
            with self.subTest(option=option):
                self.assert_redacted(
                    self.run_cli(self.base, self.candidate, option, self.secret),
                    exit_code=2,
                )

    def test_missing_required_operand_stays_generic(self):
        self.assert_redacted(self.run_cli(self.base), exit_code=2)

    def test_bad_wav_after_successful_argument_parsing_stays_private(self):
        missing = self.root / ("missing-" + self.secret + ".wav")
        self.assert_redacted(self.run_cli(self.base, missing), exit_code=3)

    def test_nonregular_audio_inputs_do_not_block_or_follow_links(self):
        # A FIFO's st_size is zero: wave.open() otherwise waits for its WAV
        # header indefinitely. Input preflight must refuse before opening it.
        linked = self.root / ("linked-" + self.secret + ".wav")
        linked.symlink_to(self.base)
        directory = self.root / ("directory-" + self.secret + ".wav")
        directory.mkdir()
        for nonregular in (linked, directory):
            with self.subTest(input_kind=nonregular.name.split("-")[0]):
                self.assert_redacted(self.run_cli(self.base, nonregular), exit_code=3)
                self.assert_redacted(self.run_cli(nonregular, self.candidate), exit_code=3)
        if hasattr(__import__("os"), "mkfifo"):
            fifo = self.root / ("fifo-" + self.secret + ".wav")
            __import__("os").mkfifo(fifo)
            self.assert_redacted(self.run_cli(self.base, fifo), exit_code=3)
            self.assert_redacted(self.run_cli(fifo, self.candidate), exit_code=3)

    def test_successful_synthetic_audio_still_emits_only_anonymous_json(self):
        process = self.run_cli(self.base, self.candidate)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        report = json.loads(process.stdout)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["candidates"][0]["candidate_id"], "candidate-01")
        self.assertNotIn(self.secret, process.stdout)
        self.assertNotIn(str(self.root), process.stdout)

    def test_warning_exit_code_remains_distinct_from_invalid_arguments(self):
        warning = self.run_cli(self.base, self.candidate, "--fail-on-warnings")
        self.assertEqual(warning.returncode, 2, warning.stderr)
        self.assertFalse(warning.stderr)
        self.assertTrue(json.loads(warning.stdout)["candidates"][0]["warnings"])


if __name__ == "__main__":
    unittest.main()
