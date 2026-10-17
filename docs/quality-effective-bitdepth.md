# ML-07 — PCM16 effective-resolution A/B preflight

This optional **CPU-only technical diagnostic** checks whether a candidate appears to
have undergone coarse, left-justified quantisation (for example 8-bit samples
packed inside a nominal PCM16 WAV) when the matching baseline demonstrably has
diverse low bits. A file labelled "16-bit PCM" does not prove 16 bits of source
resolution. This fills a narrow signal-integrity gap; **it is not music quality,
LUFS, true peak, beat detection, spectral judgement or a perceptual test**.

## Operation

```bash
python3 -m mixlab.quality.bitdepth /private/baseline.wav /private/candidate.wav
python3 -m mixlab.quality.bitdepth /private/baseline.wav /private/candidate.wav --strict
```

One baseline plus one to seven candidates. Stdlib-only, offline, without audio
uploads, model downloads, network access or output WAVs. JSON is anonymized:
candidate indices, format dimensions, per-channel aggregate evidence and
tri-state review, **never source paths, PCM values, fingerprints or filenames**.
Invalid/private path details are concealed in the API and CLI.

Admission is fail-closed: no symlink in any current parent component or source
basename, regular files only, nonblocking and nofollow FD, first/last pathname
and descriptor identity checks, PCM16 mono/stereo, 8–96 kHz, 1–2,000,000
frames and 44 B–32 MiB per file, total up to 8,000,000 source frames, A/B
sample rate/channels/frames must be exactly equal and every participant must be
a distinct inode. All sources are opened and admitted before reading PCM.
Reads are <=4096 frames; post-scan identity is checked for all sources before
returning **any** JSON. Stat-based checks cannot make arbitrary malicious
filesystem rewrites atomic; continue to use private immutable local files.

The heuristic counts each channel's **high-level samples** (absolute signed
PCM value >=2048) that have a zero-valued low byte, over 100ms windows.
An individual channel is evidenced only when it has >=4096 eligible samples
across >=4 distinct windows, each with >=32 eligible samples. A
candidate-specific warning requires baseline low-byte-zero fraction <=0.35
and candidate fraction >=0.995 on at least one channel. These conservative
thresholds deliberately permit false negatives: this method does not identify
16-to-12-bit conversion, dither or lossy codec artifacts. Intentional
bit-restricted synthesizers, waveforms with coarse amplitude grids and a
candidate that was gain-changed can cause false positives. Inspect original
source rights, gain history and blind playback before attributing cause.

`coarse_resolution_review` semantics:
- **true**: at least one evidenced channel shows that specific contrast;
  human inspection of the candidate is warranted.
- **false**: both channels (or the one mono channel) have sufficient eligible
  evidence and the contrast was not found; **not a certification** of quality.
- **null**: evidence is insufficient for a definitive negative result.

Normal CLI exit is 0 for valid PCM irrespective of tri-state; `--strict`
exits 3 on *any* true or null candidate and 2 on input errors. CLI options,
failures and Python API exceptions redact private source names. Workflows
exercise synthetic fixtures only, with fixed immutable PR SHA and process
resource limits. Hosted green checks **do not** validate real DJ preference,
stem separation, audible artifacts, M1 production or VPS deployment.

## Release boundary

Additive, independent paths only: `mixlab/quality/bitdepth.py`,
`tests/test_quality_bitdepth.py`, this document and
`.github/workflows/ml07-bitdepth.yml`. Does not touch ML-03 analysis,
ML-04 renderer, ML-05 blind-study pack, existing ML-07 modules, shared
entrypoints, zCloud or SQLite. **Keep draft** pending independent code review,
coordinated integration, a permissions-cleared private music set and >=3
blinded reviewers. No autonomous activation on the swap-exhausted VPS.
