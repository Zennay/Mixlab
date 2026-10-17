"""Independent deterministic oracle for ML-07 pairwise DC window screening.

Does not reuse quality-internal window code. Computes exact expected
per-window PCM means and whole-file means directly from generated samples,
including nonaligned 4096-frame reads and final short windows. Synthetic only.
"""
from array import array
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs


def store(path, frames, *, rate=8000):
    data = array("h", (v for frame in frames for v in frame))
    if sys.byteorder != "little":
        data.byteswap()
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(len(frames[0]))
        dst.setsampwidth(2)
        dst.setframerate(rate)
        dst.writeframes(data.tobytes())


def dc_oracle(baseline, candidate, *, window_frames, channels):
    """Independent exact rational-threshold check, excluding quiet windows."""
    audible = 0
    changed = 0
    threshold_numerator = 3
    threshold_denominator = 100 * 32768
    for start in range(0, len(baseline), window_frames):
        original = baseline[start:start + window_frames]
        variant = candidate[start:start + window_frames]
        # All fixture windows are sufficiently nonquiet; explicit assert
        # prevents accidentally testing a zero-audio fixture as audible.
        assert any(any(abs(s) >= 3000 for s in frame) for frame in original)
        audible += 1
        if any(
            abs(sum(variant[i][channel] - original[i][channel]
                    for i in range(len(original)))) * 100 >
            3 * 32768 * len(original)
            for channel in range(channels)
        ):
            changed += 1
    return (round(changed / audible, 6),
            audible >= 3 and changed / audible >= .25)


class DcWindowIndependentOracleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="PRIVATE_DC_ORACLE_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "SECRET_BASE.wav"
        self.other = self.root / "SECRET_VARIANT.wav"

    def test_window_oracle_many_lengths_and_block_boundaries(self):
        rng = random.Random(20261017)
        for channels in (1, 2):
            for frames_count in (800, 801, 4095, 4096, 4097, 9003):
                for window_frames in (160, 800):
                    with self.subTest(channels=channels, frames=frames_count,
                                      window_frames=window_frames):
                        original = [tuple(rng.choice((-1, 1)) * rng.randint(3500, 5200)
                                          for _ in range(channels))
                                    for _ in range(frames_count)]
                        variant = []
                        for frame_index, frame in enumerate(original):
                            window_index = frame_index // window_frames
                            shift = (1150 if window_index % 3 == 0
                                     else 975 if window_index % 3 == 1 else 0)
                            # Never exceed PCM16; all generated values are bounded.
                            variant.append(tuple(
                                sample + (shift if channel == channels - 1 else 0)
                                for channel, sample in enumerate(frame)
                            ))
                        store(self.base, original)
                        store(self.other, variant)
                        frozen_base, frozen_other = self.base.read_bytes(), self.other.read_bytes()
                        report = compare_wavs(self.base, [self.other],
                                              window_ms=window_frames // 8)
                        row = report["candidates"][0]
                        expected_fraction, expected_risk = dc_oracle(
                            original, variant, window_frames=window_frames,
                            channels=channels
                        )
                        self.assertEqual(expected_fraction,
                                         row["ab_dc_window_mismatch_fraction"])
                        self.assertEqual(expected_risk, row["ab_dc_window_mismatch_risk"])
                        self.assertEqual(frozen_base, self.base.read_bytes())
                        self.assertEqual(frozen_other, self.other.read_bytes())
                        serialized = json.dumps(report)
                        self.assertNotIn(str(self.root), serialized)
                        self.assertNotIn("SECRET_", serialized)
                        self.assertNotIn("dc_window_means", serialized)

    def test_realistic_sample_rates_and_partial_windows(self):
        # The scanner derives window frame boundaries from the WAV's true
        # sample rate (not the fixed 8kHz used by other fixtures).
        for rate, window_ms in ((44100, 20), (44100, 50),
                                (96000, 20), (96000, 50)):
            for channels in (1, 2):
                with self.subTest(rate=rate, ms=window_ms, channels=channels):
                    length = 9003
                    window_frames = round(rate * window_ms / 1000)
                    frames = [tuple((4300 if i % 2 else -4300)
                                    for _ in range(channels))
                              for i in range(length)]
                    changed = [tuple(v + (1080 if i < 3 * window_frames
                                          and side == channels - 1 else 0)
                                     for side, v in enumerate(frame))
                               for i, frame in enumerate(frames)]
                    store(self.base, frames, rate=rate)
                    store(self.other, changed, rate=rate)
                    row = compare_wavs(
                        self.base, [self.other], window_ms=window_ms
                    )["candidates"][0]
                    fraction, risk = dc_oracle(
                        frames, changed, window_frames=window_frames,
                        channels=channels
                    )
                    self.assertEqual(fraction, row["ab_dc_window_mismatch_fraction"])
                    self.assertEqual(risk, row["ab_dc_window_mismatch_risk"])
                    # If the requested three windows cover a short entire
                    # file, the *global* DC guard should also fire. Derive
                    # its expected result independently from PCM means.
                    total_changed = min(length, 3 * window_frames)
                    expected_global = (
                        1080 * total_changed > 3 * 32768 * length / 100
                    )
                    self.assertEqual(expected_global, row["ab_dc_offset_mismatch_risk"])
                    self.assertEqual((length + window_frames - 1) // window_frames,
                                     row["metrics"]["window_count"])

    def test_global_dc_oracle_with_opposing_stereo_channel_offsets(self):
        frames = [(4500 if i % 2 else -4500, 4000 if i % 2 else -4000)
                  for i in range(9003)]
        candidate = [(left + 1012, right - 1012) for left, right in frames]
        store(self.base, frames)
        store(self.other, candidate)
        row = compare_wavs(self.base, [self.other])["candidates"][0]
        self.assertAlmostEqual(round(1012 / 32768, 6),
                               row["ab_max_channel_dc_offset_delta_fs"],
                               places=6)
        self.assertTrue(row["ab_dc_offset_mismatch_risk"])


if __name__ == "__main__":
    unittest.main()
