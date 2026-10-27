"""Bounded mono decimation and pitch-class projection for tonal/meter proposals.

Pure standard library. Decimation uses a boxcar average, which is a crude
anti-alias filter; the pitch range below stays far from the decimated Nyquist
frequency so residual aliasing is a documented heuristic limitation.
"""
from array import array
import math
from operator import mul
from ..ingest import inspect_wav, pcm_blocks

TARGET_RATE = 4000
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# C2 (65.4 Hz) .. B5 (987.8 Hz), equal temperament around A4 = 440 Hz.
LOWEST_MIDI, HIGHEST_MIDI = 36, 83


def decimated_mono(path):
    """Return (samples, rate, info): channel-averaged PCM, decimated to ~4 kHz.

    Memory is bounded by the ingest frame cap (at most 1M float32 values for
    an 8 kHz source, far fewer for 44.1/48 kHz sources).
    """
    info = inspect_wav(path)
    channels = info["channels"]
    factor = max(1, info["sample_rate"] // TARGET_RATE)
    scale = 1 / (32768 * channels * factor)
    stride = channels * factor
    out = array("f")
    # Whole decimation groups per block; a trailing partial group is dropped.
    for block in pcm_blocks(path, block_frames=factor * (8192 // factor)):
        usable = len(block) - len(block) % stride
        columns = [block[offset:usable:stride] for offset in range(stride)]
        out.extend(sum(group) * scale for group in zip(*columns))
    return out, info["sample_rate"] / factor, info


class PitchProjector:
    """Hann-windowed single-bin DFTs at equal-tempered pitches, via C-level dot products."""

    def __init__(self, rate, length):
        if not 8 <= length <= 16384:
            raise ValueError("Unsupported analysis frame length")
        self.length = length
        window = [.5 - .5 * math.cos(2 * math.pi * n / (length - 1)) for n in range(length)]
        self.norm = 2 / sum(window)
        self.tables = []
        for midi in range(LOWEST_MIDI, HIGHEST_MIDI + 1):
            frequency = 440 * 2 ** ((midi - 69) / 12)
            step = 2 * math.pi * frequency / rate
            self.tables.append((midi % 12,
                                array("d", (w * math.cos(step * n) for n, w in enumerate(window))),
                                array("d", (w * math.sin(step * n) for n, w in enumerate(window)))))

    def chroma(self, frame):
        """Twelve octave-folded magnitudes for one frame of exactly `length` samples."""
        if len(frame) != self.length:
            raise ValueError("Frame length mismatch")
        result = [0.] * 12
        for pitch_class, cosine, sine in self.tables:
            real = sum(map(mul, frame, cosine))
            imaginary = sum(map(mul, frame, sine))
            result[pitch_class] += math.hypot(real, imaginary) * self.norm
        return result


def rms(samples, start, stop):
    start, stop = max(0, start), min(len(samples), stop)
    if stop <= start:
        return 0.
    return math.sqrt(sum(map(mul, samples[start:stop], samples[start:stop])) / (stop - start))


def cosine_distance(a, b):
    na = math.sqrt(sum(v * v for v in a))
    nb = math.sqrt(sum(v * v for v in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.
    return 1 - sum(map(mul, a, b)) / (na * nb)


def zscores(values):
    if len(values) < 2:
        return [0.] * len(values)
    mean = sum(values) / len(values)
    spread = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    if spread < 1e-12:
        return [0.] * len(values)
    return [(v - mean) / spread for v in values]
