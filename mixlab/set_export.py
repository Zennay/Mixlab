"""Build a complete offline WAV set from manually approved MixLab Studio pairs.

No automatic beatmatching, mixing-rights inference, online service or uploads.
Selected transition WAVs are reused exactly; solo sections use the same
-6 dB common gain as the existing four-family Studio renderer.
"""
from __future__ import annotations

from array import array
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import wave

from .cueprep import _inspect_source, _read_spec, _source_path
from .ingest import MAX_FRAMES, RIGHTS, digest, pcm_blocks
from .studio import FAMILY_NAMES, _open_receipt

MAX_SET_BYTES = 512 * 1024 * 1024
MAX_PAIRS = 10
BLOCK_FRAMES = 4096
STUDIO_GAIN = 10 ** (-6.0 / 20.0)


def _unique_pairs(values):
    if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= MAX_PAIRS:
        raise ValueError("Select 1..10 manually approved transition pairs")
    result, seen = [], set()
    for value in values:
        if not isinstance(value, str) or value.count(":") != 1:
            raise ValueError("Use --transition PAIR_ID:FAMILY for each transition")
        pid, family = value.split(":")
        if not pid or len(pid) > 80 or not all(c.isalnum() or c in "._-" for c in pid):
            raise ValueError("Invalid pair ID")
        if family not in FAMILY_NAMES or pid in seen:
            raise ValueError("Unknown family or repeated transition pair")
        seen.add(pid)
        result.append((pid, family))
    return result


def _valid_destination(target, source_root):
    output = Path(target).absolute()
    if output.suffix.lower() != ".wav" or output.exists() or output.is_symlink():
        raise ValueError("Choose a new, not-yet-existing .wav output")
    if not output.parent.is_dir() or output.is_relative_to(source_root):
        raise ValueError("Export to an existing private parent outside the session")
    for ancestor in (output, *output.parents):
        if ancestor.is_symlink() or (ancestor / ".git").exists():
            raise ValueError("No symlink destination or audio export inside Git")
    receipt = output.with_name(output.name + ".receipt.private.json")
    if receipt.exists() or receipt.is_symlink():
        raise ValueError("Destination private receipt already exists")
    return output, receipt


def _track_catalog(root, declared):
    result = {}
    if not isinstance(declared, list) or not 2 <= len(declared) <= 20:
        raise ValueError("Invalid normalized track catalog")
    for track in declared:
        if not isinstance(track, dict) or not isinstance(track.get("id"), str):
            raise ValueError("Invalid normalized track")
        ident = track["id"]
        if ident in result or len(ident) > 80 or not all(c.isalnum() or c in "._-" for c in ident):
            raise ValueError("Duplicate or unsafe track ID")
        if track.get("rights") not in RIGHTS or not isinstance(track.get("provenance"), str) or not track["provenance"].strip():
            raise ValueError("Explicit rights declaration and provenance required")
        path = _source_path(root, track.get("path"))
        info = _inspect_source(path, track.get("sha256"))
        result[ident] = {"path": path, "info": info, "sha256": track["sha256"]}
    return result


