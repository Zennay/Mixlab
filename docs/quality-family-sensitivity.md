# ML-07 — Independent family-stratified blind preference QA

## Problem and scope

MixLab's genuine checksum-bound `aggregate()` reports a single candidate preference fraction. That descriptive average may hide one failing transition family alongside one successful family. This opt-in **read-only** post-rating preflight checks family concentration, tiny-sample sensitivity, and inappropriate significance claims without modifying the official renderer, frozen study, evaluator, CLI, queue, or music.

## Run

```sh
python -m mixlab.quality.family_sensitivity STUDY.json PACK_DIR RATER1.json RATER2.json RATER3.json --expected-study-id PINNED_SHA256
```

Inputs are **private**. The gate calls the real `verify_study_pack_binding()`, the real `aggregate()`, compares the families in the original pinned study to the counted official family rows, and revalidates the pinned study and pack. A synthetic six-gate approval or metadata-only mock does not replace source PCM validation.

- Exit 0: no additional **family-pattern** review by these limited criteria, **not** M1 success.
- Exit 3: HOLD: likely underpowered, family imbalanced, opposing, confounded or otherwise sensitive evidence.
- Exit 2: invalid or changed private data; no path/track/listener diagnostic is emitted.
- JSON contains only anonymous group indices, counts and conservative reference statistics; never filenames, pair names, identity hashes, answer positions, IDs, or PCM.

## Statistical interpretation

The diagnostic uses pair-level majority signs, not the false assumption that three votes on the same pair are three independently sampled music pairs. It calculates a one-sided conditional sign-tail for every **configured** candidate family (`bass_swap`, `echo_exit`, `hard_cut`), Bonferroni-adjusts for all three opportunities to claim a family winner, then computes the worst one-pair omission. It checks whether all families have representative pairs and identifies opposite pair-majority directions. Multiple choices among families, lack of sample size, reviewer correlation, source-selection effects, audio confounds, unsigned music rights, and blind preference validation remain independent limitations.

Five to ten pairs spread over three families are usually too sparse to establish a stable family-level signal. **HOLD is expected**, not a demand to unfreeze a study or retrospectively select winning pairs. A nominal p-reference from this toy model is **not a validated p-value for real music or a proof of superior DJ performance**. Every output retains `milestone_pass=false`, `musical_preference_proven=false` and `listener_independence_authenticated=false`.

## Independent synthetic + original-M1 integration evidence

`tests/test_quality_family_sensitivity.py` checks loss-vs-win strata, selection concentration, familywise multiplicity, leave-one-pair fragility, ties/unusable responses, reviewer pseudo-replication, untrusted aggregation structure, and privacy. Crucially it also creates the official checksum-bound five-pair PCM fixture, produces three complete private review ballots, and invokes the **real official aggregate and frozen-study verifier**, with wrong pin, mutated audio, missing vote, family reassignment, invalid paths and CLI exit/redaction negatives.

`.github/workflows/ml07-family-sensitivity.yml` runs the new suite under Python 3.13 and 3.14 on GitHub-hosted runners at the exact PR SHA, plus existing canonical quality and CLI privacy suites, inside a 192MiB virtual-memory cap. All audio is procedural; no real music, external package, model, VPS CPU/RAM, queue, shared lease, service or deployment is touched.

This is an independent ML-07 draft. ML-05 still owns the frozen study/aggregation contract, and independent integrator review and live owner coordination are needed before merge. The M1 human listening/rights gates remain open.
