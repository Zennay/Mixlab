"""Strict aggregation for existing private blind packs. No musical self-score."""
import hashlib
import json
from pathlib import Path
import re
from ..ingest import digest

CHOICES = {"A", "B", "Tie", "Both unusable"}
LOUDNESS_TOLERANCE_LU = 0.5


def _load(path):
    path = Path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Evaluation JSON exceeds 4 MiB")
    def unique(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError("Duplicate JSON field")
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def verify_pack(root):
    root = Path(root)
    receipt = _load(root / "receipt.json")
    evidence = _load(root / "private/evidence.json")
    key = _load(root / "private/answer-key.json")
    if not isinstance(receipt, dict) or not isinstance(evidence, dict) or not isinstance(key, list):
        raise ValueError("Invalid pack structure")
    renders = evidence.get("renders")
    if not isinstance(renders, list) or not renders:
        raise ValueError("Missing render evidence")
    identity = {"manifest": evidence.get("manifest_sha256"), "answers": key,
                "outputs": [r["output_sha256"] for r in renders]}
    pack_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if evidence.get("pack_id") != pack_id or receipt.get("pack_id") != pack_id:
        raise ValueError("Pack identity mismatch")
    if receipt.get("trial_count") != len(key) or receipt.get("render_count") != len(renders):
        raise ValueError("Pack count mismatch")
    render_by_pair = {}
    for row in renders:
        pair, family = row["pair"], row["family"]
        if (pair,family) in render_by_pair:
            raise ValueError("Duplicate render identity")
        render_by_pair[pair,family] = row
    trials = {}
    for row in key:
        tid = row.get("trial")
        if not isinstance(tid, str) or not re.fullmatch(r"trial-[0-9]{3}", tid) or tid in trials:
            raise ValueError("Invalid or duplicate trial")
        if row.get("A") == row.get("B") or sum(row.get(label) == "baseline" for label in ("A","B")) != 1:
            raise ValueError("Trial must compare baseline with one candidate")
        for label in ("A","B"):
            reference = render_by_pair.get((row.get("pair"),row[label]))
            if reference is None:
                raise ValueError("Trial references missing render")
            wav = root / "review" / f"{tid}-{label}.wav"
            if digest(wav) != reference["output_sha256"]:
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
    from ..loudness import measure
    from ..quality import compare_wavs
    confounds = []
    root = Path(root)
    for tid, trial in trials.items():
        base_label = "A" if trial["A"] == "baseline" else "B"
        other_label = "B" if base_label == "A" else "A"
        base_wav, other_wav = root/"review"/f"{tid}-{base_label}.wav", root/"review"/f"{tid}-{other_label}.wav"
        result = compare_wavs(base_wav, [other_wav])["candidates"][0]
        # RMS is only a fallback hint; integrated loudness decides level comparability.
        warnings = [w for w in result["warnings"] if w != "rms_level_mismatch_not_lufs"]
        loudness = [measure(base_wav)["integrated_lufs"], measure(other_wav)["integrated_lufs"]]
        delta = None if None in loudness else round(loudness[1] - loudness[0], 3)
        if delta is None:
            warnings.append("integrated_loudness_undefined")
        elif abs(delta) > LOUDNESS_TOLERANCE_LU:
            warnings.append("integrated_loudness_mismatch")
        if warnings:
            confounds.append({"trial":tid,"warnings":warnings,"loudness_delta_lu":delta})
    kinds = {evidence.get("kind")}
    multiple_candidates = any(sum(p == row["pair"] for p,f in rows) > 1 for row in summaries)
    limitations = ["BS.1770-4 integrated loudness with sample peak; short-term loudness swings and true peak are not equalized",
                   "listener identities are pseudonyms, not independently verified"]
    if multiple_candidates: limitations.append("exploratory multi-candidate pack; not a preselected single-candidate pilot")
    if "synthetic-smoke-only" in kinds: limitations.append("synthetic input cannot establish musical preference")
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
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.exit(2,f"MixLab evaluation: {exc}\n")
    print(json.dumps(result,sort_keys=True,allow_nan=False,indent=2))
