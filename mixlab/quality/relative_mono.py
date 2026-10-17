"""Opt-in relative stereo-to-mono A/B confound screen (not a DJ-quality score).

The canonical MixLab quality scan already measures *absolute* fold-down
cancellation. This read-only companion asks a different question: is the
candidate substantially worse than the equal-duration baseline? No audio,
paths, hashes, or listener identifiers appear in the result.
"""
from __future__ import annotations

from array import array
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import wave

from . import MAX_SOURCE_BYTES, compare_wavs

MIN_DURATION_SECONDS = 1.0
MAX_SILENT_WINDOW_FRACTION = 0.2
MIN_CANDIDATE_RISK_FRACTION = 0.25
MIN_ADDED_RISK_FRACTION = 0.25
MAX_CANDIDATES = 4
WINDOW_MS = 100
STREAM_FRAMES = 4096
FRAME_ACTIVITY_ABS = 512  # 1.56% FS, sample-level screen (not LUFS)
MIN_JOINT_WINDOW_FRACTION = 0.5
MIN_JOINT_FRAMES = 4096
MIN_CONSECUTIVE_JOINT_WINDOWS = 4
MONO_LOSS_RATIO = 10 ** (-9 / 10)


def assess(
    report: dict,
    jointly_audible: dict[str, tuple[float, float] | None] | None = None,
) -> dict:
    """Only compare aligned *simultaneously active* stereo evidence.

    The existing per-file metrics remain a quick admission condition. A
    positive/no-new-risk verdict also needs the independently checked paired
    same-frame windows. Calling assess() on an untrusted report alone must
    conservatively abstain.
    """
    baseline = report["baseline"]
    output = []
    for row in report["candidates"]:
        candidate = row["metrics"]
        shared = jointly_audible.get(row["candidate_id"]) if jointly_audible else None
        adequate = (
            baseline["channels"] == candidate["channels"] == 2
            and baseline["duration_seconds"] >= MIN_DURATION_SECONDS
            and candidate["duration_seconds"] >= MIN_DURATION_SECONDS
            and baseline["silent_window_fraction"] <= MAX_SILENT_WINDOW_FRACTION
            and candidate["silent_window_fraction"] <= MAX_SILENT_WINDOW_FRACTION
            and baseline["rms_dbfs"] is not None
            and candidate["rms_dbfs"] is not None
            and shared is not None
        )
        if not adequate:
            status = "insufficient_stereo_evidence"
            delta = None
        elif any(row.get(field) is not None for field in (
                "duplicate_pcm_of", "stereo_swapped_pcm_of",
                "polarity_inverted_pcm_of")):
            # The canonical PCM digests already identify exact no-op audio,
            # copied candidates, L/R swaps and signed polarity inversions.
            # An unchanged or trivially transformed playback is not a valid
            # independent blinded transition even when its mono fold-down
            # numbers appear clean. Never echo the private match identifier.
            status = "non_independent_ab_audio"
            delta = None
        elif any(
                metrics.get(field) is True
                for metrics in (baseline, candidate)
                for field in (
                    "interior_silent_gap_risk",
                    "short_interior_pcm_dropout_risk",
                    "short_interior_stereo_channel_dropout_risk",
                    "isolated_sample_impulse_risk",
                    "severe_sample_discontinuity_risk",
                    "high_flat_top_plateau_risk",
                )):
            # The canonical reader already identifies missing PCM spans,
            # stereo-channel dropouts, sharp sample clicks, and flat tops.
            # A clean *mono fold-down* is not enough to admit a damaged
            # A/B source, including a defective crossfade baseline.
            # Emit only the category; not sample positions, audio or IDs.
            status = "ab_audio_integrity_confound"
            delta = None
        elif any(row.get(field) is True for field in (
                "short_window_level_mismatch_risk",
                "edge_silence_mismatch_risk",
                "prominent_onset_mismatch_risk")):
            # Equal duration/global RMS do not establish an equivalent
            # listening comparison: large localized gain changes or a
            # shifted audible entry/end can leak the variant to listeners.
            # The canonical detector already computed these flags from
            # bounded PCM. Do not disclose the onset time or RMS envelope.
            status = "ab_timing_or_dynamics_confound"
            delta = None
        elif row.get("level_comparable_for_blind_ab") is not True:
            # A large RMS difference invalidates a blinded comparison.
            status = "rms_level_confound"
            delta = None
        else:
            base_risk, candidate_risk = shared
            delta = round(candidate_risk - base_risk, 6)
            if (candidate_risk >= MIN_CANDIDATE_RISK_FRACTION
                    and delta >= MIN_ADDED_RISK_FRACTION):
                status = "candidate_introduces_mono_cancellation"
            elif base_risk >= MIN_CANDIDATE_RISK_FRACTION:
                status = "baseline_already_has_mono_cancellation"
            else:
                status = "no_new_sustained_mono_cancellation_detected"
        output.append({
            "candidate_id": row["candidate_id"],
            "status": status,
            "added_risky_window_fraction": delta,
            "requires_human_review": True,
        })
    return {
        "schema_version": 1,
        "purpose": "technical_relative_mono_preflight_not_musical_quality",
        "candidate_count": len(output),
        "candidates": output,
        "human_preference_test_required": True,
        "milestone_pass": False,
        "contains_source_paths_or_audio": False,
    }


