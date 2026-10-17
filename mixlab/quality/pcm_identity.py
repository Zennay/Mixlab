"""Exact PCM16 identity after trimming only fully zero-valued edge frames.

For blind A/B safety only. No music is read beyond the caller's streaming
PCM chunks; digests and raw samples must never be emitted in review reports.
"""
import hashlib


class EdgeSilencePcmFingerprint:
    """Hash the bounded PCM segment from first to last nonzero *whole frame*.

    Interior silent frames remain significant. Keep only a counter for any
    trailing zero frames, not the audio samples or a whole-recording buffer.
    """
    def __init__(self, channels: int):
        if channels not in (1, 2):
            raise ValueError("Only mono/stereo PCM16 is supported")
        self._frame_bytes = channels * 2
        self._digest = hashlib.sha256()
        self._started = False
        self._pending_zero_frames = 0

    def update(self, raw: bytes) -> None:
        width = self._frame_bytes
        if len(raw) % width:
            raise ValueError("Incomplete PCM16 frame during identity check")
        nframes = len(raw) // width
        first = 0
        while first < nframes and not any(raw[first * width:(first + 1) * width]):
            first += 1
        if first == nframes:
            if self._started:
                self._pending_zero_frames += nframes
            return
        last = nframes - 1
        while last > first and not any(raw[last * width:(last + 1) * width]):
            last -= 1
        if self._started:
            zeros = self._pending_zero_frames + first
            # Streaming O(1) memory even for millions of interior null frames.
            zero_bytes = bytes(width * 4096)
            while zeros:
                count = min(4096, zeros)
                self._digest.update(zero_bytes[:count * width])
                zeros -= count
        self._digest.update(raw[first * width:(last + 1) * width])
        self._started = True
        self._pending_zero_frames = nframes - last - 1

    def digest(self) -> bytes | None:
        """Private byte fingerprint; None for completely silent recordings."""
        return self._digest.digest() if self._started else None
