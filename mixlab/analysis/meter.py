"""Measured-heuristic downbeat and phrase proposals on a supplied beatgrid.

Downbeats are not "every fourth beat from the first onset". For each of the
possible bar phases the estimator measures low-band energy, onset contrast
and harmonic change at the beat and only proposes a phase that is clearly
and consistently accented; otherwise it abstains. Phrases are proposed only
when bar-level energy/harmony novelty repeats with one dominant phase over at
least two whole phrases. A fixed meter (default 4/4) and phrase length
(default 8 bars) are assumptions, not inferred. Scores are z-score contrasts,
not probabilities.
"""
from dataclasses import asdict, dataclass
import math
import statistics
from ._signal import PitchProjector, cosine_distance, decimated_mono, rms, zscores
from ..ingest import digest, number

VERSION = "accent-phase-v1"
MIN_BARS = 4
MAX_BEATS = 10000
DOWNBEAT_CONTRAST = .75
DOWNBEAT_MARGIN = .5
DOWNBEAT_CONSISTENCY = .6
PHRASE_CONTRAST = 1.
PHRASE_MARGIN = .5
PHRASE_CONSISTENCY = .6
LOW_CUTOFF_HZ = 150.


@dataclass(frozen=True)
class MeterProposal:
    source_sha256: str
    provider: str
    provider_version: str
    beats_per_bar: int
    phrase_bars: int
    downbeats_seconds: tuple
    downbeat_contrast: float
    downbeat_margin: float
    downbeat_consistency: float
    phrase_starts_seconds: tuple
    phrase_contrast: float
    phrase_margin: float
    phrase_consistency: float
    timing_source: str
    warnings: tuple
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


def _admit_beats(beats, duration):
    if not isinstance(beats, (tuple, list)) or len(beats) > MAX_BEATS:
        raise ValueError("Invalid beat sequence")
    previous = -1.
    for t in beats:
        number(t, "beat time", 0, duration)
        if t <= previous:
            raise ValueError("Beat times must increase strictly")
        previous = t
    return tuple(beats)


def _lowpass_rms(samples, rate, start, stop):
    # One-pole low-pass with a short warm-up before the measured window.
    alpha = 1 - math.exp(-2 * math.pi * LOW_CUTOFF_HZ / rate)
    state, total, count = 0., 0., 0
    for index in range(max(0, start - round(.05 * rate)), min(len(samples), stop)):
        state += alpha * (samples[index] - state)
        if index >= start:
            total += state * state
            count += 1
    return math.sqrt(total / count) if count else 0.


def _phase_accents(values, period):
    """Mean z-score at each phase minus the mean elsewhere; None entries are ignored."""
    accents = []
    for phase in range(period):
        inside = [v for i, v in enumerate(values) if v is not None and i % period == phase]
        outside = [v for i, v in enumerate(values) if v is not None and i % period != phase]
        accents.append(statistics.mean(inside) - statistics.mean(outside)
                       if inside and outside else -math.inf)
    return accents


def _consistency(values, period, phase, first):
    """Fraction of whole groups whose maximum lies at `phase`."""
    wins = groups = 0
    start = first
    while start + period <= len(values):
        group = values[start:start + period]
        if all(v is not None for v in group):
            groups += 1
            wins += max(range(period), key=lambda k: group[k]) == (phase - start) % period
        start += period
    return wins / groups if groups else 0.


def _combine(*features):
    """Fuse sparse feature vectors without shifting values across time indices."""
    if not features:
        return []
    length = len(features[0])
    if any(len(feature) != length for feature in features):
        raise ValueError("Feature vectors must have equal lengths")

    # Normalize observed values per feature, then put each score back at its
    # original index. Filtering None values without restoring their positions
    # shifts every later score after a gap and combines unrelated beats/bars.
    columns = []
    for feature in features:
        normalized = iter(zscores([value for value in feature if value is not None]))
        columns.append([
            next(normalized) if value is not None else None
            for value in feature
        ])

    combined = []
    for index in range(length):
        parts = [column[index] for column in columns if column[index] is not None]
        combined.append(statistics.mean(parts) if parts else None)
    return combined


def _rank(accents):
    order = sorted(range(len(accents)), key=lambda k: (-accents[k], k))
    best, second = order[0], order[1]
    return best, accents[best], accents[best] - accents[second]


