"""Linux CI-only maximum-frame synthetic stereo A/B resource proof."""
from pathlib import Path
import array
import sys
import resource
import tempfile
import time
import unittest
import wave
from mixlab.quality.intersample import MAX_FRAMES_PER_SOURCE, compare_intersample


class IntersampleResourceTests(unittest.TestCase):
    def test_full_two_million_frame_stereo_pair_has_bounded_memory(self):
        with tempfile.TemporaryDirectory() as private_dir:
            path_a, path_b = [Path(private_dir) / name for name in ("private-a.wav", "private-b.wav")]
            payload = b"\0" * (4096 * 2 * 2)
            for path in (path_a, path_b):
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(2)
                    wav.setsampwidth(2)
                    wav.setframerate(48000)
                    for _ in range(MAX_FRAMES_PER_SOURCE // 4096):
                        wav.writeframesraw(payload)
                    remaining = MAX_FRAMES_PER_SOURCE % 4096
                    wav.writeframesraw(payload[:remaining * 4])
            before = [p.stat().st_size for p in (path_a, path_b)]
            started = time.monotonic()
            report = compare_intersample(path_a, [path_b])
            elapsed = time.monotonic() - started
            rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            self.assertEqual(2_000_000, report["frames_per_source"])
            self.assertFalse(report["baseline"]["intersample_over_risk"])
            self.assertFalse(report["candidates"][0]["intersample_over_risk"])
            self.assertEqual(before, [p.stat().st_size for p in (path_a, path_b)])
            self.assertLess(rss_kib, 192 * 1024, "RSS budget 192 MiB")
            print(f"ML07 2M-frame 48kHz stereo synthetic A/B: elapsed={elapsed:.2f}s, RSS_KiB={rss_kib}")


    def test_full_frame_hot_stereo_adaptive_path_remains_bounded(self):
        # Worst-case CPU: every eligible window triggers all 8x phases.
        # The constant PCM level is legal and should never be 'true peak'
        # clipping just because the adaptive path executes.
        with tempfile.TemporaryDirectory() as private_dir:
            paths = [Path(private_dir) / name for name in ("private-hot-a.wav", "private-hot-b.wav")]
            one_chunk = array.array("h", [32600] * (4096 * 2))
            if sys.byteorder != "little":
                one_chunk.byteswap()
            raw = one_chunk.tobytes()
            for path in paths:
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(2)
                    wav.setsampwidth(2)
                    wav.setframerate(48000)
                    for _ in range(MAX_FRAMES_PER_SOURCE // 4096):
                        wav.writeframesraw(raw)
                    wav.writeframesraw(raw[:(MAX_FRAMES_PER_SOURCE % 4096) * 4])
            started = time.monotonic()
            report = compare_intersample(paths[0], [paths[1]])
            elapsed = time.monotonic() - started
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            self.assertEqual(2_000_000, report["frames_per_source"])
            self.assertGreater(report["baseline"]["adaptive_8x_refined_windows"], 1_900_000)
            self.assertGreater(report["candidates"][0]["adaptive_8x_refined_windows"], 1_900_000)
            self.assertFalse(report["baseline"]["intersample_over_risk"])
            self.assertFalse(report["candidates"][0]["intersample_over_risk"])
            self.assertLess(rss, 192 * 1024)
            print(f"ML07 worst-case 8x adaptive stereo: elapsed={elapsed:.2f}s, RSS_KiB={rss}")

if __name__ == "__main__":
    unittest.main()
