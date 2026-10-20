"""Read-only PCM16 A/B resolution-loss preflight (not a perceptual verdict).

This intentionally independent ML-07 module does not modify the renderer, the
existing quality scanner or another worker's active source files.
"""
from __future__ import annotations

import argparse
from array import array
from contextlib import ExitStack
from itertools import islice
import json
import os
from pathlib import Path
import stat
import sys
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
MAX_GROUP_FRAMES = 8_000_000
BLOCK_FRAMES = 4096
MIN_ELIGIBLE = 4096
MIN_ACTIVE_WINDOWS = 4
# Each 100ms evidence window must have >=50% high-level frames; a collection
# of sparse transients or separated islands cannot certify an A/B contrast.
MIN_WINDOW_ACTIVE_PERCENT = 50
ACTIVE_ABS = 2048
BASELINE_MAX_ZERO_FRACTION = 0.35
CANDIDATE_MIN_ZERO_FRACTION = 0.995


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _walk(path):
    """Check every current pathname component, never following a symlink."""
    # Resolve an untrusted custom PathLike exactly once. Multiple __fspath__
    # calls may return different names, allowing validation of one path but
    # attempted opening of another (or leaked caller exception details).
    try:
        raw = os.fspath(path)
    except Exception:
        # __fspath__ is user code and may raise with private source names.
        raise ValueError("unsafe source (details withheld)") from None
    if not isinstance(raw, str) or ".." in Path(raw).parts or "\x00" in raw:
        raise ValueError("unsafe source")
    absolute = Path(os.path.abspath(raw))
    if len(os.fspath(absolute)) > 4096 or len(absolute.parts) > 65:
        raise ValueError("invalid path size")
    cursor = Path(absolute.anchor)
    components = absolute.parts[1:]
    ancestor_ids = []
    for index, part in enumerate(components):
        cursor = cursor / part
        info = os.lstat(cursor)
        if index < len(components) - 1:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("non-directory source parent")
            ancestor_ids.append((info.st_dev, info.st_ino))
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError("non-regular source")
    return absolute, os.lstat(absolute), tuple(ancestor_ids)


def _open_nofollow_components(absolute):
    """Anchor every ancestor to a checked directory FD; never traverse a link.

    O_NOFOLLOW on only the basename is inadequate: its parent can become a
    symlink between lstat() and open(). Open each component relative to the
    previously opened O_DIRECTORY|O_NOFOLLOW descriptor instead. Every
    intermediate descriptor is closed even when admission fails.
    """
    directory_flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                       | os.O_NONBLOCK | os.O_CLOEXEC)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    current = os.open(absolute.anchor, directory_flags)
    try:
        for part in absolute.parts[1:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return os.open(absolute.name, file_flags, dir_fd=current)
    finally:
        os.close(current)


def _open_source(path, stack):
    absolute, initial, ancestor_ids = _walk(path)
    fd = _open_nofollow_components(absolute)
    try:
        handle = os.fdopen(fd, "rb", buffering=0)
    except BaseException:
        os.close(fd)
        raise
    stack.enter_context(handle)
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode) or _identity(info) != _identity(initial):
        raise ValueError("source changed during admission")
    if not 44 <= info.st_size <= MAX_BYTES:
        raise ValueError("source size out of bounds")
    reader = wave.open(handle, "rb")
    stack.callback(reader.close)
    if (reader.getcomptype() != "NONE" or reader.getsampwidth() != 2
            or reader.getnchannels() not in (1, 2)
            or not 8000 <= reader.getframerate() <= 96000
            or not 1 <= reader.getnframes() <= MAX_FRAMES):
        raise ValueError("unsupported source format")
    return {"path": absolute, "handle": handle, "info": info,
            "ancestor_ids": ancestor_ids,
            "reader": reader, "shape": (reader.getnchannels(),
                                         reader.getframerate(), reader.getnframes())}


