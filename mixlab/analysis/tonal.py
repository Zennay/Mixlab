"""Measured-heuristic global key proposal from a bounded PCM16 excerpt.

Krumhansl-Kessler profile correlation over an octave-folded pitch-class
profile. The scores are correlations, not calibrated probabilities. The
estimator assumes A4 = 440 Hz tuning (about +/-25 cents), one global key and
tonal content; it abstains on weak, flat or ambiguous evidence instead of
guessing. It does not detect modulation, modes other than major/minor, or
vocals.
"""
from dataclasses import asdict, dataclass
import math
from ._signal import PITCH_CLASSES, PitchProjector, decimated_mono
from ..ingest import digest

VERSION = "chroma-kk-v1"
FRAME = 4096
MAX_FRAMES = 240
# Krumhansl & Kessler (1982) probe-tone ratings.
MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
KEYS = tuple(f"{name} {mode}" for mode in ("major", "minor") for name in PITCH_CLASSES)
MIN_CORRELATION = .6
MIN_MARGIN = .04
MIN_TONAL_FRAMES = 3


@dataclass(frozen=True)
class KeyEstimate:
    source_sha256: str
    provider: str
    provider_version: str
    key: str | None
    key_source: str
    correlation: float
    margin: float
    runner_up: str | None
    tonal_frames: int
    pitch_class_profile: tuple
    warnings: tuple
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


def _pearson(a, b):
    ma, mb = sum(a) / 12, sum(b) / 12
    da = [v - ma for v in a]
    db = [v - mb for v in b]
    denominator = math.sqrt(sum(v * v for v in da) * sum(v * v for v in db))
    return sum(x * y for x, y in zip(da, db)) / denominator if denominator > 1e-12 else 0.


def key_scores(profile):
    """Correlation for all 24 keys, in KEYS order."""
    scores = []
    for template in (MAJOR, MINOR):
        for tonic in range(12):
            rotated = [template[(pc - tonic) % 12] for pc in range(12)]
            scores.append(_pearson(profile, rotated))
    return scores


def pitch_class_profile(samples, rate):
    """Sum of per-frame normalized chroma over at most MAX_FRAMES evenly spaced frames."""
    projector = PitchProjector(rate, FRAME)
    total = len(samples) // FRAME
    if total == 0:
        return [0.] * 12, 0
    if total <= MAX_FRAMES:
        picks = range(total)
    else:
        picks = sorted({round(i * (total - 1) / (MAX_FRAMES - 1)) for i in range(MAX_FRAMES)})
    frames = []
    for index in picks:
        frame = samples[index * FRAME:(index + 1) * FRAME]
        chroma = projector.chroma(frame)
        frames.append((sum(chroma), chroma))
    loudest = max((energy for energy, _ in frames), default=0.)
    profile = [0.] * 12
    used = 0
    for energy, chroma in frames:
        # Ignore near-silent frames; normalize so loud frames do not dominate.
        if energy <= max(1e-4, loudest * .05):
            continue
        used += 1
        for pc in range(12):
            profile[pc] += chroma[pc] / energy
    return profile, used


class ChromaKeyProvider:
    """Global key proposal; never a substitute for verified manual annotation."""
    version = VERSION

    def analyze(self, path):
        samples, rate, _info = decimated_mono(path)
        profile, used = pitch_class_profile(samples, rate)
        warnings = ["global key only; modulation, tuning offsets and modes are not modelled",
                    "correlation score is a heuristic, not a probability"]
        total = sum(profile)
        normalized = tuple(round(v / total, 6) for v in profile) if total > 0 else (0.,) * 12
        base = dict(source_sha256=digest(path), provider="chroma-key",
                    provider_version=self.version, tonal_frames=used,
                    pitch_class_profile=normalized)
        if used < MIN_TONAL_FRAMES or total <= 0:
            return KeyEstimate(**base, key=None, key_source="unavailable", correlation=0.,
                               margin=0., runner_up=None,
                               warnings=tuple(["insufficient tonal evidence"] + warnings))
        scores = key_scores(profile)
        ranked = sorted(range(24), key=lambda i: (-scores[i], i))
        best, second = ranked[0], ranked[1]
        correlation, margin = scores[best], scores[best] - scores[second]
        common = dict(base, correlation=round(correlation, 4), margin=round(margin, 4),
                      runner_up=KEYS[second])
        if correlation < MIN_CORRELATION or margin < MIN_MARGIN:
            return KeyEstimate(**common, key=None, key_source="unavailable",
                               warnings=tuple(["ambiguous tonal evidence; manual key required"] + warnings))
        return KeyEstimate(**common, key=KEYS[best], key_source="measured-heuristic",
                           warnings=tuple(warnings))


# MIREX-style weighted key score; used only to report error against manual references.
def key_score(reference, estimate):
    if reference not in KEYS:
        raise ValueError("Unsupported reference key")
    if estimate is None:
        return 0.
    if estimate not in KEYS:
        raise ValueError("Unsupported estimated key")
    if reference == estimate:
        return 1.
    rt, rm = reference.split()
    et, em = estimate.split()
    r, e = PITCH_CLASSES.index(rt), PITCH_CLASSES.index(et)
    if rm == em and (e - r) % 12 in (5, 7):
        return .5
    if rm == "major" and em == "minor" and (e - r) % 12 == 9:
        return .3
    if rm == "minor" and em == "major" and (e - r) % 12 == 3:
        return .3
    if r == e:
        return .2
    return 0.


def key_report(pairs):
    """Aggregate (reference, estimate) pairs into accuracy, weighted score and abstention."""
    pairs = list(pairs)
    if not pairs:
        raise ValueError("No key annotations to evaluate")
    scores = [key_score(reference, estimate) for reference, estimate in pairs]
    answered = [s for (_, estimate), s in zip(pairs, scores) if estimate is not None]
    return {"items": len(pairs), "answered": len(answered),
            "abstention_rate": 1 - len(answered) / len(pairs),
            "exact_accuracy": sum(s == 1. for s in scores) / len(pairs),
            "weighted_score": sum(scores) / len(pairs),
            "weighted_score_answered": sum(answered) / len(answered) if answered else None}


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Propose a global key for a bounded private PCM16 clip")
    parser.add_argument("wav")
    args = parser.parse_args(argv)
    try:
        result = ChromaKeyProvider().analyze(args.wav)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"MixLab key analysis: {exc}\n")
    print(json.dumps(result.to_dict(), allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
