"""Measured-heuristic beatgrid for four-on-the-floor dance music.

The broadband energy-onset proposal abstains on most real full mixes: hats,
bass and pads swamp its single envelope. Club music instead carries a kick on
every beat, so this provider:

1. low-passes the decimated mono signal (two one-pole stages, ~120 Hz) and
   takes the rectified log-energy rise per 5 ms frame as kick onset strength;
2. scores every beat period in the DJ range (default 100-140 BPM) by
   autocorrelation at one, two and four beats, then interpolates the peak;
3. picks the comb phase with the most onset energy;
4. matches the strongest onset peak near each predicted beat and fits
   t_n = t0 + n * period by least squares, dropping outliers, for a precise
   tempo and phase over the whole excerpt.

It abstains when too few beats carry a clear kick or the fit is irregular.
Assumptions: steady tempo, kick on the beat, tempo inside the DJ range (so no
octave choice is made). Scores are heuristics, not probabilities.
"""
import math
import statistics
from . import Analysis
from ._signal import decimated_mono
from ..ingest import digest

VERSION = "kick-grid-v1"
FRAME_SECONDS = .005
CUTOFF_HZ = 120.
ENVELOPE_SECONDS = .01
MIN_COVERAGE = .6
MAX_RESIDUAL_SECONDS = .015


def _onsets(samples, rate):
    alpha = 1 - math.exp(-2 * math.pi * CUTOFF_HZ / rate)
    # Envelope follower longer than one bass cycle, so the waveform itself
    # does not read as onsets; sampled every frame.
    smooth = 1 - math.exp(-1 / (ENVELOPE_SECONDS * rate))
    hop = max(1, round(rate * FRAME_SECONDS))
    a = b = e = 0.
    energy = []
    for i, x in enumerate(samples):
        a += alpha * (x - a)
        b += alpha * (a - b)
        e += smooth * (b * b - e)
        if i % hop == hop - 1:
            energy.append(e)
    floor = max(energy, default=0.) * 1e-4 + 1e-12
    level = [math.log(max(v, floor)) for v in energy]
    onset = [0., 0.] + [max(0., v - u) for u, v in zip(level, level[2:])]
    return onset[:len(level)], hop / rate


def _autocorrelation(values, lag):
    return sum(values[i] * values[i - lag] for i in range(lag, len(values)))


class KickGridProvider:
    """Beatgrid proposal for kick-driven 4/4 excerpts; abstains on anything else."""
    version = VERSION

    def __init__(self, low_bpm=100., high_bpm=140.):
        if not 40 <= low_bpm < high_bpm <= 220 or high_bpm > 2 * low_bpm:
            raise ValueError("Tempo range must lie in 40..220 BPM and span at most one octave")
        self.low_bpm, self.high_bpm = float(low_bpm), float(high_bpm)

    def analyze(self, path):
        samples, rate, info = decimated_mono(path)
        onset, step = _onsets(samples, rate)
        base = dict(source_sha256=digest(path), provider="kick-grid", provider_version=self.version,
                    duration_seconds=info["duration_seconds"], energy=(),
                    timing_source="measured-heuristic")
        warnings = ("assumes a steady four-on-the-floor kick inside "
                    f"{self.low_bpm:g}-{self.high_bpm:g} BPM; verify before rendering",
                    "downbeats, phrases, key and vocals are not inferred")

        def abstain(reason, confidence=0.):
            return Analysis(**base, bpm=None, beats_seconds=(), tempo_confidence=round(confidence, 4),
                            warnings=(reason,) + warnings)
        if len(onset) < 400 or max(onset, default=0.) <= 0:
            return abstain("insufficient low-band rhythmic evidence")
        mean = statistics.fmean(onset)
        centred = [v - mean for v in onset]
        low_lag = math.floor(60 / self.high_bpm / step)
        high_lag = math.ceil(60 / self.low_bpm / step)
        cache = {}

        def ac(lag):
            if lag not in cache:
                cache[lag] = _autocorrelation(centred, lag) if lag < len(centred) else 0.
            return cache[lag]
        scores = {lag: ac(lag) + .5 * ac(2 * lag) + .25 * ac(4 * lag)
                  for lag in range(low_lag, high_lag + 1)}
        frames = len(onset)
        threshold = statistics.median(v for v in onset if v > 0)
        # Local maxima of the period score; refine the strongest few and keep the best fit.
        peaks = [l for l in scores if scores[l] >= scores.get(l - 1, -math.inf)
                 and scores[l] >= scores.get(l + 1, -math.inf)]
        best = None
        for lag in sorted(peaks, key=scores.get, reverse=True)[:3]:
            fitted = _fit_grid(onset, step, frames, scores, lag, threshold, info["duration_seconds"])
            if fitted and (best is None or fitted[2] < best[2]):
                best = fitted
        if best is None:
            return abstain("too few kick-aligned beats")
        t0, period, rms, matched_count = best
        while t0 - period >= 0:
            t0 -= period
        while t0 < 0:
            t0 += period
        grid = tuple(round(t0 + n * period, 6)
                     for n in range(int((info["duration_seconds"] - t0) / period) + 1)
                     if t0 + n * period < info["duration_seconds"])
        coverage = min(1., matched_count / len(grid)) if grid else 0.
        bpm = 60 / period
        confidence = coverage * max(0., 1 - rms / MAX_RESIDUAL_SECONDS)
        if coverage < MIN_COVERAGE or rms > MAX_RESIDUAL_SECONDS or not self.low_bpm <= bpm <= self.high_bpm:
            return abstain("kick grid irregular or sparse; manual annotation required", confidence)
        return Analysis(**base, bpm=round(bpm, 5), beats_seconds=grid,
                        tempo_confidence=round(confidence, 4),
                        warnings=(f"kick coverage {coverage:.2f}, fit residual {rms * 1000:.1f} ms",)
                        + warnings)