class AccentMeterProvider:
    """Downbeat/phrase proposal; never a substitute for verified manual annotation."""
    version = VERSION

    def __init__(self, beats_per_bar=4, phrase_bars=8):
        if type(beats_per_bar) is not int or not 2 <= beats_per_bar <= 7:
            raise ValueError("Unsupported beats per bar")
        if type(phrase_bars) is not int or not 2 <= phrase_bars <= 32:
            raise ValueError("Unsupported phrase length")
        self.beats_per_bar, self.phrase_bars = beats_per_bar, phrase_bars

    def analyze(self, path, beats):
        samples, rate, info = decimated_mono(path)
        beats = _admit_beats(beats, info["duration_seconds"])
        warnings = [f"assumes {self.beats_per_bar} beats per bar and {self.phrase_bars}-bar phrases",
                    "contrast scores are heuristics, not probabilities; verify before rendering"]
        base = dict(source_sha256=digest(path), provider="accent-meter",
                    provider_version=self.version, beats_per_bar=self.beats_per_bar,
                    phrase_bars=self.phrase_bars, timing_source="measured-heuristic")
        empty_phrase = dict(phrase_starts_seconds=(), phrase_contrast=0., phrase_margin=0.,
                            phrase_consistency=0.)
        if len(beats) < MIN_BARS * self.beats_per_bar:
            return MeterProposal(**base, downbeats_seconds=(), downbeat_contrast=0.,
                                 downbeat_margin=0., downbeat_consistency=0., **empty_phrase,
                                 warnings=tuple(["too few beats for a bar-phase decision"] + warnings))
        period = statistics.median(b - a for a, b in zip(beats, beats[1:]))
        span = max(8, min(1024, round(period * rate * .9)))
        projector = PitchProjector(rate, span)
        quarter = max(1, round(period * rate / 4))
        low, onset, chroma, energy = [], [], [], []
        for t in beats:
            at = round(t * rate)
            low.append(_lowpass_rms(samples, rate, at, at + 2 * quarter))
            onset.append(rms(samples, at, at + quarter) - rms(samples, at - quarter, at))
            energy.append(rms(samples, at, at + 4 * quarter))
            frame = samples[at:at + span]
            chroma.append(projector.chroma(frame) if len(frame) == span else None)
        change = [None] + [cosine_distance(a, b) if a is not None and b is not None else None
                           for a, b in zip(chroma, chroma[1:])]
        combined = _combine(low, onset, change)
        phase, contrast, margin = _rank(_phase_accents(combined, self.beats_per_bar))
        consistency = _consistency(combined, self.beats_per_bar, phase, 0)
        scores = dict(downbeat_contrast=round(contrast, 4), downbeat_margin=round(margin, 4),
                      downbeat_consistency=round(consistency, 4))
        if (contrast < DOWNBEAT_CONTRAST or margin < DOWNBEAT_MARGIN or
                consistency < DOWNBEAT_CONSISTENCY):
            return MeterProposal(**base, downbeats_seconds=(), **scores, **empty_phrase,
                                 warnings=tuple(["no consistent bar accent; manual downbeats required"] + warnings))
        indices = list(range(phase, len(beats), self.beats_per_bar))
        downbeats = tuple(beats[i] for i in indices)
        # Bar-level novelty: energy jump plus harmonic change between consecutive bars.
        bars = []
        for i in indices:
            members = [chroma[j] for j in range(i, min(i + self.beats_per_bar, len(beats)))
                       if chroma[j] is not None]
            bar_chroma = [sum(c[k] for c in members) for k in range(12)] if members else None
            bar_energy = statistics.mean(energy[i:i + self.beats_per_bar])
            bars.append((bar_energy, bar_chroma))
        # Foote-style checkerboard: compare the w bars before and after each
        # bar so that chord changes repeating inside a phrase cancel out.
        w = max(1, self.phrase_bars // 2)
        jump, harmony = [], []
        for j in range(len(bars)):
            if j < w or j + w > len(bars):
                jump.append(None); harmony.append(None)
                continue
            before, after = bars[j - w:j], bars[j:j + w]
            jump.append(abs(statistics.mean(b[0] for b in after) - statistics.mean(b[0] for b in before)))
            if all(b[1] for b in before + after):
                harmony.append(cosine_distance([sum(b[1][k] for b in before) for k in range(12)],
                                               [sum(b[1][k] for b in after) for k in range(12)]))
            else:
                harmony.append(None)
        novelty = _combine(jump, harmony)
        if len(bars) < 2 * self.phrase_bars:
            return MeterProposal(**base, downbeats_seconds=downbeats, **scores, **empty_phrase,
                                 warnings=tuple(["too few bars for a phrase-phase decision"] + warnings))
        q, p_contrast, p_margin = _rank(_phase_accents(novelty, self.phrase_bars))
        p_consistency = _consistency(novelty, self.phrase_bars, q, w)
        phrase_scores = dict(phrase_contrast=round(p_contrast, 4), phrase_margin=round(p_margin, 4),
                             phrase_consistency=round(p_consistency, 4))
        if (p_contrast < PHRASE_CONTRAST or p_margin < PHRASE_MARGIN or
                p_consistency < PHRASE_CONSISTENCY):
            return MeterProposal(**base, downbeats_seconds=downbeats, **scores,
                                 phrase_starts_seconds=(), **phrase_scores,
                                 warnings=tuple(["no consistent phrase boundary; manual phrases required"] + warnings))
        phrases = tuple(downbeats[j] for j in range(q, len(downbeats), self.phrase_bars))
        return MeterProposal(**base, downbeats_seconds=downbeats, **scores,
                             phrase_starts_seconds=phrases, **phrase_scores, warnings=tuple(warnings))


def main(argv=None):
    import argparse
    import json
    from . import EnergyOnsetProvider
    parser = argparse.ArgumentParser(description="Propose downbeats/phrases for a bounded private PCM16 clip")
    parser.add_argument("wav")
    parser.add_argument("--bpm", type=float, help="verified BPM; default uses the energy-onset proposal")
    parser.add_argument("--first-beat", type=float, default=0.)
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--phrase-bars", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        provider = AccentMeterProvider(args.beats_per_bar, args.phrase_bars)
        if args.bpm is None:
            beats = EnergyOnsetProvider().analyze(args.wav).beats_seconds
            if not beats:
                raise ValueError("No beatgrid proposal; pass a verified --bpm and --first-beat")
        else:
            from . import ManualProvider
            beats = ManualProvider(args.bpm, args.first_beat, annotator="cli").analyze(args.wav).beats_seconds
        result = provider.analyze(args.wav, list(beats))
    except ValueError as exc:
        parser.exit(2, f"MixLab meter analysis: {exc}\n")
    except (OSError, TypeError):
        # OS errors carry private operator paths; never echo them.
        parser.exit(2, "MixLab meter analysis: input unavailable (details withheld)\n")
    print(json.dumps(result.to_dict(), allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
