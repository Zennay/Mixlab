"""Strict, bounded RIFF/PCM16 header consistency for *private* quality scans.

Unlike listener-public WAVs, private source WAVs may contain metadata chunks
or trailing non-audio bytes. Never surface those bytes in quality JSON.
"""
import os
from typing import BinaryIO

# A metadata-heavy private WAV can contain unknown RIFF chunks; keep the
# preflight finite rather than iterating millions of 8-byte no-op headers.
MAX_PRIVATE_HEADER_CHUNKS = 4096


def verify_private_pcm16_header(handle: BinaryIO) -> None:
    """Check RIFF consistency on the caller's already-open regular file.

    Chunk headers and the 16-18 byte fmt prefix are read; private metadata
    is only skipped, never parsed or serialized. The caller uses the same fd
    for subsequent PCM decoding and file-identity validation.
    """
    actual_bytes = os.fstat(handle.fileno()).st_size
    if actual_bytes < 44:
        raise ValueError("Invalid PCM16 RIFF header")
    handle.seek(0)
    riff = handle.read(12)
    if (len(riff) != 12 or riff[:4] != b"RIFF"
            or riff[8:12] != b"WAVE"):
        raise ValueError("Unsupported RIFF/WAVE container")
    riff_end = int.from_bytes(riff[4:8], "little") + 8
    if riff_end > actual_bytes or riff_end < 44:
        raise ValueError("Inconsistent RIFF container extent")
    offset = 12
    format_seen = False
    data_seen = False
    block_align = None
    inspected_chunks = 0
    while offset + 8 <= riff_end:
        inspected_chunks += 1
        if inspected_chunks > MAX_PRIVATE_HEADER_CHUNKS:
            raise ValueError("PCM16 RIFF header contains too many chunks")
        handle.seek(offset)
        chunk = handle.read(8)
        if len(chunk) != 8:
            raise ValueError("Truncated WAV chunk header")
        chunk_name, chunk_size = chunk[:4], int.from_bytes(chunk[4:8], "little")
        payload = offset + 8
        end = payload + chunk_size
        if end > riff_end:
            raise ValueError("WAV chunk exceeds RIFF boundary")
        if chunk_name == b"fmt ":
            if format_seen or chunk_size < 16 or chunk_size > 40:
                raise ValueError("Invalid or repeated PCM16 fmt chunk")
            fields = handle.read(16)
            if len(fields) != 16:
                raise ValueError("Truncated PCM16 fmt payload")
            # PCM has a 16-byte canonical fmt body; a recognized
            # extended body includes at least the two-byte cbSize.
            # Reject a fractional extension or forged cbSize that
            # some decoders silently ignore.
            if chunk_size != 16:
                if chunk_size < 18:
                    raise ValueError("Incomplete PCM16 fmt extension")
                advertised_extension = int.from_bytes(handle.read(2), "little")
                if advertised_extension != chunk_size - 18:
                    raise ValueError("Inconsistent PCM16 fmt extension")
            encoding = int.from_bytes(fields[0:2], "little")
            channels = int.from_bytes(fields[2:4], "little")
            rate = int.from_bytes(fields[4:8], "little")
            bytes_per_second = int.from_bytes(fields[8:12], "little")
            block_align = int.from_bytes(fields[12:14], "little")
            bits = int.from_bytes(fields[14:16], "little")
            if (encoding != 1 or channels not in (1, 2)
                    or not 8000 <= rate <= 96000
                    or bits != 16 or block_align != 2 * channels
                    or bytes_per_second != rate * block_align):
                raise ValueError("Inconsistent PCM16 format header")
            format_seen = True
        elif chunk_name == b"data":
            # Preserve the established invalid-alignment diagnostic.
            # Duplicate data is a separate malformed-container class.
            if not format_seen or chunk_size % block_align:
                raise ValueError("Invalid PCM16 data alignment")
            if data_seen:
                raise ValueError("Invalid or duplicated PCM16 data chunk")
            data_seen = True
            # Do not stop here: a second data/fmt chunk, truncated RIFF
            # trailer or unexpected structure after playback can make
            # other WAV players interpret a different recording.
        # Honor RIFF even-byte chunk alignment when skipping metadata;
        # metadata payload is never read into memory or returned.
        offset = end + (chunk_size & 1)
        if offset > riff_end:
            raise ValueError("Missing RIFF chunk padding")
    if offset != riff_end:
        raise ValueError("Incomplete RIFF chunk trailer")
    if not data_seen:
        raise ValueError("Missing PCM16 data chunk")
    # The wave module performs the bounded frame read independently;
    # header integrity is now checked through the full declared RIFF.
