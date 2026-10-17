"""Single-fd private PCM16 admission for bounded quality diagnostics.

A RIFF preflight and PCM decoder must inspect the *same* opened file,
not separately resolved paths. This is cooperative local-file protection,
not an atomic snapshot against privileged in-place tampering.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import wave

from .riff import verify_private_pcm16_header


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def open_verified_private_pcm16(path: str | Path, *, max_bytes: int):
    """Open a regular, non-symlink PCM16 WAV once and verify that same fd.

    O_NONBLOCK makes FIFO/device rejection bounded even if the name changes
    during resolution. O_NOFOLLOW disallows a final-path symlink on supported
    operating systems. fstat is authoritative after opening.
    """
    flags = os.O_RDONLY
    for constant in ("O_NONBLOCK", "O_NOFOLLOW", "O_CLOEXEC"):
        flags |= getattr(os, constant, 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        # The default OSError includes the private source path. Keep the
        # library exception generic even when it is logged outside the CLI.
        raise ValueError("Private WAV could not be opened as a regular file") from None
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Private audio input must be a regular file")
            if before.st_size > max_bytes:
                raise ValueError("WAV exceeds the 32 MiB screening limit")
            # Inspect RIFF header and then decode the *same* handle: no
            # second path lookup that could silently switch the source.
            verify_private_pcm16_header(handle)
            handle.seek(0)
            with wave.open(handle, "rb") as reader:
                yield reader
            after = os.fstat(handle.fileno())
            if _file_identity(before) != _file_identity(after):
                raise ValueError("Private WAV changed during quality preflight")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
