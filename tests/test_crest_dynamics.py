"""Synthetic, deterministic tests for the isolated ML-07 crest-factor screen."""

import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.dynamics import compare_crest_factors, _crest_factor_db


def write_wav(path, samples, *, channels=1, rate=8000):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        pcm = array.array("h", samples)
        if sys.byteorder != "little":
            pcm.byteswap()
        output.writeframes(pcm.tobytes())


class CrestDynamicsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.base = self.root / "PRIVATE_baseline.wav"
        self.alt = self.root / "PRIVATE_candidate.wav"
        self.constant = [4000] * 8000
        self.pulses = [16000 if i % 16 == 0 else 0 for i in range(8000)]
        write_wav(self.base, self.constant)
        write_wav(self.alt, self.pulses)

    def test_same_rms_different_crest_flags_transient_confound(self):
        report = compare_crest_factors(self.base, [self.alt])
        row = report["candidates"][0]
        self.assertAlmostEqual(12.041, row["crest_delta_db_vs_baseline"], places=2)
        self.assertEqual(0.0, report["baseline_crest_factor_db"])
        self.assertTrue(row["crest_factor_confound_risk"])
        self.assertEqual(
            ["crest_factor_difference_inspect_not_preference"], row["warnings"]
        )
        self.assertEqual("candidate-01", row["candidate_id"])
        self.assertTrue(report["human_preference_test_required"])
        public = json.dumps(report)
        for secret in ("PRIVATE_", str(self.root), "hash", "samples", "score"):
            self.assertNotIn(secret, public)

    def test_scaled_identical_waveform_has_no_false_positive(self):
        signal = [round(7000 * math.sin(i * 0.11)) for i in range(8000)]
        write_wav(self.base, signal)
        write_wav(self.alt, [round(sample * 0.5) for sample in signal])
        row = compare_crest_factors(self.base, [self.alt])["candidates"][0]
        self.assertAlmostEqual(0.0, row["crest_delta_db_vs_baseline"], delta=0.02)
        self.assertFalse(row["crest_factor_confound_risk"])
        self.assertEqual([], row["warnings"])

    def test_stereo_and_multiple_anonymous_candidates(self):
        normal = [v for x in self.constant for v in (x, -x)]
        pulsed = [v for x in self.pulses for v in (x, -x)]
        write_wav(self.base, normal, channels=2)
        write_wav(self.alt, pulsed, channels=2)
        identical = self.root / "SECRET_second.wav"
        write_wav(identical, normal, channels=2)
        report = compare_crest_factors(self.base, [self.alt, identical])
        self.assertEqual(["candidate-01", "candidate-02"],
                         [entry["candidate_id"] for entry in report["candidates"]])
        self.assertTrue(report["candidates"][0]["crest_factor_confound_risk"])
        self.assertFalse(report["candidates"][1]["crest_factor_confound_risk"])
        self.assertNotIn("SECRET", json.dumps(report))

    def test_silence_has_no_undefined_db_or_artificial_warning(self):
        write_wav(self.base, [0] * 8000)
        row = compare_crest_factors(self.base, [self.alt])["candidates"][0]
        self.assertIsNone(row["crest_delta_db_vs_baseline"])
        self.assertFalse(row["crest_factor_confound_risk"])
        self.assertEqual(["silence_prevents_crest_comparison"], row["warnings"])
        self.assertIsNone(compare_crest_factors(self.base, [self.alt])["baseline_crest_factor_db"])
        write_wav(self.alt, [0] * 8000)
        row = compare_crest_factors(self.base, [self.alt])["candidates"][0]
        self.assertIsNone(row["crest_factor_db"])
        self.assertIsNone(row["crest_delta_db_vs_baseline"])
        self.assertEqual(["silence_prevents_crest_comparison"], row["warnings"])

    def test_strict_cli_silence_warns_and_exits_two(self):
        write_wav(self.base, [0] * 8000)
        run = subprocess.run(
            [sys.executable, "-m", "mixlab.quality.dynamics",
             str(self.base), str(self.alt), "--fail-on-warnings"],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(2, run.returncode, run.stderr)
        result = json.loads(run.stdout)
        self.assertIn("silence_prevents_crest_comparison",
                      result["candidates"][0]["warnings"])
        self.assertNotIn(str(self.root), run.stdout + run.stderr)

    def test_threshold_and_invalid_values_fail_closed(self):
        self.assertFalse(compare_crest_factors(
            self.base, [self.alt], crest_tolerance_db=13.0,
        )["candidates"][0]["crest_factor_confound_risk"])
        for value in (True, None, float("nan"), float("inf"), -1, 0, 0.49, 24.1, "6"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    compare_crest_factors(self.base, [self.alt], crest_tolerance_db=value)
        self.assertIsNone(_crest_factor_db({"peak_dbfs": None, "rms_dbfs": None}))

    def test_quiet_one_lsb_constant_is_exact_zero_crest(self):
        # Scanner's presentation-rounded linear peak overestimates a
        # one-LSB amplitude. dBFS-derived crest must remain precisely zero.
        write_wav(self.base, [1] * 8000)
        write_wav(self.alt, [-1] * 8000)
        report = compare_crest_factors(self.base, [self.alt])
        self.assertEqual(0.0, report["baseline_crest_factor_db"])
        row = report["candidates"][0]
        self.assertEqual(0.0, row["crest_factor_db"])
        self.assertEqual(0.0, row["crest_delta_db_vs_baseline"])
        self.assertFalse(row["crest_factor_confound_risk"])

    def test_reject_mismatched_format_without_mutating_inputs(self):
        before = self.base.read_bytes()
        write_wav(self.alt, [4000] * 11025, rate=11025)
        with self.assertRaises(ValueError):
            compare_crest_factors(self.base, [self.alt])
        self.assertEqual(before, self.base.read_bytes())

    def test_cli_json_warning_exit_and_no_private_paths(self):
        command = [sys.executable, "-m", "mixlab.quality.dynamics",
                   str(self.base), str(self.alt)]
        run = subprocess.run(command + ["--fail-on-warnings"],
                             capture_output=True, text=True, timeout=20)
        self.assertEqual(2, run.returncode, run.stderr)
        self.assertTrue(json.loads(run.stdout)["candidates"][0]["crest_factor_confound_risk"])
        self.assertEqual("", run.stderr)
        for sensitive in (str(self.root), "PRIVATE_", "16000"):
            self.assertNotIn(sensitive, run.stdout + run.stderr)
        without_flag = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(0, without_flag.returncode)
        self.assertEqual(run.stdout, without_flag.stdout)

    def test_cli_bad_arguments_and_missing_files_redact_values(self):
        key = "PRIVATE_TRACK_IDENTIFICATION_CANARY"
        prefix = [sys.executable, "-m", "mixlab.quality.dynamics"]
        for args, expected in (
            ([str(self.base), str(self.alt), "--crest-tolerance-db", key], 2),
            ([str(self.base), str(self.alt), "--unknown-" + key], 2),
            ([str(self.base), str(self.root / (key + ".wav"))], 3),
        ):
            with self.subTest(args=args[-1]):
                run = subprocess.run(prefix + args, capture_output=True, text=True, timeout=20)
                self.assertEqual(expected, run.returncode)
                self.assertEqual("", run.stdout)
                self.assertNotIn(key, run.stderr)
                self.assertNotIn(str(self.root), run.stderr)
                self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
