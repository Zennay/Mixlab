# ML-07 — candidate-vs-baseline stereo-to-mono cancellation (17 Oct 2026)

**Stage:** MixLab M1 Transition Lab **OPEN**. Opt-in, CPU-first **technical** screening only; never infer DJ quality, audience preference, legal track rights, stems, or release readiness from this gate.

## Problem

The existing `mixlab.quality.compare_wavs` reports absolute stereo fold-down cancellation per WAV. A candidate can have much worse mono playback than the matched baseline while both have similar stereo RMS, so a **relative** screen makes the blind A/B preflight more actionable. This companion does not duplicate or mutate the canonical PCM scanner: it interprets its existing 100-ms active-window metrics.

## Interface

```bash
python -m mixlab.quality.relative_mono --baseline /private/baseline.wav --candidate /private/candidate.wav
```

Up to four candidates; main scanner enforces the existing PCM16 mono/stereo 8–96kHz, 2M frames, 32MiB per WAV. Use only permitted local synthetic or explicitly authorized audio. No network or packages; source paths/PCM/hashes are not emitted by this module. **Only the reported CLI output is redacted.** The companion adds a static pre-read no-symlink check for every parent and leaf component, rejects FIFOs and oversized/nonregular files before decoding, and does not write audio. It is still **not** an atomic descriptor-bound sandbox: concurrent hostile rename/path replacement between admission and the existing scanner is out of scope. Operate on a trusted private local workspace.

Exit `0`: no *new sustained* mono cancellation detected, **not** an M1 pass. Exit `3`: candidate-specific cancellation, already problematic baseline, or insufficient evidence; human/DSP review required. Exit `2`: rejected private PCM or invalid command inputs, with generic path-free error.

A candidate-specific risk requires at least 25% absolute candidate risky windows **and** at least 25 percentage points increase over the baseline. The gate abstains on mono audio, duration <1s, >20% silent 100ms windows, or absent RMS/phase metrics. A baseline already at or above 25% risky windows always requires review even if the candidate adds no risk. The output includes only opaque candidate ordinal, category and risk-fraction delta.

## Verification / release gates

`tests/test_quality_relative_mono.py` creates procedural 8 kHz stereo PCM: correlated stereo, equal-power anti-phase stereo, half-clip anti-phase, already broken baseline, silence/short excerpts, sample-count mismatch, batch abuse, and subprocess privacy checks. The dedicated hosted workflow pins triggering HEAD on Python 3.13 + 3.14 and reruns canonical quality + CLI privacy regressions under a 192MiB virtual memory budget.

This is a heuristic from 100ms RMS windows, **not** perceptual mono/LUFS or a full phase-coherence test. Sparse speech/percussion, musical intentional stereo effects, and other playback conditions require listening review. The release gate remains real rights-safe tracks, frozen study and independent blinded listeners (ML-05); no preview or model download and no shared engine, CLI, evaluator, VPS, queue, or worker branch mutation. Do not merge a draft without exact-head CI, independent integration review and lease coordination.
