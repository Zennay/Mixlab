"""Versioned CPU analysis providers. Heuristic scores are not probabilities."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
import statistics
from typing import Protocol
from ..ingest import digest, inspect_wav, number, pcm_blocks

VERSION = "energy-onset-v2"


@dataclass(frozen=True)
class Analysis:
    source_sha256: str
    provider: str
    provider_version: str
    duration_seconds: float
    bpm: float | None
    beats_seconds: tuple
    tempo_confidence: float
    energy: tuple
    timing_source: str
    downbeats_seconds: tuple = ()
    phrase_starts_seconds: tuple = ()
    key: str | None = None
    key_source: str = "unavailable"
    key_confidence: float = 0.
    key_candidates: tuple = ()
    warnings: tuple = ()
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


class Provider(Protocol):
    version: str
    def analyze(self, path) -> Analysis: ...


def _envelope(path, info):
    # Per-channel squared energy avoids cancellation in opposite-polarity stereo.
    rate, channels = info["sample_rate"], info["channels"]
    hop = max(1, round(rate * .02))
    values = []
    for block in pcm_blocks(path, block_frames=hop):
        values.append(math.sqrt(sum((v / 32768) ** 2 for v in block) / len(block)))
    return values, hop / rate


class EnergyOnsetProvider:
    """Regular-tempo proposal for percussive clips; not a general MIR model."""
    version = VERSION

    def analyze(self, path):
        info = inspect_wav(path)
        envelope, step = _envelope(path, info)
        onset = [max(0., v - (envelope[i-1] if i else 0.)) for i, v in enumerate(envelope)]
        maximum = max(onset, default=0.)
        energy = tuple((round(i * step, 6), round(v, 8)) for i, v in enumerate(envelope))
        base = dict(source_sha256=digest(path), provider="energy-onset", provider_version=self.version,
                    duration_seconds=info["duration_seconds"], energy=energy,
                    timing_source="measured-heuristic")
        warnings = ("tempo octave ambiguity; verify beatgrid before rendering",
                    "downbeats, phrases, key and vocals are not inferred")
        if maximum < .002 or len(onset) < 200:
            return Analysis(**base, bpm=None, beats_seconds=(), tempo_confidence=0.,
                            warnings=("insufficient rhythmic evidence",) + warnings)
        threshold = max(.002, maximum * .18)
        peaks = []
        for i, v in enumerate(onset):
            if v >= threshold and (i == 0 or v >= onset[i-1]) and (i+1 == len(onset) or v > onset[i+1]):
                if peaks and i - peaks[-1] < round(.12 / step):
                    if v > onset[peaks[-1]]:
                        peaks[-1] = i
                else:
                    peaks.append(i)
        if len(peaks) < 5:
            return Analysis(**base, bpm=None, beats_seconds=(), tempo_confidence=0.,
                            warnings=("too few onsets",) + warnings)
        # Normalized lag correlation. Restrict proposal to 60–180 BPM and keep
        # the shortest tied lag; octave choice always requires human verification.
        correlations = []
        for lag in range(math.ceil(60 / 180 / step), math.floor(60 / 60 / step) + 1):
            xy = sum(onset[i] * onset[i-lag] for i in range(lag, len(onset)))
            xx = sum(v*v for v in onset[lag:])
            yy = sum(v*v for v in onset[:-lag])
            score = xy / math.sqrt(xx * yy) if xx * yy > 1e-16 else 0.
            correlations.append((score, lag))
        times = [i * step for i in peaks]
        def pulse_fit(item):
            correlation, lag = item
            period = lag * step
            tolerance = max(.025, period * .08)
            # Correlation alone can prefer two-beat repetition over one beat
            # when consecutive onset strengths differ. Penalize both ignored
            # onsets (half tempo) and unsupported grid beats (double tempo).
            best_fit = 0.
            for anchor in times[:min(16, len(times))]:
                phase = anchor % period
                grid_count = max(0, math.ceil((info["duration_seconds"]-phase)/period))
                supported = set()
                explained = 0
                for t in times:
                    n = round((t-phase)/period)
                    if 0 <= n < grid_count and abs(t-(phase+n*period)) <= tolerance:
                        explained += 1
                        supported.add(n)
                matched = len(supported)
                recall = explained/len(times)
                precision = matched/grid_count if grid_count else 0.
                fit = 2*precision*recall/(precision+recall) if precision+recall else 0.
                best_fit = max(best_fit, fit)
            return correlation * best_fit
        best, lag = max(correlations, key=lambda item: (round(pulse_fit(item), 8), -item[1]))
        period = lag * step
        # Refine against observed onset gaps to reduce hop-quantization error.
        gaps = []
        for a, b in zip(times, times[1:]):
            multiple = round((b-a) / period)
            if 1 <= multiple <= 4 and abs((b-a) / multiple - period) <= .08 * period:
                gaps.append((b-a) / multiple)
        if len(gaps) >= 3:
            period = statistics.mean(gaps)
        # Choose the phase supported by the largest fraction of actual onsets.
        tolerance = max(.025, period * .08)
        def support(phase):
            errors = [abs((t-phase + period/2) % period - period/2) for t in times]
            return sum(e <= tolerance for e in errors) / len(errors)
        phase = max(times[:min(16, len(times))], key=lambda t: (support(t), -t)) % period
        grid = tuple(round(phase + n * period, 6) for n in range(
            max(0, math.ceil((info["duration_seconds"] - phase) / period))))
        matched = sum(any(abs(t-b) <= tolerance for t in times) for b in grid)
        coverage = matched / len(grid) if grid else 0.
        confidence = min(best, support(phase), coverage)
        bpm = 60 / period
        if confidence < .45 or not 60 <= bpm <= 180:
            return Analysis(**base, bpm=None, beats_seconds=(), tempo_confidence=round(confidence, 4),
                            warnings=("irregular or ambiguous rhythm; manual annotation required",) + warnings)
        return Analysis(**base, bpm=round(bpm, 5), beats_seconds=grid,
                        tempo_confidence=round(confidence, 4), warnings=warnings)


class ManualProvider:
    """Explicit human annotations, kept separate from measured provider output."""
    def __init__(self, bpm, first_beat=0., downbeats=(), phrases=(), key=None, annotator=""):
        number(bpm, "bpm", 30, 300)
        number(first_beat, "first beat", 0, 250)
        if not isinstance(annotator, str) or not annotator.strip():
            raise ValueError("Manual annotations need an annotator")
        if key is not None and key not in {f"{n} {mode}" for n in
                ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
                for mode in ("major", "minor")}:
            raise ValueError("Unsupported manual key")
        self.config = dict(bpm=bpm, first_beat=first_beat, downbeats=tuple(downbeats),
                           phrases=tuple(phrases), key=key, annotator=annotator)
        self.version = "manual-v1-" + hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()

    def analyze(self, path):
        info = inspect_wav(path)
        duration = info["duration_seconds"]
        if self.config["first_beat"] >= duration:
            raise ValueError("First beat outside audio")
        annotations = {}
        for label in ("downbeats", "phrases"):
            points = self.config[label]
            for point in points:
                number(point, label, 0, duration)
                if point >= duration:
                    raise ValueError("Annotation outside audio")
                beat = (point - self.config["first_beat"]) * self.config["bpm"] / 60
                if beat < -1e-6 or abs(beat - round(beat)) > .02:
                    raise ValueError("Annotation is not on the declared beatgrid")
            if tuple(sorted(set(points))) != points:
                raise ValueError("Annotations must increase strictly")
            annotations[label] = points
        if not set(annotations["phrases"]).issubset(annotations["downbeats"]):
            raise ValueError("Phrase starts must be confirmed downbeats")
        period = 60 / self.config["bpm"]
        start = self.config["first_beat"]
        beats = tuple(round(start + n * period, 6) for n in range(math.ceil((duration-start) / period)))
        return Analysis(source_sha256=digest(path), provider="manual",
                        provider_version=self.version, duration_seconds=duration,
                        bpm=self.config["bpm"], beats_seconds=beats, tempo_confidence=0.,
                        energy=(), timing_source="manual", downbeats_seconds=annotations["downbeats"],
                        phrase_starts_seconds=annotations["phrases"], key=self.config["key"],
                        key_source="manual" if self.config["key"] else "unavailable",
                        warnings=("human annotation; not automatically measured",))


def analyze_cached(path, cache_directory, provider=None):
    """Content/config-addressed private feature cache. No original paths saved."""
    provider = provider or EnergyOnsetProvider()
    inspect_wav(path)
    source_hash = digest(path)
    identity = {"source": source_hash, "provider": type(provider).__module__ + "." + type(provider).__qualname__,
                "version": provider.version, "schema": 1}
    cache_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    root = Path(cache_directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / (cache_key + ".json")
    if target.exists():
        result = json.loads(target.read_text())
        if result.get("cache_identity") != identity:
            raise ValueError("Cache identity mismatch")
        return result["analysis"]
    result = provider.analyze(path).to_dict()
    if digest(path) != source_hash or result["source_sha256"] != source_hash:
        raise ValueError("Source changed during analysis")
    # Publish only complete JSON. A killed analysis must not poison the cache.
    fd, temporary = tempfile.mkstemp(prefix=".analysis-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"cache_identity": identity, "analysis": result}, stream,
                      sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = json.loads(target.read_text())
            if existing.get("cache_identity") != identity or existing.get("analysis") != json.loads(json.dumps(result)):
                raise ValueError("Conflicting cache entry")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return json.loads(json.dumps(result))


def beat_errors(reference, estimated, tolerance=.07):
    """One-to-one event matching; duplicated estimates cannot inflate recall."""
    number(tolerance, "tolerance", .001, .5)
    for points in (reference, estimated):
        for t in points:
            number(t, "beat time", 0, 100000)
        if list(points) != sorted(set(points)):
            raise ValueError("Beat times must increase strictly")
    i = j = 0
    errors = []
    while i < len(reference) and j < len(estimated):
        delta = estimated[j] - reference[i]
        if abs(delta) <= tolerance:
            errors.append(abs(delta)); i += 1; j += 1
        elif delta < 0:
            j += 1
        else:
            i += 1
    precision = len(errors) / len(estimated) if estimated else 0.
    recall = len(errors) / len(reference) if reference else 0.
    return {"matched": len(errors), "precision": precision, "recall": recall,
            "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.,
            "mean_absolute_error_seconds": statistics.mean(errors) if errors else None}
