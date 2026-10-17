"""Versioned CPU analysis providers. Heuristic scores are not probabilities."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
import stat
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


# The private feature cache is an optimisation, never a second source of truth.
# Bound all disk reads and bind a canonical analysis receipt to the source/provider.
CACHE_MAX_BYTES = 1_000_000


def _cache_digest(analysis):
    raw = json.dumps(analysis, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _unique_cache_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate analysis cache JSON key")
        result[key] = value
    return result


def _cache_constant(_value):
    raise ValueError("Non-finite analysis cache JSON")


def _read_cache(target):
    """Read one bounded regular file without following a final symlink or FIFO."""
    if target.is_symlink():
        raise ValueError("Analysis cache entry must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Analysis cache entry could not be opened safely") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Analysis cache entry must be a regular file")
            if not 0 < metadata.st_size <= CACHE_MAX_BYTES:
                raise ValueError("Analysis cache size budget exceeded")
            raw = stream.read(CACHE_MAX_BYTES + 1)
            if len(raw) > CACHE_MAX_BYTES:
                raise ValueError("Analysis cache size budget exceeded")
    except OSError as exc:
        raise ValueError("Analysis cache entry could not be read safely") from exc
    try:
        item = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_cache_keys,
                          parse_constant=_cache_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid analysis cache document") from exc
    if not isinstance(item, dict):
        raise ValueError("Invalid analysis cache document")
    return item


def _validate_cached_analysis(document, identity, source_hash, provider, info):
    if set(document) != {"cache_identity", "analysis", "analysis_sha256"}:
        raise ValueError("Incomplete analysis cache receipt")
    if document["cache_identity"] != identity:
        raise ValueError("Analysis cache identity mismatch")
    analysis = document["analysis"]
    if not isinstance(analysis, dict) or set(analysis) != set(Analysis.__dataclass_fields__):
        raise ValueError("Invalid cached analysis schema")
    signature = document["analysis_sha256"]
    if (not isinstance(signature, str) or len(signature) != 64
            or any(character not in "0123456789abcdef" for character in signature)):
        raise ValueError("Invalid analysis cache digest")
    try:
        if _cache_digest(analysis) != signature:
            raise ValueError("Analysis cache integrity mismatch")
    except (TypeError, OverflowError) as exc:
        raise ValueError("Invalid cached analysis values") from exc
    if (type(analysis["schema_version"]) is not int or analysis["schema_version"] != 1
            or analysis["source_sha256"] != source_hash
            or analysis["provider_version"] != provider.version):
        raise ValueError("Analysis cache source/provider mismatch")
    for field in ("provider", "timing_source", "key_source"):
        value = analysis[field]
        if not isinstance(value, str) or not 0 < len(value) <= 100:
            raise ValueError("Invalid cached analysis provenance")
    duration = analysis["duration_seconds"]
    if (type(duration) not in (int, float) or not math.isfinite(duration)
            or abs(duration - info["duration_seconds"]) > 0.000001):
        raise ValueError("Invalid cached analysis duration")
    bpm = analysis["bpm"]
    if bpm is not None:
        number(bpm, "cached bpm", 30, 300)
    number(analysis["tempo_confidence"], "cached confidence", 0, 1)
    if analysis["key"] is not None and (
        not isinstance(analysis["key"], str) or len(analysis["key"]) > 100
    ):
        raise ValueError("Invalid cached analysis key")
    warnings = analysis["warnings"]
    if (not isinstance(warnings, (list, tuple)) or len(warnings) > 64 or
            any(not isinstance(w, str) or len(w) > 256 for w in warnings)):
        raise ValueError("Invalid cached analysis warnings")
    for field in ("beats_seconds", "downbeats_seconds", "phrase_starts_seconds"):
        points = analysis[field]
        if not isinstance(points, (list, tuple)) or len(points) > 10000:
            raise ValueError("Invalid cached analysis beatgrid")
        previous = -1.
        for point in points:
            if (type(point) not in (int, float) or not math.isfinite(point)
                    or point < 0 or point > duration + .000001 or point <= previous):
                raise ValueError("Invalid cached analysis beatgrid")
            previous = point
    energy = analysis["energy"]
    if not isinstance(energy, (list, tuple)) or len(energy) > 100000:
        raise ValueError("Invalid cached analysis energy")
    previous = -1.
    for point in energy:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("Invalid cached analysis energy")
        position, amplitude = point
        if (type(position) not in (int, float) or not math.isfinite(position)
                or position < 0 or position > duration + .000001 or position <= previous):
            raise ValueError("Invalid cached analysis energy")
        number(amplitude, "cached energy", 0, 1)
        previous = position
    # Public checksums detect corruption, not authorization: a rewritten
    # receipt can be rehashed locally. Reject impossible claims that turn a
    # manual observation into a measured provider (or invented key/phrase).
    # Limit this contract to the exact built-in provider implementations;
    # third-party provider schemas remain independently versioned.
    if type(provider) is ManualProvider:
        config = provider.config
        period = 60 / config["bpm"]
        start = config["first_beat"]
        expected_grid = tuple(round(start + n * period, 6) for n in
                              range(math.ceil((duration - start) / period)))
        if (analysis["provider"] != "manual" or
                analysis["timing_source"] != "manual" or
                analysis["tempo_confidence"] != 0 or
                analysis["bpm"] != config["bpm"] or
                analysis["key"] != config["key"] or
                analysis["key_source"] != ("manual" if config["key"] else "unavailable") or
                tuple(analysis["beats_seconds"]) != expected_grid or
                tuple(analysis["downbeats_seconds"]) != config["downbeats"] or
                tuple(analysis["phrase_starts_seconds"]) != config["phrases"] or
                analysis["energy"] or
                tuple(analysis["warnings"]) != ("human annotation; not automatically measured",)):
            raise ValueError("Manual analysis cache provenance/config mismatch")
    elif type(provider) is EnergyOnsetProvider:
        required_warnings = (
            "tempo octave ambiguity; verify beatgrid before rendering",
            "downbeats, phrases, key and vocals are not inferred",
        )
        if (tuple(analysis["warnings"])[-2:] != required_warnings or
                analysis["provider"] != "energy-onset" or
                analysis["timing_source"] != "measured-heuristic" or
                analysis["key"] is not None or
                analysis["key_source"] != "unavailable" or
                analysis["downbeats_seconds"] or
                analysis["phrase_starts_seconds"]):
            raise ValueError("Measured analysis cache provenance mismatch")
    return analysis


def analyze_cached(path, cache_directory, provider=None):
    """Content/config-addressed private feature cache with fail-closed receipts."""
    provider = provider or EnergyOnsetProvider()
    info = inspect_wav(path)
    source_hash = digest(path)
    identity = {"source": source_hash,
                "provider": type(provider).__module__ + "." + type(provider).__qualname__,
                "version": provider.version, "schema": 2}
    cache_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    root = Path(cache_directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / (cache_key + ".json")
    existing = _read_cache(target)
    if existing is not None:
        result = _validate_cached_analysis(existing, identity, source_hash, provider, info)
        if digest(path) != source_hash:
            raise ValueError("Source changed during cached analysis read")
        return result
    result = provider.analyze(path).to_dict()
    if digest(path) != source_hash or result.get("source_sha256") != source_hash:
        raise ValueError("Source changed during analysis")
    document = {"cache_identity": identity, "analysis": result,
                "analysis_sha256": _cache_digest(result)}
    _validate_cached_analysis(document, identity, source_hash, provider, info)
    serialized = json.dumps(document, sort_keys=True, allow_nan=False)
    if len(serialized.encode("utf-8")) > CACHE_MAX_BYTES:
        raise ValueError("Analysis cache size budget exceeded")
    # Publish a complete private file atomically; never overwrite a competing receipt.
    fd, temporary = tempfile.mkstemp(prefix=".analysis-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            concurrent = _read_cache(target)
            if concurrent is None:
                raise ValueError("Concurrent analysis cache entry unavailable")
            other = _validate_cached_analysis(concurrent, identity, source_hash, provider, info)
            if other != result:
                raise ValueError("Conflicting analysis cache entry")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return json.loads(json.dumps(result, allow_nan=False))

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
