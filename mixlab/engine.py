"""Bounded PCM16 WAV renderer; no decoding services, MIR or tempo estimation.

Inputs are short, manually aligned clips at the same sample rate, channel count
and declared tempo. All families share duration and gain; no per-file loudness
normalization or ranking is performed. Metrics are engineering diagnostics,
not estimates of musical quality.
"""

from array import array
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import sys
import wave

from .models import FAMILY_NAMES, Recipe

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_INPUT_FRAMES = 2_000_000
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 96000


def load_wav(path):
    path = Path(path)
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("WAV exceeds 32 MiB input limit; trim a source clip first")
    try:
        with wave.open(str(path), "rb") as source:
            channels, width, rate, count, compression, _ = source.getparams()
            if compression != "NONE" or width != 2 or channels not in (1, 2):
                raise ValueError("Only uncompressed PCM16 mono/stereo WAV is supported")
            if not MIN_SAMPLE_RATE <= rate <= MAX_SAMPLE_RATE:
                raise ValueError("Sample rate must be between 8000 and 96000 Hz")
            if not 1 <= count <= MAX_INPUT_FRAMES:
                raise ValueError("Input must contain 1 to 2,000,000 frames; trim a source clip first")
            raw = source.readframes(count)
            if len(raw) != count * channels * 2:
                raise ValueError("Truncated WAV data")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid or unsupported WAV: {exc}") from exc
    values = array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    frames = [tuple(values[i + c] / 32768.0 for c in range(channels))
              for i in range(0, len(values), channels)]
    return rate, frames


def write_wav(path, sr, frames):
    if not isinstance(sr, int) or not MIN_SAMPLE_RATE <= sr <= MAX_SAMPLE_RATE:
        raise ValueError("Sample rate must be an integer from 8000 to 96000")
    if not frames or len(frames) > MAX_INPUT_FRAMES:
        raise ValueError("Output must contain 1 to 2,000,000 frames")
    channels = len(frames[0])
    if channels not in (1, 2):
        raise ValueError("Output must be mono or stereo")
    samples = array("h")
    for frame in frames:
        if len(frame) != channels or any(not math.isfinite(v) for v in frame):
            raise ValueError("Frames must have matching channels and finite samples")
        samples.extend(max(-32768, min(32767, round(v * 32768))) for v in frame)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(sr)
        target.writeframes(samples.tobytes())


def measure(frames):
    """Describe pre-quantization audio, including samples that will clip in PCM16."""
    channels = len(frames[0])
    total = len(frames) * channels
    sums = [0.0] * channels
    power = [0.0] * channels
    peak, jump, clipped = 0.0, 0.0, 0
    previous = frames[0]
    for frame in frames:
        for c, value in enumerate(frame):
            sums[c] += value
            power[c] += value * value
            peak = max(peak, abs(value))
            jump = max(jump, abs(value - previous[c]))
            clipped += value < -1.0 or value > 32767 / 32768
        previous = frame
    return {
        "peak": peak,
        "rms": math.sqrt(sum(power) / total),
        "clipping_samples": clipped,
        "clipping_fraction": clipped / total,
        "dc_per_channel": [value / len(frames) for value in sums],
        "rms_per_channel": [math.sqrt(value / len(frames)) for value in power],
        "max_sample_jump": jump,
    }


def _digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def render(a_path, b_path, out_path, recipe: Recipe):
    """Render one transition and return JSON-serializable reproducibility metadata.

    a_start and b_start identify matching, manually chosen downbeats. Absent
    source BPM overrides mean the caller declares both sources at recipe.bpm.
    At the first/last frame every family exactly matches the selected A/B clip
    at common gain, allowing fair same-duration listening comparisons.
    """
    if not isinstance(recipe, Recipe):
        raise TypeError("recipe must be a Recipe")
    output_path = Path(out_path).resolve()
    if output_path in (Path(a_path).resolve(), Path(b_path).resolve()) or (
        output_path.exists() and any(output_path.samefile(path) for path in (a_path, b_path))
    ):
        raise ValueError("Output must not overwrite an input")
    if output_path.exists():
        raise ValueError("Output already exists; use a new candidate path")
    rate, a = load_wav(a_path)
    b_rate, b = load_wav(b_path)
    channels = len(a[0])
    if rate != b_rate or channels != len(b[0]):
        raise ValueError("Inputs must have identical sample rates and channel counts")
    count = round(recipe.beats * 60.0 / recipe.bpm * rate)
    a_offset, b_offset = round(recipe.a_start * rate), round(recipe.b_start * rate)
    if count > MAX_INPUT_FRAMES or count < 2:
        raise ValueError("Requested transition exceeds the frame budget")
    if a_offset + count > len(a) or b_offset + count > len(b):
        raise ValueError("Source clips are too short for the requested aligned transition")
    a, b = a[a_offset:a_offset + count], b[b_offset:b_offset + count]
    gain = 10 ** (recipe.gain_db / 20)
    low_a, low_b = [0.0] * channels, [0.0] * channels
    alpha = 1.0 - math.exp(-2 * math.pi * 180 / rate)
    delay = max(1, round(0.5 * 60 / recipe.bpm * rate))
    echo = [[0.0] * channels for _ in range(delay)] if recipe.family == "echo_exit" else None
    result = []
    for i, (frame_a, frame_b) in enumerate(zip(a, b)):
        t = i / (count - 1)
        wa, wb = math.cos(t * math.pi / 2), math.sin(t * math.pi / 2)
        frame = []
        for c in range(channels):
            av, bv = frame_a[c], frame_b[c]
            if recipe.family == "hard_cut":
                value = av if i < count // 2 else bv
            elif recipe.family == "bass_swap":
                low_a[c] += alpha * (av - low_a[c])
                low_b[c] += alpha * (bv - low_b[c])
                # Swap low frequencies in a short, smooth central interval.
                swap = min(1.0, max(0.0, (t - 0.4) / 0.2))
                swap = swap * swap * (3 - 2 * swap)
                value = (wa * (av - low_a[c]) + wb * (bv - low_b[c])
                         + (1 - swap) * low_a[c] + swap * low_b[c])
            elif recipe.family == "echo_exit":
                delayed = echo[i % delay][c]
                echo[i % delay][c] = av * (1 - t) + delayed * 0.35
                value = wa * av + wb * bv + delayed * 0.25 * math.sin(math.pi * t)
            else:
                value = wa * av + wb * bv
            # Explicit endpoints avoid floating trigonometric residue.
            if i == 0:
                value = av
            elif i == count - 1:
                value = bv
            frame.append(value * gain)
        result.append(tuple(frame))
    metrics = measure(result)
    # Hash source bytes before output writing; paths are local, never uploaded.
    sources = [{"path": str(path), "sha256": _digest(path)} for path in (a_path, b_path)]
    write_wav(out_path, rate, result)
    return {
        "schema_version": 1,
        "engine_version": "0.1.0",
        "recipe": asdict(recipe),
        "sample_rate": rate,
        "channels": channels,
        "frames": count,
        "duration_seconds": count / rate,
        "gain_linear": gain,
        "start_frames": {"a": a_offset, "b": b_offset},
        "alignment_source": "manual",
        "tempo_source": "manual",
        "sources": sources,
        "output_path": str(out_path),
        "output_sha256": _digest(out_path),
        "metrics": metrics,
        "metrics_stage": "pre_pcm16_quantization",
        "rights_status": "unknown",
    }