def _scan(source):
    channels, rate, frames = source["shape"]
    reader = source["reader"]
    eligible = [0] * channels
    trailing_zero = [0] * channels
    # Fixed 256-bin per-channel low-byte histograms catch shifted 8-bit
    # amplitude lattices whose bottom byte is e.g. 37 rather than zero.
    low_byte_histogram = [[0] * 256 for _ in range(channels)]
    low_nibble_histogram = [[0] * 16 for _ in range(channels)]
    low_two_histogram = [[0] * 4 for _ in range(channels)]
    # A 100 ms bucket with >=32 high-level samples is only a diagnostic;
    # stronger sustained occupancy is required before a conclusive result.
    window_counts = [{} for _ in range(channels)]
    # Private time-aligned window summaries; fixed-size active histograms are
    # recycled every 100ms, so no PCM or unbounded per-window histograms stay
    # in memory. The summaries never enter public JSON.
    window_profiles = [{} for _ in range(channels)]
    current_window = None
    region_eligible = [0] * channels
    region_hist2 = [[0] * 4 for _ in range(channels)]
    region_hist4 = [[0] * 16 for _ in range(channels)]
    region_hist8 = [[0] * 256 for _ in range(channels)]

    def finish_region(w):
        if w is None:
            return
        start = (w * rate + 9) // 10
        end = ((w + 1) * rate + 9) // 10
        if end > frames:
            return  # A partial trailing interval is not 100ms evidence.
        for channel in range(channels):
            count = region_eligible[channel]
            if count >= 32 and 100 * count >= MIN_WINDOW_ACTIVE_PERCENT * (end - start):
                window_profiles[channel][w] = {
                    "eligible_samples": count,
                    "dominant_residue_counts": {
                        "2": max(region_hist2[channel]),
                        "4": max(region_hist4[channel]),
                        "8": max(region_hist8[channel]),
                    },
                }

    frame_offset = 0
    remaining = frames
    while remaining:
        take = min(BLOCK_FRAMES, remaining)
        raw = reader.readframes(take)
        if len(raw) != take * channels * 2:
            raise ValueError("truncated PCM payload")
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        for position in range(take):
            window_index = (frame_offset + position) * 10 // rate
            if current_window != window_index:
                finish_region(current_window)
                current_window = window_index
                region_eligible = [0] * channels
                region_hist2 = [[0] * 4 for _ in range(channels)]
                region_hist4 = [[0] * 16 for _ in range(channels)]
                region_hist8 = [[0] * 256 for _ in range(channels)]
            for channel in range(channels):
                value = values[position * channels + channel]
                if abs(value) >= ACTIVE_ABS:
                    eligible[channel] += 1
                    residue = value & 255
                    low_byte_histogram[channel][residue] += 1
                    low_nibble_histogram[channel][residue & 15] += 1
                    low_two_histogram[channel][residue & 3] += 1
                    region_eligible[channel] += 1
                    region_hist2[channel][residue & 3] += 1
                    region_hist4[channel][residue & 15] += 1
                    region_hist8[channel][residue] += 1
                    if residue == 0:
                        trailing_zero[channel] += 1
                    counts = window_counts[channel]
                    counts[window_index] = counts.get(window_index, 0) + 1
        frame_offset += take
        remaining -= take
    finish_region(current_window)
    source["_private_window_profiles"] = window_profiles
    output = []
    for channel in range(channels):
        present = {w for w, count in window_counts[channel].items() if count >= 32}
        sustained = set()
        for w, count in window_counts[channel].items():
            # Use rational integer PCM frame boundaries at fractional rates.
            # Incomplete trailing windows must not count as 100ms evidence.
            start = (w * rate + 9) // 10
            end = ((w + 1) * rate + 9) // 10
            if (end <= frames and count >= 32
                    and 100 * count >= MIN_WINDOW_ACTIVE_PERCENT * (end - start)):
                sustained.add(w)
        streak = longest_streak = 0
        previous = None
        for w in sorted(sustained):
            streak = streak + 1 if previous is not None and w == previous + 1 else 1
            longest_streak = max(longest_streak, streak)
            previous = w
        evidenced = eligible[channel] >= MIN_ELIGIBLE and longest_streak >= MIN_ACTIVE_WINDOWS
        dominant_count = max(low_byte_histogram[channel])
        dominant_residues = {
            "2": max(low_two_histogram[channel]),
            "4": max(low_nibble_histogram[channel]),
            "8": dominant_count,
        }
        output.append({
            "evidenced": evidenced,
            "active_windows": len(present),
            "sustained_windows": len(sustained),
            "longest_sustained_window_run": longest_streak,
            "eligible_samples": eligible[channel],
            "low_byte_zero_samples": trailing_zero[channel],
            "dominant_low_byte_samples": dominant_count,
            "dominant_residue_counts": dominant_residues,
            "dominant_low_byte_fraction": round(dominant_count / eligible[channel], 6)
            if evidenced else None,
            "low_byte_zero_fraction": round(trailing_zero[channel] / eligible[channel], 6)
            if evidenced else None,
        })
    return output


