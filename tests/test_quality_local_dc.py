"""Synthetic, rights-free local DC-bias evidence (never real music)."""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

from mixlab.quality import local_dc


RATE = 8000
DURATION = 4


def _wav(path: Path, *, channels=1, rate=RATE, duration=DURATION, offsets=None, amplitude=700):
    frames = int(rate * duration)
    if offsets is None:
        offsets = [[0] * frames for _ in range(channels)]
    pcm = bytearray()
    for i in range(frames):
        sine = round(amplitude * math.sin(2 * math.pi * 440 * i / rate))
        for c in range(channels):
            pcm += struct.pack("<h", sine + offsets[c][i])
    with wave.open(str(path), "wb") as dest:
        dest.setnchannels(channels)
        dest.setsampwidth(2)
        dest.setframerate(rate)
        dest.writeframes(pcm)


def _offset_sections(levels, *, rate=RATE):
    return [v for level in levels for v in [level] * rate]


class LocalDCQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "baseline.wav"
        self.alt = Path(self.tmp.name) / "candidate.wav"

    def test_negative_sustained_dc_offset(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([-3400] * 4)])
        self.assertIs(local_dc.inspect(self.base, self.alt)["candidate_excess_bias_warning"][0], True)

    def test_large_gain_change_without_dc_is_not_bias(self):
        _wav(self.base, amplitude=700)
        _wav(self.alt, amplitude=10000)
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)

    def test_subthreshold_bias_does_not_flag(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([700] * 4)])
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], False)

    def test_comparison_preserves_private_file_bytes(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([3400] * 4)])
        original = [hashlib.sha256(p.read_bytes()).digest() for p in (self.base, self.alt)]
        self.assertIs(local_dc.inspect(self.base, self.alt)["warning"], True)
        after = [hashlib.sha256(p.read_bytes()).digest() for p in (self.base, self.alt)]
        self.assertEqual(original, after)

    def test_post_scan_baseline_symlink_swap_is_rejected(self):
        _wav(self.base)
        _wav(self.alt)
        original = local_dc._scan_private_pcm
        scans = 0
        def swap_after_candidate(path):
            nonlocal scans
            result = original(path)
            scans += 1
            if scans == 2:
                self.base.unlink()
                self.base.symlink_to(self.alt)
            return result
        with mock.patch.object(local_dc, "_scan_private_pcm", swap_after_candidate):
            with self.assertRaisesRegex(ValueError, "pair inspection"):
                local_dc.inspect(self.base, self.alt)

    def test_non_pcm16_width_rejected(self):
        _wav(self.base)
        with wave.open(str(self.alt), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(1)
            out.setframerate(RATE)
            out.writeframes(b"\x80" * (RATE * DURATION))
        with self.assertRaisesRegex(ValueError, "PCM16"):
            local_dc.inspect(self.base, self.alt)

    def test_identical_sources_are_negative(self):
        _wav(self.base)
        _wav(self.alt)
        data = local_dc.inspect(self.base, self.alt)
        self.assertIs(data["warning"], False)
        self.assertEqual(data["baseline_bias_warning"], [False])
        self.assertEqual(data["candidate_excess_bias_warning"], [False])
        self.assertEqual(data["complete_windows"], 16)

    def test_positive_then_negative_offsets_cancel_globally_but_warn(self):
        _wav(self.base)
        _wav(self.alt, offsets=[_offset_sections([3400, 3400, -3400, -3400])])
        data = local_dc.inspect(self.base, self.alt)
        self.assertIs(data["warning"], True)
        self.assertEqual(data["candidate_excess_bias_warning"], [True])

    def test_baseline_bad_also_warns(self):
        _wav(self.base, offsets=[_offset_sections([3400] * 4)])
        _wav(self.alt, offsets=[_offset_sections([3400] * 4)])
        data = local_dc.inspect(self.base, self.alt)
        self.assertIs(data["baseline_bias_warning"][0], True)
        self.assertIs(data["candidate_excess_bias_warning"][0], False)
        self.assertIs(data["warning"], True)

    def test_one_window_anomaly_abstains(self):
        _wav(self.base)
        offsets = [0] * (RATE * DURATION)
        offsets[RATE:RATE + RATE // 4] = [3400] * (RATE // 4)
        _wav(self.alt, offsets=[offsets])
        data = local_dc.inspect(self.base, self.alt)
        self.assertIsNone(data["candidate_excess_bias_warning"][0])
        self.assertIsNone(data["warning"])

    def test_stereo_one_channel_warns_other_does_not(self):
        _wav(self.base, channels=2)
        _wav(self.alt, channels=2,
             offsets=[_offset_sections([3400] * 4), [0] * (RATE * DURATION)])
        result = local_dc.inspect(self.base, self.alt)
        self.assertEqual(result["candidate_excess_bias_warning"], [True, False])

    def test_zero_length_and_truncated_private_inputs_rejected(self):
        _wav(self.base)
        self.alt.write_bytes(b"RIFF")
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)
        _wav(self.alt)
        payload = self.alt.read_bytes()
        self.alt.write_bytes(payload[:-14])
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_sample_rate_mismatch_rejected(self):
        _wav(self.base)
        _wav(self.alt, rate=11025)
        with self.assertRaisesRegex(ValueError, "identical shape"):
            local_dc.inspect(self.base, self.alt)

    def test_channel_mismatch_rejected(self):
        _wav(self.base)
        _wav(self.alt, channels=2)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_symlink_input_rejected(self):
        _wav(self.base)
        self.alt.symlink_to(self.base)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX specific")
    def test_fifo_is_rejected_without_blocking(self):
        _wav(self.base)
        os.mkfifo(self.alt)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_short_audio_abstains(self):
        _wav(self.base, duration=0.5)
        _wav(self.alt, duration=0.5)
        self.assertIsNone(local_dc.inspect(self.base, self.alt)["warning"])

    def test_cli_is_path_redacted_even_when_input_missing(self):
        _wav(self.base)
        private = Path(self.tmp.name) / "UNIQUE_PRIVATE_MARKER"
        command = [sys.executable, "-m", "mixlab.quality.local_dc", str(self.base), str(private)]
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout, "")
        self.assertNotIn(str(private), done.stderr)
        self.assertNotIn(str(self.base), done.stderr)

    def test_cli_does_not_echo_bad_option_values(self):
        private = str(Path(self.tmp.name) / "UNIQUE_PRIVATE_MARKER")
        done = subprocess.run([sys.executable, "-m", "mixlab.quality.local_dc",
                               "--invalid=" + private, "a", "b"],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 3)
        self.assertNotIn(private, done.stderr)

    def test_cli_strict_unknown_returns_two_and_anonymizes_output(self):
        _wav(self.base)
        offsets = [0] * (RATE * DURATION)
        offsets[RATE:RATE + RATE // 4] = [3400] * (RATE // 4)
        _wav(self.alt, offsets=[offsets])
        command = [sys.executable, "-m", "mixlab.quality.local_dc",
                   str(self.base), str(self.alt), "--strict"]
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 2, done.stderr)
        data = json.loads(done.stdout)
        self.assertIsNone(data["warning"])
        self.assertNotIn(str(self.base), done.stdout)
        self.assertNotIn(str(self.alt), done.stdout)

    def test_too_large_file_rejected_before_parsing(self):
        _wav(self.base)
        with open(self.alt, "wb") as handle:
            handle.truncate(local_dc.MAX_SOURCE_BYTES + 1)
        with self.assertRaises(ValueError):
            local_dc.inspect(self.base, self.alt)

    def test_source_changes_after_scan_are_not_accepted(self):
        _wav(self.base)
        _wav(self.alt)
        original = local_dc._scan_private_pcm
        seen = 0
        def change_after_first_scan(path):
            nonlocal seen
            r = original(path)
            seen += 1
            if seen == 1:
                # A source that mutates while a separate source is scanned
                # must be checked again before publication, not assumed frozen.
                with open(self.base, "ab") as f:
                    f.write(b"CHANGED")
            return r
        with mock.patch.object(local_dc, "_scan_private_pcm", change_after_first_scan):
            with self.assertRaisesRegex(ValueError, "pair inspection"):
                local_dc.inspect(self.base, self.alt)
