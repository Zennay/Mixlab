"""Opt-in read-only development-versus-blind-holdout source-isolation gate.

Both libraries are validated against their actual private PCM16 WAV bytes using
MixLab's existing bounded ingest. A separately preregistered study SHA-256 is
required. This checks identity collisions, not source rights or DJ quality.
"""
from __future__ import annotations

import argparse
from array import array
import json
from pathlib import Path

from ..ingest import pcm_blocks, validate_library
from .study_binding import _verified_study

_ERROR = "Invalid, inconsistent or overlapping private holdout sources"
_MAX_TOTAL_TRACKS = 50


class HoldoutIsolationError(ValueError):
    """Non-disclosing admission failure for confidential source material."""


def _refuse() -> None:
    raise HoldoutIsolationError(_ERROR)


def _path(value) -> Path:
    # Avoid executing arbitrary PathLike.__fspath__ on private evidence.
    if type(value) not in (str, type(Path("."))):
        _refuse()
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def _identity_set(tracks) -> set[tuple[str, str]]:
    result = set()
    for tid, track in tracks.items():
        result.update((
            ("track_id", tid),
            ("recording_id", track.get("recording_id", tid)),
            ("wav_sha256", track["sha256"]),
            ("decoded_pcm_sha256", track["pcm_sha256"]),
        ))
    return result


def _snapshot(manifest, tracks):
    """Retain just anonymous source evidence for the rescan consistency gate."""
    return (
        manifest,
        tuple(sorted((
            tid, row["sha256"], row["pcm_sha256"], row.get("recording_id", tid),
            row.get("partition"), row["sample_rate"], row["channels"],
            row["frame_count"],
        ) for tid, row in tracks.items())),
    )




def _pcm_exact_transform_variants(raw: bytes, channels: int) -> set[bytes]:
    """Exact integer-PCM transformations, deliberately not acoustic matching.

    Detect reuse after stereo L/R exchange, signed polarity inversion, and
    precise 2x gain, including their combinations. Fail closed on signed16
    overflow by *omitting* the impossible transform. No lossy quantization or
    guessed gain ratio: positive hits are byte-identical genuine PCM reuse.
    """
    if channels not in (1, 2) or len(raw) % (channels * 2):
        _refuse()
    source = array("h")
    source.frombytes(raw)
    frames = tuple(source)
    candidates = {raw}
    for stereo_swap in ((False, True) if channels == 2 else (False,)):
        if stereo_swap:
            values = [value for i in range(0, len(frames), 2)
                      for value in (frames[i + 1], frames[i])]
        else:
            values = frames
        for gain in (1, -1, 2, -2):
            if not all(-32768 <= value * gain <= 32767 for value in values):
                continue
            output = array("h", (value * gain for value in values))
            candidates.add(output.tobytes())
    return candidates




def _pcm_channel_views(raw: bytes, channels: int) -> tuple:
    """Keep both the full PCM stream and each genuine stereo source channel.

    Channel projections use exactly the stored PCM samples. Detect when a
    mono file copies L or R from a stereo source, or when two stereo sources
    reuse a channel. This does not mean mono downmixes are equivalent.
    """
    if channels == 1:
        return (("whole", 1, raw),)
    if channels != 2 or len(raw) % 4:
        _refuse()
    pcm = array("h")
    pcm.frombytes(raw)
    return (("whole", 2, raw),
            ("left", 1, pcm[::2].tobytes()),
            ("right", 1, pcm[1::2].tobytes()))