def _coarse_loss(base, candidate):
    """Detect a candidate-specific two-, four- or eight-LSB quantisation lattice.

    Compare exact integer counts, never presentation-rounded fractions.
    The legacy two-dict fallback allows isolated decision-boundary testing.
    """
    if "dominant_residue_counts" in base and "dominant_residue_counts" in candidate:
        return any(
            20 * base["dominant_residue_counts"][bits] <= 7 * base["eligible_samples"]
            and 200 * candidate["dominant_residue_counts"][bits] >= 199 * candidate["eligible_samples"]
            for bits in ("2", "4", "8")
        )
    baseline_concentrated = base.get("dominant_low_byte_samples", base["low_byte_zero_samples"])
    candidate_concentrated = candidate.get("dominant_low_byte_samples", candidate["low_byte_zero_samples"])
    return (20 * baseline_concentrated <= 7 * base["eligible_samples"]
            and 200 * candidate_concentrated >= 199 * candidate["eligible_samples"])


def _baseline_diverse(base):
    """Refuse a definitive negative if the baseline already has locked low bits."""
    if "dominant_residue_counts" in base:
        return all(20 * count <= 7 * base["eligible_samples"]
                   for count in base["dominant_residue_counts"].values())
    dominant = base.get("dominant_low_byte_samples", base["low_byte_zero_samples"])
    return 20 * dominant <= 7 * base["eligible_samples"]


def _aligned_active_evidence(base_source, candidate_source, channel):
    """Require enough simultaneous active PCM, not just independent activity.

    Each matched 100ms interval already meets the per-source 50% active-frame
    gate. A contiguous run of four matched intervals must contain at least
    MIN_ELIGIBLE high-level samples from each participant. This is internal
    evidence only: never disclose private time-window positions.
    """
    base = base_source["_private_window_profiles"][channel]
    candidate = candidate_source["_private_window_profiles"][channel]
    run = base_count = candidate_count = 0
    previous = None
    for w in sorted(base.keys() & candidate.keys()):
        if previous is None or w != previous + 1:
            run = base_count = candidate_count = 0
        run += 1
        base_count += base[w]["eligible_samples"]
        candidate_count += candidate[w]["eligible_samples"]
        if (run >= MIN_ACTIVE_WINDOWS and base_count >= MIN_ELIGIBLE
                and candidate_count >= MIN_ELIGIBLE):
            return True
        previous = w
    return False


