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

## Process-argument privacy for real listening sessions

The preferred **local-only** CLI does not put private study paths, reviewer
file names, or the pinned study ID in process arguments. Supply a small
JSON request through stdin instead of constructing a command with those
values on the command line:

```bash
python3 -m mixlab.quality.m1_gate_bundle --private-input-stdin < /private/m1-request.json
```

The private input file, created **outside the repository**, must contain exactly
the four keys below. This is a shape example, **not** production evidence:

```json
{
  "study": "/private/study.json",
  "pack": "/private/frozen-pack",
  "ratings": [
    "/private/reviewer-01.json",
    "/private/reviewer-02.json",
    "/private/reviewer-03.json"
  ],
  "expected_study_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

Create and store the request only on a consented/private host with restrictive
permissions (for example, `umask 077` before creating it). Do not pass the
JSON itself to `echo`, shell history, GitHub Actions expressions, CI artifacts,
chat, Notion or stdout. Avoid public CI for live listening material.

The stdin parser reads **at most 32 KiB**, rejects duplicate JSON keys,
unexpected fields, malformed types, nonfinite JSON constants, invalid UTF-8,
and any mixture of stdin mode with positional paths/flags. It uses the same
frozen PCM/ratings verification and the same exit codes as the legacy CLI.
The legacy positional form remains available for existing synthetic scripts,
but it may disclose file paths through operating-system process listings.

This reduces command-line exposure; it does not protect against malicious
local root access, unsafe storage permissions or a compromised execution host.

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

## Maximum supported offline study stress

A separate **real-file** regression extends the existing five-pair synthetic
fixture to **ten frozen pairs / twenty distinct PCM16 WAVs** with new, unique
procedural sources and recomputed answer-key, source and pack commitments.
The exact official verifier must accept all ten pairs before the bundle runs.

Two full-size variants exercise **five pseudonymous ballots** (50 submitted
choices each): mixed candidate/baseline/Tie ratings and all
`Both unusable`. Both must complete the genuine private waveform checks;
the no-decision variant is a safe methodological HOLD, never invalid data.
No WAV or per-listener answer is copied to a CI artifact.

The bounded fixture is not a substitute for real-source provenance,
independent participants or listening evidence, and does not measure
real-world runtime for the maximum **2,000,000-frame per-source** case.
It does catch cardinality-dependent integration errors at the documented
10-pair / 5-reviewer maximum.

## Integration regression: dependency changes must re-run the full suite

The GitHub Actions workflow no longer watches only this module. On every
pull request to `main` and every `main` push touching one of the imported
quality gates or evaluation admission files, it re-runs the complete bundled
M1 quality integration **and** component regression tests.

The exact-commit, no-persisted-credentials Python 3.13/3.14 matrix runs:

- `test_quality_m1_gate_bundle.py` — genuine synthetic frozen PCM and ratings,
  both legacy and protected stdin invocation, no-preference exit, and privacy.
- `test_quality_composed_m1_gates.py` — independent cross-gate invariants.
- `test_quality_assignment_balance.py`, `test_quality_listener_position.py`,
  `test_quality_pilot_sensitivity.py`, `test_quality_reviewer_influence.py`,
  and `test_quality_study_binding.py` — underlying dependency regressions.

The workflow also watches dependency tests, changes to the private bounded JSON
loader and pack helpers, its own configuration and this documentation. A later
merge modifying a validator cannot silently skip the composition gate simply
because `m1_gate_bundle.py` itself was unchanged. `workflow_dispatch`
remains available for a deliberate integration re-run. A green technical
matrix is not M1 musical evidence and is not a substitute for a separately
approved integration/merge decision.

## Real maximum-frame A/B integration, resource proof and mutation safety

The exact-head GitHub-hosted Python 3.13/3.14 quality matrix includes a
**streamed two-source 2,000,000-frame, 96 kHz stereo WAV test**, plus the other
four canonical frozen pairs and three synthetic reviewer ballots. It rebuilds
genuine pack digests and executes **all five M1 gates** on the frozen study;
the result remains non-milestone and does not claim a human preference.

A second pass produces **2,000,001-frame** original WAVs with freshly
consistent JSON/pack commitments. The existing public scanner must reject the
over-limit source with the same anonymized invalid-input verdict. This verifies
actual admission rather than mocking the 2M limit or inventing unsafe giant
fixture bytes in memory. The test is a bounded, deliberately longer run:
approximately **111–117 seconds** for the full first suite per Python
version on hosted CI at the verified max case; peak RSS stayed below **31 MiB**.
The workflow has a hard 15-minute job ceiling and 192-MiB virtual-memory cap.

Independent mutation tests deliberately change, after the fifth real gate
returns, (1) original reviewed PCM bytes and (2) the private evidence JSON
file. The bundle must reject both before publishing any technical status,
without including a path or canary in the error. This proves detection of
**persistent observed changes**; it cannot protect against a malicious actor
that changes and restores the bytes between read intervals. Freeze the
filesystem when conducting real blinded human studies.

## Stop duplicated listening examples from counting as independent pairs

The external M1 gate does **not** treat the renderer's source-ID claims as
authentication of actual music: a source hash may be self-declared while
different supposed pairs reuse the exact same listening WAV. If identical
`output_sha256` commitments appear across two **distinct frozen pairs**,
the private, already-verified pack is admitted as *structurally valid* but the
combined technical result becomes `REVIEW_REQUIRED` with the anonymous
reason `identical-render-across-frozen-pairs`.

This extra check runs on the original, independently verified private render
metadata *only after* the existing freeze validator has hashed the actual WAV
files. It reports a boolean and a generic reason, never the original checksum,
audio bytes, trial names, pair IDs, track IDs or reviewer answers. Duplicate
content within a single pair is handled separately by baseline-vs-candidate
quality checks; the cross-pair rule does not mistake the two legal sides of
one trial for independent music examples.

The real-file regression deliberately copies the verified baseline WAV from
one frozen trial into a different trial, updates that render's actual SHA,
recomputes the genuine receipt/pack identity and resubmits three complete
synthetic ballots. Both upstream `verify_pack` and pinned study binding
still accept this checksum-consistent pack. The new cross-pair screen must
force a methodological HOLD instead of counting the repeated audio as
independent support. A separate unchanged distinct-WAV control remains
unflagged. Pure contract tests reject forged non-boolean flags.

**Limitation:** exact file-level checksum equality only. Different WAV
headers, equal PCM re-encoded in another container or perceptually identical
re-renders can evade this *fast* duplicate check. The study remains
source-rights- and human-independence-UNVERIFIED; a clear technical screen
is not a statistically or musically validated result.

## Gate and ownership

Owns only this newly added module, test suite, workflow and document.
Do not merge around active ML-02/03/04/05 shared scopes without the integration
owner's review and live zCloud owner/lease coordination. Keep PR draft until
the exact-head hosted synthetic test matrix and independent review complete.
M1 is **OPEN**, `milestone_pass=false` irrespective of technical outcome.
