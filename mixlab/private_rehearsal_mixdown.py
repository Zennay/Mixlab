"""Produce a private continuous rehearsal-preview WAV from human-chosen MixLab chapters.

This is deliberate hard-joined PCM with an explicit silence gap, not a DJ
blend, normalized master, proof of source rights or validated listening study.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from .private_output import write_private_new
import tempfile
import wave

from .models import FAMILY_NAMES
from .private_transition_selection import _read_json_and_digest, _copy_and_verify_wav, _valid_sha

MAX_CHAPTERS = 8
MAX_TOTAL_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_CHAPTER_FRAMES = 2_000_000


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def _chapters(receipt):
    if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("kind") != "mixlab-private-rehearsal-reel"
            or receipt.get("status") != "human-selected-not-blind-study"
            or receipt.get("rights_status") != "unverified"):
        raise ValueError("Unsupported original private rehearsal receipt")
    chapters = receipt.get("chapters")
    if type(chapters) is not list or not 2 <= len(chapters) <= MAX_CHAPTERS:
        raise ValueError("Expected 2–8 original private rehearsal chapters")
    for i, chapter in enumerate(chapters, start=1):
        if type(chapter) is not dict or type(chapter.get("chapter")) is not int or chapter["chapter"] != i:
            raise ValueError("Chapter identity is not canonical")
        family = chapter.get("family")
        if family not in FAMILY_NAMES or chapter.get("audio") != f"{i:02d}-{family}.wav":
            raise ValueError("Unexpected original chapter audio path")
        if any(not _valid_sha(chapter.get(k)) for k in
               ("audio_sha256", "source_gallery_receipt_sha256", "human_choice_sha256")):
            raise ValueError("Original chapter source provenance is incomplete")
        note = chapter.get("private_note")
        if type(note) is not str or len(note) > 240:
            raise ValueError("Original cue note is invalid")
    return chapters


def _running_order(plan, original_receipt_sha, chapters):
    if (type(plan.get("schema_version")) is not int or plan["schema_version"] != 1
            or plan.get("kind") != "mixlab-private-rehearsal-order"
            or plan.get("status") != "human-reordered-not-blind-study"
            or plan.get("rights_status") != "unverified"
            or plan.get("receipt_sha256") != original_receipt_sha):
        raise ValueError("Running order was not exported from this exact private reel")
    entries = plan.get("order")
    if type(entries) is not list or len(entries) != len(chapters):
        raise ValueError("Running order must contain every original chapter exactly once")
    seen = set()
    result = []
    for i, entry in enumerate(entries, 1):
        if (type(entry) is not dict or type(entry.get("position")) is not int
                or entry["position"] != i or type(entry.get("original_chapter")) is not int):
            raise ValueError("Running order positions must be canonical")
        chapter = entry["original_chapter"]
        if chapter < 1 or chapter > len(chapters) or chapter in seen:
            raise ValueError("Running order duplicates or omits an original chapter")
        seen.add(chapter)
        result.append(chapter)
    return result


def render_mixdown(reel_dir, output_wav, *, order_json=None, gap_ms=350):
    """Render a locally audible, explicitly gapped private continuous rehearsal WAV."""
    if type(gap_ms) is not int or gap_ms < 0 or gap_ms > 1000:
        raise ValueError("Silence gap must be an integer from 0 to 1000 milliseconds")
    reel, output = Path(reel_dir), Path(output_wav)
    if not reel.is_dir() or not output.parent.is_dir() or output.suffix.lower() != ".wav":
        raise ValueError("Provide an original private reel and new .wav output in an existing directory")
    sidecar = output.with_suffix(".rehearsal.json")
    if any(path.exists() or path.is_symlink() for path in (output, sidecar)):
        raise ValueError("Output audio or receipt already exists; cannot replace either")
    receipt, receipt_sha = _read_json_and_digest(reel / "receipt.json")
    chapters = _chapters(receipt)
    if order_json is not None:
        plan, plan_sha = _read_json_and_digest(order_json)
        ordered_indices = _running_order(plan, receipt_sha, chapters)
    else:
        plan_sha = None
        ordered_indices = list(range(1, len(chapters) + 1))

    with tempfile.TemporaryDirectory(prefix=".mixlab-rehearsal-mixdown-", dir=output.parent) as temp:
        stage = Path(temp)
        copied = []
        info = []
        sample_rate = channels = None
        frame_count = 0
        for index in ordered_indices:
            chapter = chapters[index - 1]
            copied_path = stage / f"source-{index:02d}.wav"
            _copy_and_verify_wav(reel / chapter["audio"], copied_path, chapter["audio_sha256"])
            copied_path.chmod(0o600)
            try:
                with wave.open(str(copied_path), "rb") as src:
                    channel_count = src.getnchannels()
                    rate = src.getframerate()
                    frames = src.getnframes()
                    if (src.getcomptype() != "NONE" or src.getsampwidth() != 2
                            or channel_count not in (1, 2) or not 8000 <= rate <= 96000
                            or not 1 <= frames <= MAX_CHAPTER_FRAMES):
                        raise ValueError("Selected chapter is not supported PCM16 WAV")
            except (wave.Error, EOFError) as exc:
                raise ValueError("Selected chapter WAV is invalid") from exc
            if sample_rate is None:
                sample_rate, channels = rate, channel_count
            elif (rate, channel_count) != (sample_rate, channels):
                raise ValueError("Selected chapters have incompatible PCM formats; render same-rate/channels galleries first")
            frame_count += frames
            copied.append(copied_path)
            info.append({
                "original_chapter": index,
                "family": chapter["family"],
                "selected_wav_sha256": chapter["audio_sha256"],
                "source_gallery_receipt_sha256": chapter["source_gallery_receipt_sha256"],
                "human_choice_sha256": chapter["human_choice_sha256"],
                "private_note": chapter["private_note"],
                "frames": frames,
            })
        silent_frames = round(gap_ms * sample_rate / 1000)
        frame_count += (len(copied) - 1) * silent_frames
        if frame_count * channels * 2 + 44 > MAX_TOTAL_OUTPUT_BYTES:
            raise ValueError("Continuous rehearsal WAV exceeds output budget")
        generated = stage / "continuous-rehearsal.wav"
        with wave.open(str(generated), "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(2)
            dst.setframerate(sample_rate)
            for i, path in enumerate(copied):
                with wave.open(str(path), "rb") as src:
                    remaining = src.getnframes()
                    while remaining:
                        frames_to_read = min(4096, remaining)
                        chunk = src.readframes(frames_to_read)
                        if len(chunk) != frames_to_read * channels * 2:
                            raise ValueError("A selected chapter contains fewer PCM samples than its WAV header")
                        dst.writeframesraw(chunk)
                        remaining -= frames_to_read
                if i < len(copied) - 1 and silent_frames:
                    dst.writeframesraw(bytes(silent_frames * channels * 2))
        generated.chmod(0o600)
        output_sha = _sha(generated)
        record = {
            "schema_version": 1, "kind": "mixlab-private-gapped-rehearsal",
            "status": "human-rehearsal-preview-only", "rights_status": "unverified",
            "audio_sha256": output_sha, "original_reel_receipt_sha256": receipt_sha,
            "private_order_sha256": plan_sha, "order_source": "manual-browser-export" if plan_sha else "original",
            "chapters": info, "sample_rate": sample_rate, "channels": channels,
            "frames": frame_count, "gap_ms": gap_ms,
            "duration_seconds": frame_count / sample_rate,
            "pcm_policy": "byte-exact input frames separated by explicit PCM16 silence",
            "seamless_dj_mix": False, "loudness_normalized": False,
            "rights_verified": False, "blind_preference_verified": False,
        }
        prepared_receipt = stage / "private-rehearsal.json"
        write_private_new(prepared_receipt, (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
        # Atomic no-clobber publication of each file; sidecar failure rolls
        # back only our own newly linked WAV.
        os.link(generated, output)
        try:
            os.link(prepared_receipt, sidecar)
        except BaseException:
            output.unlink()
            raise
    return output, sidecar


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a source-verified continuous private rehearsal WAV with explicit gaps"
    )
    parser.add_argument("reel_dir", help="Original offline multi-gallery reel directory")
    parser.add_argument("output_wav", help="New continuous .wav destination (never overwritten)")
    parser.add_argument("--order", help="Optional exact-reel browser-exported running order JSON")
    parser.add_argument("--gap-ms", type=int, default=350,
                        help="Silence between chapters, 0..1000ms (default: 350)")
    args = parser.parse_args(argv)
    try:
        audio, evidence = render_mixdown(
            args.reel_dir, args.output_wav, order_json=args.order, gap_ms=args.gap_ms
        )
        print(f"Continuous rehearsal: {audio}\nPrivate source receipt: {evidence}")
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"MixLab private rehearsal mixdown: {exc}\n")


if __name__ == "__main__":
    main()
