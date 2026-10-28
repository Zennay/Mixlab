"""Measure how the kicks of two aligned segments actually line up.

Independent of any fitted beatgrid: the raw low-band kick onset strength of
segment A (from a_start) and of segment B (from b_start) are cross-correlated
over the transition length. The best lag within half a beat is the real kick
offset a listener would hear:

- about 0 ms: kicks land together;
- roughly 10-40 ms: a flam (doubled kick);
- close to half a beat: one track is locked to the other's off-beat (a
  train-wreck).

Sharpness compares the best correlation with the best one at least a quarter
beat away; low sharpness means the measurement itself is ambiguous.
"""
from dataclasses import asdict, dataclass
import math
import statistics
from ._signal import decimated_mono
from .kick import _onsets

FLAM_SECONDS = .010
TRAIN_WRECK_FRACTION = .25


@dataclass(frozen=True)
class KickOffset:
    lag_seconds: float | None
    lag_beats: float | None
    sharpness: float
    verdict: str

    def to_dict(self):
        return asdict(self)


def _segment(path, start, seconds):
    samples, rate, _info = decimated_mono(path)
    onset, step = _onsets(samples, rate)
    first = round(start / step)
    return onset[first:first + round(seconds / step)], step


def _correlate(a, b, lag):
    if lag >= 0:
        pairs = zip(a[lag:], b)
    else:
        pairs = zip(a, b[-lag:])
    return sum(x * y for x, y in pairs)


def kick_offset(a_path, a_start, b_path, b_start, bpm, seconds):
    """Positive lag: B's kicks arrive later than A's."""
    a, step = _segment(a_path, a_start, seconds)
    b, _ = _segment(b_path, b_start, seconds)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if n < 50 or not any(a) or not any(b):
        return KickOffset(None, None, 0., "insufficient kick evidence")
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    a = [v - ma for v in a]
    b = [v - mb for v in b]
    period = 60 / bpm
    half = round(period / 2 / step)
    scores = {lag: _correlate(b, a, lag) for lag in range(-half, half + 1)}
    best = max(scores, key=scores.get)
    rival = max((s for lag, s in scores.items() if abs(lag - best) * step >= period / 4), default=0.)
    peak = scores[best]
    sharpness = (peak - rival) / abs(peak) if peak > 0 else 0.
    lag = best * step
    if peak <= 0 or sharpness < .1:
        verdict = "ambiguous"
    elif abs(lag) >= TRAIN_WRECK_FRACTION * period:
        verdict = "off-beat (train-wreck risk)"
    elif abs(lag) > FLAM_SECONDS:
        verdict = "flam"
    else:
        verdict = "aligned"
    return KickOffset(round(lag, 4), round(lag / period, 4), round(sharpness, 4), verdict)
