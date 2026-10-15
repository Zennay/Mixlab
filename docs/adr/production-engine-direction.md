# Engine direction after the outside-in review — 15 October 2026

## Product decision

The durable product is an offline mix compiler, followed later by a reliable player. Given a permitted library and an event brief, it should produce a reviewed, reproducible set before the event. The event must not depend on a language model, network connection or expensive analysis finishing in real time.

A wedding adds requirements beyond good transitions: mandatory songs, excluded/explicit tracks, first-dance and speech slots, age/genre coverage, target duration, energy recovery moments and manual override. These belong to a typed event brief and hard planner constraints, not an unconstrained prompt. Live crowd adaptation remains a separate later product.

## Why the previous baseline could not reach that goal

The renderer consumed whole clips as millions of Python objects; it only accepted manually aligned equal tempos. Input validation lived inside the CLI. There was no reusable analysis contract/cache, no reliable separation between measured and human timing, and downloaded listener ratings had no strict aggregation path. Four rendered transition names alone did not demonstrate good mixing.

PR #9 implements the missing separations: bounded ingest, versioned analysis, streaming DSP, and checksum-bound evaluation. It deliberately retains the deterministic reference renderer to detect signal regressions. The same APIs can accept stronger providers without rebuilding the rest of the engine.

## Next musical implementation order

1. **Private reference library:** 20–50 permitted tracks with recording-level development/evaluation separation, varied steady/drifting tempos, vocals and genre boundaries; annotate beats, downbeats, phrase boundaries and useful intro/outro windows. Existing validator and schema now enforce the machine-verifiable portion.
2. **Analysis provider comparison:** measure a proven MIR provider against the built-in diagnostic baseline. Score tempo octave errors, beat precision/recall, downbeat errors and abstention rate. A confidence field is not evidence of calibrated correctness.
3. **Tempo and phrase alignment:** adopt a tested pitch-preserving time-stretch backend behind an explicit transform contract. Never use playback-rate changes disguised as beatmatching. Cap stretch ratio; record exact versions/settings; compare transients and vocals blind. Allow non-overlap transitions for large tempo jumps.
4. **Transition candidates:** generate several feasible arrangements at verified phrase windows. Use low-end exchange, vocal-overlap avoidance, energy handoff and optional stems only where stem artifacts are worth the benefit. Technical rejection precedes aesthetic ranking. No single score is allowed to hide clipping or uncertain timing.
5. **Candidate listening proof:** compare the same pair, duration and loudness policy; freeze a candidate before opening final ratings. The new aggregator binds judgments to actual audio bytes. Keep both-unusable and ties visible.
6. **Whole-set planning:** bounded beam search over segment/candidate edges, with event constraints, played duration after overlaps, artist/repetition spacing and a target energy curve. Compare against greedy and shuffled routes. Account for uncertainty and retain a safe fallback edge.
7. **Set compilation/player:** stream a full mix with a cue sheet, segment/transition hashes, quality receipt and replayable edit decisions. For events: pre-render, verify device output, preserve a backup playable file and provide manual pause/skip/override. A server benchmark is not event reliability proof.

## Deployment shape

One Python package with replaceable providers and explicit recipes; no microservice split or own-model training now. Originals, derived features, render artifacts and ratings have separate private directories. A content-addressed cache prevents repeat analysis. One CPU-bound batch process runs at low priority on the existing VPS; no permanent GPU service.

Ingest accepts only bounded PCM16 excerpts today. Full-track decoding/import, modern tempo conversion, automatic key/downbeat analysis, stems, creative arrangement and full sets are **not implemented by PR #9**. They need measured musical evidence. Do not market the current version as a replacement for a wedding DJ.

## Acceptance truth

Software completion, objective audio correctness, human preference and live-event reliability are four different claims. PR #9 can establish the first two only after its exact-source tests actually run. It cannot self-certify the last two.
