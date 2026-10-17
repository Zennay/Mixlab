"""CPU-only global key proposal from streamed chroma. Heuristic, not calibrated.

Mono mix -> integer-factor decimation to roughly 11 kHz -> Hann-windowed FFT
frames -> tonal spectral peaks folded into log-frequency pitch classes between C2 and C7, assuming A4 = 440 Hz
-> correlation with the 24 rotated Krumhansl-Kessler profiles. Abstains when
the signal is too quiet, atonal or the best key does not stand out. One global
key per clip: modulations, modal music and detuned sources are not modelled.
"""

from __future__ import annotations

import cmath
import math

from ..ingest import digest, inspect_wav, pcm_blocks

VERSION = "chroma-kk-v1"
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
KEYS = tuple(f"{pc} {mode}" for mode in ("major", "minor") for pc in PITCH_CLASSES)
# Krumhansl & Kessler (1982) probe-tone ratings, tonic first.
MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
LOW_HZ, HIGH_HZ = 65.406, 2093.0  # C2 .. C7
MIN_CORRELATION = .55
MIN_MARGIN = .02
MIN_RMS = 10 ** (-50 / 20)
PEAK_SPAN = 8      # bins each side for the local-mean reference
PEAK_RATIO = 3.0   # a tonal peak must exceed 3x its neighbourhood mean
MIN_TONAL_FRACTION = .03  # share of in-band magnitude carried by tonal peaks; untuned on real audio


def camelot(key: str) -> str:
    """Camelot wheel code used by DJs, e.g. 'A minor' -> '8A', 'C major' -> '8B'."""
    tonic, mode = _parse(key)
    if mode == "minor":
        tonic = (tonic + 3) % 12  # name minor keys by their relative major's position
    # Camelot steps by fifths with C major at 8B: number = (7 * tonic + 7) mod 12 + 1.
    return f"{(7 * tonic + 7) % 12 + 1}{'A' if mode == 'minor' else 'B'}"


def _parse(key):
    try:
        name, mode = key.split(" ")
        tonic = PITCH_CLASSES.index(name)
    except (AttributeError, ValueError):
        raise ValueError(f"Unsupported key: {key!r}") from None
    if mode not in ("major", "minor"):
        raise ValueError(f"Unsupported key: {key!r}")
    return tonic, mode


def key_score(reference: str, estimated: str | None) -> float:
    """MIREX weighted key score: 1 exact, .5 fifth, .3 relative, .2 parallel, else 0.

    An abstention (None) scores 0; report coverage separately.
    """
    ref_tonic, ref_mode = _parse(reference)
    if estimated is None:
        return 0.
    est_tonic, est_mode = _parse(estimated)
    interval = (est_tonic - ref_tonic) % 12
    if est_mode == ref_mode:
        if interval == 0:
            return 1.
        # A fifth above, or (for minor keys in MIREX) a fifth below, is a near miss.
        if interval == 7 or (ref_mode == "minor" and interval == 5):
            return .5
        return 0.
    if ref_mode == "major" and interval == 9 or ref_mode == "minor" and interval == 3:
        return .3
    return .2 if interval == 0 else 0.