def _joint_sample_evidence(base_source, candidate_source):
    """Read two source FDs together to require SAME-FRAME PCM activity.

    Two WAVs can each be 50% active inside every 100ms window but take
    alternating halves, yielding exactly ZERO audible overlapping samples.
    Window-level intersection alone cannot establish A/B comparability.
    This bounded second pass keeps at most two BLOCK_FRAMES PCM blocks.
    """
    channels, rate, frames = base_source["shape"]
    left, right = base_source["reader"], candidate_source["reader"]
    left.rewind()
    right.rewind()
    good = [False] * channels
    streak = [0] * channels
    simultaneous_in_streak = [0] * channels
    joint_count = [0] * channels
    active_window = None

    def finalize_window(index):
        if index is None:
            return
        start = (index * rate + 9) // 10
        end = ((index + 1) * rate + 9) // 10
        if end > frames:
            return
        for ch in range(channels):
            if (100 * joint_count[ch] >=
                    MIN_WINDOW_ACTIVE_PERCENT * (end - start)):
                streak[ch] += 1
                simultaneous_in_streak[ch] += joint_count[ch]
                if (streak[ch] >= MIN_ACTIVE_WINDOWS and
                        simultaneous_in_streak[ch] >= MIN_ELIGIBLE):
                    good[ch] = True
            else:
                streak[ch] = 0
                simultaneous_in_streak[ch] = 0

    offset = 0
    while offset < frames:
        take = min(BLOCK_FRAMES, frames - offset)
        left_data = left.readframes(take)
        right_data = right.readframes(take)
        expected = take * channels * 2
        if len(left_data) != expected or len(right_data) != expected:
            raise ValueError("truncated synchronized PCM read")
        a, b = array("h"), array("h")
        a.frombytes(left_data)
        b.frombytes(right_data)
        if sys.byteorder != "little":
            a.byteswap()
            b.byteswap()
        for pos in range(take):
            w = ((offset + pos) * 10) // rate
            if w != active_window:
                finalize_window(active_window)
                active_window = w
                joint_count = [0] * channels
            for ch in range(channels):
                at = pos * channels + ch
                if abs(a[at]) >= ACTIVE_ABS and abs(b[at]) >= ACTIVE_ABS:
                    joint_count[ch] += 1
        offset += take
    finalize_window(active_window)
    return good


def _regional_coarse_loss(base_source, candidate_source, channel):
    """Return a sustained 400ms candidate-specific quantization contrast."""
    before = base_source["_private_window_profiles"][channel]
    after = candidate_source["_private_window_profiles"][channel]
    previous = None
    consecutive = 0
    for index in sorted(before.keys() & after.keys()):
        if _coarse_loss(before[index], after[index]):
            consecutive = consecutive + 1 if previous is not None and index == previous + 1 else 1
            if consecutive >= MIN_ACTIVE_WINDOWS:
                return True
            previous = index
        else:
            consecutive = 0
            previous = None
    return False


def _regional_reference_degraded(source, channel):
    """Consecutive low-diversity baseline windows make a negative inconclusive."""
    windows = source["_private_window_profiles"][channel]
    previous = None
    consecutive = 0
    for index in sorted(windows):
        row = windows[index]
        degraded = any(
            200 * count >= 199 * row["eligible_samples"]
            for count in row["dominant_residue_counts"].values()
        )
        if degraded:
            consecutive = consecutive + 1 if previous is not None and index == previous + 1 else 1
            if consecutive >= MIN_ACTIVE_WINDOWS:
                return True
            previous = index
        else:
            consecutive = 0
            previous = None
    return False


