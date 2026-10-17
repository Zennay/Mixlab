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
- Original synthetic fixtures for reproducible infrastructure tests.
- Neutral A/B audio filenames, a local listening page, separate answer key and downloadable ratings.
- Strict streaming ingest with recording/PCM split-leakage checks and a JSON Schema.
- Replaceable analysis provider, measured regular-tempo proposals, manual cue/key annotations, content-addressed private feature cache and beat-error evaluation.
- Streaming transition renderer with exclusive complete-file publication, clipping rejection and post-PCM metrics.
- Checksum-bound rating aggregation with duplicate/coverage validation and explicit volume confounds.
- Core runtime uses only Python 3.10+ standard library; explicit tempo conversion additionally requires FFmpeg with Rubber Band.

## Reproduce on the VPS runner

Shell/build/test/render execution goes through the existing GitHub self-hosted runner on `vps-bb300bba`. Do not provision another server or install models for this slice.

```bash
python3 -m unittest discover -s tests -v
python3 -m mixlab fixture /tmp/mixlab-example-library
python3 -m mixlab validate /tmp/mixlab-example-library/library.json
python3 -m mixlab benchmark /tmp/mixlab-example-library/library.json /tmp/mixlab-example-pack --seed 42
```

Use fresh output directories; existing packs are never overwritten. Open `review/index.html` locally. Only the `review/` directory goes to listeners; `private/` contains identity mappings, recipes, source paths and metrics. Omit `--seed` for real listening pilots. The synthetic fixture is **not** a music benchmark.

Supported input: short uncompressed PCM16 WAV excerpts, identical channel count/sample rate (8–96 kHz), manually verified equal BPM and corresponding starting beats. Input caps are 32 MiB and 2 million frames per excerpt. Prepare excerpts privately; full-track decoding is not implemented. Explicit tempo stretching is available through the separate optional backend below. The benchmark renderer now processes bounded blocks and a compact delay ring; the original array renderer remains as a regression reference. VPS proof for PR #9 passed 51 tests and rendered 32 seconds of 48 kHz stereo in 8.997 seconds at 21,992 KiB peak RSS; see [proof run](https://github.com/Zennay/Ftmo/actions/runs/38754003251). These are synthetic correctness/performance results.

The current pilot uses common gain, not matched perceived loudness; this is a known listening confound to fix before a milestone-quality benchmark. Objective diagnostics are not a musical preference score. Do not tune on a frozen evaluation set.

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

## Explicit different-tempo transitions (optional installed backend)

An additional opt-in renderer uses an already installed FFmpeg build with Rubber Band, within a 0.90–1.10 tempo ratio per source and pitch scale 1. It checks float output for clipping before PCM16 publication. No package or model is installed automatically.

```bash
python3 -m mixlab.dsp.tempo a.wav b.wav mix.wav --a-bpm 120 --b-bpm 124 --target-bpm 122 --beats 8 --family bass_swap
```

Supply verified original BPM and cue offsets. The existing benchmark command continues to require equal tempos; it never silently changes a frozen recipe. The optional wrapper changes tempo explicitly and records transformations. Transient/vocal artifacts and musical quality require real listening. See [tempo backend decision](docs/adr/tempo-backend.md).