def _fft(values):
    """Iterative radix-2 FFT of a real sequence whose length is a power of two."""
    n = len(values)
    a = [complex(v) for v in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        step = cmath.exp(-2j * math.pi / size)
        half = size // 2
        twiddles = [1 + 0j]
        for _ in range(half - 1):
            twiddles.append(twiddles[-1] * step)
        for start in range(0, n, size):
            for k in range(half):
                u = a[start + k]
                v = a[start + k + half] * twiddles[k]
                a[start + k] = u + v
                a[start + k + half] = u - v
        size *= 2
    return a


def _pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.


def chroma(path) -> tuple[list[float], dict]:
    """Return a normalized 12-bin chroma (C first) and processing metadata."""
    info = inspect_wav(path)
    rate, channels = info["sample_rate"], info["channels"]
    factor = max(1, round(rate / 11025))
    analysis_rate = rate / factor
    size = 4096 if analysis_rate <= 12000 else 8192
    hop = size // 2
    window = [.5 - .5 * math.cos(2 * math.pi * i / size) for i in range(size)]
    bins = []
    for k in range(1, size // 2):
        hz = k * analysis_rate / size
        if LOW_HZ * 2 ** (-1 / 24) <= hz <= HIGH_HZ:
            bins.append((k, round(12 * math.log2(hz / 440.) + 9) % 12))
    first, last = bins[0][0], bins[-1][0]
    band_energy = 0.
    profile = [0.] * 12
    buffer, accumulator, count, energy, samples, frames = [], 0., 0, 0., 0, 0
    for block in pcm_blocks(path, block_frames=8192):
        for i in range(0, len(block), channels):
            accumulator += sum(block[i:i + channels]) / (channels * 32768)
            count += 1
            if count == factor:
                value = accumulator / factor  # box-filter decimation
                buffer.append(value)
                energy += value * value
                samples += 1
                accumulator, count = 0., 0
                if len(buffer) == size:
                    spectrum = _fft([v * w for v, w in zip(buffer, window)])
                    magnitude = [abs(spectrum[k]) for k in range(first - PEAK_SPAN, last + PEAK_SPAN + 1)]
                    for k, pc in bins:
                        # Only tonal peaks vote: a local maximum well above its
                        # neighbourhood. Broadband transients and noise do not.
                        m = magnitude[k - first + PEAK_SPAN]
                        if m <= 0 or m < magnitude[k - first + PEAK_SPAN - 1] or m < magnitude[k - first + PEAK_SPAN + 1]:
                            continue
                        local = magnitude[k - first:k - first + 2 * PEAK_SPAN + 1]
                        if m >= PEAK_RATIO * sum(local) / len(local):
                            profile[pc] += m
                    band_energy += sum(magnitude[PEAK_SPAN:len(magnitude) - PEAK_SPAN])
                    frames += 1
                    del buffer[:hop]
    rms = math.sqrt(energy / samples) if samples else 0.
    total = sum(profile)
    normalized = [v / total for v in profile] if total > 0 else profile
    tonal = total / band_energy if band_energy > 0 else 0.
    return normalized, {"frames": frames, "tonal_fraction": round(tonal, 4), "analysis_rate": analysis_rate, "fft_size": size,
                        "rms": rms, "decimation": factor}


def estimate(path) -> dict:
    """Ranked key candidates, or an abstention with the reason."""
    profile, meta = chroma(path)
    scores = []
    for mode, template in (("major", MAJOR), ("minor", MINOR)):
        for tonic in range(12):
            rotated = [template[(pc - tonic) % 12] for pc in range(12)]
            scores.append((_pearson(profile, rotated), f"{PITCH_CLASSES[tonic]} {mode}"))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    margin = best[0] - second[0]
    reason = None
    if meta["frames"] < 4:
        reason = "too little audio for key evidence"
    elif meta["rms"] < MIN_RMS:
        reason = "signal too quiet for key evidence"
    elif sum(profile) == 0 or meta["tonal_fraction"] < MIN_TONAL_FRACTION:
        reason = "no sustained tonal peaks; manual key annotation required"
    elif best[0] < MIN_CORRELATION:
        reason = "weak tonal evidence; manual key annotation required"
    elif margin < MIN_MARGIN:
        reason = "ambiguous key; top candidates too close"
    return {"key": None if reason else best[1], "correlation": round(best[0], 4),
            "margin": round(margin, 4), "abstain_reason": reason,
            "candidates": tuple((name, round(score, 4)) for score, name in scores[:3]),
            "chroma": tuple(round(v, 5) for v in profile), **meta}


class ChromaKeyProvider:
    """Global key proposal; timing fields stay unavailable."""
    version = VERSION

    def analyze(self, path):
        from . import Analysis
        info = inspect_wav(path)
        result = estimate(path)
        warnings = ["single global key, A4=440 Hz assumed; verify by ear before harmonic mixing",
                    "beats, downbeats and phrases are not inferred by this provider"]
        if result["abstain_reason"]:
            warnings.insert(0, result["abstain_reason"])
        return Analysis(source_sha256=digest(path), provider="chroma-key", provider_version=self.version,
                        duration_seconds=info["duration_seconds"], bpm=None, beats_seconds=(),
                        tempo_confidence=0., energy=(), timing_source="unavailable",
                        key=result["key"], key_source="measured-heuristic" if result["key"] else "unavailable",
                        key_confidence=result["margin"] if result["key"] else 0.,
                        key_candidates=result["candidates"], warnings=tuple(warnings))
