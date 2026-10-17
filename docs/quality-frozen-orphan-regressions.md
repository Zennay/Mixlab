# ML-07: frozen-study orphan-render quality regressions

Status: **independent QA regression suite**, not a new renderer, pilot gate,
source proof or human listener result.

## Observed integration risk

The in-flight ML-05 study-pack branch PR #71 exposes
`verify_study_pack()`, which groups private render metadata by
`study_pair` and checks the two expected rows for each study pair.
Its final loop does **not** require that *all* rows in the private render
inventory belong to these groups. A study pack with an extra unselected row,
and appropriately updated private pack/receipt hashes, can pass that isolated
structural check if the extra row is ignored. This is not a bypass of the
separate fully composed ML-07 admission or proof of actual sound quality.

The existing merged `mixlab.quality.study_binding._preflight_render_claims()`
does require precisely two outputs for each frozen 5–10 pair study, with
no unknown or duplicate study-pair identity, and validates the
preselected baseline/candidate recipe and source hashes **before PCM work**.

This add-only PR locks down that important distinction using ten synthetic
unit tests and multiple mutation subcases: one orphan with an unknown study
ID, third render in an expected pair, reassigned render (same count),
family replacement, source-identity substitution, asymmetric gain,
privacy of errors and *zero* calls into the private PCM scanner.

No WAVs, copyrighted music, renderer, shared evaluation modules or zCloud
worker claims are accessed or modified. The tests exercise *only* metadata
admission and cannot verify real source licensing, PCM integrity or a
listener's preference. They belong alongside, not instead of, the existing
`verify_study_pack_binding` and composed PR #84 pilot gate.

## Integration requirement

An eventual ML-05 frozen pack **must not be called valid on the strength of
PR #71's standalone structural check alone**. The ML-05 owner should either
reject unknown/extra render rows in its own verifier, or enforce the already
existing exact-two-row ML-07 binding as a compulsory downstream gate.
The frozen study ID must be pinned independently *before* ratings, and
review HTML, PCM hashes and permissions require their separate checks.

CI on GitHub-hosted runners checks the exact triggering SHA with
Python 3.13/3.14 under a 192MiB virtual-memory cap. No VPS render or queue
mutation is permitted while the active MixLab worker holds its lease.
