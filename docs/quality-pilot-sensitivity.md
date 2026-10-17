# ML-07 — independent tiny-pilot pair-level sensitivity check

**Gate status:** optional / private quality-validation; M1 Transition Lab **OPEN**.
This tool does not produce a musical score, a listening preference proof or a
release approval. It checks whether the *descriptive* frozen listening tally is
fragile to dropping just one of its 5–10 **whole track pairs**.

## The actual problem

Official `mixlab.evaluation.aggregate()` correctly reports all valid
listener rating counts, but a small pilot with three ratings on each of
five pairs must not treat its 15 clicks as 15 independent recordings. For
example, a synthetic 5-pair pack with **15/15 candidate votes** also has
5/5 candidate-favored pairs: a one-sided fair-sign reference is 1/32
(3.125%) **only under strong assumed independence**. Dropping one entire
pair changes that reference to 1/16 (6.25%). An apparently good pooled
vote fraction is thus *fragile to one frozen pair*.

The checker treats each single preselected family/pair group as one
analysis unit and records only aggregate category counts. It computes:
- exact one-sided fair-sign binomial reference over decisive pairs;
- the largest reference after *each* possible single-pair removal;
- whether a nominal 5%-reference signal disappears after one omission;
- source-reuse abstention when two frozen pairs contain the same SHA-256
  recording, plus abstention for <5 decisive pairs or <3 pseudonyms;
- a separate audio-confound review flag from the actual official
  `aggregate()` output.

No independent source rights or reviewer identity is inferred. Reused
tracks could correlate signs; unrelated songs may *also* violate the
independence/exchangeability assumptions. The nominal 5% threshold is
a **sensitivity demonstration**, not valid preregistered statistical
significance, an M1 pass, or a hypothesis selected before observing
outcomes. Multiple families, tunings and repeated experimentation increase
false-positive risks. Even with 10/10 unanimous synthetic pairs, the
report always says `milestone_pass: false`.

The pure `inspect_pair_sensitivity(aggregation, source_reuse=False)`
function accepts only 5–10 distinct one-candidate-per-pair totals, exact
integer counts, strictly 1–16 reviewer files, and the actual aggregator's
immutable `milestone_pass: false` status. It refuses exploratory
multi-family pack counts rather than mislabelling them as a frozen pilot.
It outputs no source hashes, names, filenames, pack IDs, reviewer codes or
per-trial votes.

## Private execution

```sh
python -m mixlab.quality.pilot_sensitivity study.json frozen-pack/ rating-1.json rating-2.json rating-3.json --expected-study-id <64-hex-pinned-externally>
```

The wrapper first invokes genuine `verify_study_pack_binding` against an
independently pinned study identity and checksum-verifies private PCM. It
then runs unchanged official `aggregate()` and repeats the pinned
study/pack consistency check before evaluating the *pair-level* result.

- exit 3: pilot remains methodology-sensitive / insufficient / confounded;
- exit 0: descriptive reference survived one pair omission, **NOT M1 pass**;
- exit 2: invalid or changed private inputs; no private path is echoed.

This standalone check reuses current production JSON loading. Until the
separate *all-path-components no-symlink* gate in open PR #87 is integrated,
operators must restrict inputs to a trusted, non-adversarial filesystem;
the exact path-security boundary is **not** independently certified here.
The check is not transactional against malicious concurrent writes.

## Controlled proof and integration

Tests generate five genuine checksum-bound synthetic PCM WAV pairs/ten
outputs via the existing merged MixLab frozen-study fixture and feed three
valid independent *synthetic pseudonym* files to the actual MixLab
`aggregate()`. This is **not real human listening**. Additional pure
tests enumerate all candidate/baseline sign outcomes for 5–10 pairs
and reject forged aggregate totals, bool/float count confusion, duplicate
pairs, exploration, reused sources and unsupported insufficient data.

A dedicated GitHub-hosted Python 3.13/3.14 matrix checks out the immutable
candidate SHA, runs under a 192 MiB virtual address-space cap, and can also
run an exact pinned ML-05 producer integration in its own ephemeral checkout.
No production VPS, real commercial music, SSH escalation, queue/lease,
worker takeover, deployment or other PR source changes.

## Reproduced with the exact ML-05 study producer

The hosted workflow also checks out the actual independent ML-05 frozen
producer at `e512d8fc2eae79efe765dc9a523105fad68a196f`. Two
distinct **real-renderer**, genuine-`aggregate()` experiments run on both
Python versions without real recordings:

1. The producer's *existing* 5-pair fixture contains only **six original
   synthetic recordings**, which are reused within the allowed frozen
   protocol. Even with **15/15 generated candidate preference ratings**,
   independent-pair significance is not justified. The gate returns
   `shared_source_across_pairs_detected=true`, both references `null`,
   and a methodology HOLD. This is not a defect of the original producer;
   limited reuse was explicitly permitted by its selection protocol.
2. A freshly generated 10-track collection freezes five pairs with
   `max_track_uses=1`, renders ten genuine original WAV outputs and
   produces three synthetic reviewer files. Now source digests are all
   disjoint, and the exact 5/5 candidate-pair sign reference is 1/32.
   Dropping any *whole pair*, as opposed to one of its three repeated
   listener clicks, gives 1/16. The gate returns a sensitivity HOLD.

Even the disjoint ten-track run proves neither true human preference nor
independent *musical* sampling. It is a structural regression witness,
not a preregistered empirical significance result.

## Owner handoff

ML-05 owns preregistration and rating aggregation. ML-07 owns technical
quality thresholds. Any promotion requires owner review, actual 20–50
licensed/original tracks, real measured musical evidence, independently
blinded human listeners, adequate pair-level experimental design and
the coordinated PR #87 / #88 / #89 gates. Do not treat a small pilot's
nominal p-reference as certification of musical quality or independent
scientific evidence.
