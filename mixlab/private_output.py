"""Private, exclusive local artifact publication with inode-owned rollback.

Callers must validate paths and payload size before invoking this writer.
No network, disk discovery, permissions escalation or overwrite capability.
"""
from __future__ import annotations

import os
from contextlib import contextmanager


@contextmanager
def open_private_new(path):
    """Bounded streaming publication, private from birth and rollback-owned."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    owned = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            current = os.stat(path, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                os.unlink(path)
        except FileNotFoundError:
            pass
        raise


def write_private_new(path, raw):
    """Create one bounded private artifact without overwriting another."""
    with open_private_new(path) as stream:
        stream.write(raw)
    return path
