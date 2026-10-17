"""Single-descriptor, non-mutating admission for local private PCM16 WAVs.

This is a standalone ML-07 integration candidate: it does not silently replace
existing readers. It is not a RIFF-chunk parser or an audio-quality verdict.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import argparse
import json
import os
import stat
import struct
import wave

MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 2_000_000
MAX_PRE_DATA_CHUNKS = 4096
MAX_GROUP_SOURCES = 8
MAX_GROUP_FRAMES = 8_000_000
_ERROR = "Private WAV admission rejected (details withheld)"


def _stamp(value):
    return (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


def _locate_data_chunk(stream, size):
    """Bound work before Wave_read parses RIFF, without a second FD.

    This is only pre-data header admission, not validation of post-data RIFF
    trailers or complete chunk semantics (owned by the scanner/RIFF reviewer).
    """
    prefix = stream.read(12)
    if len(prefix) != 12 or prefix[:4] != b"RIFF" or prefix[8:12] != b"WAVE":
        raise ValueError(_ERROR)
    declared_end = 8 + int.from_bytes(prefix[4:8], "little")
    if not 44 <= declared_end <= size:
        raise ValueError(_ERROR)
    for _ in range(MAX_PRE_DATA_CHUNKS):
        if stream.tell() + 8 > declared_end:
            raise ValueError(_ERROR)
        chunk = stream.read(8)
        if len(chunk) != 8:
            raise ValueError(_ERROR)
        chunk_size = int.from_bytes(chunk[4:8], "little")
        data_start = stream.tell()
        next_chunk = data_start + chunk_size + (chunk_size & 1)
        if next_chunk > declared_end:
            raise ValueError(_ERROR)
        if chunk[:4] == b"data":
            stream.seek(0)
            return data_start, chunk_size
        stream.seek(next_chunk)
    raise ValueError(_ERROR)


@contextmanager
def admitted_pcm16(path, *, seen_inodes=None):
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
        # A/B baseline and candidate must not be the same regular inode,
        # including different names linked to one file. The optional set is
        # private to one group admission, never returned in a report.
        if seen_inodes is not None:
            identity = (before.st_dev, before.st_ino)
            if identity in seen_inodes:
                raise ValueError(_ERROR)
            seen_inodes.add(identity)
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = -1
            # An attacker can fit millions of empty RIFF chunks below
            # 32 MiB; do not let wave.open walk an unbounded header chain.
            data_start, data_bytes = _locate_data_chunk(stream, before.st_size)
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
                        # Validate against actual data location and byte
                        # count, including noncanonical pre-data RIFF chunks.
                        or stream.tell() != data_start
                        or data_bytes != frames * channels * width
                        or data_start + data_bytes > before.st_size):
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



def _consume_pcm16(reader, *, block_frames=4096):
    """Read all declared frames without retaining source PCM."""
    remaining = reader.getnframes()
    width = reader.getnchannels() * 2
    while remaining:
        count = min(block_frames, remaining)
        if len(reader.readframes(count)) != count * width:
            raise ValueError(_ERROR)
        remaining -= count


def validate_private_ab_group(paths):
    """Strict offline A/B input-group integrity preflight.

    Open every participant once, check *all* headers and aggregate limits
    before reading any PCM, and keep all FDs open until post-scan identity
    checks. Reject different audio shapes; output no source names/hashes.
    This does not screen audible duplicates or rate musical quality.
    """
    if type(paths) not in (tuple, list) or not 2 <= len(paths) <= MAX_GROUP_SOURCES:
        raise ValueError(_ERROR)
    with ExitStack() as stack:
        identities = set()
        readers = [stack.enter_context(admitted_pcm16(path, seen_inodes=identities)) for path in paths]
        header = (readers[0].getframerate(), readers[0].getnchannels(), readers[0].getnframes())
        for reader in readers[1:]:
            if (reader.getframerate(), reader.getnchannels(), reader.getnframes()) != header:
                raise ValueError(_ERROR)
        if header[2] * len(readers) > MAX_GROUP_FRAMES:
            raise ValueError(_ERROR)
        for reader in readers:
            _consume_pcm16(reader)
    return {
        "screen": "ml07-single-fd-ab-group-integrity-v1",
        "sample_rate": header[0], "channels": header[1], "frames": header[2],
        "candidate_count": len(paths) - 1, "shape_comparable": True,
        "pcm16_payloads_complete": True, "human_listening_required": True,
    }


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid WAV admission arguments (details withheld)\\n")


def main(argv=None):
    """Optional independent probe; this does not activate the main MixLab CLI."""
    parser = _PrivateParser(description="Offline PCM16 integrity, NOT musical quality")
    parser.add_argument("source", help="Private local PCM16 WAV (never echoed)")
    parser.add_argument("candidates", nargs="*", help="Private candidate WAVs for --ab-group")
    parser.add_argument("--ab-group", action="store_true", help="Preflight baseline plus 1..7 A/B candidates")
    arguments = parser.parse_args(argv)
    if bool(arguments.candidates) != arguments.ab_group:
        parser.error("Mode mismatch")
    try:
        if arguments.ab_group:
            report = validate_private_ab_group([arguments.source, *arguments.candidates])
        else:
            report = validate_private_pcm16(arguments.source)
    except (OSError, ValueError, EOFError, wave.Error, struct.error):
        parser.exit(3, "Private WAV admission rejected (details withheld)\\n")
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
