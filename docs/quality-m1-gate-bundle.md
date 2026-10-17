# ML-07 · One-command private M1 quality bundle

## Purpose

A frozen pilot could previously run **some** independent checks while accidentally
omitting the others. This additive runner requires five gates in one command:
the external-ID-pinned WAV+answer-key study binding, private A/B assignment
balance, A/B response-position sensitivity, pair-level leave-one-out sensitivity
and full leave-one-reviewer-out stability. It cross-checks the trial and reviewer
counts, rejects contradictory audio-confound reports, and refuses modified study,
receipt, evidence, answer-key or ballots before/after the scan.

No existing evaluator, renderer, study producer, zCloud scheduling or shared
contracts are altered. This is **ML-07 quality-validation only**.

## Private-only invocation

```bash
python3 -m mixlab.quality.m1_gate_bundle \
  /private/study.json /private/frozen-pack \
  /private/ratings-01.json /private/ratings-02.json /private/ratings-03.json \
  --expected-study-id '<64-hex-preregistered-study-id>'
```

Use **3–5** consented, independent listeners and **5–10** preregistered pairs.
Original media, review WAVs, answer keys and individual ballots MUST remain
on a private machine. Do not attach them to GitHub issues, CI, artifacts or
Notion. The expected study ID must be committed *outside* the mutable study
pack before participants listen. Reviewers are pseudonyms, not proof of
independence. Do not apply this runner to live human data on public runners.

Exit contract:

- `0` = all mandatory technical checks ran and none requested methodological
  review; **NOT** permission to declare musical quality, rights or M1 success.
- `3` = technical or sampling review required.
- `2` = invalid, missing, inconsistent or observably mutated private evidence.

Only aggregated flag names and counts appear in stdout. Error messages never
print input paths or reviewer pseudonyms. No secret assignment, preference
score, family result, private source hash or original recording is included.
These checks are bounded by existing component limits, with no new network,
model, DSP, transcode, music ingestion or side effects.

This runner repeatedly rescans **real PCM** in the existing validators, so
use it on a private, idle CPU with frozen, immutable evidence. In-place swaps
and malicious byte swaps restored between checks are not prevented by these
read-only guards. Source rights, independent human identity, perceptual
loudness parity and blinded listener preference remain external release gates.

## Listener uncertainty is not invalid data

The position screen deliberately represents its A/B-dominance result as a
**tri-state** field. At least **12 decisive A/B votes** are required before a
position-dominance estimate is meaningful:

- **12 or more decisive responses:** the position flag must be a real boolean
  (`true` or `false`). Missing/unknown here means invalid evidence.
- **0–11 decisive responses:** the position flag must be `null`; the technical
  bundle returns `REVIEW_REQUIRED` (exit **3**), not corrupted-data exit 2.
- Every trial can validly be marked `Tie` or `Both unusable`; these are
  complete, admissible ratings but contain no decisive A/B preference.
- The positional vote count must equal the independently re-aggregated
  candidate+baseline count. A conflicting, boolean-spoofed or impossible count
  is rejected, even if the individual component reports superficially pass.

This matters for honest pilot reporting: uncertainty, ties and unlistenable
pairs are **methodological holds**, not evidence that listeners failed to
submit valid forms. A low-information technical hold cannot prove the
candidate beats simple crossfade.

New end-to-end synthetic-PCM regression cases exercise **3, 4 and 5
reviewers** submitting valid all-Tie and all-Both-unusable ballots,
mixed low-information ballots, exact **11/12** decisive threshold,
a real CLI exit-3 outcome, contradictory post-validation vote counts
and forged decisiveness statuses. No real human evidence is used.

## Deterministic QA without uploading private music

```bash
python -m unittest discover -s tests -p 'test_quality_m1_gate_bundle.py' -v
```

The synthetic fixture creates its own tones and synthetic ballots locally.
It proves **composition and fail-closed behavior**, not preference accuracy.
`mixlab.quality.m1_gate_bundle` is intentionally an opt-in module rather
than a replacement for the integrated MixLab CLI.

## Gate and ownership

Owns only this newly added module, test suite, workflow and document.
Do not merge around active ML-02/03/04/05 shared scopes without the integration
owner's review and live zCloud owner/lease coordination. Keep PR draft until
the exact-head hosted synthetic test matrix and independent review complete.
M1 is **OPEN**, `milestone_pass=false` irrespective of technical outcome.
