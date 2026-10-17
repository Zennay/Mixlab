# ML-07 — PCM16 effective-resolution A/B preflight

This optional **CPU-only technical diagnostic** checks whether a candidate appears to
have undergone candidate-specific 14-, 12- or 8-bit-effective quantisation
packed inside nominal PCM16, including arbitrary fixed residual offsets,
when the matching baseline has sufficient diversity at the relevant precision. A file labelled "16-bit PCM" does not prove 16 bits of source
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
A custom `os.PathLike` is evaluated **exactly once** per source and its
resulting string is frozen before checking lexical `../`, file type and
ancestor identity. This prevents a stateful `__fspath__` object from
validating one name and opening another. Arbitrary `__fspath__` failures
(including exceptions containing private filenames) become generic redacted
input errors.

Admission is fail-closed: no symlink in any current parent component or source
basename; regular files only. The original preflight lstat() is **not** enough
to safely open private audio because its parent can be swapped into a symlink
between that check and opening the final filename. Every ancestor directory is
therefore opened through a relative **O_DIRECTORY | O_NOFOLLOW** descriptor,
starting at the filesystem root, and the final file is opened with
**O_NONBLOCK | O_NOFOLLOW** relative to the pinned parent FD. Intermediate
descriptors are closed on success and every failure. The complete ancestor
directory device/inode chain is snapshotted at admission and checked again
after the entire A/B group, alongside the final pathname and file FD identity.
This rejects renamed/relocated parents even when the replacement directory
contains a hardlink to the **same source inode**.

PCM16 mono/stereo, 8–96 kHz, 1–2,000,000 frames and 44 B–32 MiB per file,
total up to 8,000,000 source frames; each A/B group must match sample rate,
channel count and frame count exactly, and all members must have distinct
file inodes. All sources are admitted before reading the first PCM frame.
Reads are <=4096 frames, and any postscan source/ancestor mutation rejects the
entire group **without partial JSON**. Adversarial rapid changes cannot be
made perfectly atomic by userspace stat comparisons; trusted, immutable local
source files remain required.

The synthetic regression suite includes two real parent-symlink swap timings
and one same-inode hardlink-parent replacement. [Original RED evidence](https://github.com/Zennay/Mixlab/actions/runs/39039047013)
demonstrated that the previous final-component-only O_NOFOLLOW was insufficient:
both Python 3.13 and 3.14 actually opened a private alternate inode before
rejecting it. The later parent-hardlink RED exposed an unchanged final file
identity hiding a replaced ancestor directory. These failures are distinct
from audio scoring and do not imply any actual exploitation of user files.

The heuristic counts each channel's **high-level samples** (absolute signed
PCM value >=2048), and their modulo-4, modulo-16 and modulo-256 residue bins.
Streaming histograms use a fixed 4 + 16 + 256 counters per channel; the
actual residue values, PCM and source names are never included in reports.
A channel is evidenced only when it has >=4096 eligible samples and **at least
four consecutive full 100ms windows** with >=50% high-level frame occupancy.
Sparse 20ms-in-100ms pulses and separated islands of three active windows
must abstain even if global sample totals or global RMS look conclusive.
At a checked precision (2, 4 or 8 lower bits), a candidate-specific warning
requires baseline dominant-residue fraction <=0.35 and candidate dominant
fraction >=0.995; exact integer counts, not display rounding, decide the
result. This now catches strongly quantised 14-bit and 12-bit samples, even
when the nominal WAV container remains 16-bit and when low-byte-zero counts
alone look normal. A degraded 14-bit baseline may still establish **further**
12-bit degradation via the modulo-16 comparison, but it must **not** be used
to proclaim a clean candidate when no further degradation is found.
**If any baseline precision band lacks sufficient diversity (>35% in a single
residue bin), an otherwise negative channel must abstain**, not report clean.
These conservative thresholds deliberately permit false negatives: dithered
quantisation and lossy-codec artifacts are not reliably measured.
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

## Sustained regional quantisation

Whole-clip averages may hide a damaged transition sub-section: four
consecutive 100ms windows of 8-bit quantisation embedded inside one
otherwise healthy second affect only ~40% of the source and would not
cross the >=99.5% whole-file lattice threshold. To avoid false clear
results, the same bounded scan now recycles private, per-window
modulo-4/16/256 counters and compares corresponding baseline/candidate
100ms intervals. It flags **four consecutive sufficiently active FULL
windows** exhibiting candidate-specific quantisation and abstains
when a baseline alone contains four consecutive pre-degraded windows.
Isolated glitches of up to three consecutive windows or four widely
separated windows do not trigger a sustained fault.

The privacy boundary is unchanged: internal window positions and
amplitude-residue values never enter public JSON. Only per-channel
tri-state outcomes are emitted. Counters are recycled per window;
no entire-PCM buffer, model or unbounded audio-region histogram
is retained. This is still a conservative engineering proxy and does
not measure audibility or listener preference.

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
