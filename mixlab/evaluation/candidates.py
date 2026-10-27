"""Build the frozen-study candidate file from a private library manifest.

Bridges ingest, analysis and `mixlab.evaluation.study`: every manifest track
gets its verified sha256, BPM and permission declaration, an explicit
development/evaluation split from a separate split file, and a key that is
either a human annotation (`manual`), a ChromaKeyProvider proposal
(`measured-heuristic`) or `unavailable` when the provider abstains or
measurement is not requested. Manual keys always win over measurement.
"""
import json
from .json_admission import load_bounded_json
from .study import KEYS, write_exclusive
from ..ingest import ID, validate_library

SPLITS = ("development", "evaluation")


def _split(path, track_ids):
    document = load_bounded_json(path)
    if (not isinstance(document, dict) or set(document) != {"schema_version", *SPLITS} or
            document["schema_version"] != 1):
        raise ValueError("Invalid split document")
    assigned = {}
    for split in SPLITS:
        ids = document[split]
        if not isinstance(ids, list) or not all(isinstance(i, str) and ID.match(i) for i in ids):
            raise ValueError("Invalid split track list")
        for track_id in ids:
            if track_id in assigned:
                raise ValueError("Track assigned to more than one split")
            assigned[track_id] = split
    if set(assigned) != set(track_ids):
        raise ValueError("Split must assign every manifest track exactly once")
    if not any(s == "evaluation" for s in assigned.values()):
        raise ValueError("Split has no evaluation tracks")
    return assigned


def _manual_keys(path, track_ids):
    if path is None:
        return {}
    document = load_bounded_json(path)
    if (not isinstance(document, dict) or set(document) != {"schema_version", "keys"} or
            document["schema_version"] != 1 or not isinstance(document["keys"], dict)):
        raise ValueError("Invalid manual key document")
    keys = document["keys"]
    if not set(keys) <= set(track_ids):
        raise ValueError("Manual key for a track outside the manifest")
    if not all(key in KEYS for key in keys.values()):
        raise ValueError("Unsupported manual key")
    return dict(keys)


def build_candidates(manifest_path, split_path, manual_keys_path=None, measure_keys=False,
                     provider=None):
    _manifest, tracks = validate_library(manifest_path)
    split = _split(split_path, tracks)
    manual = _manual_keys(manual_keys_path, tracks)
    if measure_keys and provider is None:
        from ..analysis.tonal import ChromaKeyProvider
        provider = ChromaKeyProvider()
    rows = []
    for track_id in sorted(tracks):
        track = tracks[track_id]
        if track_id in manual:
            key, source = manual[track_id], "manual"
        elif measure_keys:
            estimate = provider.analyze(track["resolved_path"])
            if estimate.source_sha256 != track["sha256"]:
                raise ValueError(f"Source changed while measuring key for {track_id}")
            key = estimate.key
            source = "measured-heuristic" if key is not None else "unavailable"
        else:
            key, source = None, "unavailable"
        rows.append({"id": track_id, "sha256": track["sha256"], "bpm": track["bpm"], "key": key,
                     "key_source": source, "split": split[track_id], "rights": track["rights"]})
    return {"schema_version": 1, "tracks": rows}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Build frozen-study candidates from a private library")
    parser.add_argument("manifest")
    parser.add_argument("split", help='{"schema_version": 1, "development": [...], "evaluation": [...]}')
    parser.add_argument("output")
    parser.add_argument("--manual-keys", help='{"schema_version": 1, "keys": {"track-id": "A minor"}}')
    parser.add_argument("--measure-keys", action="store_true",
                        help="propose keys with ChromaKeyProvider where no manual key exists")
    args = parser.parse_args(argv)
    try:
        document = build_candidates(args.manifest, args.split, args.manual_keys, args.measure_keys)
        write_exclusive(args.output, document)
    except FileExistsError:
        parser.exit(2, "MixLab candidates: output already exists; candidate files are never overwritten\n")
    except ValueError as exc:
        parser.exit(2, f"MixLab candidates: {exc}\n")
    except (OSError, TypeError, KeyError):
        # OS errors carry private operator paths; never echo them.
        parser.exit(2, "MixLab candidates: input or output unavailable (details withheld)\n")
    sources = [row["key_source"] for row in document["tracks"]]
    print(json.dumps({"tracks": len(sources), "evaluation": sum(r["split"] == "evaluation" for r in document["tracks"]),
                      "key_sources": {s: sources.count(s) for s in sorted(set(sources))}}, sort_keys=True))


if __name__ == "__main__":
    main()
