"""Render a blind pack from a frozen study: one baseline-vs-candidate trial per pair.

The manifest supplies human-verified alignment (start offsets, beats, BPM);
the frozen study supplies which pairs and which single candidate family.
The pack layout and pack_id are those of `mixlab benchmark`, so the existing
`verify_pack`/`aggregate` path applies unchanged.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import shutil
from .study import verify_study
from ..cli import digest, dump, write_review
from ..dsp import render
from ..ingest import validate_library
from ..models import Recipe


def build(manifest_path, study_path, destination, seed=None):
    study = verify_study(study_path)
    manifest, tracks = validate_library(manifest_path)
    aligned = {}
    for pair in manifest["pairs"]:
        aligned.setdefault((pair["a"], pair["b"]), pair)
    plan = []
    for entry in study["pairs"]:
        pair = aligned.get((entry["a"], entry["b"]))
        if pair is None:
            raise ValueError(f"No verified alignment in manifest for {entry['pair_id']}")
        a, b = tracks[entry["a"]], tracks[entry["b"]]
        if (a["sha256"], b["sha256"]) != (entry["a_sha256"], entry["b_sha256"]):
            raise ValueError(f"Source recording differs from frozen study for {entry['pair_id']}")
        if not entry["renderable_without_stretch"]:
            raise ValueError(f"{entry['pair_id']} needs time stretching, which is not implemented")
        plan.append((entry, pair, a, b))
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    root.chmod(0o700)
    review, private = root / "review", root / "private"
    review.mkdir()
    private.mkdir(mode=0o700)
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    cards, answers, evidence = [], [], []
    for number, (entry, pair, a, b) in enumerate(plan, 1):
        outputs = {}
        for family in ("baseline", entry["candidate_family"]):
            recipe = Recipe(family=family, bpm=pair["bpm"], beats=pair.get("beats", 8),
                            a_start=pair.get("a_start", 0.), b_start=pair.get("b_start", 0.),
                            a_bpm=a["bpm"], b_bpm=b["bpm"])
            path = private / f"{number:03d}-{family}.wav"
            metrics = render(a["resolved_path"], b["resolved_path"], path, recipe)
            metrics["source_permission_declarations"] = {"a": a["rights"], "b": b["rights"]}
            outputs[family] = path
            evidence.append({"pair": pair["id"], "study_pair": entry["pair_id"], "family": family,
                             "recipe": asdict(recipe), "metrics": metrics,
                             "source_hashes": [a["sha256"], b["sha256"]], "output_sha256": digest(path)})
        trial = f"trial-{number:03d}"
        order = ["baseline", entry["candidate_family"]]
        rng.shuffle(order)
        for label, variant in zip(("A", "B"), order):
            shutil.copyfile(outputs[variant], review / f"{trial}-{label}.wav")
        cards.append(trial)
        answers.append({"trial": trial, "pair": pair["id"], "A": order[0], "B": order[1]})
    manifest_sha = digest(manifest_path)
    pack_id = hashlib.sha256(json.dumps({"manifest": manifest_sha, "answers": answers,
                                         "outputs": [e["output_sha256"] for e in evidence]},
                                        sort_keys=True).encode()).hexdigest()
    dump(private / "answer-key.json", answers)
    dump(private / "evidence.json", {
        "schema_version": 1, "kind": "frozen-study-pilot", "manifest_sha256": manifest_sha,
        "study_id": study["study_id"], "renders": evidence, "pack_id": pack_id,
        "randomization": {"seed": seed, "mode": "seeded-smoke" if seed is not None else "system-random"},
        "limitations": ["not loudness-normalized", "manual beatgrid", "no listening-quality claim"]})
    write_review(review / "index.html", cards, pack_id)
    dump(root / "receipt.json", {"schema_version": 1, "pack_id": pack_id, "trial_count": len(cards),
                                 "render_count": len(evidence), "status": "rendered-not-listener-validated",
                                 "manifest_sha256": manifest_sha, "study_id": study["study_id"]})
    return root / "receipt.json"


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Render a blind pack from a frozen pair study")
    parser.add_argument("manifest")
    parser.add_argument("study")
    parser.add_argument("destination")
    parser.add_argument("--seed", type=int, help="For reproducible smoke tests only; omit in listener studies")
    args = parser.parse_args(argv)
    try:
        print(build(args.manifest, args.study, args.destination, args.seed))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab study pack: {exc}\n")


if __name__ == "__main__":
    main()
