"""Streaming ITU-R BS.1770-4 integrated loudness and level matching for PCM16 WAV.

Implements K-weighting (high-shelf + RLB high-pass, derived for any sample rate),
400 ms gating blocks with 75 % overlap, the -70 LUFS absolute gate and the
-10 LU relative gate. Channel weights are 1.0 for mono and stereo L/R; surround
layouts are unsupported. Peaks are sample peaks, not 4x-oversampled true peak.

Level matching only attenuates, so matched files can never clip. Loudness
equality removes a known listening confound; it is not a musical quality score.
"""

from __future__ import annotations

from array import array
import hashlib
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import wave

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FRAMES = 2_000_000
ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
MATCH_TOLERANCE_LU = 0.1
METHOD = "itu-r-bs.1770-4-integrated-sample-peak"


def k_weighting(rate: int) -> tuple[tuple, tuple]:
    """Return ((b0,b1,b2,a1,a2) shelf, (b0,b1,b2,a1,a2) high-pass) for ``rate``.

    At 48 kHz these reproduce the coefficient table published in BS.1770-4.
    """
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10 ** (gain_db / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = ((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0,
             2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    a0 = 1 + k / q + k * k
    highpass = (1.0, -2.0, 1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    return shelf, highpass


class _HashingReader:
    """Sequential reader that hashes every byte it serves.

    It deliberately has no seek/tell, so ``wave`` reads the file front to back
    and the digest covers exactly the bytes that were decoded.
    """

    def __init__(self, stream):
        self._stream = stream
        self._hash = hashlib.sha256()

    def read(self, size=-1):
        data = self._stream.read(size)
        self._hash.update(data)
        return data

    def finish(self):
        for chunk in iter(lambda: self._stream.read(65536), b""):
            self._hash.update(chunk)
        self._stream.close()
        return self._hash.hexdigest()


def _open(path):
    """Open one regular file once; returns (wave reader, hashing reader, params)."""
    try:
        # Validate the opened descriptor, not the path, so a swap cannot slip in between.
        fd = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        if Path(path).is_symlink():
            raise ValueError("Loudness input must be a regular file") from None
        raise exc
    stream = os.fdopen(fd, "rb")
    try:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Loudness input must be a regular file")
        if info.st_size > MAX_SOURCE_BYTES:
            raise ValueError("WAV exceeds the 32 MiB loudness limit")
        reader = _HashingReader(stream)
        try:
            source = wave.open(reader, "rb")
        except (wave.Error, EOFError) as exc:
            raise ValueError(f"Invalid PCM16 WAV: {exc}") from exc
        channels, width, rate, count, compression, _ = source.getparams()
        if compression != "NONE" or width != 2 or channels not in (1, 2):
            raise ValueError("Only uncompressed PCM16 mono/stereo WAV is supported")
        if not 8000 <= rate <= 96000 or not 1 <= count <= MAX_SOURCE_FRAMES:
            raise ValueError("Sample rate must be 8000..96000 Hz and frames 1..2,000,000")
    except BaseException:
        stream.close()
        raise
    return source, reader, channels, rate, count


def _blocks(source, channels, count, block_frames=4096):
    remaining = count
    while remaining:
        n = min(block_frames, remaining)
        raw = source.readframes(n)
        if len(raw) != n * channels * 2:
            raise ValueError("Truncated PCM16 WAV")
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        yield values
        remaining -= n


def _lufs(mean_square: float) -> float:
    return -0.691 + 10 * math.log10(mean_square)


def measure(path: str | Path) -> dict:
    """Integrated loudness of one PCM16 WAV using bounded memory.

    Returns ``integrated_lufs`` None when no block passes the absolute gate
    (silence) or the clip is shorter than one 400 ms block.
    """
    source, reader, channels, rate, count = _open(path)
    (s0, s1, s2, sa1, sa2), (h0, h1, h2, ha1, ha2) = k_weighting(rate)
    # Direct form II transposed state per channel and stage.
    state = [[0.0, 0.0, 0.0, 0.0] for _ in range(channels)]
    step = rate // 10  # 100 ms sub-blocks; four make one 400 ms gating block.
    subblocks, acc, filled, peak = [], 0.0, 0, 0
    try:
        with source:
            for values in _blocks(source, channels, count):
                for i in range(0, len(values), channels):
                    for c in range(channels):
                        x = values[i + c]
                        if x > peak or -x > peak:
                            peak = abs(x)
                        x /= 32768.0
                        st = state[c]
                        y = s0 * x + st[0]
                        st[0] = s1 * x - sa1 * y + st[1]
                        st[1] = s2 * x - sa2 * y
                        z = h0 * y + st[2]
                        st[2] = h1 * y - ha1 * z + st[3]
                        st[3] = h2 * y - ha2 * z
                        acc += z * z
                    filled += 1
                    if filled == step:
                        subblocks.append(acc)
                        acc, filled = 0.0, 0
        sha256 = reader.finish()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid PCM16 WAV: {exc}") from exc
    finally:
        reader._stream.close()
    # Channel weights are 1.0, so a block's weighted power is the sum of channel means.
    block_power = [sum(subblocks[j:j + 4]) / (4 * step) for j in range(len(subblocks) - 3)]
    gated = [p for p in block_power if p > 0 and _lufs(p) > ABSOLUTE_GATE_LUFS]
    integrated = None
    if gated:
        threshold = _lufs(sum(gated) / len(gated)) + RELATIVE_GATE_LU
        kept = [p for p in gated if _lufs(p) > threshold]
        integrated = round(_lufs(sum(kept) / len(kept)), 3)
    sample_peak = peak / 32768
    return {"method": METHOD, "sample_rate": rate, "channels": channels, "frames": count,
            "integrated_lufs": integrated, "gating_blocks": len(block_power),
            "blocks_above_absolute_gate": len(gated), "sha256": sha256,
            "sample_peak_dbfs": round(20 * math.log10(sample_peak), 3) if sample_peak else None}


def apply_gain(source_path: str | Path, out_path: str | Path, gain_db: float,
               expected_sha256: str | None = None) -> dict:
    """Write an attenuated PCM16 copy; refuses boosts and never overwrites.

    With ``expected_sha256`` the output is published only if the bytes that
    were actually scaled hash to that value, pinning it to the measured source.
    """
    if isinstance(gain_db, bool) or not isinstance(gain_db, (int, float)) or not math.isfinite(gain_db):
        raise ValueError("gain_db must be finite")
    if not -60 <= gain_db <= 0:
        raise ValueError("Level matching only attenuates: gain_db must be within -60..0")
    out = Path(out_path)
    if out.exists() or out.is_symlink():
        raise ValueError("Output already exists")
    gain = 10 ** (gain_db / 20)
    source, reader, channels, rate, count = _open(source_path)
    fd, temporary = tempfile.mkstemp(prefix=".mixlab-level-", suffix=".wav", dir=out.parent)
    os.close(fd)
    try:
        with source, wave.open(temporary, "wb") as target:
            target.setparams((channels, 2, rate, count, "NONE", "not compressed"))
            for values in _blocks(source, channels, count):
                scaled = array("h", (round(v * gain) for v in values))
                if sys.byteorder != "little":
                    scaled.byteswap()
                target.writeframesraw(scaled.tobytes())
        if expected_sha256 is not None and reader.finish() != expected_sha256:
            raise ValueError("Source changed after loudness measurement; refusing to publish")
        os.link(temporary, out)  # exclusive publication of a complete file
    finally:
        reader._stream.close()
        Path(temporary).unlink(missing_ok=True)
    return {"gain_db": round(gain_db, 6), "gain_linear": gain}


def match_group(paths: dict[str, Path], destination: Path, suffix: str = "-matched") -> dict:
    """Attenuate every file in ``paths`` to the quietest member's loudness.

    ``paths`` maps an opaque label to a WAV. All members must share format and
    length. Returns per-label measurements before/after, the common target and
    the matched output path. Silent members abort the group: a silent clip has
    no defined loudness to match.
    """
    if len(paths) < 2:
        raise ValueError("Level matching needs at least two files")
    before = {label: measure(path) for label, path in paths.items()}
    formats = {(m["sample_rate"], m["channels"], m["frames"]) for m in before.values()}
    if len(formats) != 1:
        raise ValueError("Level-matched files must share sample rate, channels and length")
    if any(m["integrated_lufs"] is None for m in before.values()):
        raise ValueError("Cannot loudness-match a silent or sub-400 ms render")
    target = min(m["integrated_lufs"] for m in before.values())
    result = {}
    for label, path in paths.items():
        out = Path(destination) / f"{Path(path).stem}{suffix}.wav"
        gain_db = target - before[label]["integrated_lufs"]
        gain = apply_gain(path, out, gain_db, expected_sha256=before[label]["sha256"])
        after = measure(out)
        if after["integrated_lufs"] is None or abs(after["integrated_lufs"] - target) > MATCH_TOLERANCE_LU:
            raise ValueError("Level matching missed its target; refusing to package unequal loudness")
        result[label] = {"path": out, "before": before[label], "after": after, **gain}
    return {"method": METHOD, "target_lufs": target, "policy": "attenuate-to-quietest",
            "tolerance_lu": MATCH_TOLERANCE_LU, "members": result}
