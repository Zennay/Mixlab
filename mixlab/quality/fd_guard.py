"""Single-descriptor, non-mutating admission for local private PCM16 WAVs.

This is a standalone ML-07 integration candidate: it does not silently replace
existing readers. It is not a RIFF-chunk parser or an audio-quality verdict.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import stat
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
            except (wave.Error, EOFError, OSError, ValueError):
                raise ValueError(_ERROR) from None
            try:
                channels, width, rate, frames, compression, _ = reader.getparams()
                if (compression != "NONE" or width != 2
                        or channels not in (1, 2)
                        or not 8000 <= rate <= 96000
                        or not 1 <= frames <= MAX_FRAMES
                        or 44 + frames * channels * width > before.st_size):
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
    except (OSError, wave.Error, EOFError):
        raise ValueError(_ERROR) from None
    finally:
        if fd >= 0:
            os.close(fd)
