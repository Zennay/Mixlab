"""Build a machine-prepared blind pilot pack from real, openly licensed excerpts.

Chains the existing tools on fetched audio (see mixlab.sources.archive):
measured tempo (octave-folded into the DJ range), pitch-preserving tempo
conform to an even BPM grid with ffmpeg atempo, re-measured beat grid,
measured key proposal, validated manifest, seeded split, candidates, frozen
study, downbeat-aligned frozen pairs and the one-trial-per-pair blind pack.

Every automatic step is labelled in the manifest provenance and the report.
Nothing here is human-verified: tempo, alignment and keys are machine
proposals, and the pack is a pilot until listeners rate it. M1 still needs
blinded human ratings; this tool only removes the hand-preparation step.

python3 -m mixlab.evaluation.pilot /private/library /private/pilot --pairs 8
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
from ..analysis import EnergyOnsetProvider
from ..analysis.alignment import kick_offset
from ..analysis.kick import KickGridProvider
from ..analysis.meter import AccentMeterProvider
from ..cli import digest, dump
from .candidates import build_candidates
from .study import freeze, verify_study, write_exclusive
from .study_pack import build as build_pack

DJ_RANGE = (100., 140.)
MAX_STRETCH = .03
RECHECK_TOLERANCE = .005
CONFORMED_SECONDS = 44
TRANSITION_BEATS = 16
MAX_TRACKS = 50
PAIR_FIELDS = ("id", "a", "b", "a_start", "b_start", "bpm", "beats")
SECOND_PASS_TOLERANCE = .0003
NUDGE_MIN_SHARPNESS = .2


def fold(bpm):
    """Move a measured tempo by octaves into the DJ range; octave choice is a heuristic."""
    while bpm < DJ_RANGE[0]:
        bpm *= 2
    while bpm >= DJ_RANGE[1]:
        bpm /= 2
    return bpm


def target_bpm(bpm):
    return float(2 * round(bpm / 2))


def conform(source, target, ratio):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(source), "-filter:a",
                    f"atempo={ratio:.6f}", "-t", str(CONFORMED_SECONDS), "-map_metadata", "-1",
                    "-c:a", "pcm_s16le", "-f", "wav", str(target)], check=True)


def _rank(seed, *parts):
    return hashlib.sha256(json.dumps([seed, *parts]).encode()).hexdigest()


def _nearest(points, at):
    return min(points, key=lambda t: abs(t - at)) if points else None


def prepare(library, destination, pairs=8, seed=20261027, evaluation_share=.7):
    library, root = Path(library), Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    (root / "conformed").mkdir()
    sources = json.loads((library / "sources.json").read_text())["tracks"]
    kick, onset, meter = KickGridProvider(*DJ_RANGE), EnergyOnsetProvider(), AccentMeterProvider()

    def measure(path):
        # Kick grid first (built for 4/4 club music); broadband onset as fallback.
        result = kick.analyze(path)
        return result if result.bpm is not None else onset.analyze(path)
    tracks, report = [], {"excluded": [], "tracks": []}
    for record in sources:
        excerpt = library / record["excerpt"]
        if digest(excerpt) != record["excerpt_sha256"]:
            report["excluded"].append({"id": record["id"], "reason": "excerpt checksum mismatch"})
            continue
        measured = measure(excerpt)
        if measured.bpm is None:
            report["excluded"].append({"id": record["id"], "reason": "tempo abstained",
                                       "confidence": measured.tempo_confidence})
            continue
        folded = fold(measured.bpm)
        target = target_bpm(folded)
        ratio = target / folded
        if abs(ratio - 1) > MAX_STRETCH:
            report["excluded"].append({"id": record["id"], "reason": "stretch too large"})
            continue
        wav = root / "conformed" / f"{record['id']}.wav"
        conform(excerpt, wav, ratio)
        grid = measure(wav)
        if grid.bpm is not None and grid.provider == "kick-grid" and \
                abs(grid.bpm - target) > target * SECOND_PASS_TOLERANCE:
            # Second pass from the original excerpt: correct the residual tempo
            # error so pairs do not drift apart during the transition.
            ratio = ratio * target / grid.bpm
            if abs(ratio - 1) <= MAX_STRETCH:
                wav.unlink()
                conform(excerpt, wav, ratio)
                grid = measure(wav)
        if grid.bpm is None or abs(fold(grid.bpm) - target) > target * RECHECK_TOLERANCE:
            report["excluded"].append({"id": record["id"], "reason": "conformed tempo did not re-measure",
                                       "remeasured_bpm": grid.bpm})
            continue
        beats = grid.beats_seconds
        if fold(grid.bpm) != grid.bpm:
            # Octave-folded grid: rebuild it at the target tempo from the same phase.
            period = 60 / target
            beats = tuple(round(beats[0] + n * period, 6)
                          for n in range(int((CONFORMED_SECONDS - beats[0]) / period)))
        bars = meter.analyze(wav, list(beats))
        tracks.append(dict(record=record, wav=wav, measured_bpm=measured.bpm, folded_bpm=round(folded, 3),
                           remeasured_bpm=grid.bpm,
                           tempo_provider=measured.provider,
                           target=target, ratio=round(ratio, 6), beats=beats,
                           downbeats=bars.downbeats_seconds, tempo_confidence=measured.tempo_confidence))
    if len(tracks) > MAX_TRACKS:
        # The manifest holds at most 50 tracks: keep the largest tempo groups,
        # which yield the most equal-tempo pairs, and record what was left out.
        sizes = {}
        for t in tracks:
            sizes[t["target"]] = sizes.get(t["target"], 0) + 1
        ranked = sorted(tracks, key=lambda t: (-sizes[t["target"]], t["target"], t["record"]["id"]))
        for t in ranked[MAX_TRACKS:]:
            report["excluded"].append({"id": t["record"]["id"], "reason": "manifest track cap"})
        kept = {id(t) for t in ranked[:MAX_TRACKS]}
        tracks = [t for t in tracks if id(t) in kept]
    report["tracks"] = [{"id": t["record"]["id"], "measured_bpm": t["measured_bpm"],
                         "folded_bpm": t["folded_bpm"], "target_bpm": t["target"], "stretch_ratio": t["ratio"],
                         "tempo_provider": t["tempo_provider"], "remeasured_bpm": t["remeasured_bpm"],
                         "tempo_confidence": t["tempo_confidence"],
                         "downbeats_found": bool(t["downbeats"])} for t in tracks]
    manifest_tracks = [{
        "id": t["record"]["id"], "path": f"conformed/{t['wav'].name}", "sha256": digest(t["wav"]),
        "bpm": t["target"], "rights": "licensed",
        "provenance": (f"{t['record']['creator']} - {t['record']['title']} ({t['record']['file']}), "
                       f"{t['record']['license']} {t['record']['license_url']}, {t['record']['item_url']}; "
                       f"excerpt {t['record']['excerpt_start_seconds']}s+{t['record']['excerpt_seconds']}s; "
                       f"tempo machine-measured {t['measured_bpm']} BPM ({t['tempo_provider']}, octave-folded "
                       f"{t['folded_bpm']}), pitch-preserving ffmpeg atempo x{t['ratio']} to {t['target']} BPM; "
                       f"not human-verified"),
    } for t in tracks]
    by_id = {t["record"]["id"]: t for t in tracks}
    groups = {}
    for t in tracks:
        groups.setdefault(t["target"], []).append(t["record"]["id"])
    usable = sorted((ids for ids in groups.values() if len(ids) >= 2), key=len, reverse=True)
    if not usable:
        raise ValueError("No two tracks share a conformed tempo")
    placeholder = {"id": "placeholder", "a": usable[0][0], "b": usable[0][1], "a_start": 0.,
                   "b_start": 0., "bpm": by_id[usable[0][0]]["target"], "beats": 4}
    manifest_path = root / "library.json"
    dump(manifest_path, {"schema_version": 1, "purpose": "real-cc-pilot-machine-prepared",
                         "tracks": manifest_tracks, "pairs": [placeholder]})
    # Seeded split, decided before any listening: a share of each tempo group is held out
    # for evaluation and the rest stays available for development and tuning.
    split = {"schema_version": 1, "development": [], "evaluation": []}
    for ids in groups.values():
        ordered = sorted(ids, key=lambda i: _rank(seed, "split", i))
        cut = max(2, math.ceil(len(ordered) * evaluation_share)) if len(ordered) >= 2 else 0
        split["evaluation"] += ordered[:cut]
        split["development"] += ordered[cut:]
    split_path = root / "split.json"
    split_path.write_text(json.dumps(split, indent=2))
    candidates_path = root / "candidates.json"
    write_exclusive(candidates_path, build_candidates(manifest_path, split_path, measure_keys=True))
    possible = sum(len(ids) * (len(ids) - 1) // 2 for ids in groups.values()
                   if len([i for i in ids if i in split["evaluation"]]) >= 2)
    count = max(5, min(pairs, 10))
    study_path = root / "study.json"
    write_exclusive(study_path, freeze(candidates_path, count, seed))
    study = verify_study(study_path)
    aligned = []
    for entry in study["pairs"]:
        a, b = by_id[entry["a"]], by_id[entry["b"]]
        period = 60 / a["target"]
        span = TRANSITION_BEATS * period
        # A: a bar line around the middle of its excerpt; B: an early bar line.
        a_points = [t for t in (a["downbeats"] or a["beats"]) if t + span <= CONFORMED_SECONDS - 1]
        b_points = [t for t in (b["downbeats"] or b["beats"]) if t + span <= CONFORMED_SECONDS - 1]
        a_start, b_start = _nearest(a_points, 20.), _nearest(b_points, 2.)
        if a_start is None or b_start is None:
            raise ValueError(f"No beat-aligned window for {entry['pair_id']}")
        # Independent check: cross-correlate the raw kick onsets of both
        # segments over the window a listener hears; nudge B only on clear evidence.
        span_seconds = TRANSITION_BEATS * 60 / a["target"]
        check = kick_offset(a["wav"], a_start, b["wav"], b_start, a["target"], span_seconds)
        nudge = None
        if (check.verdict in ("flam", "off-beat (train-wreck risk)") and check.sharpness >= NUDGE_MIN_SHARPNESS
                and 0 <= b_start + check.lag_seconds and b_start + check.lag_seconds + span_seconds <= CONFORMED_SECONDS - .5):
            b_start = b_start + check.lag_seconds
            after = kick_offset(a["wav"], a_start, b["wav"], b_start, a["target"], span_seconds)
            nudge = {"seconds": check.lag_seconds, "after": after.to_dict()}
        else:
            after = check
        aligned.append({"id": f"{entry['a']}-{entry['b']}", "a": entry["a"], "b": entry["b"],
                        "a_start": round(a_start, 6), "b_start": round(b_start, 6),
                        "bpm": a["target"], "beats": TRANSITION_BEATS,
                        "kick_alignment_before": check.to_dict(), "kick_nudge": nudge,
                        "kick_alignment": after.verdict,
                        "alignment": "machine-proposed downbeat" if a["downbeats"] and b["downbeats"]
                        else "machine-proposed beat (downbeat abstained)"})
    final_manifest = root / "library-aligned.json"
    dump(final_manifest, {"schema_version": 1, "purpose": "real-cc-pilot-machine-prepared",
                          "tracks": manifest_tracks,
                          "pairs": [{k: v for k, v in p.items() if k in PAIR_FIELDS} for p in aligned]})
    receipt = build_pack(final_manifest, study_path, root / "pack")
    report.update(study_id=study["study_id"], pairs=aligned, receipt=str(receipt.relative_to(root)),
                  evaluation_tracks=len(split["evaluation"]), development_tracks=len(split["development"]),
                  tempo_groups={str(k): len(v) for k, v in sorted(groups.items())}, possible_pairs=possible,
                  limitations=["tempo, beat alignment and keys are machine proposals, not human-verified",
                               "excerpts are tempo-conformed with ffmpeg atempo (pitch-preserving)",
                               "integrated BS.1770-4 loudness matched per trial (study_pack); not short-term matched",
                               "kick alignment is a measured proxy, not a listening result", "no listener ratings yet"])
    (root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Machine-prepare a blind pilot pack from fetched CC excerpts")
    parser.add_argument("library", help="directory written by mixlab.sources.archive")
    parser.add_argument("destination")
    parser.add_argument("--pairs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261027)
    args = parser.parse_args(argv)
    report = prepare(args.library, args.destination, args.pairs, args.seed)
    print(json.dumps({k: report[k] for k in ("study_id", "evaluation_tracks", "development_tracks",
                                             "tempo_groups")}, sort_keys=True))
    print(f"excluded: {len(report['excluded'])}, pairs: {len(report['pairs'])}")


if __name__ == "__main__":
    main()
