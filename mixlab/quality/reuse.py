"""Optional CPU-only exact PCM reuse screen for offline MixLab blind A/B.

Detect potentially unintended near-copies and one-channel stale outputs.
Exact PCM matching is not musical quality or perceptual similarity.
No audio, raw samples, paths, fingerprints or positions are emitted.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import stat
import sys
import wave

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
MAX_TOTAL_FRAMES = 8_000_000
MAX_CANDIDATES = 8
READ_FRAMES = 4096
ACTIVE_PCM_ABS = 1024
MIN_ACTIVE_FRAMES = 1000
MIN_ACTIVE_FRACTION = 0.05
NEAR_IDENTICAL_FRACTION = 0.98
ONE_CHANNEL_STALE_FRACTION = 0.95
OTHER_CHANNEL_CHANGED_FRACTION = 0.80


def _snapshot(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _source(path: str | Path, expected: tuple[int, int, int] | None = None):
    """Read an unchanged regular WAV through one nonblocking no-follow FD."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
            raise ValueError("Unsupported WAV source")
        with wave.open(source, "rb") as wav:
            channels, width, rate, frames, compression, _ = wav.getparams()
            if compression != "NONE" or width != 2 or channels not in (1, 2):
                raise ValueError("Only PCM16 mono/stereo WAV supported")
            if rate < 8000 or rate > 96000 or frames < 1 or frames > MAX_FRAMES:
                raise ValueError("WAV dimensions rejected")
            header = (rate, channels, frames)
            if expected is not None and header != expected:
                raise ValueError("Audio shape mismatch")
            yield wav, header
        after = os.fstat(source.fileno())
        same_path = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(same_path.st_mode) or _snapshot(before) != _snapshot(after) or (
            same_path.st_dev, same_path.st_ino
        ) != (before.st_dev, before.st_ino):
            raise ValueError("Audio changed during quality scan")


def _compare_pair(baseline: str | Path, candidate: str | Path, header: tuple[int, int, int]) -> dict:
    _, channels, frames = header
    active = identical = left_same = right_same = swapped = 0
    win_active = [0] * 8
    win_left = [0] * 8
    win_right = [0] * 8
    with ExitStack() as stack:
        base, _ = stack.enter_context(_source(baseline, expected=header))
        other, _ = stack.enter_context(_source(candidate, expected=header))
        processed = 0
        while processed < frames:
            amount = min(READ_FRAMES, frames - processed)
            a = base.readframes(amount)
            b = other.readframes(amount)
            expected_bytes = amount * channels * 2
            if len(a) != expected_bytes or len(b) != expected_bytes:
                raise ValueError("Truncated PCM payload")
            # Bytewise signed PCM16 equality has no float/host-endian drift.
            for pos in range(0, expected_bytes, 2 * channels):
                ba = a[pos:pos + 2 * channels]
                bb = b[pos:pos + 2 * channels]
                if not any(abs(int.from_bytes(frame[k:k + 2], "little", signed=True)) >= ACTIVE_PCM_ABS
                           for frame in (ba, bb) for k in range(0, len(frame), 2)):
                    continue
                active += 1
                if ba == bb:
                    identical += 1
                if channels == 2:
                    left_match = ba[:2] == bb[:2]
                    right_match = ba[2:] == bb[2:]
                    left_same += left_match
                    right_same += right_match
                    swapped += ba != bb and ba[:2] == bb[2:] and ba[2:] == bb[:2]
                    window = min(7, 8 * (processed + pos // (2 * channels)) // frames)
                    win_active[window] += 1
                    win_left[window] += left_match
                    win_right[window] += right_match
            processed += amount
    evidence = active >= MIN_ACTIVE_FRAMES and active / frames >= MIN_ACTIVE_FRACTION
    if not evidence:
        return {"active_fraction": round(active / frames, 4),
                "exact_frame_reuse_fraction": None,
                "stereo_left_reuse_fraction": None,
                "stereo_right_reuse_fraction": None,
                "stereo_swapped_frame_fraction": None,
                "stereo_temporal_stale_window_fraction": None,
                "warnings": ["insufficient_audible_pcm_for_reuse_inspection"]}
    exact = identical / active
    left = left_same / active if channels == 2 else None
    right = right_same / active if channels == 2 else None
    swap = swapped / active if channels == 2 else None
    warnings = []
    temporal_stale_fraction = None
    if channels == 2:
        eligible = stale_windows = 0
        minimum_window_frames = max(100, round(frames / 8 * MIN_ACTIVE_FRACTION))
        for count, matches_left, matches_right in zip(win_active, win_left, win_right):
            if count < minimum_window_frames:
                continue
            eligible += 1
            if ((matches_left / count >= ONE_CHANNEL_STALE_FRACTION
                 and matches_right / count <= OTHER_CHANNEL_CHANGED_FRACTION)
                or (matches_right / count >= ONE_CHANNEL_STALE_FRACTION
                    and matches_left / count <= OTHER_CHANNEL_CHANGED_FRACTION)):
                stale_windows += 1
        if eligible >= 3:
            temporal_stale_fraction = stale_windows / eligible
            if stale_windows >= 2 and temporal_stale_fraction >= 0.25:
                warnings.append("stereo_temporal_single_channel_stale_pcm_inspect")
        else:
            warnings.append("stereo_temporal_reuse_coverage_inconclusive_inspect")
    if exact >= NEAR_IDENTICAL_FRACTION:
        warnings.append("near_identical_candidate_pcm_inspect")
    # Useful render regression indicator, not evidence that creative panning is wrong.
    if channels == 2 and ((left >= ONE_CHANNEL_STALE_FRACTION and right <= OTHER_CHANNEL_CHANGED_FRACTION)
                          or (right >= ONE_CHANNEL_STALE_FRACTION and left <= OTHER_CHANNEL_CHANGED_FRACTION)):
        warnings.append("stereo_single_channel_stale_pcm_inspect")
    if channels == 2 and swap >= 0.75 and exact < 0.05:
        warnings.append("stereo_channel_swap_pcm_inspect")
    return {"active_fraction": round(active / frames, 4),
            "exact_frame_reuse_fraction": round(exact, 4),
            "stereo_left_reuse_fraction": round(left, 4) if left is not None else None,
            "stereo_right_reuse_fraction": round(right, 4) if right is not None else None,
            "stereo_swapped_frame_fraction": round(swap, 4) if swap is not None else None,
            "stereo_temporal_stale_window_fraction": (round(temporal_stale_fraction, 4)
                                                      if temporal_stale_fraction is not None else None),
            "warnings": warnings}


def compare_pcm_reuse(baseline: str | Path, candidates: list[str | Path]) -> dict:
    """Bounded scanning with anonymous output; fail closed on unsafe input."""
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("Candidate count rejected")
    with _source(baseline) as (_, header):
        pass
    frames = header[2]
    if frames * (1 + len(candidates)) > MAX_TOTAL_FRAMES:
        raise ValueError("Aggregate frame budget exceeded")
    rows = []
    for i, candidate in enumerate(candidates, 1):
        result = _compare_pair(baseline, candidate, header)
        rows.append({"id": f"candidate-{i:02d}", **result})
    return {"screen": "ml07-exact-pcm-reuse-proxy-v1",
            "candidates": rows, "human_listening_required": True}


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid quality arguments (details withheld)\n")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateParser(description=__doc__)
    parser.add_argument("baseline")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = compare_pcm_reuse(args.baseline, args.candidates)
    except (OSError, ValueError, EOFError, wave.Error):
        print("Quality reuse input rejected (details withheld)", file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 2 if args.fail_on_warnings and any(row["warnings"] for row in result["candidates"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
