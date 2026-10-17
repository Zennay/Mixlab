# ML-07 · independent whole-reviewer influence validation

**Status:** opt-in offline quality diagnostic; M1 Transition Lab stays OPEN.

The frozen-pair sensitivity check already merged into `main` (PR #90)
measures what happens if one **whole source pair** is removed from a
tiny blind listening pilot. Pre-rating A/B placement checks (PR #88)
and post-rating A/B button-choice pattern checks (PR #89) are actively
owned separately. This independent check asks **another** question:
would the candidate's descriptive preference plurality disappear if
one **entire synthetic/human reviewer ballot** were omitted?

The stock `mixlab.evaluation.aggregate()` validates checksum-bound PCM
and correctly counts legal blind votes. Counting 15 rating clicks
across 5 song pairs should not hide the fact that only 3 reviewer
files contributed. Even with full trial coverage and checksum-valid
private WAVs, one reviewer may drive the reported preference.

## Computation and strict authority

Command:

```sh
python -m mixlab.quality.reviewer_influence study.json frozen-pack/ private-review-1.json private-review-2.json private-review-3.json --expected-study-id 64-hex-external-study-id
```

The checker:
1. requires 3–5 real reviewer files and an externally pinned 5–10-pair
   study; verifies the study and real PCM-bound frozen pack through the
   **existing** `verify_study_pack_binding`.
2. snapshot-hashes decoded reviewer data with the established bounded,
   no-final-symlink JSON reader; rejects untrusted PathLike arguments
   and duplicate lexical reviewer paths.
3. invokes **unchanged production** `aggregate(pack, all_reviews)`
   and separately invokes the same real PCM + audio-confound validator
   after removing each **whole** reviewer file, one at a time;
   rejects inconsistent aggregate/trial-group totals or audio warnings.
4. mathematically cross-checks that every review occurs exactly
   `n-1` times across all omission runs, rechecks original input
   snapshots and PCM/study binding before emitting a report.
5. returns only the full candidate fraction, smallest/largest
   leave-one-reviewer-out fraction, worst absolute percentage shift and
   anonymous Boolean flags. No reviewer identity, omit-index, track
   ID, private path, per-trial votes, pack hash or source audio is emitted.

Warning when the candidate's **strict >50%** plurality reverses on
one reviewer omission or the share changes by at least **20 percentage
points**; also warning when there are fewer than five decisive votes
or an official audio-confound warning. The heuristic is conservative
and arbitrary, not a significance test, accusation of unreliable
reviewers, assessment of independent personhood or a release rule.
A fully unanimous **synthetic** study can be *stable* under omissions,
but still proves nothing about musical quality.

Exit 0: no observed voter-omission sensitivity, **not M1 pass**.
Exit 3: methodological review needed, not a fraud finding.
Exit 2: inconsistent, unavailable or changed private evidence,
without private paths or secret arguments in stderr.

Always `milestone_pass:false`, `real_human_identity_verified:false`,
`source_rights_independently_authenticated:false`, and
`human_musical_preference_proven:false` regardless of outcome.

## Bounded, synthetic evidence

The isolated regression suite uses the current merged five-pair,
ten-WAV fully checksum-bound procedural PCM fixture, writes three
legitimate synthetic reviewer files, and reruns genuine official
aggregation four times for each valid case. It verifies that:

- with unanimous candidate synthetic ballots, 15/15 and all
  omit-one-reviewer runs remain 100% descriptive candidate share;
- with one candidate rater, one 3/5 candidate rater, and one baseline
  rater, the *pooled* candidate fraction is 8/15, but removing the
  candidate-only rater drops it to 3/10, reversing the plurality;
- a 20-percentage-point influence warning can appear even without
  changing the winning side; tie/unusable-only votes abstain;
- duplicate reviewer codes, wrong pack ID, changed JSON mid-analysis,
  tampered subset aggregates, hostile PathLike, symlinks, too few or
  too many raters, and failure-message privacy all fail closed.

The GitHub-hosted workflow runs exact trigger SHA code on Python
3.13 and 3.14 with 192MiB address-space budget; no real commercial
music, network service, production VPS CPU, queue/worker, personal
reviewer identities or other worker branch is touched.

## Known limits and handoff

Files in symlinked *ancestor* directories are addressed separately
in the live PR #87; the merged JSON reader currently forbids final
symlink, and operator inputs here must be in trusted directories until
that owner's integration lands. The pre- and post-check comparison is
not transactional against a malicious rapid swap-and-restore writer.

Rating pseudonyms do not prove unique human participants. Full-study
real rights, measured musical transitions, registered evaluator
hypotheses, genuine blinded human ratings and owner-reviewed release
acceptance are still OPEN. This CLI is opt-in: merging it does not
automatically affect M1, the evaluator, renderer or release gate.
