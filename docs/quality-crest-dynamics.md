# ML-07: RMS-matched but peak-different A/B screening

This **optional** CPU-only technical preflight complements the existing
`python -m mixlab.quality` checks without altering the renderer, ingest,
loudness matcher, release paths, or blind-review pack. The tool is separate
to avoid shared ownership conflicts with the ML-07 core/CLI PRs.

## Usage

```bash
python3 -m mixlab.quality.dynamics BASELINE.wav CANDIDATE.wav
python3 -m mixlab.quality.dynamics BASELINE.wav CANDIDATE.wav --fail-on-warnings
```

All operands remain private/local. This module reuses the existing
`compare_wavs` reader: **PCM16 WAV only, mono or stereo, sample rate
8–96 kHz, at most 2 million frames and 32 MiB per source**, plus matching
sample rate, channel count, and exact frame count. Existing readers may
enforce additional restrictions. No packages, models, downloads, audio
uploads, new VPS processes or playlists are needed.

The diagnostics calculate sample **crest factor**, in decibels:

```text
crest_factor_db = 20 * log10(sample_peak / whole_clip_RMS)
crest_delta_db = candidate_crest_factor_db - baseline_crest_factor_db
```

An absolute difference **>= 6.0 dB** (configurable between 0.5 and 24)
adds `crest_factor_difference_inspect_not_preference`. This can reveal
a bias that global RMS matching alone misses: a steady 4000-LSB signal
and a 16000-LSB pulse once per 16 frames have equal RMS, but differ in
crest factor by about 12 dB. Conversely, scaling a waveform uniformly
changes RMS without changing crest factor.

If either side is fully silent, the delta is `null` rather than
infinity, NaN or a fabricated warning. Multiple candidates use only
`candidate-01`, `candidate-02`, etc. The output has no filenames,
paths, source hashes, audio samples, private time envelopes, trial
answers or actual/guessed preference winners. It is intentionally
**not** a musical score.

Exit statuses: **0** report generated; **2** parser error, or technical
difference with `--fail-on-warnings`; **3** unreadable or invalid
input. Invalid arguments and read errors are redacted on stderr.

## Limits and human gate

Crest factor is **not LUFS, true peak, short-term loudness, dynamic range,
a distortion measure, or evidence of a better DJ transition**. Drums,
intentional transient shaping, arrangement, limiting, silence and source
material legitimately influence the number. Even a warning-free result
does not prove that clips sound comparable. Use this as an extra
inspect-only screening cue alongside ML-07 sample-level checks,
ML-05 blind listening evaluation and the separate loudness work.

No M1 gate changes: licensed/local music and at least three blinded
human reviewers remain necessary, and zCloud write/runner admission
is owned by separate workers. Merge/release stays with its owner.

## Deterministic validation

```bash
python3 -m unittest tests.test_crest_dynamics -v
python3 -m compileall -q mixlab/quality tests/test_crest_dynamics.py
```

`tests/test_crest_dynamics.py` covers steady-vs-pulsed same-RMS
signals, gain scaling, stereo/multiple candidates, fully silent audio,
threshold validation, format mismatch, unmodified bytes and CLI
privacy/exit contracts. The existing quality CI invokes its companion
test discovery through `test_quality.py`, because this file begins
with `test_c` rather than `test_q`.
