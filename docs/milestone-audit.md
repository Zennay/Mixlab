# Independent code review and milestone audit

Review date: 2 October 2026. Review scope: read-only inspection of `mixlab/cli.py`, `mixlab/engine.py`, `mixlab/models.py` and `ops/prove.py` in the founding implementation identified by the integration owner as commit `f089e0ddfc22347b7ccb08f88c5dfa6ec12663cf`. This is an independent reasoning review within the founding agent team, not an independent external certification. No tests, audio playback, deployment or resource measurement were performed by this reviewer.

The integration owner reports a VPS validation workflow committed in zCloud at `27c9b81dc2e27ed660c5bc6bb1a9814bd12e8815`. At initial inspection no execution evidence had been reviewed. The dated addendum below records subsequently fetched GitHub job status/logs and distinguishes the tested founding commit from later corrections.

## Observed implementation

The standard-library engine loads bounded PCM16 mono/stereo WAV files, requires matching sample rate/channel count and declared tempo, and renders equal-power baseline, filtered bass swap, echo exit or hard cut. It checks output does not overwrite inputs and records source/output hashes plus pre-quantization amplitude diagnostics. No tempo estimation, automatic beat alignment, key estimation, time stretching, source separation, discovery or set planning is implemented in the inspected scope.

The CLI generates original synthetic stereo fixtures, validates local source hashes/declared permission/provenance, renders private candidate outputs, and builds a browser listening pack with opaque A/B trial IDs and a separate private answer key. Review responses export locally as JSON. The code explicitly labels the pack development-only, unnormalized and not listener-validated.

The proof runner intends to execute unit-test discovery and the fixture → validate → benchmark flow, then checks four renders, three trials and six listener WAV files. It captures workflow/commit environment values, child peak RSS, elapsed time and output hashes in sanitized metadata. Presence of this script establishes intended verification, not execution success. Expected test count reported by the integration owner is 17; this reviewer has not verified the test files, assertions, discovery count or runtime result.

## Findings at initial inspection

These findings preserve the initial review. See the addendum for corrections subsequently inspected; remaining benchmark/resource gates are unchanged.

| Priority | Finding | Implication and required action |
| --- | --- | --- |
| Before real ratings | Ratings carry reviewer/trial IDs but no immutable pack or manifest ID. Trial IDs restart for each pack. | Add a pack ID derived from frozen study inputs/assignment and include it in exported responses; reject responses from another pack during aggregation. Until then, do not combine exports across runs. |
| Before milestone preference claims | The current pack compares all three candidate families against the baseline for every pair. The frozen pilot protocol specifies one preselected candidate per pair. | Treat this as development exploration. Implement a frozen candidate selection/study manifest before applying the pilot success rule; do not select the best observed family afterward and claim preregistered success. |
| Before reproducible studies | Seed/assignment version is not recorded in evidence or receipt; default assignment uses system randomness. The private answer key preserves the realized order. | Retain the private key and immutable pack identity; record assignment configuration privately so a study can be reproduced without leaking labels to listeners. |
| Before fuller library validation | `validate_library` does not instantiate/validate pair recipes or check segment bounds; invalid starts/beats or insufficient clip duration can pass `validate` and fail in `benchmark`. | Validate all pair recipes and ranges before output creation; distinguish metadata/source validation from complete render readiness until then. |
| Before budget acceptance | Maximum-sized stereo inputs expand from PCM into Python floats/tuples for both sources and output. A 32 MiB byte cap and 2M frame cap are not a 512 MiB memory guarantee. | Measure realistic and upper-bound cases on the runner; use chunking or lower bounds before accepting the proposed operating envelope. Synthetic-fixture RSS alone is insufficient. |
| Before a rights-complete artifact contract | CLI manifest permission is checked, but renderer metadata emits `rights_status: unknown`; core dataclass schemas and CLI manifest fields are distinct. | Consolidate adapters/schema and propagate explicit rights/provenance into canonical transition records. Do not claim the typed models currently enforce the full CLI pipeline. |
| Before musical-quality claims | Same gain does not ensure matched perceptual loudness; echo/filter families can differ in energy. | Preserve the existing limitation label and resolve/report loudness confounds before blind preference interpretation. |

No obvious integration blocker to the short synthetic path was found by inspection. This is not assurance that it runs; the designated VPS workflow must supply that evidence. The engine's explicit manual-alignment and unknown-rights output labels are appropriately cautious.

## Gate status at initial inspection

