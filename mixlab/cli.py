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

from .engine import FAMILY_NAMES, load_wav, render, write_wav
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


def validate_library(manifest_path):
    source = Path(manifest_path).resolve()
    manifest = json.loads(source.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported library schema")
    if not 2 <= len(manifest.get("tracks", [])) <= 50:
        raise ValueError("Library must have 2–50 explicitly registered tracks")
    tracks = {}
    for track in manifest["tracks"]:
        if not isinstance(track.get("id"), str) or not track["id"] or track["id"] in tracks:
            raise ValueError("Track IDs must be unique nonempty strings")
        if track.get("rights") not in {"synthetic", "licensed", "user-permitted", "public-domain"}:
            raise ValueError("Explicit permitted rights status required")
        if not isinstance(track.get("provenance"), str) or not track["provenance"].strip():
            raise ValueError("Provenance required")
        path = (source.parent / track["path"]).resolve()
        if not path.is_relative_to(source.parent):
            raise ValueError("Source path must remain within the library directory")
        if path.suffix.lower() != ".wav" or not path.is_file():
            raise ValueError("Source must be an existing WAV")
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Source exceeds 32 MiB prototype cap; prepare a shorter excerpt")
        if digest(path) != track.get("sha256"):
            raise ValueError("Source checksum mismatch")
        bpm = track.get("bpm")
        if isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not math.isfinite(bpm) or not 30 <= bpm <= 300:
            raise ValueError("Manual BPM between 30 and 300 required")
        load_wav(path)
        tracks[track["id"]] = {**track, "resolved_path": path}
    pairs = manifest.get("pairs", [])
    if not 1 <= len(pairs) <= 10:
        raise ValueError("Register 1–10 explicit pairs")
    ids = set()
    for pair in pairs:
        if not isinstance(pair.get("id"), str) or not pair["id"] or pair["id"] in ids:
            raise ValueError("Pair IDs must be unique nonempty strings")
        ids.add(pair["id"])
        if pair.get("a") not in tracks or pair.get("b") not in tracks or pair["a"] == pair["b"]:
            raise ValueError("Pair must reference two distinct registered tracks")
        bpm = pair.get("bpm")
        if bpm != tracks[pair["a"]]["bpm"] or bpm != tracks[pair["b"]]["bpm"]:
            raise ValueError("Prototype requires equal manually verified BPM; no time stretch implemented")
    return manifest, tracks


def benchmark(manifest_path, destination, seed=None):
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
            outputs[family] = path
            evidence.append({"pair": pair["id"], "family": family,
                             "recipe": asdict(recipe), "metrics": metrics,
                             "source_hashes": [a["sha256"], b["sha256"]], "output_sha256": digest(path)})
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
    dump(private / "answer-key.json", answers)
    dump(private / "evidence.json", {"schema_version": 1, "kind": manifest.get("purpose", "development-pilot"),
                                      "manifest_sha256": digest(manifest_path), "renders": evidence,
                                      "limitations": ["not loudness-normalized", "manual beatgrid", "no listening-quality claim"]})
    write_review(review / "index.html", cards)
    dump(root / "receipt.json", {"schema_version": 1, "trial_count": len(cards),
                                 "render_count": len(evidence), "status": "rendered-not-listener-validated",
                                 "manifest_sha256": digest(manifest_path)})
    return root / "receipt.json"


def write_review(path, trials):
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
<form><label>Anonymous reviewer code <input name="reviewer" required maxlength="40" placeholder="e.g. listener-01"></label>''' + ''.join(sections) + '''<button>Download my ratings</button><p id="status" aria-live="polite">Ratings stay on this device until you share the JSON file.</p></form>
<script>document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);const reviewer=f.get('reviewer');const ratings=[...document.querySelectorAll('[data-trial]')].map(el=>({trial:el.dataset.trial,preference:f.get(el.dataset.trial)}));const blob=new Blob([JSON.stringify({schema_version:1,reviewer,ratings},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='mixlab-ratings.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='Ratings downloaded. Keep the answer key hidden until all ratings are locked.'});</script></html>'''
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
    args = parser.parse_args()
    try:
        if args.command == "fixture":
            print(fixture(args.destination))
        elif args.command == "validate":
            manifest, _ = validate_library(args.manifest)
            print(json.dumps({"valid": True, "tracks": len(manifest["tracks"]), "pairs": len(manifest["pairs"])}))
        else:
            print(benchmark(args.manifest, args.destination, args.seed))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab: {exc}\n")


if __name__ == "__main__":
    main()