def inspect_ab(baseline, candidates):
    """Screen high-level PCM low-byte collapse vs baseline, per channel.

    True = candidate-specific likely coarse PCM quantization; False = enough
    comparison evidence without that specific signature; None = abstention.
    Never exposes source paths, PCM, fingerprints or source metadata.
    """
    try:
        if isinstance(candidates, (str, bytes, Path)):
            raise ValueError("candidates must be a sequence")
        # Never materialize an unbounded sequence or exhaust an infinite
        # generator. Reject at the eighth candidate, before opening audio.
        try:
            bounded_candidates = list(islice(iter(candidates), 8))
        except Exception:
            # Custom iterator errors can include private track paths.
            raise ValueError("Invalid candidates (details withheld)") from None
        paths = [baseline, *bounded_candidates]
        if not 2 <= len(paths) <= 8:
            raise ValueError("expected baseline and 1..7 candidates")
        with ExitStack() as stack:
            sources = [_open_source(path, stack) for path in paths]
            if len({(s["info"].st_dev, s["info"].st_ino) for s in sources}) != len(sources):
                raise ValueError("repeated source inode")
            shape = sources[0]["shape"]
            if any(s["shape"] != shape for s in sources[1:]):
                raise ValueError("A/B format or duration mismatch")
            if sum(s["shape"][2] for s in sources) > MAX_GROUP_FRAMES:
                raise ValueError("A/B processing budget exceeded")
            results = [_scan(source) for source in sources]
            # An additional bounded synchronous read proves PCM is present
            # in BOTH sources on the same frames, not alternating half-windows.
            joint_evidence = [
                _joint_sample_evidence(sources[0], candidate)
                for candidate in sources[1:]
            ]
            # Check every earlier source *after* scanning the last member.
            for source in sources:
                _, path_info, current_ancestors = _walk(source["path"])
                descriptor_info = os.fstat(source["handle"].fileno())
                if (current_ancestors != source["ancestor_ids"]
                        or _identity(path_info) != _identity(source["info"])
                        or _identity(descriptor_info) != _identity(source["info"])):
                    raise ValueError("source changed during read")
        comparisons = []
        for index, candidate in enumerate(results[1:], start=1):
            per_channel = []
            for channel, (base, current) in enumerate(zip(results[0], candidate)):
                base_windows = sources[0]["_private_window_profiles"][channel]
                candidate_windows = sources[index]["_private_window_profiles"][channel]
                if (not base["evidenced"] or not current["evidenced"]
                        or not _aligned_active_evidence(sources[0], sources[index], channel)
                        or not joint_evidence[index - 1][channel]):
                    # Independent sustained activity is NOT evidence that
                    # the two sources contain simultaneous comparable PCM.
                    per_channel.append(None)
                elif _regional_coarse_loss(sources[0], sources[index], channel):
                    # A sustained defect proved on the SAME aligned windows.
                    per_channel.append(True)
                elif base_windows.keys() != candidate_windows.keys():
                    # Unmatched audible spans can skew global statistics and
                    # can hide a missing/stale section of a render. Abstain.
                    per_channel.append(None)
                elif _coarse_loss(base, current):
                    per_channel.append(True)
                elif (not _baseline_diverse(base)
                      or _regional_reference_degraded(sources[0], channel)):
                    per_channel.append(None)
                else:
                    per_channel.append(False)
            status = True if True in per_channel else (
                False if all(v is False for v in per_channel) else None
            )
            comparisons.append({
                "candidate_index": index,
                "candidate_channel_metrics": candidate,
                "coarse_resolution_review": status,
                "per_channel_review": per_channel,
            })
        return {
            "metric": "pcm16_sample_joint_multi_resolution_vs_baseline_v6",
            "technical_proxy_only": True,
            "channels": shape[0],
            "sample_rate": shape[1],
            "frames_per_source": shape[2],
            "baseline_channel_metrics": results[0],
            "candidates": comparisons,
        }
    except (OSError, ValueError, TypeError, EOFError, wave.Error) as exc:
        raise ValueError("Invalid or unreadable PCM16 source (details withheld)") from None


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "PCM resolution preflight: invalid arguments (details withheld)\n")


def main(argv=None):
    parser = _RedactedArgumentParser(description="Private offline PCM16 resolution proxy, not a musical verdict")
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 3 for a warning OR inconclusive channel evidence")
    args = parser.parse_args(argv)
    try:
        report = inspect_ab(args.baseline, args.candidates)
    except ValueError:
        parser.exit(2, "PCM resolution preflight: invalid sources (details withheld)\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    if args.strict and any(row["coarse_resolution_review"] is not False
                           for row in report["candidates"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
