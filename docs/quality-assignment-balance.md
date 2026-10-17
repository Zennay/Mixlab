# ML-07 — private side-assignment confound preflight

Status: isolated opt-in **quality-validation** candidate, not an integrated
release gate. M1 is open. This check can identify A/B *presentation-order*
imbalance **before listening**. It cannot establish that listeners were
blinded, that audio was lawful, that A/B sounds good, or that reviewers prefer
one transition. It never outputs per-trial labels or the private answer key.

## Motivation and actual reproducible failure mode

The current ML-05 frozen-study renderer uses one independent
`rng.shuffle(["baseline", candidate])` for every trial. It does not enforce
side-position balance. Even a fully valid, pinned five-pair checksum-bound
pack can place baseline on side A **all five times**; all WAV digests and
`verify_study_pack_binding` remain valid. A/B presentation bias may then
be confounded with observed preference.

This new add-only checker explicitly holds when (a) total A/B assignment
differs by more than one, (b) *within any candidate family* assignment differs
by more than one, or (c) three or more successive baseline assignments
appear on the same side. These are conservative *study-design*
diagnostics, **not** a statistical significance claim. Since small-study
randomness can naturally produce such a sequence, a HOLD means review and
regenerate a new **pre-registration before collecting ratings**; it does not
mean that already-collected ratings are invalidated by this check.

## Usage (private local study and pack only)

```sh
python -m mixlab.quality.assignment_balance study.json pack/ --expected-study-id <externally-pinned-64-hex>
```

Exit 0: independently pinned current study/PCM checks passed and no
configured side-position flag. Exit 3: verified pack has a potential
side-position confound; review protocol before listening. Exit 2: invalid,
inconsistent or changed inputs, with private paths withheld.

Every report has `milestone_pass: false`; output contains only boolean
diagnostics and trial count. The checker invokes the real
`verify_study_pack_binding` against the independent pinned ID, and
compares the read answer-key data before/after that verification to refuse
observable changes. Source audio remains local. Like upstream local pack
verification, this is **not atomic storage** under a malicious concurrent
writer; keep frozen study/pack immutable and use the separately implemented
full-path admission before public reviewer release.

## Synthetic proof

`tests/test_quality_assignment_balance.py` reuses the already-merged real
5-pair/10-WAV PCM16 fixture. It actually swaps A/B **WAV contents**, updates
the private answer key, recomputes the official pack ID from true manifests,
answers and WAV output hashes, and proves that the real `verify_pack`
continues to accept a 5:0 skew, a 3-run with balanced totals and a
family-specific skew with balanced totals. The opt-in checker flags each;
correct assignment passes. Also tests invalid commitment, mutation during
validation, malformed/oversized inputs and private CLI redaction.

Workflow is GitHub-hosted Python 3.13/3.14, immutable PR-SHA checkout and
192 MiB address-space limit. No permanent VPS, live workers, data transfers,
queue/lease, production services, music downloads or deployment.

## Integration handoff

The owner of ML-05 study selection/randomization should consider assigning
sides with a constrained balanced schedule *before* the frozen pack ID and
private answer key are finalized (not after ratings). Re-run the independent
PCM/study gate when adopting this checker. Do not move the producer,
canonical evaluator or other open QA PRs from this branch without explicit
scope transfer and review.
