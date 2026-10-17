# MixLab ML-07 — optional 5ms envelope microtiming A/B preflight

Run offline on **authorized, local** synthetic or permitted PCM16 excerpts:

```sh
python3 -m mixlab.quality.alignment BASELINE.wav CANDIDATE.wav [MORE.wav] --fail-on-warnings
```

This independent, CPU-only check addresses a distinct A/B confound: two equal-length
clips with a **continuous audible floor** may have a ~30–200ms global relative
offset even though their global RMS and sample-rate match and leading/trailing
silence tests see no difference. Such timing differences can unfairly change
a listening verdict. Per-channel samples are reduced to **private 5ms RMS
envelope bins**; normalized cross-correlation compares lag zero with bounded
positive/negative offsets. A non-zero offset triggers an *inspect*, never
a claim that the transition is musically incorrect.

Only high-confidence, substantially better non-zero correlations are warned:
at least 30ms offset, best correlation ≥0.85 and improvement ≥0.20 over
zero-lag correlation. Zero-lag correlation ≥0.85 gives a negative risk flag.
An uninformative or unrelated envelope gives JSON `null`, **not false clean**.
In addition, the **regional** screen divides sufficiently long recordings
into up to eight private 0.5-second-or-longer regions, and asks whether at least
two regions have a strongly improved ±30–200ms alignment while at least one
independent region remains confidently aligned at zero lag. This catches
within-clip partial timing displacement missed by whole-track cross-correlation
without confusing a uniformly delayed whole recording with regional drift.
The result is `regional_timing_shift_risk: true|false|null`. Sparse, uniformly
delayed or heavily edited/uninformative material may return `null`; a boolean
`false` is only emitted when **every** evaluated region is informative and confidently aligned at zero lag (not merely two clean regions). Two clean regions surrounded by silent, re-edited, uncorrelated or ambiguous source are **not** enough to call the entire pair clean; output `null` instead, with a generic inspect warning.
The output **never** includes regional positions, lag directions or
correlation statistics, and an inspect warning does not imply tempo drift.

This is deliberately NOT beat, downbeat, phrase, transient, pitch, LUFS or
DJ-quality analysis. Tempo mismatch and creative edits are not resolved by
the checker; inspect/measure them with authorized music and blinded humans.

## Resource, privacy and safety contract

- Up to eight comparison candidates; each is a regular no-follow file.
  Single-descriptor, nonblocking source open protects against a FIFO hang.
- Uncompressed mono/stereo PCM16, 8–96kHz, 1–2,000,000 frames per file,
  ≤32 MiB including WAV metadata and ≤8,000,000 aggregate decoded frames.
- Candidate format, sample rate, channels and frame count must match the
  baseline header before candidate decoding. Truncated frames fail closed.
  Compare source descriptor metadata before/after and final pathname identity;
  file replacement checks are best effort, not a general adversarial FS guarantee.
- Read up to 4,096 PCM frames per step. No PCM or paths are written, uploaded,
  logged, hashed into public output or returned; only bounded private envelopes
  remain in process memory. Output is opaque sequential candidate ids,
  a `true` / `false` / `null` risk signal, generic warnings and
  `human_listening_required: true`.
- Errors redact operator-provided arguments and filenames: CLI exit 2 for
  malformed command/warnings under `--fail-on-warnings`, exit 3 for invalid
  sources, 0 for normal completed screening. A warning is not release approval.

No third-party packages, models, cloud music services, VPS process or live
worker are required. Synthetic tests are in `tests/test_quality_alignment.py`. They exercise the actual 2,000,000-frame WAV admission boundary (constant PCM), regional two-half mono/stereo timing displacements, A/B reversal, equal-gain and one-off clean controls, reverse-direction stereo shifts, pair isolation, truncation and file-type denial. Invariance tests additionally change the private WAV read batch to 1/257/4096/8191 frames without altering any comparison result; production keeps 4096 frames/read. Dedicated exact-PR-SHA hosted CI prints elapsed seconds and peak-process RSS from `/usr/bin/time`. This measurement is a synthetic QA upper-size sample, not a measured VPS or real-track render budget.
This isolated contribution does not change existing ML-07 core, spectral,
dynamics, HTML review pack, ingest, CLI or DSP owner files. **M1 remains open**
until licensed source, original MIR/stems work and ≥3 blinded listeners supply
separately auditable musical preference evidence.
