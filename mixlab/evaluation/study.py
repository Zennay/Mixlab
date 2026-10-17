"""Freeze a 5-10 pair blind study before any ratings exist.

Selection is stratified by harmonic compatibility and ordered by a recorded
seed, so it can be reproduced and audited but not tuned on listener results.
Each pair gets exactly one preselected candidate family, balanced across
families, to be compared with the equal-power baseline. Only tracks declared
in the evaluation split are eligible. The output hash-binds the inputs and
selection; it is a private study manifest, not a signature or rights proof.
"""
import hashlib
import json
import math
import os
from pathlib import Path
from .json_admission import load_bounded_json
from ..ingest import HASH, ID, RIGHTS, number
from ..models import FAMILY_NAMES

SCHEMA = 1
KIND = "mixlab-frozen-pair-study"
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
KEYS = {f"{name} {mode}" for name in PITCH_CLASSES for mode in ("major", "minor")}
KEY_SOURCES = {"manual", "measured-heuristic", "unavailable"}
SPLITS = {"development", "evaluation"}
MAX_TRACKS = 200
CANDIDATE_FAMILIES = tuple(f for f in FAMILY_NAMES if f != "baseline")
PROTOCOL = {
    "comparison": "equal-power baseline versus exactly one preselected candidate per pair",
    "selection": "seeded hash order, stratified by harmonic compatibility, frozen before ratings",
    "minimum_listeners": 3,
    "loudness": "match perceived loudness or report the confound before any preference claim",
    "tuning": "never tune recipes on evaluation-split tracks or their ratings",
}


def camelot(key):
    """Camelot wheel position (1..12, 'A' minor / 'B' major)."""
    tonic, mode = key.split()
    pc = PITCH_CLASSES.index(tonic)
    if mode == "minor":
        pc = (pc + 3) % 12
    return (pc * 7 + 7) % 12 + 1, "A" if mode == "minor" else "B"


def camelot_distance(a, b):
    (na, la), (nb, lb) = camelot(a), camelot(b)
    steps = min((na - nb) % 12, (nb - na) % 12)
    return steps + (la != lb)


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _rank(seed, *parts):
    return hashlib.sha256(_canonical([seed, *parts])).hexdigest()


def _tracks(document):
    if (not isinstance(document, dict) or set(document) != {"schema_version", "tracks"} or
            document["schema_version"] != 1 or not isinstance(document["tracks"], list) or
            not 1 <= len(document["tracks"]) <= MAX_TRACKS):
        raise ValueError("Invalid study candidate document")
    tracks = {}
    for raw in document["tracks"]:
        if not isinstance(raw, dict) or set(raw) != {"id", "sha256", "bpm", "key", "key_source",
                                                      "split", "rights"}:
            raise ValueError("Invalid study track fields")
        if not isinstance(raw["id"], str) or not ID.match(raw["id"]):
            raise ValueError("Invalid track id")
        if raw["id"] in tracks:
            raise ValueError("Duplicate track id")
        if not isinstance(raw["sha256"], str) or not HASH.match(raw["sha256"]):
            raise ValueError("Invalid track sha256")
        number(raw["bpm"], "bpm", 30, 300)
        if raw["split"] not in SPLITS or raw["rights"] not in RIGHTS:
            raise ValueError("Unsupported split or rights declaration")
        if raw["key_source"] not in KEY_SOURCES:
            raise ValueError("Unsupported key source")
        if (raw["key"] is None) != (raw["key_source"] == "unavailable") or (
                raw["key"] is not None and raw["key"] not in KEYS):
            raise ValueError("Key and key source disagree")
        tracks[raw["id"]] = raw
    hashes = [t["sha256"] for t in tracks.values()]
    if len(set(hashes)) != len(hashes):
        raise ValueError("The same recording appears under two track ids")
    return tracks


def _describe(a, b, tolerance):
    delta = abs(a["bpm"] - b["bpm"]) / min(a["bpm"], b["bpm"]) * 100
    if delta > tolerance + 1e-9:
        return None
    distance = camelot_distance(a["key"], b["key"]) if a["key"] and b["key"] else None
    stratum = "unknown" if distance is None else "compatible" if distance <= 1 else "contrasting"
    return {"tempo_delta_percent": round(delta, 4), "camelot_distance": distance,
            "harmonic_class": stratum, "renderable_without_stretch": delta <= 1e-9}