def _paired_phase_fractions(baseline: str, candidate: str) -> tuple[float, float] | None:
    """Read bounded aligned PCM16 windows, retaining no audio or source IDs.

    A file-wise 100ms RMS scanner cannot distinguish alternating even/odd
    samples with zero simultaneous audible frames. Require >=50% jointly
    active frames in each eligible 100ms interval, at least four *consecutive*
    eligible windows, and >=4096 jointly active frames in accepted windows.
    A loss is assessed on those same overlapping frames in both variants.
    """
    with wave.open(str(baseline), "rb") as a, wave.open(str(candidate), "rb") as b:
        left, right = a.getparams(), b.getparams()
        if (left.nchannels != 2 or right.nchannels != 2
                or left.sampwidth != 2 or right.sampwidth != 2
                or left.comptype != "NONE" or right.comptype != "NONE"
                or left.framerate != right.framerate
                or left.nframes != right.nframes
                or not 8000 <= left.framerate <= 96000
                or not 1 <= left.nframes <= 2_000_000):
            raise ValueError("private stereo A/B format mismatch")
        step = round(left.framerate * WINDOW_MS / 1000)
        eligible = bad_a = bad_b = matched_frames = 0
        consecutive = longest_consecutive = 0
        in_window = joint = a_energy = b_energy = a_mix = b_mix = 0

        def _accepted() -> None:
            nonlocal eligible, bad_a, bad_b, matched_frames
            nonlocal consecutive, longest_consecutive
            if joint * 2 < step:
                consecutive = 0
                return
            eligible += 1
            matched_frames += joint
            consecutive += 1
            longest_consecutive = max(longest_consecutive, consecutive)
            if a_mix <= 2 * MONO_LOSS_RATIO * a_energy:
                bad_a += 1
            if b_mix <= 2 * MONO_LOSS_RATIO * b_energy:
                bad_b += 1

        for start in range(0, left.nframes, STREAM_FRAMES):
            count = min(STREAM_FRAMES, left.nframes - start)
            chunk_a, chunk_b = a.readframes(count), b.readframes(count)
            if len(chunk_a) != 4 * count or len(chunk_b) != 4 * count:
                raise ValueError("private PCM16 truncated during aligned scan")
            samples_a, samples_b = array("h"), array("h")
            samples_a.frombytes(chunk_a)
            samples_b.frombytes(chunk_b)
            if sys.byteorder != "little":
                samples_a.byteswap()
                samples_b.byteswap()
            for position in range(0, len(samples_a), 2):
                al, ar = samples_a[position], samples_a[position + 1]
                bl, br = samples_b[position], samples_b[position + 1]
                if (max(abs(al), abs(ar)) >= FRAME_ACTIVITY_ABS
                        and max(abs(bl), abs(br)) >= FRAME_ACTIVITY_ABS):
                    joint += 1
                    a_energy += al * al + ar * ar
                    b_energy += bl * bl + br * br
                    a_mix += (al + ar) ** 2
                    b_mix += (bl + br) ** 2
                in_window += 1
                if in_window == step:
                    _accepted()
                    in_window = joint = a_energy = b_energy = a_mix = b_mix = 0

        # Partial trailing windows carry too little evidence and never pass.
        if (eligible < MIN_CONSECUTIVE_JOINT_WINDOWS
                or longest_consecutive < MIN_CONSECUTIVE_JOINT_WINDOWS
                or matched_frames < MIN_JOINT_FRAMES):
            return None
        return bad_a / eligible, bad_b / eligible


