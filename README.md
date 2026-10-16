# MixLab · Transition Lab

An offline AI-DJ research project: understand track segments, discover surprising combinations, render real transitions and eventually build full sets around context and an energy journey.

**Current phase: M0 foundation / partial M1 implementation.** Musical quality is unproven. This first slice uses manually aligned, equal-tempo excerpts; regular-tempo beat proposals and manual annotation providers are implemented, but automatic downbeat/phrase/key analysis, stems, discovery and set planning remain future work.

- [Notion project](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
- [Current handoff](https://app.notion.com/p/3e79e19ac95581f4bf15c26a833da642)
- [Architecture and evaluation](docs/architecture.md)
- [Infrastructure plan](docs/infrastructure.md)
- [Worker tasks and ownership](docs/worker-plan.md)

## Implemented

- Canonical Track, Segment, Recipe and TransitionCandidate records.
- Validated, checksum-bound local audio manifests with explicit permission declarations.
- Deterministic PCM16 mono/stereo renderer: equal-power baseline, bass swap, echo exit and hard cut.
- Peak, RMS, clipping, DC offset and sample-jump diagnostics; identical render length and common gain across recipes.
- Streaming ITU-R BS.1770-4 integrated loudness and per-pair, attenuation-only loudness matching of every A/B listening file (`python3 -m mixlab loudness <wav>...`).
- Original synthetic fixtures for reproducible infrastructure tests.
- Neutral A/B audio filenames, a local listening page, separate answer key and downloadable ratings.
- Strict streaming ingest with recording/PCM split-leakage checks and a JSON Schema.
- Replaceable analysis provider, measured regular-tempo proposals, manual cue/key annotations, content-addressed private feature cache and beat-error evaluation.
- Streaming transition renderer with exclusive complete-file publication, clipping rejection and post-PCM metrics.
- Checksum-bound rating aggregation with duplicate/coverage validation and explicit volume confounds.
- No runtime dependencies beyond Python 3.10+ standard library.

## Reproduce on the VPS runner

Shell/build/test/render execution goes through the existing GitHub self-hosted runner on `vps-bb300bba`. Do not provision another server or install models for this slice.

```bash
python3 -m unittest discover -s tests -v
python3 -m mixlab fixture /tmp/mixlab-example-library
python3 -m mixlab validate /tmp/mixlab-example-library/library.json
python3 -m mixlab benchmark /tmp/mixlab-example-library/library.json /tmp/mixlab-example-pack --seed 42
```

Use fresh output directories; existing packs are never overwritten. Open `review/index.html` locally. Only the `review/` directory goes to listeners; `private/` contains identity mappings, recipes, source paths and metrics. Omit `--seed` for real listening pilots. The synthetic fixture is **not** a music benchmark.

Supported input: short uncompressed PCM16 WAV excerpts, identical channel count/sample rate (8–96 kHz), manually verified equal BPM and corresponding starting beats. Input caps are 32 MiB and 2 million frames per excerpt. Prepare excerpts privately; full-track decoding and tempo stretching are not implemented. The benchmark renderer now processes bounded blocks and a compact delay ring; the original array renderer remains as a regression reference. The exact-source VPS run must establish measured memory and timing.

Renders use common gain; `benchmark` then attenuates every family of a pair to the quietest family's BS.1770-4 integrated loudness before packaging, and aggregation re-measures the frozen listening files ([loudness decisions](docs/adr/loudness-matching.md)). This removes the whole-clip level confound only: true peak and short-term loudness inside the transition are not equalized. `--no-loudness-match` is for diagnostics only. Objective diagnostics are not a musical preference score. Do not tune on a frozen evaluation set.

## Local library manifest

The fixture command writes a complete example. Replace sources only with explicitly permitted local excerpts and recompute their SHA-256 values. Each track requires `id`, relative `path`, `sha256`, `bpm`, `rights` and nonempty `provenance`. Supported manifest permissions: `synthetic`, `licensed`, `user-permitted`, `public-domain`. A permission declaration is provenance metadata, not verification of legal ownership. `pairs` declares distinct `a`/`b` IDs, BPM, integer beat count and start offsets in seconds.

Keep source media, derived stems, private renders, manifests with personal paths and credentials outside this public repository. Only synthetic CI fixtures and sanitized aggregate evidence may be uploaded by the foundation workflow.

## Engine tools

```bash
python3 -m mixlab.ingest /private/library/library.json
python3 -m mixlab.analysis /private/library/clip.wav --cache /private/features
python3 -m mixlab.evaluation /private/pack /private/ratings/listener-*.json
```

The analyzer proposes a constant beatgrid from regular percussive excerpts and abstains on insufficient evidence. It does not identify musical phrases, vocals or key automatically, and never silently overwrites manual rendering metadata. ManualProvider accepts verified downbeats/phrases/key; these stay labelled manual. See [analysis decisions](docs/adr/analysis-provider.md), [renderer decisions](docs/adr/renderer-quality.md), [manifest contract](docs/dataset-manifest.md) and [evaluation rules](docs/benchmark-report.md).

## Continue

> Werk verder aan MixLab. Kijk in Notion naar de huidige fase en wat er nog moet gebeuren, claim een vrije taak en werk die uit.

Detailed coordination belongs in [AGENTS.md](AGENTS.md) and the worker plan. GitHub holds code and task specifications; the zCloud VPS SQLite queue holds live claims and scheduling. Notion is the product/decision/handoff mirror. Do not infer a live queue entry from an issue or a plan file.
