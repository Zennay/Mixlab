"""Private, deterministic manual-metadata energy-journey suggestions for MixLab.

A planning aid, not automatic BPM/key/phrase detection or preference proof.
No audio decoding, networking or source modifications. Plans are SHA-pinned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .media_import import _fingerprint, _regular_source
from .project_wizard import (
    _ask, _float_between, _media_listing, _selection,
)

LIMIT = 1024 * 1024
MAX_CANDIDATES = 20
MAX_SET = 11
BEAM = 192
NOTE_KIND = "mixlab-private-energy-notes-v1"
PLAN_KIND = "mixlab-private-energy-plan-v1"
SHAPES = ("build", "peak", "late-peak", "release")


def _source_root(folder):
    root = Path(folder).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Private music folder must be an existing non-symlink directory")
    root = root.resolve(strict=True)
    if any((p / ".git").exists() for p in (root, *root.parents)):
        raise ValueError("Keep local music and planning data outside Git")
    return root


def _private_json_path(root, location, *, existing):
    path = Path(location).absolute()
    if path.parent != root or path.suffix.lower() != ".json" or path.is_symlink():
        raise ValueError("Private JSON must be a non-symlink file directly in the music folder")
    if existing:
        if not path.is_file():
            raise ValueError("Private JSON input is missing")
    elif path.exists():
        raise ValueError("Refusing to overwrite existing private JSON")
    return path


def _no_duplicates(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ValueError("Duplicate private JSON property")
        obj[key] = value
    return obj


def _read_json(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Private JSON is unavailable") from exc
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= LIMIT:
            raise ValueError("Private JSON must be a bounded regular file")
        raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT or os.fstat(stream.fileno()).st_size != meta.st_size:
            raise ValueError("Private JSON changed during read")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite number")))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid private planning JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Private planning JSON must be an object")
    return parsed, hashlib.sha256(raw).hexdigest()


def _write_json(path, data):
    raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > LIMIT:
        raise ValueError("Private planning JSON exceeds 1 MiB")
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
    return path


def _tags(raw):
    if not raw.strip():
        return []
    result = [value.strip().lower() for value in raw.split(",")]
    if (len(result) > 6 or len(result) != len(set(result)) or
            any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,23}", value) for value in result)):
        raise ValueError("Up to six unique comma-separated ASCII genre/mood tags")
    return result


def capture_notes(music_folder, new_notes, *, read=input, write=print):
    """Prompt for verifiable human BPM, subjective energy and mood notes."""
    root = _source_root(music_folder)
    target = _private_json_path(root, new_notes, existing=False)
    files = _media_listing(root)
    write("MixLab journey notes: annotate 2..20 permitted LOCAL sources.")
    write("No inferred tempo or music analysis. Verify BPM yourself; energy is subjective (1..10).")
    for number, name in enumerate(files, 1):
        write(f"{number:>3}. {name}")
    numbers = _ask(read, write, "Song numbers to consider (2..20, comma-separated): ",
                   _selection(len(files)))
    if len(numbers) > MAX_CANDIDATES:
        raise ValueError("At most 20 candidates")
    records = []
    for number in numbers:
        name = files[number - 1]
        write(f"Manual notes for {name}")
        bpm = _ask(read, write, "Verified BPM (30..300): ", _float_between(30, 300))
        energy = _ask(read, write, "Subjective energy (1..10): ", _float_between(1, 10))
        tags = _ask(read, write, "Optional genre/mood tags (comma-separated): ", _tags)
        sha, _ = _fingerprint(_regular_source(root, name))
        records.append({"path": name, "sha256": sha, "bpm": bpm, "energy": energy,
                        "tags": tags, "source": "human-annotation"})
    _write_json(target, {"kind": NOTE_KIND, "tracks": records})
    write("Saved local, SHA-pinned human track notes (private, chmod 0600).")
    return target


def _records(root, items):
    if not isinstance(items, list) or not 2 <= len(items) <= MAX_CANDIDATES:
        raise ValueError("Need 2..20 annotated source records")
    seen = set()
    records = []
    for row in items:
        if not isinstance(row, dict):
            raise ValueError("Invalid track annotation")
        name, sha = row.get("path"), row.get("sha256")
        bpm, energy, tags = row.get("bpm"), row.get("energy"), row.get("tags")
        if (not isinstance(name, str) or not name or name in seen or
                not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha) or
                type(bpm) not in (float, int) or not math.isfinite(bpm) or not 30 <= bpm <= 300 or
                type(energy) not in (float, int) or not math.isfinite(energy) or not 1 <= energy <= 10 or
                not isinstance(tags, list) or not all(isinstance(t, str) for t in tags) or
                _tags(",".join(tags)) != tags):
            raise ValueError("Invalid or duplicate manual track annotation")
        seen.add(name)
        _fingerprint(_regular_source(root, name), expected=sha)
        records.append({"path": name, "sha256": sha, "bpm": bpm,
                        "energy": energy, "tags": tags})
    return records


def _targets(shape, count):
    if shape not in SHAPES or not 2 <= count <= MAX_SET:
        raise ValueError("Unsupported journey shape or song count")
    result = []
    for index in range(count):
        t = index / (count - 1)
        if shape == "build":
            value = 2 + 7 * t
        elif shape == "release":
            value = 9 - 7 * t
        elif shape == "peak":
            value = 2 + 7 * (1 - abs(2 * t - 1))
        else:  # late-peak: sustained ascent followed by a measured closing release
            value = 2 + 7 * min(1, t / .8) - 2 * max(0, (t - .8) / .2)
        result.append(round(value, 3))
    return result


def _choose(records, count, shape, prefer_tag=None, tempo=None,
            opening=None, closing=None, excluded=()):
    targets = _targets(shape, count)
    known = {row["path"] for row in records}
    if not isinstance(excluded, (list, tuple)) or len(excluded) > MAX_CANDIDATES:
        raise ValueError("Invalid excluded-track list")
    if (any(not isinstance(name, str) or name not in known for name in excluded)
            or len(excluded) != len(set(excluded))
            or (opening is not None and opening not in known)
            or (closing is not None and closing not in known)
            or (opening is not None and opening == closing)
            or opening in excluded or closing in excluded):
        raise ValueError("Opening/closing/excluded songs must be distinct annotated local filenames")
    groups = {}
    for row in records:
        if row["path"] not in excluded and (tempo is None or row["bpm"] == tempo):
            groups.setdefault(row["bpm"], []).append(row)
    best = None
    for bpm, group in sorted(groups.items()):
        if (len(group) < count or
                (opening is not None and not any(row["path"] == opening for row in group)) or
                (closing is not None and not any(row["path"] == closing for row in group))):
            continue
        group.sort(key=lambda row: row["path"].casefold())
        states = [(0., (), 0)]  # score, ordered indexes, selection bit mask
        for position, target in enumerate(targets):
            expanded = []
            for score, sequence, mask in states:
                for idx, row in enumerate(group):
                    if mask & (1 << idx):
                        continue
                    if ((position == 0 and opening is not None and row["path"] != opening) or
                            (position > 0 and row["path"] == opening) or
                            (position == count - 1 and closing is not None and row["path"] != closing) or
                            (position < count - 1 and row["path"] == closing)):
                        continue
                    deviation = 1.5 * (row["energy"] - target) ** 2
                    pace = 0.
                    if sequence:
                        delta = abs(row["energy"] - group[sequence[-1]]["energy"])
                        pace = 0.65 * max(0., delta - 2.) ** 2
                    preference = -0.25 if prefer_tag and prefer_tag in row["tags"] else 0.
                    expanded.append((score + deviation + pace + preference,
                                     sequence + (idx,), mask | (1 << idx)))
            expanded.sort(key=lambda item: (round(item[0], 9),
                            tuple(group[i]["path"].casefold() for i in item[1])))
            states = expanded[:BEAM]
        if not states:
            continue
        score, sequence, _ = states[0]
        pick = [group[i] for i in sequence]
        candidate = (round(score, 6), tuple(r["path"].casefold() for r in pick), bpm, pick)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        raise ValueError("No same-BPM group has enough annotated tracks; tempo matching is not automatic")
    return best[2], best[3], targets, best[0]


def plan_journey(music_folder, notes, new_plan, *, tracks=5, shape="build",
                 tempo=None, prefer_tag=None, opening=None, closing=None, excluded=()):
    """Produce a private, pinned and inspectable suggestion; never render."""
    root = _source_root(music_folder)
    source = _private_json_path(root, notes, existing=True)
    target = _private_json_path(root, new_plan, existing=False)
    if source == target:
        raise ValueError("Plan destination must be different from notes")
    data, notes_sha = _read_json(source)
    if data.get("kind") != NOTE_KIND:
        raise ValueError("Expected human energy notes, not an arbitrary manifest")
    records = _records(root, data.get("tracks"))
    if type(tracks) is not int or not 2 <= tracks <= MAX_SET:
        raise ValueError("Select 2..11 tracks")
    if tempo is not None and (type(tempo) not in (float, int) or not math.isfinite(tempo)
                              or not 30 <= tempo <= 300):
        raise ValueError("Invalid manual BPM filter")
    if prefer_tag is not None and _tags(prefer_tag) != [prefer_tag]:
        raise ValueError("Use one lowercase genre/mood tag")
    bpm, chosen, targets, score = _choose(records, tracks, shape,
                                         prefer_tag=prefer_tag, tempo=tempo,
                                         opening=opening, closing=closing, excluded=excluded)
    data = {"kind": PLAN_KIND, "shape": shape, "source_notes_sha256": notes_sha,
            "bpm": bpm, "preference_proven": False, "automatic_tempo_matching": False,
            "selection_method": "bounded-human-metadata-heuristic-v1",
            "objective_cost": score,
            "requested_opening": opening, "requested_closing": closing,
            "excluded_tracks": list(excluded),
            "entries": [{**row, "target_energy": targets[i]} for i, row in enumerate(chosen)]}
    return _write_json(target, data)


def load_journey(music_folder, private_plan):
    """Recheck every chosen local recording before Playlist Studio can use it."""
    root = _source_root(music_folder)
    source = _private_json_path(root, private_plan, existing=True)
    data, _ = _read_json(source)
    entries = data.get("entries")
    if (data.get("kind") != PLAN_KIND or data.get("shape") not in SHAPES or
            not isinstance(entries, list) or not 2 <= len(entries) <= MAX_SET or
            not isinstance(data.get("source_notes_sha256"), str) or
            not re.fullmatch("[0-9a-f]{64}", data["source_notes_sha256"])):
        raise ValueError("Invalid private journey plan")
    clean = _records(root, entries)
    if (len({r["bpm"] for r in clean}) != 1 or data.get("bpm") != clean[0]["bpm"] or
            data.get("automatic_tempo_matching") is not False or
            data.get("preference_proven") is not False):
        raise ValueError("Journey is not an admissible manual same-BPM suggestion")
    targets = _targets(data["shape"], len(clean))
    for index, row in enumerate(entries):
        if type(row.get("target_energy")) not in (int, float) or row["target_energy"] != targets[index]:
            raise ValueError("Journey targets do not match declared shape")
    return clean


def main():
    parser = argparse.ArgumentParser(description="Private human-energy DJ journey planner (no automatic BPM detection)")
    sub = parser.add_subparsers(dest="action", required=True)
    note = sub.add_parser("notes", help="Create human BPM/energy annotations for local songs")
    note.add_argument("music_directory")
    note.add_argument("new_notes_json")
    plan = sub.add_parser("plan", help="Suggest a SHA-bound same-tempo song order")
    plan.add_argument("music_directory")
    plan.add_argument("notes_json")
    plan.add_argument("new_plan_json")
    plan.add_argument("--tracks", type=int, default=5)
    plan.add_argument("--shape", choices=SHAPES, default="build")
    plan.add_argument("--tempo", type=float)
    plan.add_argument("--prefer-tag")
    plan.add_argument("--opening", help="Exact local filename to play first")
    plan.add_argument("--closing", help="Exact local filename to play last")
    plan.add_argument("--exclude-track", action="append", default=[],
                      help="Exact local filename to omit; repeatable")
    args = parser.parse_args()
    try:
        if args.action == "notes":
            path = capture_notes(args.music_directory, args.new_notes_json)
            result = {"stage": "human-notes", "private_notes": str(path)}
        else:
            path = plan_journey(args.music_directory, args.notes_json, args.new_plan_json,
                                tracks=args.tracks, shape=args.shape,
                                tempo=args.tempo, prefer_tag=args.prefer_tag,
                                opening=args.opening, closing=args.closing,
                                excluded=args.exclude_track)
            result = {"stage": "suggested-journey", "private_plan": str(path),
                      "accepted": False, "automatic_music_analysis": False}
    except (ValueError, TypeError, OSError, EOFError, KeyboardInterrupt) as exc:
        parser.exit(2, f"MixLab journey: {exc}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
