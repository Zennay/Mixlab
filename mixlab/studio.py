"""Local DJ audition and export of actual MixLab transition audio.

This is an intentionally *unblinded* creative workflow, not an A/B study.
Use `mixlab.evaluation` for frozen listener evidence instead.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import stat

from .dsp import render
from .engine import FAMILY_NAMES
from .ingest import digest, validate_library
from .models import Recipe

MAX_SESSION_BYTES = 512 * 1024 * 1024
MAX_RECEIPT_BYTES = 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _ensure_new_private_dir(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("Destination must not exist; sessions and exports are immutable")
    if not path.parent.is_dir():
        raise ValueError("Destination parent directory must exist")
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Audio must remain outside the source repository")
    path.mkdir(mode=0o700)
    return path


def _safe_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid pair ID")
    return value


def _selected_pairs(manifest, pair_id):
    pairs = manifest["pairs"]
    if pair_id is None:
        return pairs
    _safe_id(pair_id)
    chosen = [pair for pair in pairs if pair["id"] == pair_id]
    if len(chosen) != 1:
        raise ValueError("Requested pair is not present in the validated library")
    return chosen


def _price_session(pairs, tracks):
    total = 0
    for pair in pairs:
        info = tracks[pair["a"]]
        frames = round(pair.get("beats", 8) * 60 / pair["bpm"] * info["sample_rate"])
        total += (44 + frames * info["channels"] * 2) * len(FAMILY_NAMES)
    if total > MAX_SESSION_BYTES:
        raise ValueError("Session audio budget exceeds 512 MiB; select one pair with --pair")


def _section(pair, records):
    pid = pair["id"]
    safe = html.escape(pid, quote=True)
    cards = []
    for record in records:
        family = record["family"]
        name = html.escape(family.replace("_", " ").title())
        src = html.escape(record["relative_path"], quote=True)
        cards.append(
            '<article class="variant"><h3>' + name + '</h3>'
            '<audio controls preload="none" src="' + src + '"></audio>'
            '<a class="save" download="' + safe + '-' + family + '.wav" href="' + src +
            '">Save this WAV</a></article>'
        )
    return ('<section class="pair" data-pair="' + safe +
            '"><header><p class="eyebrow">Transition pair</p><h2>' + safe +
            '</h2><p class="muted">All styles render the same manual BPM and beat duration.</p></header>'
            '<div class="variants">' + "".join(cards) + '</div></section>')


def _write_studio_page(path, sessions):
    cards = "".join(_section(pair, records) for pair, records in sessions)
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>MixLab / Transition Studio</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#f4f5f8;background:#0d0e12}
*{box-sizing:border-box}body{margin:0}main{max-width:1220px;margin:0 auto;padding:52px 22px 100px}
.eyebrow{text-transform:uppercase;letter-spacing:.2em;color:#b7a1ff;font-size:.72rem;font-weight:800}
h1{font-size:clamp(3rem,8vw,6rem);letter-spacing:-.075em;line-height:.99;margin:.2em 0}
.lede{color:#bac0cd;max-width:690px;line-height:1.7;font-size:1.05rem}
.notice{padding:16px 20px;border:1px solid #394052;background:#191c25;border-radius:15px;margin-top:30px}
section.pair{margin-top:54px}section.pair header{display:flex;align-items:end;gap:20px;flex-wrap:wrap}
h2{font-size:2rem;margin:0}h3{margin:0 0 22px;font-size:1.15rem;text-transform:capitalize}
.muted{color:#9199ad}.variants{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px;margin-top:22px}
.variant{border:1px solid #313645;background:linear-gradient(135deg,#242538,#171920);
border-radius:21px;padding:24px;min-height:188px}
audio{width:100%;height:44px}.save{display:inline-block;color:#d6ccff;margin-top:16px;text-decoration:none;font-size:.92rem}
.save:focus-visible{outline:3px solid #c4b5fd;outline-offset:3px}
footer{margin-top:72px;color:#8b92a5;font-size:.85rem}
</style></head><body><main>
<p class="eyebrow">MIXLAB / PRIVATE CREATIVE WORKSPACE</p>
<h1>Transition<br>Studio.</h1>
<p class="lede">Hear every rendering style for your manually chosen track pairs.
Preview locally, then save the version you want to use. Source WAVs and
provenance remain on your computer.</p>
<div class="notice"><strong>Creative audition — not a blind listening study.</strong>
Styles are labelled and no musical-preference or automatic-analysis claim is made.
For a formal controlled A/B study, use the separate benchmark workflow.</div>
''' + cards + '''
<footer>MixLab · Offline PCM16 audition · No analytics, uploads or external fonts</footer>
</main></body></html>'''
    path.write_text(page, encoding="utf-8")


def build_studio(manifest_path, destination, pair_id=None):
    """Render private side-by-side auditions for validated track pairs."""
    manifest_path = Path(manifest_path).absolute()
    manifest, tracks = validate_library(manifest_path)
    pairs = _selected_pairs(manifest, pair_id)
    _price_session(pairs, tracks)
    destination = Path(destination).absolute()
    # Prevent accidental archive publication of audio into source or project.
    if destination.is_relative_to(manifest_path.parent):
        raise ValueError("Store audition sessions outside the source library directory")
    root = _ensure_new_private_dir(destination)
    try:
        all_records = []
        page_sections = []
        media = root / "auditions"
        media.mkdir(mode=0o700)
        for pair in pairs:
            pid = pair["id"]
            folder = media / pid
            folder.mkdir(mode=0o700)
            a = tracks[pair["a"]]
            b = tracks[pair["b"]]
            entries = []
            for family in FAMILY_NAMES:
                relative = f"auditions/{pid}/{family}.wav"
                target = root / relative
                recipe = Recipe(family=family, bpm=pair["bpm"],
                                beats=pair.get("beats", 8),
                                a_start=pair.get("a_start", 0),
                                b_start=pair.get("b_start", 0),
                                a_bpm=a["bpm"], b_bpm=b["bpm"])
                result = render(a["resolved_path"], b["resolved_path"], target, recipe)
                records = {"pair": pid, "family": family, "relative_path": relative,
                           "sha256": result["output_sha256"],
                           "frames": result["frames"],
                           "sample_rate": result["sample_rate"],
                           "channels": result["channels"],
                           "peak": result["post_pcm_metrics"]["peak"],
                           "rms": result["post_pcm_metrics"]["rms"],
                           "clipped_samples": result["post_pcm_metrics"]["clipping_samples"]}
                # No full source paths or original track titles reach HTML/receipt.
                entries.append(records)
                all_records.append(records)
            page_sections.append((pair, entries))
        session = {"schema_version": 1, "kind": "private-unblinded-creative-audition",
                   "manifest_sha256": digest(manifest_path),
                   "status": "rendered-not-human-preference-validated",
                   "pair_count": len(pairs), "family_count": len(FAMILY_NAMES),
                   "renders": all_records}
        session["session_id"] = hashlib.sha256(_json_bytes(session)).hexdigest()
        raw = _json_bytes(session)
        if len(raw) > MAX_RECEIPT_BYTES:
            raise ValueError("Unexpectedly large studio receipt")
        (root / "studio-receipt.private.json").write_bytes(raw)
        _write_studio_page(root / "index.html", page_sections)
        return root / "index.html"
    except BaseException:
        shutil.rmtree(root)
        raise


def _open_receipt(root):
    receipt = root / "studio-receipt.private.json"
    if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("Private studio receipt missing or invalid")
    with receipt.open("rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECEIPT_BYTES:
            raise ValueError("Invalid studio receipt")
        data = source.read(MAX_RECEIPT_BYTES + 1)
        after = os.fstat(source.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Studio receipt changed during inspection")
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate receipt keys")
            result[key] = value
        return result
    try:
        session = json.loads(data, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Malformed studio receipt") from exc
    if not isinstance(session, dict) or session.get("schema_version") != 1 or session.get("kind") != "private-unblinded-creative-audition":
        raise ValueError("Unsupported studio receipt")
    identity = session.get("session_id")
    base = {k: v for k, v in session.items() if k != "session_id"}
    if not isinstance(identity, str) or hashlib.sha256(_json_bytes(base)).hexdigest() != identity:
        raise ValueError("Studio receipt integrity mismatch")
    return session


def export_candidate(session_dir, pair_id, family, destination):
    """Exclusively export one checksum-pinned creative result; never overwrite."""
    root = Path(session_dir).resolve(strict=True)
    pair_id = _safe_id(pair_id)
    if family not in FAMILY_NAMES:
        raise ValueError("Unknown transition family")
    session = _open_receipt(root)
    matches = [r for r in session["renders"]
               if isinstance(r, dict) and r.get("pair") == pair_id and r.get("family") == family]
    if len(matches) != 1:
        raise ValueError("No unique render for this pair/family")
    record = matches[0]
    if record.get("relative_path") != f"auditions/{pair_id}/{family}.wav":
        raise ValueError("Unexpected render location")
    if not isinstance(record.get("sha256"), str) or not SHA.fullmatch(record["sha256"]):
        raise ValueError("Render has no valid checksum")
    path = root / record["relative_path"]
    if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError("Render WAV unavailable or redirected")
    if digest(path) != record["sha256"]:
        raise ValueError("Render WAV no longer matches its session receipt")
    target = Path(destination).absolute()
    if target.exists() or target.is_symlink() or target.suffix.lower() != ".wav":
        raise ValueError("Choose a new .wav export filename")
    if target.is_relative_to(root):
        raise ValueError("Export outside immutable session directory")
    for ancestor in (target, *target.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Do not export private audio to a Git checkout")
    try:
        with path.open("rb") as source, target.open("xb") as output:
            shutil.copyfileobj(source, output, length=65536)
        if digest(target) != record["sha256"]:
            raise ValueError("Exported WAV checksum mismatch")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def main():
    parser = argparse.ArgumentParser(description="MixLab local, unblinded DJ Transition Studio")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("render", help="Make a new local audition session")
    create.add_argument("manifest")
    create.add_argument("destination")
    create.add_argument("--pair", help="Limit rendering to one registered pair")
    pick = sub.add_parser("export", help="Export one pinned WAV without overwriting")
    pick.add_argument("session")
    pick.add_argument("pair")
    pick.add_argument("family", choices=FAMILY_NAMES)
    pick.add_argument("destination")
    args = parser.parse_args()
    try:
        result = (build_studio(args.manifest, args.destination, args.pair)
                  if args.action == "render" else
                  export_candidate(args.session, args.pair, args.family, args.destination))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"MixLab studio: {exc}\n")
    print(result)


if __name__ == "__main__":
    main()
