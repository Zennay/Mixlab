"""Offline orchestration. Source media and answer keys stay on the execution host."""
import argparse
from dataclasses import asdict
import hashlib
import html
import json
import math
from pathlib import Path
import random
import shutil

from .engine import FAMILY_NAMES, write_wav
from .ingest import validate_library
from .dsp import render
from .loudness import match_group, measure as measure_loudness
from .models import Recipe


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def fixture(destination):
    """Generate our own tones/percussion: infrastructure proof, not musical proof."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    sr = 16000
    tracks = []
    for index, freq in enumerate((110, 164.8138)):
        frames = []
        for i in range(sr * 8):
            t = i / sr
            beat_phase = t % .5
            kick = .25 * math.sin(2 * math.pi * 65 * t) * math.exp(-beat_phase * 35)
            envelope = min(1., t * 20, (8 - t) * 20)
            left = envelope * (.18 * math.sin(2 * math.pi * freq * t) + kick)
            right = envelope * (.18 * math.sin(2 * math.pi * freq * 2 * t) + kick)
            frames.append((left, right))
        name = f"source-{index + 1}.wav"
        write_wav(root / name, sr, frames)
        tracks.append({"id": f"synthetic-{index+1}", "path": name,
                       "sha256": digest(root / name), "bpm": 120.,
                       "rights": "synthetic", "provenance": "MixLab original procedural fixture v1"})
    manifest = {"schema_version": 1, "purpose": "synthetic-smoke-only", "tracks": tracks,
                "pairs": [{"id": "pair-001", "a": "synthetic-1", "b": "synthetic-2",
                           "a_start": 0., "b_start": 0., "bpm": 120., "beats": 8}]}
    dump(root / "library.json", manifest)
    return root / "library.json"


def benchmark(manifest_path, destination, seed=None, loudness_match=True):
    manifest, tracks = validate_library(manifest_path)
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    root.chmod(0o700)
    review = root / "review"
    private = root / "private"
    review.mkdir()
    private.mkdir(mode=0o700)
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    cards, answers, evidence = [], [], []
    number = 0
    for pair_index, pair in enumerate(manifest["pairs"]):
        outputs = {}
        a, b = tracks[pair["a"]], tracks[pair["b"]]
        for family in FAMILY_NAMES:
            recipe = Recipe(family=family, bpm=pair["bpm"], beats=pair.get("beats", 8),
                            a_start=pair.get("a_start", 0.), b_start=pair.get("b_start", 0.),
                            a_bpm=a["bpm"], b_bpm=b["bpm"])
            path = private / f"{pair_index:03d}-{family}.wav"
            metrics = render(a["resolved_path"], b["resolved_path"], path, recipe)
            metrics["source_permission_declarations"] = {"a": a["rights"], "b": b["rights"]}
            outputs[family] = path
            evidence.append({"pair": pair["id"], "family": family,
                             "recipe": asdict(recipe), "metrics": metrics,
                             "source_hashes": [a["sha256"], b["sha256"]], "output_sha256": digest(path)})
        if loudness_match:
            # Attenuate every family of this pair to its quietest member, so A/B
            # preference is not "louder sounds better". output_sha256 then names
            # the exact listening file; render_sha256 keeps the unmatched render.
            matched = match_group(outputs, private)
            for row in evidence[-len(FAMILY_NAMES):]:
                member = matched["members"][row["family"]]
                outputs[row["family"]] = member["path"]
                row["render_sha256"] = row["output_sha256"]
                row["output_sha256"] = digest(member["path"])
                row["loudness"] = {"method": matched["method"], "policy": matched["policy"],
                                   "target_lufs": matched["target_lufs"], "gain_db": member["gain_db"],
                                   "before_lufs": member["before"]["integrated_lufs"],
                                   "after_lufs": member["after"]["integrated_lufs"],
                                   "after_sample_peak_dbfs": member["after"]["sample_peak_dbfs"]}
        families = [f for f in FAMILY_NAMES if f != "baseline"]
        rng.shuffle(families)
        for family in families:
            number += 1
            trial = f"trial-{number:03d}"
            order = ["baseline", family]
            rng.shuffle(order)
            for label, variant in zip(("A", "B"), order):
                shutil.copyfile(outputs[variant], review / f"{trial}-{label}.wav")
            cards.append(trial)
            answers.append({"trial": trial, "pair": pair["id"], "A": order[0], "B": order[1]})
    pack_id = hashlib.sha256(json.dumps({"manifest": digest(manifest_path), "answers": answers,
                                       "outputs": [e["output_sha256"] for e in evidence]},
                                      sort_keys=True).encode()).hexdigest()
    dump(private / "answer-key.json", answers)
    dump(private / "evidence.json", {"schema_version": 1, "kind": manifest.get("purpose", "development-pilot"),
                                      "manifest_sha256": digest(manifest_path), "renders": evidence,
                                      "pack_id": pack_id, "randomization": {"seed": seed, "mode": "seeded-smoke" if seed is not None else "system-random"},
                                      "loudness_matching": "bs1770-4-attenuate-to-quietest-per-pair" if loudness_match else "none",
                                      "limitations": [("loudness-matched by integrated BS.1770-4; sample peak, not true peak"
                                                       if loudness_match else "not loudness-normalized"),
                                                      "manual beatgrid", "no listening-quality claim"]})
    write_review(review / "index.html", cards, pack_id)
    dump(root / "receipt.json", {"schema_version": 1, "pack_id": pack_id, "trial_count": len(cards),
                                 "render_count": len(evidence), "status": "rendered-not-listener-validated",
                                 "manifest_sha256": digest(manifest_path)})
    return root / "receipt.json"


def write_review(path, trials, pack_id):
    sections = []
    for trial in trials:
        tid = html.escape(trial)
        sections.append(f'<fieldset data-trial="{tid}"><legend>{tid}</legend>' +
                        ''.join(f'<label>{label}<audio controls preload="none" src="{tid}-{label}.wav"></audio></label>' for label in ("A", "B")) +
                        f'<label>Preference <select required name="{tid}"><option value="">Choose…</option><option>A</option><option>B</option><option>Tie</option><option>Both unusable</option></select></label></fieldset>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MixLab · Listening Lab</title><style>
body{font:17px system-ui;background:#11141b;color:#eff1f5;max-width:740px;margin:auto;padding:32px 20px}h1{font-size:40px;letter-spacing:-1px}p{color:#bec6d4;line-height:1.6}fieldset{border:1px solid #3b4352;border-radius:16px;margin:24px 0;padding:24px}legend{color:#c4b5fd}label{display:block;margin:12px 0}audio{display:block;width:100%;margin:10px 0}select,button,input{font:inherit;padding:12px;background:#282e3b;color:white;border:1px solid #596174;border-radius:8px}button{background:#c4b5fd;color:#11141b;font-weight:700;cursor:pointer}small{color:#c8cfdb}</style>
<small>MIXLAB / TRANSITION LAB</small><h1>Which transition works?</h1><p>Listen to both clips at a comfortable volume. Choose the transition you prefer. This is a development pilot; synthetic clips test the pipeline, not musical quality.</p>
<form data-pack-id="''' + html.escape(pack_id, quote=True) + '''"><label>Anonymous reviewer code <input name="reviewer" required maxlength="40" placeholder="e.g. listener-01"></label>''' + ''.join(sections) + '''<button>Download my ratings</button><p id="status" aria-live="polite">Ratings stay on this device until you share the JSON file.</p></form>
<script>document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);const reviewer=f.get('reviewer');const pack_id=e.target.dataset.packId;const ratings=[...document.querySelectorAll('[data-trial]')].map(el=>({trial:el.dataset.trial,preference:f.get(el.dataset.trial)}));const blob=new Blob([JSON.stringify({schema_version:1,pack_id,reviewer,ratings},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='mixlab-ratings.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='Ratings downloaded. Keep the answer key hidden until all ratings are locked.'});</script></html>'''
    Path(path).write_text(page)


def main():
    parser = argparse.ArgumentParser(description="MixLab offline Transition Lab")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fixture", help="Create original synthetic WAVs and manifest")
    p.add_argument("destination")
    p = sub.add_parser("validate", help="Validate local source provenance and hashes")
    p.add_argument("manifest")
    p = sub.add_parser("benchmark", help="Render private development A/B pack")
    p.add_argument("manifest")
    p.add_argument("destination")
    p.add_argument("--seed", type=int, help="For reproducible smoke tests only; omit in listener studies")
    p.add_argument("--no-loudness-match", action="store_true",
                   help="Package unmatched renders (regression/diagnostics only; reintroduces a loudness confound)")
    p = sub.add_parser("loudness", help="Measure BS.1770-4 integrated loudness of PCM16 WAVs")
    p.add_argument("wavs", nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "fixture":
            print(fixture(args.destination))
        elif args.command == "validate":
            manifest, _ = validate_library(args.manifest)
            print(json.dumps({"valid": True, "tracks": len(manifest["tracks"]), "pairs": len(manifest["pairs"])}))
        elif args.command == "loudness":
            results = []
            for index, path in enumerate(args.wavs, start=1):
                try:
                    result = measure_loudness(path)
                except OSError as exc:
                    # Never echo private source locations into job logs.
                    parser.exit(2, f"MixLab loudness: input {index} unreadable ({type(exc).__name__})\n")
                except ValueError as exc:
                    parser.exit(2, f"MixLab loudness: input {index}: {exc}\n")
                result.pop("sha256")
                results.append(result)
            print(json.dumps(results, indent=2, allow_nan=False))
        else:
            print(benchmark(args.manifest, args.destination, args.seed, not args.no_loudness_match))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab: {exc}\n")


if __name__ == "__main__":
    main()