def freeze(candidates_path, count, seed, tempo_tolerance_percent=0., max_track_uses=2):
    if type(count) is not int or not 5 <= count <= 10:
        raise ValueError("A study freezes 5 to 10 pairs")
    if type(seed) is not int or not 0 <= seed < 2 ** 63:
        raise ValueError("Seed must be a recorded nonnegative 63-bit integer")
    number(tempo_tolerance_percent, "tempo tolerance percent", 0, 8)
    if type(max_track_uses) is not int or not 1 <= max_track_uses <= 4:
        raise ValueError("Track reuse must be between 1 and 4")
    document = load_bounded_json(candidates_path)
    tracks = _tracks(document)
    evaluation = sorted(i for i, t in tracks.items() if t["split"] == "evaluation")
    development = sorted(i for i, t in tracks.items() if t["split"] == "development")
    strata = {"compatible": [], "contrasting": [], "unknown": []}
    for x in range(len(evaluation)):
        for y in range(x + 1, len(evaluation)):
            a, b = tracks[evaluation[x]], tracks[evaluation[y]]
            described = _describe(a, b, tempo_tolerance_percent)
            if described is None:
                continue
            order = _rank(seed, "pair", a["id"], b["id"])
            if int(order[-1], 16) % 2:
                a, b = b, a
            strata[described["harmonic_class"]].append((order, a, b, described))
    for items in strata.values():
        items.sort(key=lambda item: item[0])
    uses = {}
    chosen = []

    def take(pool, limit):
        for item in pool:
            if len(chosen) >= limit:
                return
            _, a, b, _ = item
            if item in chosen or uses.get(a["id"], 0) >= max_track_uses or \
                    uses.get(b["id"], 0) >= max_track_uses:
                continue
            chosen.append(item)
            uses[a["id"]] = uses.get(a["id"], 0) + 1
            uses[b["id"]] = uses.get(b["id"], 0) + 1

    # Representative rather than flattering: half compatible, half contrasting
    # or unknown, then fill any shortfall from the remaining pool.
    take(strata["compatible"], math.ceil(count / 2))
    take(sorted(strata["contrasting"] + strata["unknown"], key=lambda item: item[0]), count)
    take(sorted(strata["compatible"] + strata["contrasting"] + strata["unknown"],
                key=lambda item: item[0]), count)
    if len(chosen) < count:
        raise ValueError("Not enough eligible evaluation pairs for the requested study size")
    chosen.sort(key=lambda item: item[0])
    families = sorted(CANDIDATE_FAMILIES, key=lambda family: _rank(seed, "family", family))
    pairs = []
    for index, (_, a, b, described) in enumerate(chosen):
        pairs.append(dict(described, pair_id=f"pair-{index + 1:02d}", a=a["id"], b=b["id"],
                          a_sha256=a["sha256"], b_sha256=b["sha256"], a_bpm=a["bpm"], b_bpm=b["bpm"],
                          key_sources=[a["key_source"], b["key_source"]],
                          candidate_family=families[index % len(families)]))
    study = {"schema_version": SCHEMA, "kind": KIND, "protocol": PROTOCOL, "seed": seed,
             "candidates_sha256": hashlib.sha256(_canonical(document)).hexdigest(),
             "development_track_ids_sha256": hashlib.sha256(_canonical(development)).hexdigest(),
             "evaluation_track_count": len(evaluation), "tempo_tolerance_percent": tempo_tolerance_percent,
             "max_track_uses": max_track_uses, "pairs": pairs,
             "warnings": ["selection is not a preference result; no ratings were used",
                          "measured-heuristic keys must be confirmed before study use"
                          if any("measured-heuristic" in p["key_sources"] for p in pairs) else
                          "key sources recorded per pair"]}
    study["study_id"] = hashlib.sha256(_canonical(study)).hexdigest()
    return study


def verify_study(path):
    study = load_bounded_json(path)
    if not isinstance(study, dict) or study.get("kind") != KIND or study.get("schema_version") != SCHEMA:
        raise ValueError("Not a frozen MixLab pair study")
    claimed = study.get("study_id")
    body = {k: v for k, v in study.items() if k != "study_id"}
    if claimed != hashlib.sha256(_canonical(body)).hexdigest():
        raise ValueError("Study identity mismatch")
    pairs = study.get("pairs")
    if not isinstance(pairs, list) or not 5 <= len(pairs) <= 10:
        raise ValueError("Invalid study pairs")
    seen, uses, families = set(), {}, {}
    for index, pair in enumerate(pairs):
        if pair.get("pair_id") != f"pair-{index + 1:02d}" or pair.get("a") == pair.get("b"):
            raise ValueError("Invalid study pair")
        unordered = frozenset((pair["a"], pair["b"]))
        if unordered in seen:
            raise ValueError("Duplicate study pair")
        seen.add(unordered)
        for track in unordered:
            uses[track] = uses.get(track, 0) + 1
        if pair.get("candidate_family") not in CANDIDATE_FAMILIES:
            raise ValueError("Invalid preselected candidate family")
        families[pair["candidate_family"]] = families.get(pair["candidate_family"], 0) + 1
    if max(uses.values()) > study.get("max_track_uses", 0):
        raise ValueError("Track reuse exceeds the frozen limit")
    if max(families.values()) - min(families.get(f, 0) for f in CANDIDATE_FAMILIES) > 1:
        raise ValueError("Candidate families are not balanced")
    return study


def write_exclusive(path, study):
    path = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(json.dumps(study, sort_keys=True, indent=2, allow_nan=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def main(argv=None):
    import argparse
    import secrets
    parser = argparse.ArgumentParser(description="Freeze or verify a private 5-10 pair blind study")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("freeze")
    make.add_argument("candidates")
    make.add_argument("output")
    make.add_argument("--pairs", type=int, default=8)
    make.add_argument("--seed", type=int, help="omit to draw and record a fresh seed")
    make.add_argument("--tempo-tolerance-percent", type=float, default=0.)
    make.add_argument("--max-track-uses", type=int, default=2)
    check = commands.add_parser("verify")
    check.add_argument("study")
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            seed = secrets.randbelow(2 ** 63) if args.seed is None else args.seed
            study = freeze(args.candidates, args.pairs, seed, args.tempo_tolerance_percent,
                           args.max_track_uses)
            write_exclusive(args.output, study)
        else:
            study = verify_study(args.study)
    except FileExistsError:
        parser.exit(2, "MixLab study: output already exists; studies are never overwritten\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"MixLab study: {exc}\n")
    print(json.dumps({"study_id": study["study_id"], "pairs": len(study["pairs"])}, sort_keys=True))


if __name__ == "__main__":
    main()
