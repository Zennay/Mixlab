"""Independent arithmetic oracles for ML-07 streaming PCM16 metrics.

Exercises both mono and stereo, odd final reads, full-scale signed minimum,
window boundaries and deterministic sample distributions. No external media.
"""
from array import array
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs, scan_wav


def write_test_wav(path, frames, channels, rate=8000):
    values = array("h", (sample for frame in frames for sample in frame))
    if sys.byteorder != "little":
        values.byteswap()
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(values.tobytes())


def dbfs(x):
    return round(20 * math.log10(x), 3) if x else None


class PcmMetricsOracleTests(unittest.TestCase):
    def test_exact_peak_rms_channel_means_and_window_count(self):
        temp = tempfile.TemporaryDirectory(prefix="mixlab-secret-PCM-oracle-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        source = root / "PRIVATE_TRACK_PCM16.wav"
        for channels in (1, 2):
            for frame_count in (1, 799, 800, 801, 4095, 4096, 4097, 9003):
                with self.subTest(channels=channels, frames=frame_count):
                    rng = random.Random(2211 + frame_count * 19 + channels)
                    frames = [tuple(rng.choice(
                        (-32768, -17003, -1, 0, 1, 1337, 16384, 32767)
                    ) for _ in range(channels)) for _ in range(frame_count)]
                    write_test_wav(source, frames, channels)
                    before = source.read_bytes()
                    report = scan_wav(source, window_ms=100)
                    flat = [sample for frame in frames for sample in frame]
                    peak = max(abs(sample) for sample in flat) / 32768
                    rms = math.sqrt(sum(sample * sample for sample in flat) / len(flat)) / 32768
                    self.assertEqual(round(peak, 6), report["peak"])
                    self.assertEqual(dbfs(peak), report["peak_dbfs"])
                    self.assertEqual(round(rms, 8), report["rms"])
                    self.assertEqual(dbfs(rms), report["rms_dbfs"])
                    self.assertEqual(frame_count, report["frames"])
                    self.assertEqual(channels, report["channels"])
                    self.assertEqual(math.ceil(frame_count / 800), report["window_count"])
                    self.assertEqual(
                        [round(sum(frame[c] for frame in frames) / frame_count / 32768, 7)
                         for c in range(channels)],
                        report["dc_per_channel"],
                    )
                    self.assertEqual(
                        [dbfs(math.sqrt(sum(frame[c] ** 2 for frame in frames)
                             / frame_count) / 32768) for c in range(channels)],
                        report["channel_rms_dbfs"],
                    )
                    self.assertEqual(round(frame_count / 8000, 6), report["duration_seconds"])
                    self.assertEqual(before, source.read_bytes())
                    self.assertNotIn(str(root), json.dumps(report))
                    self.assertNotIn("PRIVATE_TRACK", json.dumps(report))

    def test_identical_audio_across_different_valid_riff_metadata_is_a_noop(self):
        temp = tempfile.TemporaryDirectory(prefix="mixlab-private-cross-container-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        base = root / "PRIVATE_artist_A.wav"
        candidate = root / "PRIVATE_artist_B.wav"
        frames = [(3000 if i % 2 else -3000,) for i in range(4097)]
        write_test_wav(base, frames, 1)
        base_bytes = base.read_bytes()
        # JUNK before fmt is legal in private WAV. It must not change the
        # PCM identity or turn a duplicated blind trial into a distinct one.
        riff_chunk = b"JUNK" + (3).to_bytes(4, "little") + b"xyz\x00"
        original_riff_size = int.from_bytes(base_bytes[4:8], "little")
        candidate_bytes = (
            base_bytes[:4] + (original_riff_size + len(riff_chunk)).to_bytes(4, "little")
            + base_bytes[8:12] + riff_chunk + base_bytes[12:]
        )
        candidate.write_bytes(candidate_bytes)
        report = compare_wavs(base, [candidate])
        row = report["candidates"][0]
        self.assertEqual("baseline", row["duplicate_pcm_of"])
        self.assertEqual(report["baseline"], row["metrics"])
        self.assertIn("identical_pcm_to_baseline_inspect_for_noop", row["warnings"])
        self.assertEqual(base_bytes, base.read_bytes())
        self.assertEqual(candidate_bytes, candidate.read_bytes())
        self.assertNotIn(str(root), json.dumps(report))


if __name__ == "__main__":
    unittest.main()
