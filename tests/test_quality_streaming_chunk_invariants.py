"""Regression invariants for PCM16 stream chunk boundaries (synthetic only).

An audio preflight must not change its result because a 4096-frame read
ends inside an isolated click, a 50ms dropout or a channel dropout.
This suite deliberately does not touch renderer, evaluation or private audio.
"""
from __future__ import annotations

from array import array
import json
import math
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
           extra_chunk: bool = False, sample_rate: int = RATE) -> None:
    pcm = array("h", (sample for frame in frames for sample in frame))
    if sys.byteorder != "little":
        pcm.byteswap()
    raw = pcm.tobytes()
    if extra_chunk:
        # RIFF JUNK is not part of the audible PCM and must not alter
        # the private stream fingerprint or computed signal metrics.
        fmt = struct.pack("<HHIIHH", 1, channels, sample_rate, sample_rate * channels * 2,
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
            output.setframerate(sample_rate)
            output.writeframes(raw)


class StreamingChunkInvariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _make(self, name: str, channels: int, *, spike=None, gap=None,
              left_gap=None, extra_chunk=False, amplitude=4000, sample_rate=RATE, gap_frames=480):
        frames = [[amplitude] * channels for _ in range(FRAMES)]
        if spike is not None:
            for offset in (-1, 1):
                frames[spike + offset] = [0] * channels
            frames[spike] = [10000] * channels
        if gap is not None:
            for index in range(gap, gap + gap_frames):
                frames[index] = [0] * channels
        if left_gap is not None:
            self.assertEqual(channels, 2)
            for index in range(left_gap, left_gap + gap_frames):
                frames[index][0] = 0
        result = self.root / name
        _write(result, channels, [tuple(f) for f in frames],
               extra_chunk=extra_chunk, sample_rate=sample_rate)
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

    def test_chunk_click_detection_across_supported_sample_rates(self):
        # A readframe(4096) split is measured in frames, not seconds.
        # Preserve sample-local impulse detection at 8k, 16k, 48k and 96k.
        for rate in (8000, 16000, 48000, 96000):
            for channels in (1, 2):
                with self.subTest(rate=rate, channels=channels):
                    path = self._make(f"rate-{rate}-{channels}.wav", channels,
                                      spike=CHUNK, sample_rate=rate)
                    result = scan_wav(path)
                    self.assertEqual(result["sample_rate"], rate)
                    self.assertEqual(result["frames"], FRAMES)
                    self.assertEqual(result["isolated_sample_impulse_count"],
                                     channels)
                    self.assertTrue(result["isolated_sample_impulse_risk"])

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

    def test_exact_fifty_millisecond_dropout_threshold_across_rates(self):
        # A 50ms threshold must not turn into 49.9ms or 50.1ms when
        # samples span readframes(4096). 44.1kHz is intentionally non-round.
        for rate in (8000, 16000, 44100, 96000):
            limit = rate // 20
            for frames in (limit - 1, limit):
                start = CHUNK - 3
                with self.subTest(rate=rate, length=frames, kind="all"):
                    sample = self._make(f"all-{rate}-{frames}.wav", 2,
                                        gap=start, gap_frames=frames,
                                        sample_rate=rate)
                    metrics = scan_wav(sample)
                    self.assertEqual(metrics["short_interior_pcm_dropout_risk"],
                                     frames >= limit)
                with self.subTest(rate=rate, length=frames, kind="left"):
                    sample = self._make(f"left-{rate}-{frames}.wav", 2,
                                        left_gap=start, gap_frames=frames,
                                        sample_rate=rate)
                    metrics = scan_wav(sample)
                    self.assertEqual(
                        metrics["short_interior_stereo_channel_dropout_risk"],
                        frames >= limit)
                    self.assertFalse(metrics["short_interior_pcm_dropout_risk"])

    def test_clean_periodic_audio_does_not_create_fake_read_boundary_clicks(self):
        # Use a real continuous, non-DC procedural tone, rather than the
        # constant baseline used to isolate particular positive cases.
        for channels in (1, 2):
            with self.subTest(channels=channels):
                baseline = self.root / f"clean-{channels}.wav"
                candidate = self.root / f"quiet-clean-{channels}.wav"
                def tone(amplitude):
                    return [tuple(round(amplitude * math.sin(2 * math.pi * 220 * i / RATE))
                                  for _ in range(channels)) for i in range(FRAMES)]
                _write(baseline, channels, tone(6000))
                _write(candidate, channels, tone(5600))
                for path in (baseline, candidate):
                    result = scan_wav(path)
                    self.assertFalse(result["isolated_sample_impulse_risk"])
                    self.assertFalse(result["severe_sample_discontinuity_risk"])
                    self.assertFalse(result["short_interior_pcm_dropout_risk"])
                    self.assertFalse(result["dc_offset_risk"])
                    if channels == 2:
                        self.assertFalse(result["short_interior_stereo_channel_dropout_risk"])
                        self.assertFalse(result["mono_fold_down_cancellation_risk"])
                report = compare_wavs(baseline, [candidate])
                self.assertFalse(report["baseline_warnings"])
                self.assertFalse(report["candidates"][0]["warnings"])
                self.assertTrue(report["candidates"][0]["level_comparable_for_blind_ab"])
                self.assertNotIn(str(self.root), json.dumps(report))

    def test_leading_and_trailing_silence_are_not_interior_dropouts(self):
        # Starting/ending a listening excerpt in silence is not itself a
        # mid-playback transport gap. Cover both stereo projected-channel
        # and full-channel PCM runs, alongside the positive interior oracle.
        for channels in (1, 2):
            for offset in (0, FRAMES - 480):
                with self.subTest(channels=channels, edge=offset, kind="all"):
                    sample = self._make(f"edge-all-{channels}-{offset}.wav",
                                        channels, gap=offset)
                    metrics = scan_wav(sample)
                    self.assertFalse(metrics["short_interior_pcm_dropout_risk"])
                    self.assertFalse(metrics["interior_silent_gap_risk"])
                if channels == 2:
                    with self.subTest(channels=channels, edge=offset, kind="left"):
                        sample = self._make(f"edge-left-{offset}.wav", 2,
                                            left_gap=offset)
                        metrics = scan_wav(sample)
                        self.assertFalse(
                            metrics["short_interior_stereo_channel_dropout_risk"])
                        self.assertFalse(metrics["short_interior_pcm_dropout_risk"])

    def test_signed_minimum_sample_at_read_boundary_is_bounded(self):
        # -32768 cannot be safely sign-inverted as signed PCM16. The
        # fingerprint must abstain, not wrap to a bogus negative/positive
        # match. The valid original source must still scan and warn.
        for channels in (1, 2):
            for offset in (CHUNK - 1, CHUNK):
                with self.subTest(channels=channels, offset=offset):
                    frames = [(4000,) * channels for _ in range(FRAMES)]
                    frames[offset] = (-32768,) * channels
                    sample = self.root / f"min-{channels}-{offset}.wav"
                    _write(sample, channels, frames)
                    metrics, digest, _, swapped, inverted = _scan_wav_with_digest(sample)
                    self.assertEqual(metrics["frames"], FRAMES)
                    self.assertEqual(len(digest), 32)
                    self.assertIsNone(inverted)
                    self.assertGreater(metrics["near_full_scale_fraction"], 0)
                    self.assertTrue(metrics["severe_sample_discontinuity_risk"])
                    self.assertEqual(swapped is not None, channels == 2)

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

    def test_multicandidate_swapped_and_inverted_pcm_stays_detectable(self):
        # A source reused after a stereo L/R swap or sign inversion is still
        # the same listening evidence. Assert the real comparison path,
        # including a sample change exactly on both sides of readframes(4096).
        frames = [
            (round(4700 * math.sin(2 * math.pi * 220 * i / RATE)),
             round(3700 * math.sin(2 * math.pi * 330 * i / RATE)))
            for i in range(FRAMES)
        ]
        for pos in (CHUNK - 1, CHUNK):
            with self.subTest(position=pos):
                original = list(frames)
                original[pos] = (7139, -3941)
                root = self.root / f"source-{pos}.wav"
                swapped = self.root / f"swap-{pos}.wav"
                inverted = self.root / f"invert-{pos}.wav"
                duplicate = self.root / f"dupe-{pos}.wav"
                _write(root, 2, original)
                _write(swapped, 2, [(right, left) for left, right in original])
                _write(inverted, 2, [(-left, -right) for left, right in original])
                _write(duplicate, 2, original, extra_chunk=True)
                comparison = compare_wavs(root, [swapped, inverted, duplicate])
                rows = comparison["candidates"]
                self.assertEqual(rows[0]["stereo_swapped_pcm_of"], "baseline")
                self.assertIn("stereo_channel_swapped_pcm_inspect_for_reused_audio",
                              rows[0]["warnings"])
                self.assertEqual(rows[1]["polarity_inverted_pcm_of"], "baseline")
                self.assertIn("polarity_inverted_pcm_inspect_for_reused_audio",
                              rows[1]["warnings"])
                self.assertEqual(rows[2]["duplicate_pcm_of"], "baseline")
                self.assertIn("identical_pcm_to_baseline_inspect_for_noop",
                              rows[2]["warnings"])
                self.assertFalse(comparison["contains_source_paths_or_audio"])
                self.assertNotIn(str(self.root), json.dumps(comparison))

    def test_truncation_in_each_streaming_read_rejected(self):
        # A valid header can still lie about available source frames.
        # Cut both inside the first chunk and just after a complete first
        # chunk; never promote an incomplete remaining read to a clean scan.
        for channels in (1, 2):
            sample = self._make(f"trunc-source-{channels}.wav", channels)
            content = sample.read_bytes()
            header_length = len(content) - FRAMES * channels * 2
            for have in (1, CHUNK - 1, CHUNK, CHUNK + 1, FRAMES - 1):
                with self.subTest(channels=channels, frames_available=have):
                    sample.write_bytes(content[:header_length + have * channels * 2])
                    with self.assertRaises((ValueError, OSError, EOFError)):
                        scan_wav(sample)

    def test_truncated_declared_wav_never_pretends_valid(self):
        sample = self._make("truncated.wav", 1)
        data = sample.read_bytes()
        sample.write_bytes(data[:-9])
        with self.assertRaises((ValueError, OSError, EOFError)):
            scan_wav(sample)


if __name__ == "__main__":
    unittest.main()
