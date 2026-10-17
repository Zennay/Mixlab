"""Offline PCM repeatability gate for two independent MixLab render artifacts.

The sole assertion is whether separate files have the same complete PCM16
payload under the same format. This is not a music-quality or preference score.
No audio, private filename or source checksum is included in a report.
"""

from __future__ import annotations

from contextlib import ExitStack
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import sys
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
CHUNK_FRAMES = 4096
_ERROR = "invalid, changed or incompatible source"


class RepeatabilityError(ValueError):
    """Sanitized, non-source-bearing preflight refusal."""


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _source(path: Path, stack: ExitStack) -> tuple[wave.Wave_read, object, os.stat_result]:
    # Reject symlink traversal and FIFOs before parsing even a WAV header.
    if not hasattr(os, "O_NOFOLLOW"):
        raise RepeatabilityError(_ERROR)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 44 <= info.st_size <= MAX_BYTES:
            raise RepeatabilityError(_ERROR)
        handle = os.fdopen(fd, "rb", buffering=0)
    except BaseException:
        os.close(fd)
        raise
    stack.enter_context(handle)
    reader = wave.open(handle, "rb")
    stack.callback(reader.close)
    params = reader.getparams()
    if (
        params.nchannels not in (1, 2)
        or params.sampwidth != 2
        or params.comptype != "NONE"
        or not 8000 <= params.framerate <= 96000
        or not 1 <= params.nframes <= MAX_FRAMES
    ):
        raise RepeatabilityError(_ERROR)
    return reader, handle, info


def _unchanged(path: Path, handle: object, original: os.stat_result) -> bool:
    # A descriptor snapshot alone does not establish that the original name
    # still refers to that source after a concurrent rename/replacement.
    info = os.fstat(handle.fileno())
    named = os.stat(path, follow_symlinks=False)
    return (
        stat.S_ISREG(named.st_mode)
        and _identity(info) == _identity(original) == _identity(named)
    )


def verify_repeatability(first: str | os.PathLike[str], second: str | os.PathLike[str]) -> dict:
    """Compare all declared PCM bytes from two distinct, privately held WAVs.

    Raises only sanitized RepeatabilityError for refused inputs. A mismatch in
    otherwise valid, equally shaped renders is a normal result, not an error.
    No filesystem isolation can eliminate races after the final identity check.
    """
    try:
        paths = (Path(first), Path(second))
        with ExitStack() as stack:
            sources = [_source(p, stack) for p in paths]
            (left, left_handle, left_stat), (right, right_handle, right_stat) = sources
            if (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino):
                raise RepeatabilityError(_ERROR)
            left_format = (left.getnchannels(), left.getsampwidth(), left.getframerate(), left.getnframes())
            right_format = (right.getnchannels(), right.getsampwidth(), right.getframerate(), right.getnframes())
            if left_format != right_format:
                raise RepeatabilityError(_ERROR)
            channels, width, _, frames = left_format
            expected_frame_bytes = channels * width
            digests = (hashlib.sha256(), hashlib.sha256())
            for offset in range(0, frames, CHUNK_FRAMES):
                frames_now = min(CHUNK_FRAMES, frames - offset)
                for reader, digest in zip((left, right), digests):
                    pcm = reader.readframes(frames_now)
                    if len(pcm) != frames_now * expected_frame_bytes:
                        raise RepeatabilityError(_ERROR)
                    digest.update(pcm)
            if not all(_unchanged(p, h, s) for p, (_, h, s) in zip(paths, sources)):
                raise RepeatabilityError(_ERROR)
            equal = hmac.compare_digest(digests[0].digest(), digests[1].digest())
        return {
            "schema_version": 1,
            "repeatable_pcm": equal,
            "independent_sources_verified": True,
            "format_and_frame_count_verified": True,
            "technical_review_required": not equal,
            "human_preference_test_required": True,
        }
    except (OSError, EOFError, ValueError, wave.Error, OverflowError, TypeError):
        raise RepeatabilityError(_ERROR) from None


_USAGE = "Usage: python -m mixlab.quality.repeatability FIRST.wav SECOND.wav [--strict]"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["-h"] or args == ["--help"]:
        print(_USAGE)
        return 0
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    if len(args) != 2 or any(a.startswith("-") for a in args):
        print("repeatability: invalid arguments", file=sys.stderr)
        return 3
    try:
        result = verify_repeatability(args[0], args[1])
    except RepeatabilityError:
        print("repeatability: invalid or changed source", file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True))
    return 2 if strict and not result["repeatable_pcm"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
