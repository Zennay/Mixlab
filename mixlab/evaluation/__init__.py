"""Strict aggregation for existing private blind packs. No musical self-score."""
import hashlib
import json
from pathlib import Path
import re
from ..ingest import inspect_wav_and_digest
from .json_admission import load_bounded_json as _load

CHOICES = {"A", "B", "Tie", "Both unusable"}


# Reuse the independently validated, single-FD, regular-file-only admission
# primitive.  stat(path) followed by Path.read_text() could block forever on
# FIFOs, race with a replacement file and read beyond the original size check.


def verify_pack(root):
    root = Path(root)
    receipt = _load(root / "receipt.json")
    evidence = _load(root / "private/evidence.json")
    key = _load(root / "private/answer-key.json")
    if not isinstance(receipt, dict) or not isinstance(evidence, dict) or not isinstance(key, list):
        raise ValueError("Invalid pack structure")
    # The public receipt must describe the same manifest and schema as the
    # private listening evidence. Without this, public provenance can be
    # silently relabelled while the pack-id still verifies private data.
    if (type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] != 1
            or type(evidence.get("schema_version")) is not int
            or evidence["schema_version"] != 1):
        raise ValueError("Invalid frozen pack schema")
    manifest_sha = evidence.get("manifest_sha256")
    if (not isinstance(manifest_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha)
            or receipt.get("manifest_sha256") != manifest_sha):
        raise ValueError("Frozen pack manifest identity mismatch")
    # The producer emits an *unvalidated* frozen listening pack. Human
    # listening approvals belong to separate reviewed rating evidence,
    # never to an editable public receipt status outside pack_id hashing.
    if receipt.get("status") != "rendered-not-listener-validated":
        raise ValueError("Invalid frozen pack status")
    renders = evidence.get("renders")
    if not isinstance(renders, list) or not renders:
        raise ValueError("Missing render evidence")
    # A validated library contains no more than ten registered pairs.
    # Current renderer produces one baseline and three variants (at most
    # forty source renders and thirty blind trials). Bound both JSON arrays
    # *before* hashing or opening any private listening audio.
    if not 1 <= len(key) <= 30 or len(renders) > 40:
        raise ValueError("Frozen pack trial/render budget exceeded")
    identity = {"manifest": evidence.get("manifest_sha256"), "answers": key,
                "outputs": [r["output_sha256"] for r in renders]}
    pack_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if evidence.get("pack_id") != pack_id or receipt.get("pack_id") != pack_id:
        raise ValueError("Pack identity mismatch")
    # JSON floats with integral values compare equal to ints (3.0 == 3),
    # and bool is a subclass of int. Neither is valid provenance for frozen
    # experiment counts: insist on the actual JSON integer representation.
    if (type(receipt.get("trial_count")) is not int
            or type(receipt.get("render_count")) is not int
            or receipt["trial_count"] != len(key)
            or receipt["render_count"] != len(renders)):
        raise ValueError("Pack count mismatch")
    render_by_pair = {}
    for row in renders:
        pair, family = row["pair"], row["family"]
        if (pair,family) in render_by_pair:
            raise ValueError("Duplicate render identity")
        render_by_pair[pair,family] = row
    trials = {}
    candidate_trials = set()
    for row in key:
        tid = row.get("trial")
        if not isinstance(tid, str) or not re.fullmatch(r"trial-[0-9]{3}", tid) or tid in trials:
            raise ValueError("Invalid or duplicate trial")
        if row.get("A") == row.get("B") or sum(row.get(label) == "baseline" for label in ("A","B")) != 1:
            raise ValueError("Trial must compare baseline with one candidate")
        # Different trial IDs must not disguise a repeated selection of the
        # same candidate for the same pair: otherwise one render can receive
        # multiple independent-looking preference votes in the pilot.
        candidate = row["B"] if row["A"] == "baseline" else row["A"]
        pair = row.get("pair")
        if not isinstance(pair, str) or not isinstance(candidate, str):
            raise ValueError("Invalid pair or candidate")
        selection = (pair, candidate)
        if selection in candidate_trials:
            raise ValueError("Duplicate candidate trial identity")
        candidate_trials.add(selection)
        for label in ("A","B"):
            reference = render_by_pair.get((row.get("pair"),row[label]))
            if reference is None:
                raise ValueError("Trial references missing render")
            wav = root / "review" / f"{tid}-{label}.wav"
            # Render integrity must be checked on a bounded regular PCM16
            # descriptor, not with the unbounded digest(path) iterator:
            # a replaced review WAV could otherwise block on a FIFO or
            # consume unbounded bytes before rejecting the frozen pack.
            if inspect_wav_and_digest(wav)[1] != reference["output_sha256"]:
                raise ValueError("Listening audio changed after pack freeze")
        trials[tid] = row
    return receipt, evidence, trials


