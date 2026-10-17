# ML-07 — independent PCM render repeatability gate

## Purpose and isolation

The offline renderer is designed to be deterministic. Before accepting two separately
produced artifacts as evidence of repeatability, compare **all declared PCM16 frames**
of the two distinct WAV files. This check deliberately does not compare their filenames,
RIFF metadata chunks, provenance identifiers, musical preference, quality or loudness.
It is an optional standalone command; no renderer, ingestion, evaluation, central CLI,
project queue, worker or production behavior changes.

Run on **two independently generated files** from the same expected render:

    python3 -m mixlab.quality.repeatability first.wav second.wav --strict

- Exit **0**: admitted PCM streams match.
- Exit **2** (strict only): admitted PCM streams differ, inspect reproducibility.
- Exit **3**: rejected, malformed, changed, unsupported or incompatible inputs;
  **no report** is emitted. Errors do not contain private paths.
- Without --strict, admitted mismatches produce JSON and exit 0.
- --help provides static usage without opening a source.

The public JSON reports only schema version, yes/no PCM equality, source-independence
and format checks, a technical-review flag and the constant reminder that human
preference testing remains necessary. Private audio bytes, audio fingerprints, hashes,
filenames, paths and listening keys are not emitted.

## Bounds and safety

Supports standard uncompressed PCM16 mono/stereo RIFF WAV, 8–96 kHz,
1–2,000,000 frames/source, 32 MiB/source. Both participants must have equal
sample rates, channels and frame counts before reading PCM, and must be
different device/inode files; a self-comparison or hardlink is rejected.
No-follow, nonblocking read-only descriptors reject symlinks and FIFOs.
PCM is digested in chunks of at most 4,096 frames, never loaded wholesale.
The digests are compared in memory only and never serialized. After both scans,
descriptor identity *and original path identity* are checked against the initial
device/inode/size/mtime/ctime snapshot. This is a best-effort race defense,
not an atomic filesystem transaction or a tamper-resistant signature.

RIFF non-audio chunk differences and changed-but-equivalent rendering metadata are
intentionally ignored. Different PCM output does **not** prove a DSP bug without
confirming input recipe, source, engine version and intentional randomness. Equal
PCM does **not** prove the recipe/provenance is authentic, that both files were
independently rendered, perceptual equivalence, licensed rights, acceptable quality
or that a blind A/B test is valid. The caller must independently bind input recipe,
source fingerprints, renderer build/SHA and sample-rate contract, preferably using
the existing immutable receipts.

## Evidence and release

The dedicated hosted workflow runs Python compilation, a deterministic synthetic
test suite including shape mismatch, hardlinks, FIFO/symlink rejection, truncation,
streaming bounds, concurrent path swap/unlink and cross-participant mutation, plus
redacted strict/normal CLI exit behavior. It records the exact checkout SHA.
No production-VPS audio workload, private music, package download or model is needed.

Keep this candidate in draft pending independent quality/integration-owner review
and correct worker-lease coordination. It adds **mechanical reproducibility evidence
only**; MixLab M1 remains open until rights-permitted real-track analysis/stems,
5–10 frozen blind A/B pairs and at least three independent listeners establish
preference over simple crossfades. See [ML-07 issue](https://github.com/Zennay/Mixlab/issues/7)
and the [Notion handoff](https://app.notion.com/p/3e79e19ac95581f4bf15c26a833da642).
