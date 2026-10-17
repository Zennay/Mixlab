"""Synthetic privacy, streaming and stereo regression tests for ML-07."""
from array import array
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.reuse import compare_pcm_reuse, MAX_TOTAL_FRAMES


def write_wav(path, signal, *, channels=1, rate=8000):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(rate)
        payload = array("h", signal)
        if sys.byteorder != "little":
            payload.byteswap()
        f.writeframes(payload.tobytes())


def tone(n=16000):
    return [3000 + (i * 1771 % 11000) for i in range(n)]


class PcmReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.baseline = Path(self.tmp.name) / "source_PRIVATE.wav"
        self.candidate = Path(self.tmp.name) / "other_PRIVATE.wav"
        self.samples = tone()
        write_wav(self.baseline, self.samples)
        write_wav(self.candidate, self.samples)

    def row(self):
        return compare_pcm_reuse(self.baseline, [self.candidate])["candidates"][0]

    def test_identical_audio_detected(self):
        row = self.row()
        self.assertEqual(1.0, row["exact_frame_reuse_fraction"])
        self.assertIn("near_identical_candidate_pcm_inspect", row["warnings"])

    def test_one_percent_change_not_missed_by_total_rms_similarity(self):
        changed = self.samples.copy()
        changed[-150:] = [-v for v in changed[-150:]]
        write_wav(self.candidate, changed)
        self.assertIn("near_identical_candidate_pcm_inspect", self.row()["warnings"])

    def test_meaningful_change_is_not_false_copy(self):
        changed = [-v if i % 2 else v for i, v in enumerate(self.samples)]
        write_wav(self.candidate, changed)
        row = self.row()
        self.assertLess(row["exact_frame_reuse_fraction"], 0.8)
        self.assertEqual([], row["warnings"])

    def test_silence_has_no_copy_proof(self):
        write_wav(self.baseline, [0] * 8000)
        write_wav(self.candidate, [0] * 8000)
        self.assertIsNone(self.row()["exact_frame_reuse_fraction"])
        self.assertIn("insufficient_audible_pcm_for_reuse_inspection", self.row()["warnings"])

    def test_mono_stereo_specific_fields_are_null(self):
        row = self.row()
        self.assertIsNone(row["stereo_left_reuse_fraction"])
        self.assertIsNone(row["stereo_swapped_frame_fraction"])

    def test_stereo_single_stale_channel_detected(self):
        stereo = [v for s in self.samples for v in (s, s - 200)]
        edited = [v for s in self.samples for v in (s, -s)]
        write_wav(self.baseline, stereo, channels=2)
        write_wav(self.candidate, edited, channels=2)
        self.assertIn("stereo_single_channel_stale_pcm_inspect", self.row()["warnings"])

    def test_stereo_swap_detected(self):
        stereo = [v for s in self.samples for v in (s, -s)]
        swapped = [v for s in self.samples for v in (-s, s)]
        write_wav(self.baseline, stereo, channels=2)
        write_wav(self.candidate, swapped, channels=2)
        self.assertIn("stereo_channel_swap_pcm_inspect", self.row()["warnings"])

    def test_two_changed_stereo_channels_not_false_stale(self):
        stereo = [v for s in self.samples for v in (s, -s)]
        edited = [v for s in self.samples for v in (-s, s + 50)]
        write_wav(self.baseline, stereo, channels=2)
        write_wav(self.candidate, edited, channels=2)
        self.assertNotIn("stereo_single_channel_stale_pcm_inspect", self.row()["warnings"])

    def test_channel_swap_with_identical_channels_does_not_fake_evidence(self):
        stereo = [v for s in self.samples for v in (s, s)]
        write_wav(self.baseline, stereo, channels=2)
        write_wav(self.candidate, stereo, channels=2)
        self.assertEqual(0.0, self.row()["stereo_swapped_frame_fraction"])

    def test_independent_candidates_and_anonymized_json(self):
        other = Path(self.tmp.name) / "secret-token-sample.wav"
        write_wav(other, [-v for v in self.samples])
        out = compare_pcm_reuse(self.baseline, [self.candidate, other])
        self.assertEqual(["candidate-01", "candidate-02"], [x["id"] for x in out["candidates"]])
        dumped = json.dumps(out)
        self.assertNotIn("PRIVATE", dumped)
        self.assertNotIn("secret-token", dumped)
        self.assertEqual(1.0, out["candidates"][0]["exact_frame_reuse_fraction"])
        self.assertEqual(0, out["candidates"][1]["exact_frame_reuse_fraction"])

    def test_mismatched_channels_rejected(self):
        write_wav(self.candidate, [v for s in self.samples for v in (s, s)], channels=2)
        with self.assertRaises(ValueError):
            self.row()

    def test_mismatched_rate_rejected(self):
        write_wav(self.candidate, self.samples, rate=16000)
        with self.assertRaises(ValueError):
            self.row()

    def test_truncated_payload_rejected(self):
        with self.candidate.open("r+b") as f:
            f.truncate(200)
        with self.assertRaises((ValueError, EOFError, wave.Error)):
            self.row()

    def test_symlink_rejected(self):
        link = Path(self.tmp.name) / "link.wav"
        link.symlink_to(self.baseline)
        with self.assertRaises(OSError):
            compare_pcm_reuse(link, [self.candidate])

    def test_fifo_rejected_without_blocking(self):
        import os
        if not hasattr(os, "mkfifo"):
            self.skipTest("POSIX FIFO required")
        fifo = Path(self.tmp.name) / "source-fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            compare_pcm_reuse(fifo, [self.candidate])
        with self.assertRaises(ValueError):
            compare_pcm_reuse(self.baseline, [fifo])

    def test_too_many_candidates_rejected(self):
        with self.assertRaises(ValueError):
            compare_pcm_reuse(self.baseline, [self.candidate] * 9)

    def test_aggregate_frame_budget_rejected(self):
        self.assertLess(MAX_TOTAL_FRAMES, 2_000_000 * 5)
        samples = [4000] * 2_000_000
        write_wav(self.baseline, samples)
        write_wav(self.candidate, samples)
        with self.assertRaises(ValueError):
            compare_pcm_reuse(self.baseline, [self.candidate] * 4)

    def test_cli_success_has_no_private_paths(self):
        p = subprocess.run([sys.executable, "-m", "mixlab.quality.reuse",
                            str(self.baseline), str(self.candidate)], capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertTrue(json.loads(p.stdout)["human_listening_required"])
        self.assertNotIn("PRIVATE", p.stdout + p.stderr)

    def test_cli_fail_on_warnings(self):
        p = subprocess.run([sys.executable, "-m", "mixlab.quality.reuse",
                            str(self.baseline), str(self.candidate), "--fail-on-warnings"],
                           capture_output=True, text=True)
        self.assertEqual(2, p.returncode)
        self.assertNotIn("PRIVATE", p.stdout + p.stderr)

    def test_cli_argument_injection_redacted(self):
        marker = "SECRET-ABSOLUTE-MUSIC-PATH"
        p = subprocess.run([sys.executable, "-m", "mixlab.quality.reuse",
                            str(self.baseline), str(self.candidate), "--not-an-option=" + marker],
                           capture_output=True, text=True)
        self.assertEqual(2, p.returncode)
        self.assertNotIn(marker, p.stdout + p.stderr)

    def test_cli_invalid_wav_path_redacted(self):
        marker = "SECRET-MUSIC-NOT-FOUND"
        p = subprocess.run([sys.executable, "-m", "mixlab.quality.reuse",
                            str(self.baseline), marker], capture_output=True, text=True)
        self.assertEqual(3, p.returncode)
        self.assertNotIn(marker, p.stdout + p.stderr)

    def test_exact_output_deterministic(self):
        self.assertEqual(compare_pcm_reuse(self.baseline, [self.candidate]),
                         compare_pcm_reuse(self.baseline, [self.candidate]))


    def test_maximum_two_million_stereo_frames_stream_without_memory_copy(self):
        # Exercise the real upper frame bound, not only a header rejection.
        # No giant Python sample array: emit deterministic PCM in 4k chunks.
        for target in (self.baseline, self.candidate):
            with wave.open(str(target), "wb") as dst:
                dst.setnchannels(2)
                dst.setsampwidth(2)
                dst.setframerate(96000)
                chunk = b"\x88\x13\x78\xec" * 4096
                for _ in range(488):
                    dst.writeframesraw(chunk)
                dst.writeframesraw(b"\x88\x13\x78\xec" * 1152)
        row = self.row()
        self.assertEqual(1.0, row["exact_frame_reuse_fraction"])
        self.assertEqual(1.0, row["active_fraction"])

    def test_more_than_two_million_frames_rejected_before_pcm_read(self):
        # Valid tiny sample values, real frame count just past hard limit.
        with wave.open(str(self.baseline), "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(2)
            dst.setframerate(8000)
            chunk = b"\x88\x13" * 4096
            for _ in range(488):
                dst.writeframesraw(chunk)
            dst.writeframesraw(b"\x88\x13" * 1153)
        with self.assertRaises(ValueError):
            self.row()

    def test_sparse_oversized_source_rejected_even_with_small_wav_header(self):
        # A small declared PCM body does not exempt a huge file from the
        # 32MiB physical admission limit.
        from mixlab.quality.reuse import MAX_SOURCE_BYTES
        with self.candidate.open("r+b") as handle:
            handle.truncate(MAX_SOURCE_BYTES + 1)
        with self.assertRaises(ValueError):
            self.row()


if __name__ == "__main__":
    unittest.main()