def _exact_pcm_excerpt_overlap(development, evaluation) -> bool:
    """Bounded exact audible excerpt reuse screen, no fingerprints disclosed.

    Four shared seconds are not required: a 200-ms sufficiently audible run
    that is byte-for-byte reused is enough to hold for provenance review.
    This catches clips cut from a longer source with different container and
    full-file PCM digests, *provided their sample rate/channels still match*.
    Anchors also cover exact polarity inversion, L/R swap, and 2x gain
    combinations, and genuine stereo-channel projections; these are
    deterministic PCM operations, not music matching.

    At most 3 anchored windows per source and at most 50 total sources;
    all source reads are streamed through the validated single-FD PCM reader.
    This is NOT a robust musical fingerprint or a remaster detector.
    """
    by_format = {}
    groups = (("dev", development), ("eval", evaluation))
    for group, tracks in groups:
        for tid, track in tracks.items():
            rate = track["sample_rate"]
            channels = track["channels"]
            frames = track["frame_count"]
            width = min(4096, rate // 5, frames)
            if width < 256:
                _refuse()
            starts = {0, (frames - width) // 2, frames - width}
            for start in sorted(starts):
                pcm = b"".join(samples.tobytes() for samples in pcm_blocks(
                    track["resolved_path"], start=start, frames=width))
                if len(pcm) != width * channels * 2:
                    _refuse()
                values = array("h")
                values.frombytes(pcm)
                # Ignore silent / near-silent reusable spacers, avoiding
                # false leakage from common zeros, padding and quiet tails.
                if sum(abs(sample) for sample in values) < 512 * len(values):
                    continue
                for _, view_channels, view_pcm in _pcm_channel_views(pcm, channels):
                    for variant in _pcm_exact_transform_variants(
                            view_pcm, view_channels):
                        by_format.setdefault((rate, view_channels), []).append(
                            (group, tid, variant))

    for group, tracks in groups:
        for tid, track in tracks.items():
            channels = track["channels"]
            rate = track["sample_rate"]
            # Decide active stream projections once, before opening audio.
            plans = {}
            for name, projection in (("whole", channels),
                                     *([("left", 1), ("right", 1)]
                                       if channels == 2 else [])):
                candidates = [
                    anchor for anchor_group, anchor_id, anchor
                    in by_format.get((rate, projection), ())
                    if not (group == anchor_group and tid == anchor_id)
                    and not (group == "dev" and anchor_group == "dev")
                ]
                if candidates:
                    frame_bytes = 2 * projection
                    largest = max(map(len, candidates))
                    retain = ((largest - 1 + frame_bytes - 1)
                              // frame_bytes) * frame_bytes
                    plans[name] = (candidates, frame_bytes, retain, b"")
            if not plans:
                continue
            collision = False
            for samples in pcm_blocks(track["resolved_path"], block_frames=32768):
                if channels == 1:
                    projections = (("whole", samples.tobytes()),)
                else:
                    projections = (("whole", samples.tobytes()),
                                   ("left", samples[::2].tobytes()),
                                   ("right", samples[1::2].tobytes()))
                for name, data in projections:
                    if name not in plans:
                        continue
                    candidates, frame_bytes, retained, overlap = plans[name]
                    chunk = overlap + data
                    if not collision:
                        for anchor in candidates:
                            offset = chunk.find(anchor)
                            while offset >= 0:
                                if offset % frame_bytes == 0:
                                    collision = True
                                    break
                                offset = chunk.find(anchor, offset + 1)
                            if collision:
                                break
                    plans[name] = (candidates, frame_bytes, retained,
                                   chunk[-retained:] if retained else b"")
            # Finish the real PCM descriptor read even when a match was found,
            # so its ordinary source-mutation checks still run before refuse.
            if collision:
                return True
    return False


def audit_holdout_isolation(development_manifest, evaluation_manifest,
                            study_path, expected_study_id) -> dict:
    """Reject identical recordings in development and a frozen evaluation set.

    All 5-10 preregistered pairs must exhaust the evaluation manifest: this
    deliberately narrow gate does not accept exploratory, unselected tracks as
    frozen listening material. The blind-study SHA must be independently pinned
    outside this tool and before any actual reviewer feedback.
    """
    try:
        dev_path = _path(development_manifest)
        eva_path = _path(evaluation_manifest)
        study_path = _path(study_path)
        if len({str(dev_path), str(eva_path), str(study_path)}) != 3:
            _refuse()

        # Each call verifies all actual source WAV bytes, checks SHA-256 and
        # decoded PCM identity, plus local permissions and pair constraints.
        dev_manifest, dev = validate_library(dev_path)
        eva_manifest, eva = validate_library(eva_path)
        if not 2 <= len(dev) or not 10 <= len(eva) or len(dev) + len(eva) > _MAX_TOTAL_TRACKS:
            _refuse()
        if any(track.get("partition") != "development" for track in dev.values()):
            _refuse()
        if any(track.get("partition") != "evaluation" for track in eva.values()):
            _refuse()
        if _identity_set(dev).intersection(_identity_set(eva)):
            _refuse()

        study = _verified_study(study_path, expected_study_id)
        frozen = study["pairs"]
        frozen_ids = set()
        frozen_pairs = set()
        for pair in frozen:
            a, b = pair["a"], pair["b"]
            frozen_ids.update((a, b))
            frozen_pairs.add((a, b))
            for label, track_id in (("a", a), ("b", b)):
                track = eva.get(track_id)
                if (track is None
                        or track["sha256"] != pair[label + "_sha256"]
                        or track["bpm"] != pair[label + "_bpm"]):
                    _refuse()

        # A frozen evaluation manifest may not contain unseen tracks/pairs,
        # even when the new files themselves appear to have clean checksums.
        manifest_pairs = eva_manifest["pairs"]
        if (set(eva) != frozen_ids
                or len(manifest_pairs) != len(frozen_pairs)
                or {(row["a"], row["b"]) for row in manifest_pairs} != frozen_pairs):
            _refuse()

        # Do not count the same underlying recording twice in evaluation
        # merely by changing IDs or re-encoding the WAV header.
        eval_recordings = [row.get("recording_id", tid) for tid, row in eva.items()]
        if len(set(eval_recordings)) != len(eval_recordings):
            _refuse()
        eval_pcm = [row["pcm_sha256"] for row in eva.values()]
        if len(set(eval_pcm)) != len(eval_pcm):
            _refuse()

        # Same-song subclips can evade both full-file hashes and an inaccurate
        # recording_id. Require a bounded actual PCM substring preflight.
        if _exact_pcm_excerpt_overlap(dev, eva):
            _refuse()

        # Observable mutations between the first PCM reads and final verdict
        # invalidate the result; the gate is not an immutable storage system.
        again_dev = validate_library(dev_path)
        again_eva = validate_library(eva_path)
        if (_snapshot(dev_manifest, dev) != _snapshot(*again_dev)
                or _snapshot(eva_manifest, eva) != _snapshot(*again_eva)
                or _verified_study(study_path, expected_study_id) != study):
            _refuse()

        return {
            "schema_version": 1,
            "development_track_count": len(dev),
            "evaluation_track_count": len(eva),
            "frozen_pair_count": len(frozen),
            "development_evaluation_source_identity_separate": True,
            "evaluation_sources_match_externally_pinned_study": True,
            "source_rights_independently_authenticated": False,
            "recording_lineage_independently_authenticated": False,
            "human_preference_proven": False,
            "milestone_pass": False,
        }
    except (ValueError, OSError, KeyError, TypeError, IndexError,
            OverflowError, RecursionError):
        raise HoldoutIsolationError(_ERROR) from None


def main(argv=None) -> int:
    class SafeParser(argparse.ArgumentParser):
        def error(self, _message):
            self.exit(2, "MixLab holdout isolation: invalid arguments\n")

    parser = SafeParser(description="Private holdout PCM identity preflight, NOT release approval")
    parser.add_argument("development_manifest")
    parser.add_argument("evaluation_manifest")
    parser.add_argument("study")
    parser.add_argument("--expected-study-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_holdout_isolation(
            args.development_manifest, args.evaluation_manifest,
            args.study, args.expected_study_id)
    except HoldoutIsolationError:
        parser.exit(2, "MixLab holdout isolation: private inputs invalid or overlapping\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
