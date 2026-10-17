# ML-07 — PCM16 effective-resolution A/B preflight

This optional **CPU-only technical diagnostic** checks whether a candidate appears to
have undergone coarse 8-bit-step quantisation packed inside nominal PCM16,
including 8-bit-left-shifted samples with an arbitrary fixed low-byte offset,
when the corresponding baseline has genuinely diverse low bits. A file labelled "16-bit PCM" does not prove 16 bits of source
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
Invalid/private path details are concealed in the API and CLI. Candidate
iterators are consumed for **at most eight entries**, even if infinite, and
iterator failures are redacted rather than propagating private strings.

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
PCM value >=2048), their 256 possible low-byte residue bins, and the most
populated bin. Streaming histograms use a fixed 256 counts per channel; the
actual residue values, PCM and source names are never included in reports.
A channel is evidenced only when it has >=4096 eligible samples and **at least
four consecutive full 100ms windows** with >=50% high-level frame occupancy.
Sparse 20ms-in-100ms pulses and separated islands of three active windows
must abstain even if global sample totals or global RMS look conclusive.
A candidate-specific warning requires baseline dominant low-byte fraction <=0.35
and candidate dominant fraction >=0.995 on at least one evidenced channel;
exact integer counts, not rounded display fractions, decide the result.
**If the baseline channel itself has insufficient PCM diversity (>35% of
eligible samples in one residue bin), that channel must abstain** rather than
report a clean candidate. This avoids treating two equally damaged inputs
as proof that the blind listening stimulus is technically comparable. These conservative
thresholds deliberately permit false negatives: this method does not reliably
identify 16-to-12-bit conversion, dithered 8-bit data or lossy codec artifacts.
Intentional bit-restricted synthesizers, waveforms with coarse amplitude grids
and gain or DC offsets can cause false positives. Inspect original
source rights, gain history and blind playback before attributing cause.

`coarse_resolution_review` semantics:
- **true**: at least one evidenced channel shows that specific contrast;
  human inspection of the candidate is warranted.
- **false**: both channels (or the one mono channel) have sufficient eligible
  sustained evidence **and a sufficiently diverse baseline** and the contrast
  was not found; **not a certification** of quality.
- **null**: evidence is insufficient for a definitive negative result, including
  a sparse or discontinuous signal, a quiet channel or an already degraded
  baseline; strict mode rejects this as inconclusive.

Normal CLI exit is 0 for valid PCM irrespective of tri-state; `--strict`
exits 3 on *any* true or null candidate and 2 on input errors. CLI options,
failures and Python API exceptions redact private source names. Workflows
exercise synthetic fixtures only, with fixed immutable PR SHA and process
resource limits. Hosted green checks **do not** validate real DJ preference,
stem separation, audible artifacts, M1 production or VPS deployment.

## Deterministic maximum-bound evidence

`tests/test_quality_bitdepth_stress.py` separately constructs original PCM16
fixtures and actually scans 4 distinct 48-kHz stereo files of 2M frames each
(**8M input frames total**) to prove read-path and output within the cap.
The companion tests reject 8×1,000,001-frame matching sources **before a single
PCM read** and reject an over-32MiB sparse input. Both Python 3.13/3.14 use
the exact immutable checkout with a 192MiB virtual memory cap and RSS logging.
The stress test is GitHub-hosted only: no production VPS load or imported music.

## Actual M1 engine integration (rights-free fixtures)

The focused suite now invokes the real `mixlab.engine.render` on
`FAMILY_NAMES` using original generated stereo PCM, checking all supported
transition families against a separately rendered baseline, the path-private
no-false-alarm result, and SHA-256 file integrity *after* read-only screening.
A separate real hard-cut renderer output is quantized to 8-bit steps with a
**fixed nonzero residue**, saved into a distinct local corruption fixture and
shown to trigger the Python API **and** strict CLI exit 3 while its unmodified
candidate stays clear. This proves technical source-to-renderer integration,
not preference from real tracks or human listening.

## Release boundary

Additive, independent paths only: `mixlab/quality/bitdepth.py`,
`tests/test_quality_bitdepth.py`, `tests/test_quality_bitdepth_stress.py`,
this document and `.github/workflows/ml07-bitdepth.yml`. Does not touch
ML-03 analysis, ML-04 renderer, ML-05 blind-study pack, existing ML-07 modules,
shared entrypoints, zCloud or SQLite. **Keep draft** pending independent code
review, coordinated integration, a permissions-cleared private music set and
>=3 blinded reviewers. No autonomous activation on the swap-exhausted VPS.
