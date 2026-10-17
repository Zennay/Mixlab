"""Offline, bounded JSON file admission for ML-05 blind-evaluation inputs.

This standalone primitive does not replace the active ML-05 integration:
the evaluation owner must wire it into the caller after source review.
Only a stable regular, non-symlink file is admitted. No private paths are
included in public errors; no audio or network access is performed.
"""
import json
import math
import os
from pathlib import Path
import stat

MAX_EVALUATION_JSON_BYTES = 4 * 1024 * 1024


def _unchanged(before, after):
    return (before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_ctime_ns == after.st_ctime_ns)


def _read_bounded(fd):
    chunks = []
    total = 0
    while total <= MAX_EVALUATION_JSON_BYTES:
        chunk = os.read(fd, min(65536, MAX_EVALUATION_JSON_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > MAX_EVALUATION_JSON_BYTES:
        raise ValueError("Evaluation JSON exceeds 4 MiB")
    return b"".join(chunks)


def load_bounded_json(path):
    """Load a stable, strictly bounded JSON regular file or fail closed.

    Nonblocking single-descriptor access refuses FIFOs, sockets, directories
    and final symlinks before any content read. The initial and final path
    identities plus descriptor metadata detect observed replacement/growth.
    This is a file-integrity consistency gate, not cryptographic signing.
    """
    if not hasattr(os, "O_NONBLOCK") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("Safe evaluation JSON admission is unavailable")
    source = Path(path).absolute()
    try:
        first = os.stat(source, follow_symlinks=False)
        if not stat.S_ISREG(first.st_mode):
            raise ValueError("Evaluation JSON must be a regular file")
        fd = os.open(source, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW |
                     getattr(os, "O_CLOEXEC", 0))
    except OSError:
        raise ValueError("Evaluation JSON source unavailable") from None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or not _unchanged(first, opened):
            raise ValueError("Evaluation JSON source identity changed")
        if opened.st_size > MAX_EVALUATION_JSON_BYTES:
            raise ValueError("Evaluation JSON exceeds 4 MiB")
        content = _read_bounded(fd)
        finished = os.fstat(fd)
        final = os.stat(source, follow_symlinks=False)
        if (not stat.S_ISREG(final.st_mode)
                or not _unchanged(opened, finished)
                or not _unchanged(opened, final)):
            raise ValueError("Evaluation JSON source changed during admission")
    except OSError:
        raise ValueError("Evaluation JSON source unavailable") from None
    finally:
        os.close(fd)
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Invalid evaluation JSON UTF-8") from None

    # Explicit shallow JSON structure limit instead of relying on a
    # Python-version-specific decoder recursion ceiling. Delimiters within
    # quoted strings and escaped quotes are ignored.
    depth = 0
    quoted = False
    escaped = False
    for char in decoded:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 64:
                raise ValueError("Evaluation JSON nesting limit exceeded")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                # The JSON decoder retains authority over syntax errors.
                break

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate evaluation JSON field")
            result[key] = value
        return result

    def refuse_nonfinite(_):
        raise ValueError("Nonfinite evaluation JSON constant")

    def finite_float(token):
        # JSON's ordinary exponent syntax (e.g. 1e999) can overflow
        # Python float to infinity despite parse_constant rejecting NaN.
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("Nonfinite evaluation JSON number")
        return value

    try:
        result = json.loads(decoded, object_pairs_hook=unique_pairs,
                            parse_constant=refuse_nonfinite,
                            parse_float=finite_float)
    except RecursionError:
        raise ValueError("Evaluation JSON nesting limit exceeded") from None

    # JSON escapes can decode to unpaired UTF-16 surrogates even when the
    # source bytes were valid UTF-8. Such strings cannot be safely emitted
    # as UTF-8 in the operator/reviewer handoff. Check keys AND values.
    # Iterative traversal stays bounded by our 4 MiB / depth-64 admission.
    pending = [result]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise ValueError("Invalid evaluation JSON Unicode scalar")
        elif isinstance(item, dict):
            for key, value in item.items():
                pending.append(key)
                pending.append(value)
        elif isinstance(item, list):
            pending.extend(item)
    return result
