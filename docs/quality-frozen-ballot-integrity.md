# ML-07 · Cross-gate frozen ballot integrity (technical QA)

**Scope:** isolated tests and a dedicated Python workflow. The production
review-form generator, renderer, frozen study protocol, official evaluator,
aggregate reports and all other workers' PRs are untouched.

## Real checks exercised with synthetic sources

The fixture creates an actual immutable checksum-bound five-pair/ten-WAV
procedural PCM16 listening pack, pinned study metadata and three fictional
reviewers. Four publicly shipped opt-in gates are called:

* Pre-rating A/B side allocation is intentionally independent of ballots.
* Post-rating A/B-button response screening invokes the official aggregator.
* Post-rating whole-pair sensitivity invokes pinned study + official aggregator.
* Post-rating whole-reviewer sensitivity invokes pinned study + repeated
  official aggregates for each omitted reviewer.

The extra integration matrix proves that **all three rating-consuming gates**
reject: a different pack ID, reviewer pseudonyms that the ingest grammar
refuses, case-insensitive duplicate reviewers, boolean schema versions, a
missing trial, a duplicated trial, a foreign trial and invalid preferences.
The same input with a repeated ballot file path is also rejected. Four further raw JSON corruptions (trailing second document, duplicate object key, nonfinite JSON token and invalid UTF-8) plus a symlinked ballot path are independently rejected by each of the three rating-consuming gates. The
pre-rating screen deliberately remains able to inspect the unchanged frozen
answer key: it must never be misinterpreted as post-rating admission.

Positive controls: valid three-reviewer ballots succeed without approving
M1; all-tie ballots are admissible but do not establish a candidate winner.
Every rejection is checked for anonymity and for no mutation to the private
receipt, answer key, evidence or ratings. These checks use the real
evaluator's WAV checksum verification, never a mocked verification result.

## Evidence and limitations

Run locally only on independently permitted execution resources, or review
the exact-head GitHub Action `ml07-frozen-ballot-integrity.yml`.
This SHA-pinned Python 3.13/3.14 workflow uses a 192 MiB process
address-space limit, stdlib tests and original procedurally generated WAVs.
GitHub-hosted synthetic QA is **not** evidence of VPS renderer performance;
the canonical resource/production runner proof remains a separate concern.

This regression closes no M1 audio quality or statistical power gate.
There are no licensed real songs, proved source permissions, verified human
identity, blinded independent music preferences, measured beat/key accuracy,
DJ endorsements, or release/deploy changes. Keep the work on a separate
draft branch until independent owner review and live zCloud queue lease
coordination. No shared SQLite claim, VPS job or worker concurrency change
is authorized by these tests.