def _admit_regular_path(source: str) -> tuple[int, ...]:
    """Reject symlinked paths, special files, and overlarge input before scan.

    This is a static admission guard, NOT an atomic open-descriptor binding
    under concurrent hostile renames. Only use in a trusted local workspace.
    """
    path = Path(os.path.abspath(source))
    for parent in reversed(path.parents):
        if not stat.S_ISDIR(os.lstat(parent).st_mode):
            raise ValueError("private audio parent is not a regular directory")
    leaf = os.lstat(path)
    if not stat.S_ISREG(leaf.st_mode) or not 44 <= leaf.st_size <= MAX_SOURCE_BYTES:
        raise ValueError("private input must be a bounded regular WAV")
    return (leaf.st_dev, leaf.st_ino, leaf.st_size, leaf.st_mtime_ns, leaf.st_ctime_ns)


def inspect(baseline: str, candidates: list[str]) -> dict:
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("expected 1..4 candidates")
    paths = (baseline, *candidates)
    identities = tuple(_admit_regular_path(path) for path in paths)
    report = compare_wavs(baseline, candidates, window_ms=WINDOW_MS)
    # Clear format, duration or silence admission failures already
    # require abstention. Skip the expensive paired read for those cases,
    # but *not* merely for a loudness mismatch: a sparse RMS-confounded
    # candidate can also have zero credible common-frame phase evidence.
    base = report["baseline"]
    base_admissible = (
        base["channels"] == 2
        and base["duration_seconds"] >= MIN_DURATION_SECONDS
        and base["silent_window_fraction"] <= MAX_SILENT_WINDOW_FRACTION
        and base["rms_dbfs"] is not None
    )
    paired = {}
    for index, candidate in enumerate(candidates, 1):
        row = report["candidates"][index - 1]
        data = row["metrics"]
        candidate_admissible = (
            data["channels"] == 2
            and data["duration_seconds"] >= MIN_DURATION_SECONDS
            and data["silent_window_fraction"] <= MAX_SILENT_WINDOW_FRACTION
            and data["rms_dbfs"] is not None
        )
        paired[f"candidate-{index:02d}"] = (
            _paired_phase_fractions(baseline, candidate)
            if base_admissible and candidate_admissible else None
        )
    if tuple(_admit_regular_path(path) for path in paths) != identities:
        raise ValueError("private PCM source changed during QA scan")
    return assess(report, paired)


class _PrivateArgumentParser(argparse.ArgumentParser):
    """Never echo potentially sensitive unknown arguments or paths."""

    def error(self, message: str) -> None:
        raise ValueError("private CLI arguments invalid")


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateArgumentParser(
        description="Offline relative stereo/mono QA; never certifies music quality"
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", action="append", required=True)
    try:
        options = parser.parse_args(argv)
        result = inspect(options.baseline, options.candidate)
    except Exception:
        # Hide all parser, OS, and decoder diagnostics; external arguments
        # can include confidential audio names. No private paths in stderr.
        print(json.dumps({"status": "invalid_private_pcm", "milestone_pass": False}))
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    statuses = {entry["status"] for entry in result["candidates"]}
    return 3 if any(s != "no_new_sustained_mono_cancellation_detected" for s in statuses) else 0


if __name__ == "__main__":
    sys.exit(main())
