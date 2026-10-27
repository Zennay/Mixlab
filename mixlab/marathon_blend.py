"""Human-approved, bounded PCM16 crossfades at *completed-event* boundaries.

This independent post-production route works on a verified Event Marathon,
not the shared ML-04 transition engine. No BPM, key, phrase or source-rights
inference is performed. It does not silently replace the original master.
"""
from __future__ import annotations

import argparse
from array import array
import json
import os
from pathlib import Path
import stat
import sys
import wave
import zipfile
import subprocess

from .event_marathon import (_PAGE, _digest_file, _meta_key, _new_folder,
                             BLOCK_FRAMES, MAX_BYTES, MAX_HTML)
from .event_vault import _marathon_duration, _read_small_json

CHOICES = (2, 4, 8, 16)
CROSSFADE_BLOCK = 8192


def _blend_frames(a_bytes, b_bytes, initial, fade_frames):
    """Bounded complement-gain stereo transition; neither channel sums > 1."""
    a = array("h")
    b = array("h")
    a.frombytes(a_bytes)
    b.frombytes(b_bytes)
    if sys.byteorder != "little":
        a.byteswap()
        b.byteswap()
    if len(a) != len(b) or len(a) % 2:
        raise ValueError("PCM16 stereo overlap became inconsistent")
    combined = array("h")
    last = fade_frames - 1
    for frame in range(len(a) // 2):
        outgoing = last - initial - frame
        incoming = initial + frame
        for channel in (0, 1):
            index = frame * 2 + channel
            value = round((a[index] * outgoing + b[index] * incoming) / last)
            combined.append(max(-32768, min(32767, value)))
    if sys.byteorder != "little":
        combined.byteswap()
    return combined.tobytes()


def _copy_exact(reader, writer, start_frame, frames):
    reader.setpos(start_frame)
    remaining = frames
    while remaining:
        count = min(remaining, BLOCK_FRAMES)
        data = reader.readframes(count)
        if len(data) != count * 4:
            raise ValueError("The approved original master was truncated")
        writer.writeframesraw(data)
        remaining -= count


def _overlap(reader, writer, last_frame_start, next_frame_start, fade_frames):
    offset = 0
    while offset < fade_frames:
        count = min(CROSSFADE_BLOCK, fade_frames - offset)
        reader.setpos(last_frame_start + offset)
        tail = reader.readframes(count)
        reader.setpos(next_frame_start + offset)
        head = reader.readframes(count)
        if len(tail) != count * 4 or len(head) != count * 4:
            raise ValueError("A joined WAV transition source changed or was truncated")
        writer.writeframesraw(_blend_frames(tail, head, offset, fade_frames))
        offset += count


def publish_blended_marathon(approved_marathon_wav, new_private_folder, *,
                             fade_seconds=8, join_fades=None, join_plan=None, start=None, bundle=False,
                             delivery=None, bitrate_kbps=192,
                             read=input, write=print):
    """Create a new continuous WAV with actual manually chosen crossfades.

    Input is an ORIGINAL, SHA-verified sample-preserving Marathon. Every
    frame range comes from the original exact output receipt. The new WAV
    is deliberately a separately published derivative, never a mutation.
    """
    if type(fade_seconds) is not int or fade_seconds not in CHOICES:
        raise ValueError("Choose exactly 2, 4, 8 or 16 seconds of crossfade")
    if (join_plan is not None and (join_fades is not None or fade_seconds != 8)):
        raise ValueError("Choose manual fades OR an original-SHA-bound Join Studio plan, not both")
    if join_fades is not None and fade_seconds != 8:
        raise ValueError("Choose a common fade OR a per-boundary sequence, not both")
    if type(bundle) is not bool:
        raise ValueError("Portable bundle option must be boolean")
    if delivery not in (None, "mp3", "flac") or type(bitrate_kbps) is not int or bitrate_kbps not in (128,192,256,320):
        raise ValueError("Choose optional private MP3/FLAC and allowed bitrate")
    original = Path(approved_marathon_wav).absolute()
    if original.name != "marathon.wav" or original.is_symlink():
        raise ValueError("Choose the original exact Marathon WAV")
    original_duration, count, evidence = _marathon_duration(original.parent, original)
    source_receipt = _read_small_json(original.parent / "marathon.receipt.private.json")
    if (evidence != "marathon" or source_receipt.get("kind") !=
            "mixlab-private-continuous-event-v1" or count < 2):
        raise ValueError("Only original sample-preserving Marathon receipts may be blended")

    rate = source_receipt["rate"]
    original_sections = source_receipt["sections"]
    if join_plan is not None:
        from .event_vault import _read_small_json
        plan_path = Path(join_plan).absolute()
        if plan_path.suffix.lower() != ".json" or plan_path.is_symlink():
            raise ValueError("Choose an actual local private Join Studio JSON plan")
        for ancestor in plan_path.parents:
            if ancestor.is_symlink():
                raise ValueError("Private render plan must not use a symlinked directory")
        plan = _read_small_json(plan_path)
        if (not isinstance(plan, dict) or plan.get("schema_version") != 1 or
                plan.get("kind") != "mixlab-private-manual-join-plan-v1" or
                plan.get("original_wav_sha256") != source_receipt["wav_sha256"] or
                plan.get("original_frames") != source_receipt["frames"] or
                plan.get("rate") != rate or
                plan.get("source_event_sha256s") !=
                [section["source_sha256"] for section in original_sections] or
                plan.get("private_only") is not True):
            raise ValueError("Join plan belongs to a different completed Marathon master")
        join_fades = plan.get("fade_seconds_by_join")
    if join_fades is None:
        seconds_by_join = (fade_seconds,) * (count - 1)
    else:
        if (not isinstance(join_fades, (list, tuple)) or
                len(join_fades) != count - 1 or
                any(type(v) is not int or v not in (0, *CHOICES) for v in join_fades)):
            raise ValueError("Choose 0s hard join or 2, 4, 8 or 16-second fade per event boundary")
        seconds_by_join = tuple(join_fades)
    overlaps = tuple(seconds * rate for seconds in seconds_by_join)
    for i, section in enumerate(original_sections):
        incoming = overlaps[i - 1] if i else 0
        outgoing = overlaps[i] if i + 1 < count else 0
        if section["frames"] <= incoming + outgoing:
            raise ValueError("An approved set is too short for its selected adjacent fades")
    frames = source_receipt["frames"] - sum(overlaps)
    if frames <= 0 or frames * 4 > MAX_BYTES:
        raise ValueError("The private blended WAV exceeds its bounded duration or size")
    if start is not None:
        from .marathon_showbook import CLOCK
        if not isinstance(start, str) or not CLOCK.fullmatch(start):
            raise ValueError("Planned local start must be HH:MM")
    dest = _new_folder(new_private_folder, [original.parent])
    write("MixLab private transition editing: ORIGINAL approved continuous WAV only.")
    for i, seconds in enumerate(seconds_by_join):
        write(f"  Join {i + 1}: {original_sections[i]['label']} -> {original_sections[i+1]['label']}: {seconds} seconds")
    write("Each join uses a real, bounded gain-complementary PCM16 crossfade.")
    write("No BPM, pitch, phrase, harmonic, loudness or sound-quality certification.")
    write("The separate new WAV still needs a real listening review and appropriate rights.")
    if read("Type yes to render this exact private version: ").strip() != "yes":
        raise ValueError("Explicit approval to make a new private blended WAV was not given")

    dest.mkdir(mode=0o700)
    wav_path = dest / "marathon.wav"
    receipt_path = dest / "marathon.receipt.private.json"
    player_path = dest / "index.html"
    created = []
    try:
        sections = []
        for i, section in enumerate(original_sections):
            sections.append({
                "index": i + 1,
                "label": section["label"],
                "source_sha256": section["source_sha256"],
                "start_frame": section["start_frame"] - sum(overlaps[:i]),
                "frames": section["frames"],
                "start_seconds": round((section["start_frame"] - sum(overlaps[:i])) / rate, 5),
            })
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(original, flags)
        with os.fdopen(fd, "rb") as stream:
            stamp = _meta_key(os.fstat(stream.fileno()))
            with wave.open(stream, "rb") as src:
                if (src.getframerate() != rate or src.getnframes() != source_receipt["frames"] or
                        src.getnchannels() != 2 or src.getsampwidth() != 2 or
                        src.getcomptype() != "NONE"):
                    raise ValueError("Original WAV format has changed")
                with wav_path.open("xb") as output:
                    created.append(wav_path)
                    os.fchmod(output.fileno(), 0o600)
                    with wave.open(output, "wb") as writer:
                        writer.setnchannels(2)
                        writer.setsampwidth(2)
                        writer.setframerate(rate)
                        writer.setnframes(frames)
                        for i, section in enumerate(original_sections):
                            incoming = overlaps[i - 1] if i else 0
                            outgoing = overlaps[i] if i + 1 < count else 0
                            from_frame = section["start_frame"] + incoming
                            to_frame = section["start_frame"] + section["frames"] - outgoing
                            _copy_exact(src, writer, from_frame, to_frame - from_frame)
                            if i + 1 < count and outgoing:
                                _overlap(src, writer, to_frame,
                                         original_sections[i + 1]["start_frame"], outgoing)
            if stamp != _meta_key(os.fstat(stream.fileno())):
                raise ValueError("Source WAV changed during private transition render")
        # Re-read the immutable original after processing so the admitted
        # source receipt cannot be swapped between validation and rendering.
        if _digest_file(original) != source_receipt["wav_sha256"]:
            raise ValueError("Source WAV no longer matches its original SHA-bound receipt")
        digest = _digest_file(wav_path)
        payload = {
            "schema_version": 1,
            "kind": "mixlab-private-blended-event-v1",
            "wav_name": wav_path.name,
            "wav_sha256": digest,
            "source_marathon_sha256": source_receipt["wav_sha256"],
            "rate": rate,
            "channels": 2,
            "sample_width_bytes": 2,
            "frames": frames,
            "duration_seconds": frames / rate,
            "sections": sections,
            "overlap_frames_by_join": list(overlaps),
            "fade_seconds_by_join": list(seconds_by_join),
            "transition_curve": "complementary-linear-pcm16-v1",
            "no_automatic_tempo_matching": True,
            "sample_preserving_joins": False,
            "private_local_use_only": True,
            "automatic_licensing": False,
            "musical_preference_proven": False,
        }
        with receipt_path.open("xb") as target:
            created.append(receipt_path)
            os.fchmod(target.fileno(), 0o600)
            target.write((json.dumps(payload, sort_keys=True, indent=2,
                                     allow_nan=False) + "\n").encode("utf-8"))

        showbook = None
        warning = None
        try:
            from .marathon_showbook import create_runbook
            showbook = create_runbook(wav_path, dest / "marathon.runbook.private.html", start=start)
            created.append(showbook)
        except (ValueError, TypeError, KeyError, OSError):
            warning = "The real blended WAV exists; optional showbook was not published"
        viewer = {
            "wav_name": wav_path.name,
            "wav_sha256": digest,
            "showbook": showbook.name if showbook else None,
            "duration_seconds": frames / rate,
            "sections": [{"label": section["label"], "start_seconds": section["start_seconds"],
                          "fade_in_seconds": seconds_by_join[i - 1] if i else 0}
                         for i, section in enumerate(sections)],
        }
        blob = json.dumps(viewer, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        page = (_PAGE.replace(
            "A gapless assembly of real, independently completed private MixLab sets. No artificial remix, automatic harmonic matching, tempo shift or re-encoding.",
            "Your actual edited private WAV: bounded, manually approved complementary-gain crossfades between already completed sets. No automatic beatmatch, pitch or key analysis.")
            .replace(
                "Each joint is an intentional, sample-exact boundary between completed sets. This is not a DJ-quality transition or evidence of listening preference.",
                "Each new set starts at a real short crossfade in this independently rendered PCM16 WAV. Audition every join yourself; no musical quality or listener preference is proven.")
            .replace('button.textContent=String(i+1)+". "+section.label;',
                      'button.textContent=String(i+1)+". "+section.label+(section.fade_in_seconds?" · "+section.fade_in_seconds+"s fade-in":"");')
            .replace("__DATA__", blob)).encode("utf-8")
        if len(page) > MAX_HTML:
            raise ValueError("Private blended event page exceeds the output budget")
        with player_path.open("xb") as target:
            created.append(player_path)
            os.fchmod(target.fileno(), 0o600)
            target.write(page)
    except Exception:
        for item in reversed(created):
            item.unlink(missing_ok=True)
        dest.rmdir()
        raise

    result = {
        "private_event_folder": str(dest),
        "continuous_wav": str(wav_path),
        "private_receipt": str(receipt_path),
        "private_player": str(player_path),
        "private_show_runbook": str(showbook) if showbook else None,
        "source_marathon_sha256": source_receipt["wav_sha256"],
        "wav_sha256": digest,
        "joined_events": count,
        "fade_seconds_by_join": list(seconds_by_join),
        "duration_seconds": frames / rate,
        "offline": True,
        "new_audio_rendered": True,
        "automatic_tempo_matching": False,
        "musical_preference_proven": False,
    }
    if warning:
        result["showbook_warning"] = warning
    if delivery:
        try:
            from .marathon_delivery import export_mobile_marathon
            result["mobile_delivery"] = export_mobile_marathon(
                wav_path, dest / ("marathon." + delivery), bitrate_kbps=bitrate_kbps)
        except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
            result["mobile_warning"] = "Actual blended WAV exists; optional portable encoding unavailable"
    if bundle:
        try:
            from .marathon_bundle import export_marathon_bundle
            result["private_bundle"] = export_marathon_bundle(
                wav_path, dest / "marathon.private.zip")
        except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile):
            result["bundle_warning"] = "Blended WAV exists; optional private ZIP was not published"
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Render explicit hard joins or manual 2–16s crossfades from verified original event sets")
    parser.add_argument("original_marathon_wav")
    parser.add_argument("new_private_folder")
    fades = parser.add_mutually_exclusive_group()
    fades.add_argument("--fade-seconds", type=int, choices=CHOICES, default=8,
                       help="One duration used at every event boundary")
    fades.add_argument("--join-fades", help="Comma-separated 0 (hard cut) or 2/4/8/16s for EACH join, e.g. 0,4,8")
    fades.add_argument("--join-plan", help="Original SHA-locked private JSON exported by Join Studio")
    parser.add_argument("--start", help="Optional local show start HH:MM")
    parser.add_argument("--bundle", action="store_true", help="Also create optional private USB ZIP")
    parser.add_argument("--delivery",choices=("mp3","flac"),help="Optional private mobile audio copy")
    parser.add_argument("--bitrate-kbps",type=int,choices=(128,192,256,320),default=192)
    args = parser.parse_args()
    try:
        per_join = tuple(int(item.strip()) for item in args.join_fades.split(",")) if args.join_fades is not None else None
        result = publish_blended_marathon(args.original_marathon_wav, args.new_private_folder,
                                         fade_seconds=args.fade_seconds, join_fades=per_join, join_plan=args.join_plan,
                                         start=args.start, bundle=args.bundle,
                                         delivery=args.delivery, bitrate_kbps=args.bitrate_kbps)
    except (ValueError, KeyError, TypeError, OSError, EOFError, KeyboardInterrupt, wave.Error):
        parser.exit(2, "MixLab blend: source or explicit approval failed; no blended output was published.\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
