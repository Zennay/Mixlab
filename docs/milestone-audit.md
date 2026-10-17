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

## Independent ML-06 evidence reconciliation — 17 October 2026

**Audit boundary.** This dated addendum reconciles repository/PR metadata against the 2 October review; it is a source-and-release-evidence audit, not a fresh WAV playback, private artifact download, permanent-VPS execution, legal-licensing check, or blind human listening study. Keep earlier conclusions tied to their exact commits; do not retrospectively promote historical synthetic tests into live M1 proof. Source snapshot: **MixLab main `4224e2aeb640ea658404fca5483a8ae0e27cfa4b`** (GitHub branch API at this review).

### Verified immutable GitHub lineage and boundaries

| Workstream | GitHub lineage inspected | Evidence status / limitation |
| --- | --- | --- |
| ML-07 bounded pack resource admission | [PR #29](https://github.com/Zennay/Mixlab/pull/29), head `ed86f47051fd06b7f18f3bfc2d28c73cb1201b01`, **merged** `26e088191a6f0b04b33b044f75b4be99d7552e82` | The merged implementation declares a **512 MiB aggregate WAV** and **100,000,000 declared frames** pre-scan admission limit; this is a pack-size guard, *not* a measured maximum-RSS bound or musical-quality acceptance. |
| Frozen trial sequence | [PR #30](https://github.com/Zennay/Mixlab/pull/30), head `d16ab6fd6230c2cbdfbb112dc7d56a8a41bb71b1`, **merged** `2e5cbd76d4e2f17ec3cdc5384df4e1b23bc4de99` | Continuous `trial-001…trial-N` inventory enforcement is implemented according to PR source/acceptance description; it does **not** freeze the experimental hypothesis, treatments, listener assignment or answer key. |
| In-scan review-pack stability | [PR #31](https://github.com/Zennay/Mixlab/pull/31), head `caa904193b75e6636c4d16a012987d104af1f480`, **merged** `60503072cf261572494c9334849359b79fcb1f11` | Device/inode/size/mtime/ctime rechecks are best-effort evidence of ordinary replacement/edit **during** the scan; neither cryptographic signing nor protection from modifications *after* the check is demonstrated. |
| Attenuated flat-top signal warning | [PR #32](https://github.com/Zennay/Mixlab/pull/32), head `6306fa7a4527ba5d30ed9672131f81dff4bcd567`, **merged** `b2a6f2903e34927c1cbaede266092653fd979eb6` | Streaming inspection of high-amplitude equal-sample runs emits a diagnostic; it can flag legitimate sustained/square-like content and **must not** be called measured clipping or listener preference. |
| Cross-component synthetic regression | [PR #54](https://github.com/Zennay/Mixlab/pull/54), head `8c24ffdf962070d53d2047581fb1cb3367d57b5b`, **merged to present main** `4224e2aeb640ea658404fca5483a8ae0e27cfa4b` | A bounded companion suite intentionally excludes recursive `test_quality.py`; [reported exact-PR-head hosted check #38991771335](https://github.com/Zennay/Mixlab/actions/runs/38991771335) ran 68 quality and 49 companion synthetic test executions (117 total). The run outcome/count comes from the contemporaneous Notion handoff, **not** independent raw log inspection in this addendum; a merged-main full-suite check was not established here. |
| New private WAV/signed-swap hardening | [draft PR #55](https://github.com/Zennay/Mixlab/pull/55), **open/unmerged**, current head `d14ad04920377ffbb86116cff84192cd26464928` | Independent QA branch owns `mixlab/quality/` and private RIFF tests. Handoff's prior 149/149 hosted result belongs to **older** head `e2af6b238ad8b6bc9346fb7b28d30f41240f0f4c` ([run #38994013252](https://github.com/Zennay/Mixlab/actions/runs/38994013252)); do not transpose it to the newly observed head or main. |
| Other active implementation | [draft PR #40](https://github.com/Zennay/Mixlab/pull/40) HTML, [PR #56](https://github.com/Zennay/Mixlab/pull/56) CLI privacy, [PR #10](https://github.com/Zennay/Mixlab/pull/10) tempo backend, [PR #11](https://github.com/Zennay/Mixlab/pull/11) loudness | All remain open in the inspected PR inventory; independent branches are **not** landed capabilities or deployed/accepted release evidence. This audit does not modify their paths. |

### Reconciled milestone matrix (do not close M1)

| Original acceptance dimension | 17 October conclusion | Concrete next evidence |
| --- | --- | --- |
| M0 synthetic reproducible transition engine | **Evidenced for prior pinned code**, see 2 October immutable run `36994858704`; newer engineering source exists on main but no equivalent merged-main physical proof independently reviewed here | Bind fresh suite + renderer output hashes to **current main SHA**, record exact executor, elapsed time and RSS, and retain a sanitized receipt. |
| M1 analysis/downbeat/phrase/key/stems | **Partial/missing.** Existing measured regular-tempo/manual feature providers are not automatic key/phrase recognition or source-separated stems | Produce permissioned, reproducible real-track analysis with measured accuracy and explicit abstention; independent source/artifact provenance. |
| Bounded DSP and quality preflight | **Partially evidenced by merged source** (#29–#32, #54); current draft #55 remains provisional | Exact-current-head hosted acceptance for each merged change; real-VPS bounded memory/CPU proof for intended workload, not just synthetic baseline. |
| Frozen A/B design and musical improvement | **Missing human proof.** Opaque files, trial continuity, hashes and clipping warnings are engineering guards, not a controlled listener study | Freeze 5–10 legally permitted pairs and exactly one candidate per pair; independent answer key, loudness normalization/confound accounting and >=3 blinded human ratings before any preference claim. |
| Rights and privacy | **Partial only.** A declaration and private/public file separation are necessary but cannot establish lawful external rights | Independent rights review of real audio sources, derived stems, data retention and artifact publishing; never upload private source WAVs or listener identity. |
| Live portfolio admission/release | **Not evidenced.** MixLab Notion [PWQ-320](https://app.notion.com/p/3f89e19ac95581ccb671d029e380014d) still reports `Eligible NO` in the handoff | Do not infer runtime claims from issue/PR activity; require explicit authorized queue admission, service proof and relevant release ownership before VPS activation. |

**Disposition:** ML-06 remains **open** and M1 remains **not accepted**. The review identifies **more** bounded synthetic engineering evidence than the 2 October baseline but does not independently establish current-main physical acceptance, real-music quality, human blinded preference, rights clearance or an authorized production release. Next reviewer should fetch the latest immutable heads and actual GitHub logs again rather than treating this historical addendum as a continuously live status monitor.


## Follow-up — source-level recovery and exact-head proof, 17 October 2026

This **source-evidence-only** checkpoint updates the earlier snapshot `4224e2a`. All three observed changes are now **merged into canonical MixLab `main`**, which was `846f093aafe48198c6da4ab74932f93d72bdfef7` at this read. It does not replace the historical initial 2 October audit and proves neither worker runtime recovery nor listening preference. Source SHA and test outcomes below were independently retrieved from GitHub.

| Existing issue / root cause | Immutable source → main lineage | Hosted verification boundary |
| --- | --- | --- |
| [ML-03 #3](https://github.com/Zennay/Mixlab/issues/3) analysis cache trusted matching external `cache_identity` without verifying analysis payload/source/provider provenance | [PR #58](https://github.com/Zennay/Mixlab/pull/58), head `40194f03b11c93f211e2920f177549b27752a69d` → main `8bc1ad782f9f254efc6d51c1bb44a6edc478c96b` | Exact-head [38994941149](https://github.com/Zennay/Mixlab/actions/runs/38994941149) and [38994944255](https://github.com/Zennay/Mixlab/actions/runs/38994944255) **SUCCESS**: each 23 targeted tests and 133 full synthetic tests (65 companion included). |
| [ML-02 #2](https://github.com/Zennay/Mixlab/issues/2) WAV PCM metadata and declared source SHA derived from separate filename opens, subject to mixed-inode replacement | [PR #59](https://github.com/Zennay/Mixlab/pull/59), integrated candidate `1eba91dc1e36a8bd60e8349814354b3de17d5fe6` → main `e39826b9186891d9be941724c432eb575c529b19` | Exact-head [38995346686](https://github.com/Zennay/Mixlab/actions/runs/38995346686) and [38995349139](https://github.com/Zennay/Mixlab/actions/runs/38995349139) **SUCCESS**, 15 targeted and 140 full synthetic tests each (72 companion included). |
| [ML-02 #2](https://github.com/Zennay/Mixlab/issues/2) manifest preflight used `stat()` followed by unbounded `read_text()`; FIFO size 0 could block indefinitely; file growth/path swap could bypass the 1MiB size contract | [PR #60](https://github.com/Zennay/Mixlab/pull/60), source `4dde5fc99435affba952f784e5e9553a35008acf` → squash main `846f093aafe48198c6da4ab74932f93d72bdfef7` | [38996083220](https://github.com/Zennay/Mixlab/actions/runs/38996083220) **SUCCESS**, 30 manifest/ingest tests; [38996083409](https://github.com/Zennay/Mixlab/actions/runs/38996083409) **SUCCESS**, 15 targeted plus 150 full synthetic (82 companion) tests. Postmerge-main [38996190247](https://github.com/Zennay/Mixlab/actions/runs/38996190247) **SUCCESS** for bounded manifest ingest. |

**Scope and unresolved gates.** ML-02 and ML-03 are source hardening, not measured transition quality. Hash receipts are not signatures, metadata identity checks are not immutable filesystem snapshots, and these checks use original synthetic fixtures, not rights-cleared recordings. ML-07 active drafts [#55](https://github.com/Zennay/Mixlab/pull/55) and [#56](https://github.com/Zennay/Mixlab/pull/56) and independent [#40](https://github.com/Zennay/Mixlab/pull/40), tempo [#10](https://github.com/Zennay/Mixlab/pull/10) and loudness [#11](https://github.com/Zennay/Mixlab/pull/11) remain **unmerged** in this snapshot; their capabilities must not be claimed as main. Active MixLab [PWQ-320](https://app.notion.com/p/3f89e19ac95581ccb671d029e380014d) remains **Eligible NO** for live zCloud workers. Formal M1 remains **OPEN** pending permitted real-source library, independent downbeat/key/stem evidence and frozen blinded A/B with at least three human reviewers and defensible level confounds. No VPS/runner/release mutation, external audio upload, musical performance proof or authenticated rights validation occurred in this source-only checkpoint.
