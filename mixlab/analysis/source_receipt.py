"""Private PCM source identity guard shared by musical cue and reference flows.

A record binds regular-file filesystem identity to provider-by-provider source
hashes. This detects ordinary replacement/edit races, not hostile same-metadata
mutation, and never authorizes publishing, rendering or legal use of the audio.
"""
from __future__ import annotations

import os
import stat

from ..ingest import MAX_BYTES, inspect_wav_and_digest


def source_identity(path):
    """Observe one regular bounded PCM source without following the final symlink."""
    try:
        record = os.lstat(path)
    except OSError as exc:
        raise ValueError("Private PCM source unavailable or changed") from exc
    if not stat.S_ISREG(record.st_mode) or not 0 < record.st_size <= MAX_BYTES:
        raise ValueError("Private PCM source must be a bounded regular file")
    return (record.st_dev, record.st_ino, record.st_size,
            record.st_mtime_ns, record.st_ctime_ns)


def verify_source(path, identity, sha256):
    """Require unchanged physical identity and checksum after separate provider reads.

    The existing one-descriptor WAV inspector hashes the bytes it inspected
    while rejecting symlinks and regular-file changes. Match those bytes to
    all provider-record source hashes, then recheck pathname identity.
    """
    if source_identity(path) != identity:
        raise ValueError("Private PCM source changed during analysis")
    _info, observed_sha = inspect_wav_and_digest(path)
    if observed_sha != sha256 or source_identity(path) != identity:
        raise ValueError("Private PCM source changed during analysis")