def _fit_grid(onset, step, frames, scores, lag, threshold, duration):
    left, right = scores.get(lag - 1, scores[lag]), scores.get(lag + 1, scores[lag])
    curvature = left - 2 * scores[lag] + right
    shift = .5 * (left - right) / curvature if curvature < 0 else 0.
    period = (lag + max(-.5, min(.5, shift))) * step
    period_frames = period / step
    phases = [sum(onset[int(round(p + n * period_frames))]
                  for n in range(int((frames - 1 - p) / period_frames) + 1))
              for p in range(int(period_frames))]
    phase = max(range(len(phases)), key=phases.__getitem__) * step
    window = max(1, round(.08 * period / step))
    count = int((duration - phase) / period) + 1
    matched = []
    for n in range(count):
        centre = round((phase + n * period) / step)
        lo, hi = max(0, centre - window), min(frames, centre + window + 1)
        if lo >= hi:
            continue
        peak = max(range(lo, hi), key=onset.__getitem__)
        if onset[peak] > threshold:
            matched.append((n, peak * step))
    t0 = phase
    for _ in range(3):
        if len(matched) < 8:
            return None
        xs, ys = [m[0] for m in matched], [m[1] for m in matched]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        period = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        t0 = my - period * mx
        residuals = [abs(y - (t0 + period * x)) for x, y in matched]
        kept = [m for m, r in zip(matched, residuals) if r <= 2.5 * MAX_RESIDUAL_SECONDS]
        if len(kept) == len(matched):
            break
        matched = kept
    if len(matched) < 8:
        return None
    rms = math.sqrt(statistics.fmean((y - (t0 + period * x)) ** 2 for x, y in matched))
    return t0, period, rms, len(matched)


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Propose a kick-driven beatgrid for a bounded PCM16 clip")
    parser.add_argument("wav")
    parser.add_argument("--low-bpm", type=float, default=100.)
    parser.add_argument("--high-bpm", type=float, default=140.)
    args = parser.parse_args(argv)
    try:
        result = KickGridProvider(args.low_bpm, args.high_bpm).analyze(args.wav)
    except ValueError as exc:
        parser.exit(2, f"MixLab kick analysis: {exc}\n")
    except (OSError, TypeError):
        parser.exit(2, "MixLab kick analysis: input unavailable (details withheld)\n")
    summary = result.to_dict()
    summary["beats_seconds"] = list(summary["beats_seconds"][:8]) + (["..."] if len(result.beats_seconds) > 8 else [])
    print(json.dumps(summary, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
