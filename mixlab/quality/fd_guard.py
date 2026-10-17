"""Single-descriptor, non-mutating admission for local private PCM16 WAVs.

This is a standalone ML-07 integration candidate: it does not silently replace
existing readers. It is not a RIFF-chunk parser or an audio-quality verdict.
"""

from __future__ import annotations

from contextlib import contextmanager
import argparse
import json
import os
import stat
import struct
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
_ERROR = "Private WAV admission rejected (details withheld)"


def _stamp(value):
    return (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


@contextmanager
def admitted_pcm16(path):
    """Yield a WAV reader tied to one regular, bounded, non-symlink descriptor.

    Linux/POSIX only: O_NOFOLLOW and O_NONBLOCK are mandatory. The caller must
    consume frames while inside this context. At successful context exit we
    recheck the opened inode, size, timestamps and the named path identity.
    This detects ordinary replacements/edits; it cannot authenticate a hostile
    filesystem or prove the musical content has not been edited upstream.
    """
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK")
            or not hasattr(os, "O_CLOEXEC")):
        raise ValueError(_ERROR)
    try:
        name = os.fspath(path)
        if not isinstance(name, (str, bytes)):
            raise TypeError
    except (TypeError, ValueError):
        raise ValueError(_ERROR) from None

    fd = -1
    try:
        # No preliminary path stat: otherwise a FIFO can block or a file can
        # be swapped between checking the path and opening it.
        fd = os.open(
            name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or not 44 <= before.st_size <= MAX_BYTES):
            raise ValueError(_ERROR)
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = -1
            try:
                reader = wave.open(stream, "rb")
            except (wave.Error, EOFError, OSError, ValueError, struct.error):
                raise ValueError(_ERROR) from None
            try:
                channels, width, rate, frames, compression, _ = reader.getparams()
                if (compression != "NONE" or width != 2
                        or channels not in (1, 2)
                        or not 8000 <= rate <= 96000
                        or not 1 <= frames <= MAX_FRAMES
                        # wave reads arbitrary legal pre-data chunks. Count
                        # available bytes from the *actual* data start, not
                        # a fixed 44-byte canonical WAV-header assumption.
                        or stream.tell() + frames * channels * width > before.st_size):
                    raise ValueError(_ERROR)
                yield reader
                after = os.fstat(stream.fileno())
                # lstat-equivalent comparison rejects rename/replacement and
                # a new symlink at the original path, without following it.
                named = os.stat(name, follow_symlinks=False)
                if (not stat.S_ISREG(named.st_mode)
                        or _stamp(before) != _stamp(after)
                        or _stamp(before) != _stamp(named)):
                    raise ValueError(_ERROR)
            finally:
                reader.close()
    except (OSError, wave.Error, EOFError, struct.error):
        raise ValueError(_ERROR) from None
    finally:
        if fd >= 0:
            os.close(fd)


def validate_private_pcm16(path, *, block_frames=4096):
    """Check every declared PCM frame on the admitted FD, without writing audio.

    This optional source-integrity preflight does not replace the full RIFF
    parser or evaluate musical quality. No path, PCM or hash is returned.
    """
    if (type(block_frames) is not int or not 1 <= block_frames <= 4096):
        raise ValueError(_ERROR)
    with admitted_pcm16(path) as reader:
        rate = reader.getframerate()
        channels = reader.getnchannels()
        frames = reader.getnframes()
        remaining = frames
        while remaining:
            count = min(block_frames, remaining)
            raw = reader.readframes(count)
            if len(raw) != count * channels * 2:
                raise ValueError(_ERROR)
            remaining -= count
    return {"screen": "ml07-single-fd-pcm16-integrity-v1",
            "sample_rate": rate, "channels": channels, "frames": frames,
            "pcm16_payload_complete": True, "human_listening_required": True}


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid WAV admission arguments (details withheld)\\n")


def main(argv=None):
    """Optional independent probe; this does not activate the main MixLab CLI."""
    parser = _PrivateParser(description="Offline PCM16 integrity, NOT musical quality")
    parser.add_argument("source", help="Private local PCM16 WAV (never echoed)")
    arguments = parser.parse_args(argv)
    try:
        report = validate_private_pcm16(arguments.source)
    except (OSError, ValueError, EOFError, wave.Error, struct.error):
        parser.exit(3, "Private WAV admission rejected (details withheld)\\n")
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
