"""Regression invariants for PCM16 stream chunk boundaries (synthetic only).

An audio preflight must not change its result because a 4096-frame read
ends inside an isolated click, a 50ms dropout or a channel dropout.
This suite deliberately does not touch renderer, evaluation or private audio.
"""
from __future__ import annotations

from array import array
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

from mixlab.quality import compare_wavs, scan_wav, _scan_wav_with_digest


RATE = 8000
FRAMES = 10003
CHUNK = 4096


def _write(path: Path, channels: int, frames: list[tuple[int, ...]], *,
           extra_chunk: bool = False) -> None:
    pcm = array("h", (sample for frame in frames for sample in frame))
    if sys.byteorder != "little":
        pcm.byteswap()
    raw = pcm.tobytes()
    if extra_chunk:
        # RIFF JUNK is not part of the audible PCM and must not alter
        # the private stream fingerprint or computed signal metrics.
        fmt = struct.pack("<HHIIHH", 1, channels, RATE, RATE * channels * 2,
                          channels * 2, 16)
        chunks = ((b"fmt ", fmt), (b"JUNK", b"synthetic-not-private"),
                  (b"data", raw))
        body = b"".join(tag + struct.pack("<I", len(payload)) + payload +
                        (b"\x00" if len(payload) & 1 else b"")
                        for tag, payload in chunks)
        path.write_bytes(b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body)
    else:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(raw)


class StreamingChunkInvariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _make(self, name: str, channels: int, *, spike=None, gap=None,
              left_gap=None, extra_chunk=False, amplitude=4000):
        frames = [[amplitude] * channels for _ in range(FRAMES)]
        if spike is not None:
            for offset in (-1, 1):
                frames[spike + offset] = [0] * channels
            frames[spike] = [10000] * channels
        if gap is not None:
            for index in range(gap, gap + 480):
                frames[index] = [0] * channels
        if left_gap is not None:
            self.assertEqual(channels, 2)
            for index in range(left_gap, left_gap + 480):
                frames[index][0] = 0
        result = self.root / name
        _write(result, channels, [tuple(f) for f in frames], extra_chunk=extra_chunk)
        return result

    def test_isolated_click_detected_on_both_sides_of_read_boundary(self):
        for channels in (1, 2):
            reference = None
            for position in (CHUNK - 2, CHUNK - 1, CHUNK, CHUNK + 1):
                with self.subTest(channels=channels, position=position):
                    sample = self._make(f"click-{channels}-{position}.wav",
                                        channels, spike=position)
                    metrics = scan_wav(sample)
                    self.assertTrue(metrics["isolated_sample_impulse_risk"])
                    self.assertEqual(metrics["isolated_sample_impulse_count"], channels)
                    self.assertEqual(metrics["frames"], FRAMES)
                    # Adjacent jumps and peak, unlike timing envelopes, must
                    # remain invariant under moving an identical isolated spike.
                    stable = (metrics["max_adjacent_sample_jump"],
                              metrics["peak"], metrics["near_full_scale_fraction"])
                    if reference is None:
                        reference = stable
                    self.assertEqual(stable, reference)

    def test_global_pcm_dropout_straddling_internal_read_boundary(self):
        for channels in (1, 2):
            for start in (CHUNK - 240, CHUNK - 1, CHUNK + 1):
                with self.subTest(channels=channels, start=start):
                    path = self._make(f"gap-{channels}-{start}.wav",
                                      channels, gap=start)
                    metrics = scan_wav(path)
                    self.assertTrue(metrics["short_interior_pcm_dropout_risk"])
                    self.assertGreaterEqual(
                        metrics["longest_interior_quiet_pcm_gap_ms"], 60)
                    self.assertFalse(metrics["interior_silent_gap_risk"])

    def test_one_channel_dropout_straddling_internal_read_boundary(self):
        for start in (CHUNK - 240, CHUNK - 1, CHUNK + 1):
            with self.subTest(start=start):
                path = self._make(f"stereo-{start}.wav", 2, left_gap=start)
                metrics = scan_wav(path)
                self.assertTrue(metrics["short_interior_stereo_channel_dropout_risk"])
                self.assertGreaterEqual(
                    metrics["longest_interior_stereo_channel_quiet_gap_ms"], 60)
                self.assertFalse(metrics["short_interior_pcm_dropout_risk"])

    def test_pcm_digest_ignores_non_audio_riff_chunks(self):
        for channels in (1, 2):
            with self.subTest(channels=channels):
                canonical = self._make(f"plain-{channels}.wav", channels)
                decorated = self._make(f"junk-{channels}.wav", channels,
                                       extra_chunk=True)
                clean = _scan_wav_with_digest(canonical)
                other = _scan_wav_with_digest(decorated)
                self.assertEqual(clean, other)
                self.assertEqual(scan_wav(canonical)["window_count"], 13)
                self.assertEqual(scan_wav(decorated)["frames"], FRAMES)
                report = compare_wavs(canonical, [decorated])
                self.assertNotIn(str(self.root), json.dumps(report))
                self.assertTrue(report["human_preference_test_required"])

    def test_candidate_chunk_click_survives_ab_comparison(self):
        baseline = self._make("baseline.wav", 2)
        variant = self._make("variant.wav", 2, spike=CHUNK)
        report = compare_wavs(baseline, [variant])
        self.assertIn("isolated_sample_impulse_inspect_for_clicks",
                      report["candidates"][0]["warnings"])
        self.assertEqual(report["candidates"][0]["candidate_id"], "candidate-01")
        self.assertFalse(report["contains_source_paths_or_audio"])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_public_review_rejects_extra_riff_metadata_before_pcm_scan(self):
        from mixlab.quality.pack import inspect_review_pack

        review = self.root / "review"
        review.mkdir()
        _write(review / "trial-001-A.wav", 2, [(4000, 4000)] * 8000)
        _write(review / "trial-001-B.wav", 2, [(4000, 4000)] * 8000,
               extra_chunk=True)
        # Internal scanner allows a valid JUNK chunk because it diagnoses
        # PCM, but the *public* listener pack must refuse it: textual RIFF
        # metadata can leak artist/variant identities during blind review.
        self.assertEqual(scan_wav(review / "trial-001-B.wav")["frames"], 8000)
        with self.assertRaises(ValueError):
            inspect_review_pack(review)

    def test_truncated_declared_wav_never_pretends_valid(self):
        sample = self._make("truncated.wav", 1)
        data = sample.read_bytes()
        sample.write_bytes(data[:-9])
        with self.assertRaises((ValueError, OSError, EOFError)):
            scan_wav(sample)


if __name__ == "__main__":
    unittest.main()
