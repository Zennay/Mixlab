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
import math
import os
from pathlib import Path
import stat
import sys
import wave

from ..models import FAMILY_NAMES

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


def _open_no_symlink_components(path: Path) -> int:
    """Open an admitted file while refusing symlinks in EVERY path component.

    A bare O_NOFOLLOW on the final component still follows parent-directory
    symlinks. Walk an absolute lexical path using O_DIRECTORY | O_NOFOLLOW
    dirfds, closing every intermediate descriptor before returning the final
    (nonblocking, no-follow) read-only source descriptor.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RepeatabilityError(_ERROR)
    absolute = Path(os.path.abspath(os.fspath(path)))
    components = absolute.parts
    if len(components) < 2:
        raise RepeatabilityError(_ERROR)
    common = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    directory_flags = common | os.O_DIRECTORY | getattr(os, "O_NONBLOCK", 0)
    file_flags = common | getattr(os, "O_NONBLOCK", 0)
    with ExitStack() as dirs:
        parent = os.open(os.sep, directory_flags)
        dirs.callback(os.close, parent)
        for component in components[1:-1]:
            next_parent = os.open(component, directory_flags, dir_fd=parent)
            dirs.callback(os.close, next_parent)
            parent = next_parent
        return os.open(components[-1], file_flags, dir_fd=parent)


def _source(path: Path, stack: ExitStack) -> tuple[wave.Wave_read, object, os.stat_result]:
    # Reject parent-component symlinks, final symlinks and FIFOs before
    # parsing a header or streaming any private PCM.
    fd = _open_no_symlink_components(path)
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
    # Reopen the complete named path without traversing symlinked ancestors:
    # a basename-only lstat would still follow a swapped parent directory.
    check_fd = _open_no_symlink_components(path)
    try:
        named = os.fstat(check_fd)
    finally:
        os.close(check_fd)
    return (
        stat.S_ISREG(named.st_mode)
        and _identity(info) == _identity(original) == _identity(named)
    )


def _admit_receipt_shape(receipt: object) -> None:
    """Bound in-process receipt metadata BEFORE JSON serialization.

    A post-serialization length check alone cannot defend memory usage: an
    attacker may supply multi-megabyte strings, enormous dicts, recursive
    containers or deeply nested metadata. Accept only plain JSON value types;
    cap nodes, recursion depth and an upper bound on raw scalar length.
    """
    pending = [(receipt, 0)]
    seen_containers: set[int] = set()
    nodes = 0
    text_budget = 16_384
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 2_048 or depth > 16:
            raise RepeatabilityError(_ERROR)
        if type(value) in (dict, list):
            if id(value) in seen_containers:
                # Also conservatively disallow aliased mutable containers.
                raise RepeatabilityError(_ERROR)
            seen_containers.add(id(value))
            if len(value) > 128:
                raise RepeatabilityError(_ERROR)
            if type(value) is dict:
                for key, child in value.items():
                    if type(key) is not str or len(key) > 128:
                        raise RepeatabilityError(_ERROR)
                    text_budget -= len(key)
                    pending.append((child, depth + 1))
            else:
                pending.extend((item, depth + 1) for item in value)
        elif type(value) is str:
            text_budget -= len(value)
        elif value is None or type(value) is bool:
            text_budget -= 4
        elif type(value) is int:
            if value.bit_length() > 128:
                raise RepeatabilityError(_ERROR)
            text_budget -= 48
        elif type(value) is float:
            if not math.isfinite(value):
                raise RepeatabilityError(_ERROR)
            text_budget -= 48
        else:
            raise RepeatabilityError(_ERROR)
        if text_budget < 0:
            raise RepeatabilityError(_ERROR)


def _receipt_contract(receipt: object, shape: tuple[int, int, int, int]) -> tuple[str, str]:
    """Validate a private renderer receipt without ever serializing it publicly.

    The receipt is an *untrusted statement*, not a signature: source hashes
    and recipe are compared with the other receipt, while output_sha256 is
    independently recomputed from its actual open WAV descriptor.
    """
    if not isinstance(receipt, dict):
        raise RepeatabilityError(_ERROR)
    try:
        # Reject oversized or cyclic containers before any encoding work.
        # Do not retain or publish the private receipt or its serialization.
        _admit_receipt_shape(receipt)
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw) > 16384:
            raise RepeatabilityError(_ERROR)
        channels, width, rate, frames = shape
        if (type(receipt.get("schema_version")) is not int
                or receipt["schema_version"] != 1
                or type(receipt.get("engine_version")) is not str
                or not receipt["engine_version"]
                or type(receipt.get("channels")) is not int
                or receipt["channels"] != channels
                or type(receipt.get("sample_rate")) is not int
                or receipt["sample_rate"] != rate
                or type(receipt.get("frames")) is not int
                or receipt["frames"] != frames
                or width != 2):
            raise RepeatabilityError(_ERROR)
        recipe = receipt.get("recipe")
        origins = receipt.get("sources")
        positions = receipt.get("start_frames")
        if (not isinstance(recipe, dict) or not recipe
                or not isinstance(positions, dict)
                or not {"a", "b"} <= positions.keys()
                or not isinstance(origins, list) or len(origins) != 2):
            raise RepeatabilityError(_ERROR)
        source_hashes = [item.get("sha256") if isinstance(item, dict) else None
                         for item in origins]
        output_hash = receipt.get("output_sha256")
        if not all(
            isinstance(h, str) and len(h) == 64
            and all(c in "0123456789abcdef" for c in h)
            for h in (*source_hashes, output_hash)
        ):
            raise RepeatabilityError(_ERROR)
        # Two equally malformed receipts cannot establish even metadata
        # consistency. Validate the ordinary numeric/structural contract
        # before checking equality of its declared semantic fields.
        def positive_number(value: object) -> bool:
            return (type(value) in (float, int)
                    and math.isfinite(value) and value > 0)

        if (type(recipe.get("family")) is not str
                or recipe["family"] not in FAMILY_NAMES
                or not positive_number(recipe.get("bpm"))
                or not 30 <= recipe["bpm"] <= 300
                or type(recipe.get("beats")) is not int
                or not 1 <= recipe["beats"] <= 64
                or not positive_number(receipt.get("duration_seconds"))
                or not positive_number(receipt.get("gain_linear"))
                or any(type(positions.get(part)) is not int
                       or positions[part] < 0 for part in ("a", "b"))
                or any(not isinstance(receipt.get(part), str)
                       or not receipt[part] for part in (
                           "alignment_source", "tempo_source"))):
            raise RepeatabilityError(_ERROR)
        # Independently recompute physical facts from actual admitted PCM
        # shape and the same deterministic Recipe timing/gain conventions.
        # Do not accept even two IDENTICALLY forged contradictory receipts.
        bpm, beats = recipe["bpm"], recipe["beats"]
        gain_db = recipe.get("gain_db")
        if (type(gain_db) not in (float, int)
                or not math.isfinite(gain_db) or not -60 <= gain_db <= 0):
            raise RepeatabilityError(_ERROR)
        for key in ("a_start", "b_start"):
            start = recipe.get(key)
            if (type(start) not in (float, int)
                    or not math.isfinite(start) or not 0 <= start <= MAX_FRAMES / rate):
                raise RepeatabilityError(_ERROR)
        for key in ("a_bpm", "b_bpm"):
            declared = recipe.get(key)
            if declared is not None and (
                type(declared) not in (float, int)
                or not math.isfinite(declared)
                or abs(declared - bpm) > 1e-9
            ):
                raise RepeatabilityError(_ERROR)
        duration_expected = frames / rate
        gain_expected = 10 ** (gain_db / 20)
        if (beats * 60 / bpm > 120
                or round(beats * 60 / bpm * rate) != frames
                or not math.isclose(receipt["duration_seconds"], duration_expected,
                                    rel_tol=1e-12, abs_tol=1e-12)
                or not math.isclose(receipt["gain_linear"], gain_expected,
                                    rel_tol=1e-12, abs_tol=1e-12)
                or any(positions[side] != round(recipe[key] * rate)
                       for side, key in (("a", "a_start"), ("b", "b_start")))):
            raise RepeatabilityError(_ERROR)
        # Bind the semantic render contract; intentionally exclude the
        # output pathname, the output hash and block_frames. Block sizes may
        # differ while the intended recipe and output PCM remain identical.
        keys = ("schema_version", "engine_version", "recipe", "sample_rate",
                "channels", "frames", "duration_seconds", "gain_linear",
                "start_frames", "alignment_source", "tempo_source")
        if any(key not in receipt for key in keys):
            raise RepeatabilityError(_ERROR)
        semantic = {key: receipt[key] for key in keys}
        semantic["ordered_source_sha256"] = source_hashes
        fingerprint = json.dumps(semantic, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False)
        return fingerprint, output_hash
    except (TypeError, ValueError, KeyError, RecursionError):
        raise RepeatabilityError(_ERROR) from None


def _digest_open_file(handle: object, size: int) -> str:
    # Use the same admitted descriptor, not a second pathname open. Recheck
    # all file identities once both entire containers have been scanned.
    handle.seek(0)
    digest = hashlib.sha256()
    remaining = size
    while remaining:
        data = handle.read(min(65536, remaining))
        if not data:
            raise RepeatabilityError(_ERROR)
        remaining -= len(data)
        digest.update(data)
    return digest.hexdigest()


def verify_repeatability(
    first: str | os.PathLike[str],
    second: str | os.PathLike[str],
    *,
    receipts: tuple[dict, dict] | None = None,
) -> dict:
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
            receipt_contracts = None
            if receipts is not None:
                if not isinstance(receipts, (tuple, list)) or len(receipts) != 2:
                    raise RepeatabilityError(_ERROR)
                receipt_contracts = tuple(
                    _receipt_contract(receipt, shape)
                    for receipt, shape in zip(receipts, (left_format, right_format))
                )
                if not hmac.compare_digest(
                    receipt_contracts[0][0], receipt_contracts[1][0]
                ):
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
            if receipt_contracts is not None:
                # Each complete WAV must match its own private renderer
                # output_sha256. Same PCM with altered container metadata
                # must not pass when receipts are explicitly supplied.
                for (_, handle, info), (_, expected_hash) in zip(
                    sources, receipt_contracts
                ):
                    if not hmac.compare_digest(
                        _digest_open_file(handle, info.st_size), expected_hash
                    ):
                        raise RepeatabilityError(_ERROR)
            if not all(_unchanged(p, h, s) for p, (_, h, s) in zip(paths, sources)):
                raise RepeatabilityError(_ERROR)
            equal = hmac.compare_digest(digests[0].digest(), digests[1].digest())
        report = {
            "schema_version": 1,
            "repeatable_pcm": equal,
            "distinct_output_files_verified": True,
            "independent_render_executions_proven": False,
            "format_and_frame_count_verified": True,
            "technical_review_required": not equal,
            "human_preference_test_required": True,
        }
        if receipt_contracts is not None:
            report["render_receipts_consistent"] = True
        return report
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