| Gate | Evidence inspected | Status |
| --- | --- | --- |
| Permitted source policy | Manifest requires a permitted declaration/provenance; synthetic fixture is original procedural audio | Policy implemented; real library absent from reviewed evidence |
| Canonical Track/Segment/TransitionCandidate | Dataclasses exist; CLI uses a separate manifest representation | Partial integration; schema propagation follow-up open |
| Evaluation protocol | Written pilot protocol and development A/B export | Protocol specified; frozen study enforcement/identity and real ratings open |
| Reproducible renderer | Recipes/hashes and deterministic primitives present | Runtime and repeat-render evidence pending |
| Resource envelope | One-core affinity and nice value in proof script; RSS reporting intended | Proposed budget unverified; no memory cap demonstrated |
| M0 foundation | Core code and proof path exist | Do not close until observed successful execution and reproducibility evidence are linked |
| M1 Transition Lab | Four families and development listening pack scaffold | Open: real 20–50 permitted tracks, 5–10 pairs, analysis/key/stems, frozen blinded review and human proof absent |
| M2 discovery onward | No implementation reviewed | Not started/proven in this review |

## Evidence to append after execution

Append the actual repository SHA, workflow run URL/ID, final conclusion, discovered/pass/fail test counts, receipt hashes, measured elapsed time/RSS and reproducibility result. Keep this inspection-time assessment intact and add dated evidence; do not retroactively describe inspection as runtime verification. Publishing sanitized test results does not authorize publishing music, private paths, listener identities or answer keys.

## Addendum — first VPS proof and correction review, 2 October 2026

The reviewer independently fetched GitHub job `110799140663` logs and run `36994858704` job status via the connector. GitHub reports the proof job completed successfully; every reported job step succeeded. Logs bind the checkout and runtime SHA check to the original MixLab commit `f089e0ddfc22347b7ccb08f88c5dfa6ec12663cf`, identify runner `zcloud-vps-1` and host `vps-bb300bba`, and show the following evidence:

| Evidence | Observed result |
| --- | --- |
| Run | [36994858704](https://github.com/Zennay/zCloud/actions/runs/36994858704) |
| Tests | 17 tests, 7.403 seconds, `OK`; no reported failures |
| End-to-end synthetic proof | Four rendered families, three A/B trials; proof script checks six listener WAV files |
| Proof duration | 11.949 seconds |
| Child peak RSS | 62,876 KiB, approximately 61.4 MiB; synthetic fixture only |
| Manifest SHA-256 | `ce1bc31ef01d78edf727fec1081e5ce8698b6d1b677feaf7e92ff9beefacc76e` |
| Sanitized artifact | [11220969408](https://github.com/Zennay/zCloud/actions/runs/36994858704/artifacts/11220969408), upload confirmed in job logs |
| Artifact ZIP hash reported by upload step | `4d14b51389131e8439f7941f4da16c650b296fc8cbb90840c8d82a7ff91bc752` |
| zSSH continuation | SQLite API response confirmed `zssh-mixlab-foundation-integration-20261002`, project `zssh`, status `queued` |

The artifact ZIP itself was not downloaded by this reviewer; its ID/hash are observed upload-log evidence. Queue acceptance proves durable dispatch was confirmed by the SQLite-backed API at that time, not that integration or deployment has completed. Run logs show synthetic hashes/aggregate evidence uploads, not permission to distribute real music.

The reviewer also read `tests/test_engine.py`. Its determinism test compares two rendered WAV byte sequences and hashes for every family, and the corresponding test is marked successful in the fetched job logs. This establishes repeat-render behavior for the tested synthetic cases on that runtime. It does not establish every input/platform combination or musical quality.

### Corrections inspected after the tested commit

Read-only reinspection of the latest local `mixlab/cli.py` and `tests/test_cli.py` confirms:

- A SHA-256 `pack_id` incorporates the source manifest hash, realized answer assignments and output hashes. It is included in private evidence, receipt, HTML form and rating-export JSON. The test checks its presence/length and HTML inclusion. Future aggregation must still enforce pack matching and duplicate-vote rules; no browser-executed export test was reviewed.
- Private evidence now records randomization mode and seed, with the realized answer key retained separately from listeners.
- Pair recipes are instantiated during library validation, before destination creation. An added test rejects boolean beat counts and verifies no output directory remains. Source-duration/segment-bound validation still happens during rendering, so complete render-readiness preflight remains open.
- Renderer evidence now records each source's explicit permission declaration. Core `rights_status: unknown` remains conservative; a consolidated canonical schema adapter and derived-output permission policy are still future work.

These corrections were not part of run `36994858704`. At this addendum's writing their second run is pending evidence; the first run must not be presented as their verification.

### Updated conclusion

The original founding commit has observed successful VPS execution and synthetic reproducibility evidence. Its M0 engineering foundation is materially demonstrated. Final M0 closure should be tied to the corrected commit's successful rerun and an explicit integration-owner acceptance of the canonical schema/protocol scope. M1 remains open: no permitted real library, frozen human study result, measured analysis/key/stem deliverables or musical preference proof was inspected. The approximately 61.4 MiB synthetic RSS result does not close the proposed 512 MiB envelope for maximum-sized real inputs. Frozen one-candidate-per-pair selection and loudness-confound handling remain mandatory before milestone preference claims.
