"""Private, offline pre-listening *metadata* binding for a frozen MixLab study.

This is a supplementary QA gate, not a renderer or a signature. The caller
must supply the study_id recorded in a separate, immutable preregistration.
Neither editable pack metadata nor self-reported source rights can prove that
the WAV was actually rendered from a specific licensed recording.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from ..engine import FAMILY_NAMES
from ..evaluation import verify_pack
from ..evaluation.json_admission import load_bounded_json

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_STUDY_KIND = "mixlab-frozen-pair-study"
_FAMILIES = frozenset(FAMILY_NAMES) - {"baseline"}


def _fail():
    raise ValueError("Frozen study and listening pack do not match")


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _verified_study(path, expected_study_id):
    if not isinstance(expected_study_id, str) or _SHA.fullmatch(expected_study_id) is None:
        _fail()
    study = load_bounded_json(path)
    if not isinstance(study, dict) or type(study.get("schema_version")) is not int:
        _fail()
    if study["schema_version"] != 1 or study.get("kind") != _STUDY_KIND:
        _fail()
    claimed = study.get("study_id")
    if claimed != expected_study_id:
        _fail()
    unsigned = {key: value for key, value in study.items() if key != "study_id"}
    if hashlib.sha256(_canonical(unsigned)).hexdigest() != claimed:
        _fail()
    pairs = study.get("pairs")
    if not isinstance(pairs, list) or not 5 <= len(pairs) <= 10:
        _fail()
    # A recomputed hash only proves internal JSON consistency. It does NOT
    # establish the frozen study is a legal sampling protocol. Enforce the
    # independent ML-05 study reuse and candidate balance constraints here,
    # before ever opening review WAVs or touching private listener material.
    limit = study.get("max_track_uses")
    if type(limit) is not int or not 1 <= limit <= 4:
        _fail()
    uses = {}
    families = {name: 0 for name in _FAMILIES}
    id_to_source = {}
    source_to_id = {}
    seen = set()
    for i, row in enumerate(pairs, 1):
        if not isinstance(row, dict) or row.get("pair_id") != f"pair-{i:02d}":
            _fail()
        if (not isinstance(row.get("candidate_family"), str)
                or row["candidate_family"] not in _FAMILIES):
            _fail()
        if (not isinstance(row.get("a"), str) or not isinstance(row.get("b"), str)
                or not row["a"] or row["a"] == row["b"]):
            _fail()
        track_pair = frozenset((row["a"], row["b"]))
        if track_pair in seen:
            _fail()
        # Validate hash types before using user-controlled values as
        # dictionary keys. A list/dict source digest must fail as ValueError,
        # not escape as TypeError with private parser context.
        for field in ("a_sha256", "b_sha256"):
            if not isinstance(row.get(field), str) or _SHA.fullmatch(row[field]) is None:
                _fail()
        seen.add(track_pair)
        families[row["candidate_family"]] += 1
        for label in ("a", "b"):
            tid, sha = row[label], row.get(f"{label}_sha256")
            if uses.get(tid, 0) >= limit:
                _fail()
            uses[tid] = uses.get(tid, 0) + 1
            # Two IDs for one PCM source (or one ID with different hashes)
            # undermine independent evaluation even with distinct trial IDs.
            if (tid in id_to_source and id_to_source[tid] != sha
                    or sha in source_to_id and source_to_id[sha] != tid):
                _fail()
            id_to_source[tid] = sha
            source_to_id[sha] = tid
        for field in ("a_bpm", "b_bpm"):
            val = row.get(field)
            if type(val) not in (int, float) or not math.isfinite(val) or not 30 <= val <= 300:
                _fail()
        # The frozen study producer explicitly marks pairs that require
        # time stretching. The current production MixLab renderer cannot
        # render those pairs, so a fabricated PCM pack cannot certify them.
        if (row.get("renderable_without_stretch") is not True
                or row["a_bpm"] != row["b_bpm"]):
            _fail()
    if max(families.values()) - min(families.values()) > 1:
        _fail()
    return study


def _preflight_render_claims(study, evidence):
    """Reject forged render metadata before scanning bounded private PCM.

    The verdict must still be checked against independently verified WAVs;
    callers compare the loaded claims with verify_pack's post-read evidence.
    """
    pairs = study["pairs"]
    renders = evidence.get("renders")
    if not isinstance(renders, list) or len(renders) != 2 * len(pairs):
        _fail()
    by_study = {}
    seen_pack_pairs = set()
    for row in renders:
        if not isinstance(row, dict):
            _fail()
        study_pair = row.get("study_pair")
        pair = row.get("pair")
        family = row.get("family")
        if (not isinstance(study_pair, str) or not isinstance(pair, str)
                or not pair or not isinstance(family, str)):
            _fail()
        by_study.setdefault(study_pair, []).append(row)

    binding = []
    for index, frozen in enumerate(pairs, 1):
        rows = by_study.get(frozen["pair_id"], [])
        if len(rows) != 2:
            _fail()
        families = {r["family"] for r in rows}
        if families != {"baseline", frozen["candidate_family"]}:
            _fail()
        pack_pairs = {r["pair"] for r in rows}
        if len(pack_pairs) != 1:
            _fail()
        pair = next(iter(pack_pairs))
        if pair in seen_pack_pairs:
            _fail()
        seen_pack_pairs.add(pair)
        for row in rows:
            if row.get("source_hashes") != [frozen["a_sha256"], frozen["b_sha256"]]:
                _fail()
            recipe = row.get("recipe")
            if not isinstance(recipe, dict) or recipe.get("family") != row["family"]:
                _fail()
            bpm = recipe.get("bpm")
            if (type(bpm) not in (int, float) or not math.isfinite(bpm)
                    or bpm != frozen["a_bpm"]):
                _fail()
            beats = recipe.get("beats")
            if type(beats) is not int or not 1 <= beats <= 64:
                _fail()
            for field, expected in (("a_bpm", frozen["a_bpm"]),
                                    ("b_bpm", frozen["b_bpm"])):
                actual = recipe.get(field)
                if (type(actual) not in (int, float) or not math.isfinite(actual)
                        or actual != expected):
                    _fail()
        binding.append((index, pair, families))
    if set(by_study) != {row["pair_id"] for row in pairs}:
        _fail()
    return binding


def verify_study_pack_binding(study_path, pack_path, expected_study_id):
    """Validate frozen-selection/pack claims against a separately pinned ID.

    Pre-admit every cheap frozen study/render metadata contract before opening
    the private PCM. Then verify actual review WAV checksums using the existing
    bounded pack validator and reject evidence modified between the passes.
    This is not authentication of original source recordings.
    """
    study = _verified_study(study_path, expected_study_id)
    root = Path(pack_path)
    public_hint = load_bounded_json(root / "receipt.json")
    private_hint = load_bounded_json(root / "private" / "evidence.json")
    # Schema-v1 public receipts intentionally contain NO study_id: the
    # strict public ML-07 allowlist rejects unknown keys to avoid leaking
    # source/answer provenance. The separately pinned study commitment is
    # checked solely against private evidence; never demand a public leak.
    if (not isinstance(public_hint, dict) or not isinstance(private_hint, dict)
            or "study_id" in public_hint
            or private_hint.get("study_id") != expected_study_id):
        _fail()
    binding = _preflight_render_claims(study, private_hint)
    receipt, evidence, trials = verify_pack(pack_path)
    if (receipt != public_hint or "study_id" in receipt
            or evidence.get("study_id") != expected_study_id
            or evidence.get("renders") != private_hint.get("renders")
            or len(trials) != len(binding)):
        _fail()
    for index, pair, families in binding:
        trial = trials.get(f"trial-{index:03d}")
        if (not isinstance(trial, dict) or trial.get("pair") != pair
                or {trial.get("A"), trial.get("B")} != families):
            _fail()

    return {
        "schema_version": 1,
        "study_pack_metadata_consistent_with_pinned_id": True,
        "trial_count": len(binding),
        "source_permissions_independently_authenticated": False,
        "actual_source_audio_authenticated_by_this_gate": False,
        "human_preference_proven": False,
        "milestone_pass": False,
    }


def main(argv=None):
    class PrivateParser(argparse.ArgumentParser):
        def error(self, _message):
            # argparse normally echoes unrecognized options verbatim.
            # Untrusted options may carry private source names or tokens.
            self.exit(2, "MixLab study binding: invalid arguments\\n")

    parser = PrivateParser(
        description="Private frozen-study/pack metadata QA (not a music quality certificate)")
    parser.add_argument("study", help="private preregistered study manifest")
    parser.add_argument("pack", help="private frozen review pack root")
    parser.add_argument("--expected-study-id", required=True,
                        help="64-hex ID recorded outside the pack before rating")
    args = parser.parse_args(argv)
    try:
        result = verify_study_pack_binding(args.study, args.pack, args.expected_study_id)
    except (ValueError, OSError, KeyError, TypeError, IndexError, OverflowError):
        # Errors from private files or malformed metadata must not expose
        # paths, source IDs, rendered audio or private answer keys.
        parser.exit(2, "MixLab study binding: private inputs invalid or inconsistent\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
