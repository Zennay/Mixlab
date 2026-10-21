"""Score measured analysis proposals against private manual reference annotations.

Input is a private annotation JSON beside the excerpts. Output aggregates
contain track IDs and scores only: no paths, PCM or feature vectors. Synthetic
annotations verify the harness; only permitted, human-annotated music
produces analysis evidence for M1.
"""
import math
from pathlib import Path
import statistics
from . import EnergyOnsetProvider, beat_errors
from .meter import AccentMeterProvider
from .source_receipt import source_identity, verify_source
from .tonal import KEYS, ChromaKeyProvider, key_report
from ..evaluation.json_admission import load_bounded_json
from ..ingest import HASH, ID, number

MAX_ITEMS = 200
FIELDS = {"id", "path", "sha256", "bpm", "first_beat", "downbeats", "key", "annotator"}


def _item(raw, root):
    if not isinstance(raw, dict) or not set(raw) <= FIELDS or not {"id", "path", "sha256", "bpm",
                                                                    "annotator"} <= set(raw):
        raise ValueError("Invalid reference item fields")
    if not isinstance(raw["id"], str) or not ID.match(raw["id"]):
        raise ValueError("Invalid reference id")
    relative = raw["path"]
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute() or
            ".." in Path(relative).parts):
        raise ValueError("Reference path must stay beside the annotation file")
    if not isinstance(raw["sha256"], str) or not HASH.match(raw["sha256"]):
        raise ValueError("Invalid reference sha256")
    if not isinstance(raw["annotator"], str) or not raw["annotator"].strip():
        raise ValueError("Reference annotations need an annotator")
    bpm = number(raw["bpm"], "bpm", 30, 300)
    first = number(raw.get("first_beat", 0.), "first beat", 0, 250)
    downbeats = raw.get("downbeats", [])
    if not isinstance(downbeats, list) or len(downbeats) > 10000:
        raise ValueError("Invalid reference downbeats")
    previous = -1.
    for t in downbeats:
        number(t, "downbeat", 0, 100000)
        if t <= previous:
            raise ValueError("Reference downbeats must increase strictly")
        previous = t
    key = raw.get("key")
    if key is not None and key not in KEYS:
        raise ValueError("Unsupported reference key")
    return dict(id=raw["id"], path=root / relative, sha256=raw["sha256"], bpm=bpm,
                first_beat=first, downbeats=tuple(downbeats), key=key)


def load_references(path):
    document = load_bounded_json(path)
    if (not isinstance(document, dict) or set(document) != {"schema_version", "items"} or
            document["schema_version"] != 1 or not isinstance(document["items"], list) or
            not 1 <= len(document["items"]) <= MAX_ITEMS):
        raise ValueError("Invalid reference annotation document")
    root = Path(path).absolute().parent
    items = [_item(raw, root) for raw in document["items"]]
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Duplicate reference id")
    return items


def _grid(item, duration):
    period = 60 / item["bpm"]
    return tuple(round(item["first_beat"] + n * period, 6)
                 for n in range(max(0, math.ceil((duration - item["first_beat"]) / period))))


def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def evaluate(path, tolerance=.07):
    """Run beat, downbeat and key providers on every reference item."""
    items = load_references(path)
    beat_provider, meter, tonal = EnergyOnsetProvider(), AccentMeterProvider(), ChromaKeyProvider()
    rows = []
    for item in items:
        # Observe one physical regular-file identity before all separate
        # provider reads. An in-place edit or swap must not mix source A's
        # reference beatgrid with source B's key or meter analysis.
        original_identity = source_identity(item["path"])
        if not isinstance(item["sha256"], str):
            raise ValueError("Invalid private PCM checksum")
        def bound(record):
            # Every provider hashes the bytes it analysed; all of them must be
            # the annotated recording, so a swap between providers fails closed.
            if (record.source_sha256 != item["sha256"] or
                    source_identity(item["path"]) != original_identity):
                raise ValueError("Private PCM changed during reference analysis")
            return record
        beats = bound(beat_provider.analyze(item["path"]))
        reference_grid = _grid(item, beats.duration_seconds)
        row = {"id": item["id"], "beat_abstained": not beats.beats_seconds,
               "beat_f1": beat_errors(reference_grid, beats.beats_seconds, tolerance)["f1"]
               if beats.beats_seconds else None}
        if item["downbeats"]:
            # Downbeats on the verified grid isolate bar-phase errors from tempo errors.
            on_reference = bound(meter.analyze(item["path"], list(reference_grid)))
            row["downbeat_abstained_reference_grid"] = not on_reference.downbeats_seconds
            row["downbeat_f1_reference_grid"] = (beat_errors(
                item["downbeats"], on_reference.downbeats_seconds, tolerance)["f1"]
                if on_reference.downbeats_seconds else None)
            if len(beats.beats_seconds) >= 16:
                on_estimate = bound(meter.analyze(item["path"], list(beats.beats_seconds)))
                row["downbeat_f1_estimated_grid"] = (beat_errors(
                    item["downbeats"], on_estimate.downbeats_seconds, tolerance)["f1"]
                    if on_estimate.downbeats_seconds else None)
            else:
                row["downbeat_f1_estimated_grid"] = None
        if item["key"] is not None:
            estimate = bound(tonal.analyze(item["path"]))
            row["reference_key"], row["estimated_key"] = item["key"], estimate.key
        verify_source(item["path"], original_identity, item["sha256"])
        rows.append(row)
    downbeat_rows = [r for r in rows if "downbeat_abstained_reference_grid" in r]
    key_rows = [(r["reference_key"], r["estimated_key"]) for r in rows if "reference_key" in r]
    summary = {
        "items": len(rows), "tolerance_seconds": tolerance,
        "beat_abstention_rate": sum(r["beat_abstained"] for r in rows) / len(rows),
        "beat_f1_mean_answered": _mean(r["beat_f1"] for r in rows),
        "downbeat_items": len(downbeat_rows),
        "downbeat_abstention_rate_reference_grid": (sum(
            r["downbeat_abstained_reference_grid"] for r in downbeat_rows) / len(downbeat_rows)
            if downbeat_rows else None),
        "downbeat_f1_mean_answered_reference_grid": _mean(
            r["downbeat_f1_reference_grid"] for r in downbeat_rows),
        "downbeat_f1_mean_answered_estimated_grid": _mean(
            r["downbeat_f1_estimated_grid"] for r in downbeat_rows),
        "key": key_report(key_rows) if key_rows else None,
        "providers": {"beat": beat_provider.version, "meter": meter.version, "key": tonal.version},
        "evidence_boundary": "scores against the supplied manual annotations only; "
                             "not listener preference or rights verification",
    }
    return {"summary": summary, "items": rows}


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Score analysis proposals against private manual annotations")
    parser.add_argument("annotations")
    parser.add_argument("--tolerance", type=float, default=.07)
    args = parser.parse_args(argv)
    try:
        number(args.tolerance, "tolerance", .001, .5)
        result = evaluate(args.annotations, args.tolerance)
    except ValueError as exc:
        parser.exit(2, f"MixLab analysis benchmark: {exc}\n")
    except (OSError, TypeError):
        # OS errors carry private operator paths; never echo them.
        parser.exit(2, "MixLab analysis benchmark: input unavailable (details withheld)\n")
    print(json.dumps(result, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
