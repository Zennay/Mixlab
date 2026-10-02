# MixLab architecture and proof boundaries

Status: founding implementation design, 2 October 2026. This document describes scope and acceptance criteria; it is not a runtime validation report.

## Product and current scope

MixLab's product is rendered musical transitions, eventually discovering surprising track/segment combinations and constructing coherent sets. M0 begins with a private, offline, deterministic transition engine and review artifacts. A synthetic audio fixture demonstrates the pipeline without requiring music downloads. It does not establish musical quality.

The initial Python standard-library implementation accepts explicit track metadata, segment positions and manually supplied BPM. Its implemented families are equal-power crossfade baseline, bass swap, echo exit and hard cut. Low/high frequency filtering is not source separation. Manual metadata is not MIR analysis. Equal BPM or declared compatible timing is not proof of measured beat/phrase alignment. Unsupported sample formats, channel layouts, tempo conversion and metadata must fail clearly rather than silently changing musical intent.

## Component boundaries

| Component | Responsibility | Evidence |
| --- | --- | --- |
| Source registry | Private local paths, provenance, permission declaration, content hashes | Machine-readable track manifest |
| Track and segment models | Audio format, bounded segment ranges, manual BPM and confidence/source metadata | Validated serialized inputs |
| Transition recipe | Input IDs, segment positions, family, duration and parameters | Versioned deterministic recipe |
| Renderer | Decode supported PCM, slice, apply deterministic operations, write private output | WAV plus recipe and hashes |
| Signal checks | Report measurable amplitude/length properties and invalid samples | Structured metrics with units |
| Review pack | Randomize baseline/candidate positions with reproducible seed | Listener pack and separate private answer key |
| Future analysis adapters | Beat/downbeat/key/stem providers behind stable contracts | ADR, reference dataset, measured errors |

Source paths and music remain private. Git contains code, schemas, synthetic fixtures and non-sensitive aggregate evidence. Derived metadata and private renders have separate lifecycle and permissions from source music. Permission to analyze locally does not imply permission to redistribute source or rendered audio.

## Reproducibility contract

Record commit SHA, recipe/schema version, input hashes, explicit metadata, randomization seed, output hash and signal metrics. Treat any recipe or input change as a new render. The same recipe and inputs on the supported runtime should reproduce the same PCM payload; container/header metadata must not create misleading hash claims. Evaluation responses refer to immutable candidate IDs, never mutable filenames alone.

## Frozen pilot evaluation protocol v0

Freeze the manifest, recipes, comparator and decision rule before opening evaluation responses. Use 20–50 permitted real tracks and 5–10 prespecified evaluation pairs, separate from development pairs. Record provenance and permission for each track; deduplicate alternate encodings before splitting. Reserve unseen tracks for later discovery evaluation. No tuning on frozen pairs; a change after listening requires a new benchmark version.

For each pair compare one preselected candidate with the simple equal-power crossfade baseline. Use matched context length and the same declared gain policy. Randomize A/B placement reproducibly per pair/listener; expose only opaque IDs and keep the answer key outside the listener package. Report peak/RMS diagnostics, and explicitly report whether perceptual loudness matching was performed. RMS alone is not perceptual loudness. If loudness is materially different, record that confound and do not claim an unbiased preference win.

Collect at least three distinct listeners, preferably including an experienced DJ, who hear every pair without technique labels. Ask overall preference (A/B/tie), musical coherence, timing, smoothness, impact and surprise; collect an optional failure note. The first decision uses one recorded response per listener per pair. Replays are allowed; repeated responses cannot increase the sample count. Require complete review coverage and preserve the original responses.

Proposed pilot success rule: a meaningful subset means at least three pairs have strictly more candidate wins than baseline wins across listeners, at least 60% of all non-tied preferences favor candidates, and there are no unresolved major audible defects. Report ties, full denominators, listener count, pair count and individual pair outcomes. With this small sample, a pass is exploratory evidence, not a general performance claim or statistical significance. An independent Auditor OS review checks the frozen manifest, randomization, raw ratings and calculations before accepting the gate.

## Milestone gates

M0 is complete only after a permitted source policy, canonical Track/Segment/TransitionCandidate schemas, frozen protocol and reproducible renderer evidence exist. Merely committing these documents does not complete M0.

M1 remains open until the Notion roadmap's beat/downbeat/phrase analysis, key analysis, stem separation, 3–5 transition families, deterministic rendering and blind review deliverables are addressed with real audio evidence. Adapter stubs or manually supplied fields do not satisfy analysis/separation. If analysis or stems are intentionally deferred, Company OS must explicitly revise scope and Auditor OS must distinguish the revised milestone from the original M1.

Do not start full-set planning or live autonomous mixing because a synthetic test passes. M2 additionally needs non-obvious, automatically discovered pairs preferred by humans; handpicked benchmark pairs cannot prove discovery.

## Audit risks and controls

| Risk | Required control |
| --- | --- |
| Synthetic success mistaken for product proof | Label fixtures synthetic; keep real-audio and human gates open |
| Candidate louder than baseline | Declare gain policy; check and report loudness confounds |
| Selection or answer-key leakage | Freeze candidates; separate key; opaque listener IDs |
| Music appears in GitHub logs/artifacts | No source/real render upload; publish aggregate evidence only |
| Automatic heavyweight models consume VPS capacity | Separate ADR and install approval; no model downloads in baseline CI |
| Workers overwrite shared contracts | Scoped task ownership, dependency order, serial integration |
| Metric mislabeled as perceptual judgment | Distinguish measured DSP properties from listener preference |

## Source of product truth

- [MixLab HQ](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
- [Roadmap and definition of done](https://app.notion.com/p/3e79e19ac9558150a32cf32a96fb1f64)
- [Architecture, data and evaluation](https://app.notion.com/p/3e79e19ac9558173bf7df35b277f09a4)

Notion records decisions and evidence. zCloud's VPS SQLite queue owns execution state and assignments.