def _admit(root, choices):
    # These are existing private sources from mixlab.session; never repair or
    # update their data during compilation.
    source_manifest = root / "sources" / "source_manifest.json"
    excerpt_manifest = root / "excerpts" / "library.json"
    studio_dir = root / "studio"
    session_receipt = _read_spec(root / "session-receipt.private.json")
    if session_receipt.get("kind") != "offline-manual-transition-session":
        raise ValueError("Expected a completed one-command private session")
    if session_receipt.get("studio_receipt_sha256") != digest(studio_dir / "studio-receipt.private.json"):
        raise ValueError("Studio receipt no longer matches the private session")
    if session_receipt.get("prepared_manifest_sha256") != digest(excerpt_manifest):
        raise ValueError("Prepared cues changed after session rendering")
    studio = _open_receipt(studio_dir)
    if studio.get("manifest_sha256") != digest(excerpt_manifest):
        raise ValueError("Studio does not match the prepared pair manifest")
    spec = _read_spec(source_manifest)
    tracks = _track_catalog(source_manifest.parent, spec.get("tracks"))
    raw_pairs = spec.get("pairs")
    if not isinstance(raw_pairs, list) or not 1 <= len(raw_pairs) <= MAX_PAIRS:
        raise ValueError("Invalid pair catalog")
    pair_map = {}
    for pair in raw_pairs:
        if not isinstance(pair, dict) or not isinstance(pair.get("id"), str) or pair["id"] in pair_map:
            raise ValueError("Invalid or duplicate pair")
        pair_map[pair["id"]] = pair

    records = studio.get("renders")
    if not isinstance(records, list) or len(records) > MAX_PAIRS * len(FAMILY_NAMES):
        raise ValueError("Invalid studio renders")
    selected, previous_b = [], None
    format_reference = None
    for pid, family in choices:
        pair = pair_map.get(pid)
        if not pair or pair.get("a") not in tracks or pair.get("b") not in tracks:
            raise ValueError("Chosen pair is not present in imported songs")
        if pair["a"] == pair["b"] or (previous_b is not None and pair["a"] != previous_b):
            raise ValueError("Pair order must form one continuous outgoing->incoming track route")
        previous_b = pair["b"]
        a, b = tracks[pair["a"]], tracks[pair["b"]]
        rate, channels = a["info"]["rate"], a["info"]["channels"]
        if (rate, channels) != (b["info"]["rate"], b["info"]["channels"]):
            raise ValueError("Source tracks have incompatible PCM formats")
        if format_reference is None:
            format_reference = rate, channels
        elif format_reference != (rate, channels):
            raise ValueError("A continuous set requires one common PCM format")
        bpm = pair.get("bpm")
        beats = pair.get("beats", 8)
        if (type(bpm) not in (float, int) or not math.isfinite(bpm) or not 30 <= bpm <= 300
                or type(beats) is not int or not 1 <= beats <= 64):
            raise ValueError("Invalid manually verified BPM/transition duration")
        frames = round(beats * 60.0 / bpm * rate)
        if not 2 <= frames <= MAX_FRAMES:
            raise ValueError("Transition length exceeds source renderer budget")
        offsets = []
        for side, track in (("a", a), ("b", b)):
            second = pair.get(side + "_start_seconds")
            if type(second) not in (int, float) or not math.isfinite(second) or second < 0:
                raise ValueError("Manual cue start missing or invalid")
            start = round(second * rate)
            if start + frames > track["info"]["frames"]:
                raise ValueError("Transition cue extends beyond a normalized song")
            offsets.append(start)
        matches = [x for x in records if isinstance(x, dict)
                   and x.get("pair") == pid and x.get("family") == family]
        if len(matches) != 1:
            raise ValueError("Chosen transition was not uniquely rendered by Studio")
        record = matches[0]
        relative = f"auditions/{pid}/{family}.wav"
        if record.get("relative_path") != relative:
            raise ValueError("Unexpected transition location")
        render_path = studio_dir / relative
        if render_path.is_symlink() or not render_path.resolve(strict=True).is_relative_to(studio_dir):
            raise ValueError("Rendered transition was redirected")
        if record.get("sha256") != digest(render_path):
            raise ValueError("Rendered transition hash changed")
        transition_info = _inspect_source(render_path, record["sha256"])
        if (transition_info["rate"], transition_info["channels"], transition_info["frames"]) != (rate, channels, frames):
            raise ValueError("Rendered transition does not match manually approved timing")
        selected.append({"pair": pid, "family": family, "a": pair["a"], "b": pair["b"],
                         "start_a": offsets[0], "start_b": offsets[1], "frames": frames,
                         "render": render_path, "render_sha256": record["sha256"]})

    portions = []
    for index, item in enumerate(selected):
        begin = 0 if index == 0 else selected[index - 1]["start_b"] + selected[index - 1]["frames"]
        end = item["start_a"]
        if end < begin:
            raise ValueError("Manual cuepoints overlap/backtrack; cannot build continuous set")
        portions.append(("solo", item["a"], begin, end - begin))
        portions.append(("transition", item["pair"], 0, item["frames"]))
    last = selected[-1]
    remaining = tracks[last["b"]]["info"]["frames"] - (last["start_b"] + last["frames"])
    if remaining < 0:
        raise ValueError("Final track is shorter than its transition")
    portions.append(("solo", last["b"], last["start_b"] + last["frames"], remaining))
    total = sum(row[3] for row in portions)
    rate, channels = format_reference
    if not 2 <= total or 44 + total * channels * 2 > MAX_SET_BYTES:
        raise ValueError("Set exceeds 512 MiB PCM16 output budget")
    return {"sources": tracks, "selected": selected, "portions": portions, "frames": total,
            "rate": rate, "channels": channels, "session_hash": digest(root / "session-receipt.private.json"),
            "studio_hash": digest(studio_dir / "studio-receipt.private.json")}


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _write_solo(out, path, start, frames, channels, rate):
    """Stream potentially multi-minute tracks via one verified regular FD.

    Canonical pcm_blocks deliberately limits *entire* WAVs to 2M frames, so
    it is only appropriate for the short Studio transition candidates.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Full track is no longer a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or _identity(before) != _identity(opened):
            raise ValueError("Track changed before reading")
        try:
            with wave.open(handle, "rb") as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate(),
                    source.getcomptype()) != (channels, 2, rate, "NONE"):
                    raise ValueError("Track format changed after manifest verification")
                if start < 0 or frames < 0 or start + frames > source.getnframes():
                    raise ValueError("Manually approved solo section is out of bounds")
                source.setpos(start)
                remaining = frames
                while remaining:
                    n = min(remaining, BLOCK_FRAMES)
                    raw = source.readframes(n)
                    if len(raw) != n * channels * 2:
                        raise ValueError("Full track ended before its selected cue")
                    samples = array("h")
                    samples.frombytes(raw)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    scaled = array("h", (round(int(x) * STUDIO_GAIN) for x in samples))
                    if sys.byteorder != "little":
                        scaled.byteswap()
                    out.writeframesraw(scaled.tobytes())
                    remaining -= n
        except (EOFError, wave.Error) as exc:
            raise ValueError("Invalid PCM16 solo section") from exc
        after = os.fstat(handle.fileno())
    if _identity(opened) != _identity(after) or _identity(opened) != _identity(path.lstat()):
        raise ValueError("Normalized full track changed during export")


def _write_transition(out, path, frames, channels):
    """Reuse the exact existing Studio candidate without applying gain twice."""
    for block in pcm_blocks(path, 0, frames, BLOCK_FRAMES):
        if len(block) % channels:
            raise ValueError("Incomplete transition PCM frame")
        if sys.byteorder != "little":
            block.byteswap()
        out.writeframesraw(block.tobytes())

def export_set(session_dir, destination, selections):
    root = Path(session_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Session must be a private directory")
    selected = _unique_pairs(selections)
    target, receipt_path = _valid_destination(destination, root)
    plan = _admit(root, selected)
    by_pair = {x["pair"]: x for x in plan["selected"]}
    fd, tmp_name = tempfile.mkstemp(prefix=".mixlab-set-", suffix=".wav", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    published = False
    try:
        with wave.open(str(tmp), "wb") as out:
            out.setparams((plan["channels"], 2, plan["rate"], plan["frames"], "NONE", "not compressed"))
            for kind, identity, start, frames in plan["portions"]:
                path = plan["sources"][identity]["path"] if kind == "solo" else by_pair[identity]["render"]
                if kind == "solo":
                    _write_solo(out, path, start, frames, plan["channels"], plan["rate"])
                else:
                    _write_transition(out, path, frames, plan["channels"])
        if tmp.stat().st_size != 44 + plan["frames"] * plan["channels"] * 2:
            raise ValueError("Final PCM output frame count differs from planned set")
        for track in plan["sources"].values():
            if digest(track["path"]) != track["sha256"]:
                raise ValueError("A normalized source changed during export")
        for record in plan["selected"]:
            if digest(record["render"]) != record["render_sha256"]:
                raise ValueError("A chosen transition changed during export")
        final_hash = digest(tmp)
        receipt = {"schema_version": 1, "kind": "private-continuous-manual-set",
                   "source_session_sha256": plan["session_hash"],
                   "studio_receipt_sha256": plan["studio_hash"],
                   "format": "PCM16-WAV", "sample_rate": plan["rate"],
                   "channels": plan["channels"], "frames": plan["frames"],
                   "duration_seconds": plan["frames"] / plan["rate"],
                   "common_gain_db": -6, "source_separation": False,
                   "automatic_beatmatching": False,
                   "selected_transitions": [{"pair": x["pair"], "family": x["family"],
                                             "render_sha256": x["render_sha256"]}
                                            for x in plan["selected"]],
                   "output_sha256": final_hash,
                   "warnings": ["private rights-permitted audio only",
                                "manual verified cuepoints and matching BPM required",
                                "creative playback is not blind preference proof"]}
        os.link(tmp, target)  # Atomic, exclusive complete-file publication.
        published = True
        raw = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
        with receipt_path.open("x", encoding="utf-8") as private:
            os.fchmod(private.fileno(), 0o600)
            private.write(raw)
        return target
    except BaseException:
        if published:
            target.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise
    finally:
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Export a private continuous MixLab set from manually aligned Studio tracks")
    parser.add_argument("session", help="Existing successful private mixlab.session output directory")
    parser.add_argument("output", help="New private .wav output path outside session and Git")
    parser.add_argument("--transition", action="append", required=True, metavar="PAIR:FAMILY",
                        help="Ordered transition choice, repeat for a continuous route (max 10)")
    args = parser.parse_args()
    try:
        exported = export_set(args.session, args.output, args.transition)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"MixLab continuous set: {exc}\n")
    print(json.dumps({"continuous_set": str(exported),
                      "receipt": str(exported) + ".receipt.private.json",
                      "mode": "private-manual-creative",
                      "automatic_beatmatching": False,
                      "musical_quality_claim": False}))


if __name__ == "__main__":
    main()