def aggregate(root, rating_paths):
    receipt, evidence, trials = verify_pack(root)
    if not 1 <= len(rating_paths) <= 100:
        raise ValueError("Expected 1–100 reviewer files")
    reviewers, rows = set(), {}
    for path in rating_paths:
        vote = _load(path)
        if not isinstance(vote, dict) or type(vote.get("schema_version")) is not int or vote["schema_version"] != 1:
            raise ValueError("Invalid rating schema")
        if vote.get("pack_id") != receipt["pack_id"]:
            raise ValueError("Ratings belong to a different pack")
        reviewer = vote.get("reviewer")
        if not isinstance(reviewer, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", reviewer):
            raise ValueError("Invalid reviewer pseudonym")
        normalized = reviewer.casefold()
        if normalized in reviewers: raise ValueError("Duplicate reviewer")
        reviewers.add(normalized)
        ratings = vote.get("ratings")
        if not isinstance(ratings, list): raise ValueError("Ratings must be a list")
        seen = set()
        for rating in ratings:
            if not isinstance(rating, dict): raise ValueError("Invalid rating")
            tid, preference = rating.get("trial"), rating.get("preference")
            if not isinstance(tid, str) or tid not in trials or tid in seen:
                raise ValueError("Duplicate or foreign trial")
            if not isinstance(preference, str) or preference not in CHOICES:
                raise ValueError("Invalid preference")
            seen.add(tid)
            trial = trials[tid]
            candidate = trial["B"] if trial["A"] == "baseline" else trial["A"]
            group = (trial["pair"],candidate)
            counts = rows.setdefault(group, {"candidate":0,"baseline":0,"ties":0,"both_unusable":0})
            outcome = ("ties" if preference == "Tie" else "both_unusable" if preference == "Both unusable"
                       else "baseline" if trial[preference] == "baseline" else "candidate")
            counts[outcome] += 1
        if seen != set(trials):
            raise ValueError("Incomplete reviewer coverage")
    summaries = [{"pair":p,"candidate_family":f,**counts} for (p,f),counts in sorted(rows.items())]
    total = {key:sum(r[key] for r in summaries) for key in ("candidate","baseline","ties","both_unusable")}
    decisive = total["candidate"] + total["baseline"]
    # Re-scan the bound listening files instead of trusting editable metric JSON.
    from ..quality import compare_wavs
    confounds = []
    root = Path(root)
    for tid, trial in trials.items():
        base_label = "A" if trial["A"] == "baseline" else "B"
        other_label = "B" if base_label == "A" else "A"
        result = compare_wavs(root/"review"/f"{tid}-{base_label}.wav",
                              [root/"review"/f"{tid}-{other_label}.wav"])["candidates"][0]
        if not result["level_comparable_for_blind_ab"] or result["warnings"]:
            confounds.append({"trial":tid,"warnings":result["warnings"]})
    # Private evidence.kind is editable metadata *outside* the frozen pack
    # identity hash. Do not let relabelling an all-synthetic source pack
    # suppress the explicit "not musical preference evidence" limitation.
    # This cross-check does not independently authenticate permission claims.
    all_synthetic = all(
        isinstance(row.get("metrics"), dict)
        and isinstance(row["metrics"].get("source_permission_declarations"), dict)
        and row["metrics"]["source_permission_declarations"].get("a") == "synthetic"
        and row["metrics"]["source_permission_declarations"].get("b") == "synthetic"
        for row in evidence["renders"]
    )
    multiple_candidates = any(sum(p == row["pair"] for p,f in rows) > 1 for row in summaries)
    limitations = ["RMS comparison is not perceptual loudness matching",
                   "listener identities are pseudonyms, not independently verified"]
    if multiple_candidates: limitations.append("exploratory multi-candidate pack; not a preselected single-candidate pilot")
    if evidence.get("kind") == "synthetic-smoke-only" or all_synthetic:
        limitations.append("synthetic input cannot establish musical preference")
    return {"schema_version":1,"pack_id":receipt["pack_id"],"reviewers":len(reviewers),
            "trials":len(trials),"counts":total,"non_tied_preferences":decisive,
            "candidate_preference_fraction":total["candidate"]/decisive if decisive else None,
            "per_pair_family":summaries,"audio_confounds":confounds,
            "limitations":limitations,"milestone_pass":False,
            "status":"descriptive-only-requires-independent-human-review"}


def main():
    import argparse
    parser=argparse.ArgumentParser(description="Aggregate a private, checksum-bound blind listening pack")
    parser.add_argument("pack")
    parser.add_argument("ratings",nargs="+")
    args=parser.parse_args()
    try:
        result=aggregate(args.pack,args.ratings)
    except (OSError,ValueError,KeyError,TypeError):
        # OSError/KeyError may carry private source paths or reviewer data.
        # Do not pass untrusted exception text to stderr.
        parser.exit(2,"MixLab evaluation: invalid or unavailable private input\n")
    print(json.dumps(result,sort_keys=True,allow_nan=False,indent=2))
