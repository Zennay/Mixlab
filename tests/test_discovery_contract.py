"""Prevent future ML-07 companion tests from silently escaping CI discovery.

The primary test_quality module spawns the other suites using a glob which
deliberately excludes test_quality.py. Any newly named 'test_quality_*' module
would also be excluded. Keep critical independent preflight suites visible.
"""
from fnmatch import fnmatchcase
from pathlib import Path
import re
import unittest


class CompanionDiscoveryContractTests(unittest.TestCase):
    def test_ml07_owned_quality_regressions_are_selected_by_real_ci_pattern(self):
        tests_dir = Path(__file__).resolve().parent
        orchestrator = (tests_dir / "test_quality.py").read_text()
        match = re.search(r'sibling_pattern\s*=\s*"([^"]+)"', orchestrator)
        self.assertIsNotNone(match, "Missing real companion CI pattern")
        pattern = match.group(1)
        self.assertNotEqual("test_quality.py", pattern)
        expected = {
            "test_shifted_transformed_pcm.py",
            "test_level_preflight_gate.py",
            "test_request_preflight.py",
            "test_pcm_identity_metamorphic.py",
            "test_pcm_metrics_oracle.py",
            "test_riff_chunk_matrix.py",
            "test_blind_report_invariance.py",
            "test_stereo_level_confound.py",
            "test_stereo_window_balance.py",
            "test_fold_down_ab_level.py",
            "test_fold_down_windows.py",
        }
        selected = {path.name for path in tests_dir.glob(pattern)}
        self.assertTrue(expected <= selected, "ML-07 test omitted from companion CI: " +
                        ", ".join(sorted(expected - selected)))
        self.assertFalse(fnmatchcase("test_quality.py", pattern),
                         "Nested unittest discovery would recursively rerun itself")


if __name__ == "__main__":
    unittest.main()
