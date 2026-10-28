"""Independent, seed-reproducible PCM16 numerical oracle for ML-07.

This test package does NOT call canonical scanner helpers when deriving
expected PCM measurements. It uses independently constructed sample frames
and elementary equations; only assertions invoke the production scanner.
All audio is synthesized in a temporary directory. No real recordings,
network services, downloads, credentials or private review identities.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import struct
import tempfile
import unittest
import wave

from mixlab.quality import _scan_wav_with_digest, scan_wav

SEED = 0x47A71CE
FULL_SCALE = 32768
READ_FRAMES = 4096


def _write(path: Path, frames: list[tuple[int, ...]], rate: int) -> bytes:
    channels = len(frames[0])
    raw = b"".join(struct.pack("<" + "h" * channels, *frame) for frame in frames)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(raw)
    return raw


def _dbfs(value: float) -> float | None:
    return round(20 * math.log10(value), 3) if value > 0 else None


def _independent_oracle(frames: list[tuple[int, ...]], rate: int,
                        window_ms: int) -> dict:
    """Brute-force reference; never reuses MixLab source or its helpers."""
    channels = len(frames[0])
    count = len(frames)
    samples = [value for frame in frames for value in frame]
    squared = sum(value ** 2 for value in samples)
    rms = math.sqrt(squared / len(samples)) / FULL_SCALE
    peak = max(abs(value) for value in samples) / FULL_SCALE
    windowsize = max(1, round(rate * window_ms / 1000))
    windows = [
        frames[offset:offset + windowsize]
        for offset in range(0, count, windowsize)
    ]
    window_rms = [
        math.sqrt(sum(value ** 2 for frame in window for value in frame)
                  / (len(window) * channels)) / FULL_SCALE
        for window in windows
    ]
    jumps = [
        abs(frames[pos + 1][ch] - frames[pos][ch])
        for pos in range(count - 1) for ch in range(channels)
    ]
    impulses = sum(
        abs(frames[pos][ch]) >= 8192
        and abs(frames[pos - 1][ch]) <= 2048
        and abs(frames[pos + 1][ch]) <= 2048
        for pos in range(1, count - 1) for ch in range(channels)
    )
    high_plateaus = 0
    for ch in range(channels):
        run = 0
        preceding = None
        for frame in frames:
            value = frame[ch]
            if abs(value) >= round(0.72 * FULL_SCALE) and value == preceding:
                run += 1
            elif abs(value) >= round(0.72 * FULL_SCALE):
                run = 1
            else:
                run = 0
            if run == 4:
                high_plateaus += 1
            preceding = value

    prominent = next(
        (pos for pos, frame in enumerate(frames)
         if any(abs(value) >= 1638 for value in frame)), None
    )
    starts = [
        next((pos for pos, frame in enumerate(frames)
              if abs(frame[ch]) >= 1638), None)
        for ch in range(channels)
    ]
    skew = (
        round(1000 * abs(starts[0] - starts[1]) / rate, 3)
        if channels == 2 and all(value is not None for value in starts)
        else None
    )

    # Segment-based quiet-run oracle: quiet runs count only when audible
    # material occurs strictly before *and after* that segment.
    longest_interior = 0
    pos = 0
    while pos < count:
        if any(abs(value) > 64 for value in frames[pos]):
            pos += 1
            continue
        first = pos
        while pos < count and all(abs(value) <= 64 for value in frames[pos]):
            pos += 1
        if first > 0 and pos < count and any(
                any(abs(x) > 64 for x in frame) for frame in frames[:first]
        ):
            longest_interior = max(longest_interior, pos - first)
    return {
        "channels": channels,
        "sample_rate": rate,
        "frames": count,
        "window_count": len(windows),
        "duration_seconds": round(count / rate, 6),
        "peak": round(peak, 6),
        "peak_dbfs": _dbfs(peak),
        "rms": round(rms, 8),
        "rms_dbfs": _dbfs(rms),
        "dc_per_channel": [
            round(sum(frame[ch] for frame in frames) / count / FULL_SCALE, 7)
            for ch in range(channels)
        ],
        "channel_rms_dbfs": [
            _dbfs(math.sqrt(sum(frame[ch] ** 2 for frame in frames)
                            / count) / FULL_SCALE)
            for ch in range(channels)
        ],
        "near_full_scale_fraction": round(
            sum(abs(value) >= 32760 for value in samples) / len(samples), 8
        ),
        "max_adjacent_sample_jump": round(max(jumps, default=0) / FULL_SCALE, 6),
        "severe_adjacent_jump_count": sum(delta >= FULL_SCALE / 2 for delta in jumps),
        "isolated_sample_impulse_count": impulses,
        "high_flat_top_plateau_count": high_plateaus,
        "prominent_audio_onset_ms": (
            round(1000 * prominent / rate, 3) if prominent is not None else None
        ),
        "stereo_channel_onset_gap_ms": skew,
        "playback_start_peak": round(
            max(abs(value) for value in frames[0]) / FULL_SCALE, 6
        ),
        "playback_end_peak": round(
            max(abs(value) for value in frames[-1]) / FULL_SCALE, 6
        ),
        "min_window_rms_dbfs": _dbfs(min(window_rms)),
        "max_window_rms_dbfs": _dbfs(max(window_rms)),
        "longest_interior_quiet_pcm_gap_ms": round(
            1000 * longest_interior / rate, 3
        ),
        "short_interior_pcm_dropout_risk": 1000 * longest_interior >= 50 * rate,
        "_windows": window_rms,
    }


def _fixtures(seed: int, length: int, channels: int, family: int):
    rng = random.Random(seed)
    if family == 0:  # broadband, including valid signed-16 extrema
        return [
            tuple(rng.randint(-32768, 32767) for _ in range(channels))
            for _ in range(length)
        ]
    if family == 1:  # sparse impulse and silence, true frame locality
        choices = [-32768, -27000, -9200, -64, 0, 64, 9200, 27000, 32767]
        return [
            tuple(rng.choice(choices) if rng.randrange(8) == 0 else 0
                  for _ in range(channels))
            for _ in range(length)
        ]
    if family == 2:  # bounded non-DC periodic audio with different channels
        return [
            tuple(round(4500 * math.sin(2 * math.pi * (97 + 113 * ch)
                                        * i / 8000))
                  for ch in range(channels))
            for i in range(length)
        ]
    if family == 3:  # repeated near-full-scale plateaus and hard sign flips
        return [
            tuple((26000 if (i // 4 + ch) % 2 == 0 else -26000)
                  for ch in range(channels))
            for i in range(length)
        ]
    return [
        tuple(rng.randint(-20, 20) for _ in range(channels))
        for _ in range(length)
    ]  # genuine quiet PCM, not inventing audio above the threshold


class PcmNumericalOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mixlab-pcm-oracle-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _check(self, path: Path, frames: list[tuple[int, ...]],
               rate: int, window_ms: int):
        raw = _write(path, frames, rate)
        reference = _independent_oracle(frames, rate, window_ms)
        # _scan_wav_with_digest geeft later 12 waarden terug; deze test gebruikt de eerste 5
        actual, digest, windows, swapped, inverted = _scan_wav_with_digest(
            path, window_ms=window_ms
        )[:5]
        independent_windows = reference.pop("_windows")
        for field, expected in reference.items():
            with self.subTest(field=field):
                self.assertEqual(actual[field], expected)
        self.assertEqual(digest, hashlib.sha256(raw).digest())
        self.assertEqual(len(windows), len(independent_windows))
        for real, theoretical in zip(windows, independent_windows):
            self.assertAlmostEqual(real, theoretical, delta=1e-11)
        if len(frames[0]) == 1:
            self.assertIsNone(swapped)
        else:
            other = b"".join(struct.pack("<hh", right, left)
                             for left, right in frames)
            self.assertEqual(swapped, hashlib.sha256(other).digest())
        if any(-32768 in frame for frame in frames):
            self.assertIsNone(inverted)
        else:
            opposite = b"".join(
                struct.pack("<" + "h" * len(frame),
                            *(-sample for sample in frame))
                for frame in frames
            )
            self.assertEqual(inverted, hashlib.sha256(opposite).digest())
        # Public scan may disclose calculated metrics but not source identity,
        # exact sample arrays, private hashes or any private file location.
        self.assertEqual(scan_wav(path, window_ms=window_ms), actual)
        data = json.dumps(actual, allow_nan=False, sort_keys=True)
        self.assertNotIn(str(self.root), data)
        self.assertNotIn(digest.hex(), data)
        return actual

    def test_seeded_120_differential_pcm_oracle_cases(self):
        # Independently derived oracle over five signal families, both
        # channel modes, three rates, 20/50/100/1000ms windows, 4096 seams
        # and 16-bit extremes. The fixed seed makes failures reproducible.
        rng = random.Random(SEED)
        lengths = (1, 2, 31, 159, 160, 513, 4095, 4096,
                   4097, 8191, 8192, 8193, 10301)
        for index in range(120):
            channels = 1 + (index % 2)
            rate = (8000, 44100, 96000)[index % 3]
            width = (20, 50, 100, 1000)[index % 4]
            nframes = lengths[(index * 7 + index // 13) % len(lengths)]
            family = (index // 2) % 5
            frames = _fixtures(rng.getrandbits(32), nframes, channels, family)
            with self.subTest(case=index, frames=nframes, rate=rate,
                              channels=channels, family=family, window=width):
                self._check(self.root / f"oracle-{index}.wav",
                            frames, rate, width)

    def test_64_deterministic_dropout_frame_threshold_oracles(self):
        # Sample-count oracle is independent of the production 4096-frame
        # block reader. All-channel silence starting inside a *valid*
        # audible region is a missing-PCM risk only if >= 50ms and recovers.
        nframes = 16001
        for rate in (8000, 16000, 44100, 96000):
            threshold = rate // 20
            for channels in (1, 2):
                for start in (4095, 4096, 4097, 8191):
                    for count in (threshold - 1, threshold):
                        frames = [tuple([5500] * channels) for _ in range(nframes)]
                        for i in range(start, start + count):
                            frames[i] = tuple([0] * channels)
                        with self.subTest(rate=rate, channels=channels,
                                          start=start, quiet=count):
                            result = self._check(
                                self.root / f"drop-{rate}-{channels}-{start}-{count}.wav",
                                frames, rate, 100
                            )
                            self.assertEqual(
                                result["short_interior_pcm_dropout_risk"],
                                count == threshold,
                            )

    def test_reference_oracle_is_sensitive_to_mutated_metrics(self):
        # A trivial test implementation that only checks report shape
        # cannot catch regressions. Intentionally corrupt separately
        # computed values and show independent equality assertions fail.
        frames = [(0,), (9000,), (0,), (-32768,), (32767,), (0,)]
        target = self.root / "oracle-control.wav"
        self._check(target, frames, 8000, 100)
        true_reference = _independent_oracle(frames, 8000, 100)
        result = scan_wav(target)
        for field, wrong in (
            ("isolated_sample_impulse_count", result["isolated_sample_impulse_count"] + 1),
            ("peak", 0.1),
            ("rms_dbfs", 0.0),
            ("max_adjacent_sample_jump", 0.0),
            ("high_flat_top_plateau_count", 5),
        ):
            with self.subTest(field=field):
                poisoned = dict(result, **{field: wrong})
                with self.assertRaises(AssertionError):
                    self.assertEqual(poisoned[field], true_reference[field])


if __name__ == "__main__":
    unittest.main()
