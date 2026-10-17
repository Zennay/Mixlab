"""Linux CI-only maximum-frame synthetic stereo A/B resource proof."""
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
