"""Streaming deterministic PCM16 transitions, bounded by block and delay sizes."""
from array import array
from dataclasses import asdict
import math
import os
from pathlib import Path
import sys
import tempfile
import wave
from ..ingest import MAX_FRAMES, digest, inspect_wav, pcm_blocks
from ..models import Recipe


class Meter:
    def __init__(self, channels):
        self.channels = channels
        self.count = 0
        self.power = [0.] * channels
        self.sums = [0.] * channels
        self.previous = None
        self.peak = self.jump = 0.
        self.clipped = 0

    def add(self, frame):
        for c, value in enumerate(frame):
            if not math.isfinite(value):
                raise ValueError("Non-finite DSP output")
            self.power[c] += value * value
            self.sums[c] += value
            self.peak = max(self.peak, abs(value))
            if self.previous is not None:
                self.jump = max(self.jump, abs(value - self.previous[c]))
            self.clipped += value < -1. or value > 32767 / 32768
        self.previous = frame
        self.count += 1

    def result(self):
        total = self.count * self.channels
        return {"peak": self.peak, "rms": math.sqrt(sum(self.power) / total),
                "clipping_samples": self.clipped, "clipping_fraction": self.clipped / total,
                "dc_per_channel": [v / self.count for v in self.sums],
                "rms_per_channel": [math.sqrt(v / self.count) for v in self.power],
                "max_sample_jump": self.jump}


def render(a_path, b_path, out_path, recipe, *, block_frames=4096):
    """Render the established four families without keeping whole clips in RAM.

    Fail before publishing if any sample exceeds PCM16. No silent limiter,
    tempo conversion, per-family normalization, stem or perceptual claims.
    """
    if not isinstance(recipe, Recipe):
        raise TypeError("recipe must be a Recipe")
    if type(block_frames) is not int or not 1 <= block_frames <= 65536:
        raise ValueError("Invalid block size")
    a_path, b_path, out = Path(a_path), Path(b_path), Path(out_path)
    sources = [a_path.resolve(), b_path.resolve()]
    if out.resolve() in sources or (out.exists() and any(out.samefile(p) for p in sources)):
        raise ValueError("Output must not overwrite an input")
    if out.exists() or out.is_symlink():
        raise ValueError("Output already exists")
    a, b = inspect_wav(a_path), inspect_wav(b_path)
    rate, channels = a["sample_rate"], a["channels"]
    if (rate, channels) != (b["sample_rate"], b["channels"]):
        raise ValueError("Inputs must have identical sample rates and channels")
    count = round(recipe.beats * 60 / recipe.bpm * rate)
    offsets = [round(recipe.a_start * rate), round(recipe.b_start * rate)]
    if not 2 <= count <= MAX_FRAMES:
        raise ValueError("Transition exceeds frame budget")
    if any(offset + count > info["frame_count"] for offset, info in zip(offsets, (a, b))):
        raise ValueError("Source clips are too short")
    hashes = [digest(p) for p in sources]
    gain = 10 ** (recipe.gain_db / 20)
    low_a, low_b = [0.] * channels, [0.] * channels
    alpha = 1 - math.exp(-2 * math.pi * 180 / rate)
    delay = max(1, round(.5 * 60 / recipe.bpm * rate))
    echo = array("d", [0.]) * (delay * channels) if recipe.family == "echo_exit" else None
    pre, post = Meter(channels), Meter(channels)
    fd, temporary = tempfile.mkstemp(prefix=".mixlab-render-", suffix=".wav", dir=out.parent)
    os.close(fd)
    try:
        with wave.open(temporary, "wb") as target:
            target.setparams((channels, 2, rate, count, "NONE", "not compressed"))
            position = 0
            chunks_a = pcm_blocks(a_path, offsets[0], count, block_frames)
            chunks_b = pcm_blocks(b_path, offsets[1], count, block_frames)
            for avs, bvs in zip(chunks_a, chunks_b):
                if len(avs) != len(bvs):
                    raise ValueError("Source changed while rendering")
                packed = array("h")
                for k in range(0, len(avs), channels):
                    i = position
                    t = i / (count - 1)
                    wa, wb = math.cos(t * math.pi / 2), math.sin(t * math.pi / 2)
                    frame = []
                    for c in range(channels):
                        av, bv = avs[k+c] / 32768, bvs[k+c] / 32768
                        if recipe.family == "hard_cut":
                            value = av if i < count // 2 else bv
                        elif recipe.family == "bass_swap":
                            low_a[c] += alpha * (av - low_a[c])
                            low_b[c] += alpha * (bv - low_b[c])
                            swap = min(1., max(0., (t - .4) / .2))
                            swap = swap * swap * (3 - 2 * swap)
                            value = (wa * (av-low_a[c]) + wb * (bv-low_b[c])
                                     + (1-swap)*low_a[c] + swap*low_b[c])
                        elif recipe.family == "echo_exit":
                            slot = (i % delay)*channels+c
                            delayed = echo[slot]
                            echo[slot] = av*(1-t) + delayed*.35
                            value = wa*av + wb*bv + delayed*.25*math.sin(math.pi*t)
                        else:
                            value = wa*av + wb*bv
                        if i == 0: value = av
                        elif i == count-1: value = bv
                        frame.append(value*gain)
                    pre.add(frame)
                    if pre.clipped:
                        raise ValueError("PCM16 clipping rejected; lower the common recipe gain")
                    quantized = [round(v*32768) for v in frame]
                    packed.extend(quantized)
                    post.add(tuple(v/32768 for v in quantized))
                    position += 1
                if sys.byteorder != "little": packed.byteswap()
                target.writeframesraw(packed.tobytes())
            if position != count:
                raise ValueError("Source changed while rendering")
        if [digest(p) for p in sources] != hashes:
            raise ValueError("Source changed while rendering")
        # Same-filesystem hard link publishes a complete file exclusively.
        # Unlike rename/replace, an existing candidate can never be overwritten.
        os.link(temporary, out)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"schema_version": 1, "engine_version": "0.2.0-stream",
            "recipe": asdict(recipe), "sample_rate": rate, "channels": channels, "frames": count,
            "duration_seconds": count/rate, "gain_linear": gain,
            "start_frames": {"a": offsets[0], "b": offsets[1]},
            "alignment_source": "manual", "tempo_source": "manual",
            "sources": [{"path": str(p), "sha256": h} for p, h in zip((a_path,b_path), hashes)],
            "output_path": str(out_path), "output_sha256": digest(out),
            "metrics": pre.result(), "metrics_stage": "pre_pcm16_quantization",
            "post_pcm_metrics": post.result(), "clipping_policy": "reject_before_publication",
            "rights_status": "unknown", "block_frames": block_frames}
