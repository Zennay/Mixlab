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

The public JSON reports only schema version, yes/no PCM equality, **distinct
output-file inode verification**, format checks, a technical-review flag and
the constant reminder that human preference testing remains necessary. The
explicit `independent_render_executions_proven: false` prevents a two-file
comparison from being misread as proof that two independent renders actually
occurred: the producer must separately establish that execution history. Private audio bytes, audio fingerprints, hashes,
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

## Optional private renderer-receipt binding

The basic CLI intentionally confirms PCM identity **only**. For programmatic
quality pipelines holding the private return dictionaries from
mixlab.dsp.render / mixlab.engine.render, the standalone validator can
additionally verify that the declared output hash belongs to each actual
output WAV and that both receipts claim the same render contract:

    from mixlab.quality.repeatability import verify_repeatability
    verdict = verify_repeatability(
        first_wav, second_wav,
        receipts=(first_private_renderer_receipt, second_private_renderer_receipt),
    )
    assert verdict["repeatable_pcm"] and verdict["render_receipts_consistent"]

This mode checks each complete WAV's SHA-256 against its own private
output_sha256 receipt on the already opened, read-only descriptor. It also
requires identical recipe, engine version, ordered **declared** source SHA-256
values, sample rate, channels, frame count, duration, gain, start-frame
offsets, alignment and tempo declarations. Renderer block_frames and
output_path are intentionally excluded: different chunk sizes and private
output filenames must not change the intended render. A malformed, oversized,
non-finite, contradictory or mismatched receipt fails closed with the same
redacted rejection as an invalid WAV. No receipt fields, filenames, hashes or
source audio appear in the result. With receipts absent, the report retains
the original pure-PCM schema and makes **no** receipt-consistency claim.

**Physical receipt invariants:** incoming declared `frames` must equal
`round(beats * 60 / bpm * sample_rate)`; `duration_seconds` must match
the observed PCM frame count divided by its sample rate; `gain_linear`
must match `10 ** (gain_db / 20)`, and start-frame offsets must match
the corresponding declared cue seconds. Recipe BPM, beat count, gain dB,
source BPM overrides and start positions must satisfy the current bounded
M1 Recipe contract. These checks reject **two equally false receipts**,
not merely mismatches between receipts. They do not infer source rights,
beat accuracy or perceptual quality.

**Bound before serializing:** an in-process caller can accidentally pass
untrusted receipt metadata. The validator now walks only plain JSON-type
containers, rejecting cyclic/shared containers, depths above 16, more
than 2,048 scalar/container nodes, more than 128 entries in a collection,
huge strings and excessive total scalar lengths **before** `json.dumps`
can construct an unbounded serialized copy. A separate 16 KiB ceiling
applies to the actual serialized receipt. All rejections are path-free.
These are defensive bounds on the optional private API, not a general
network-facing JSON parser.

**Trust boundary:** self-reported input fingerprints and recipes are
cross-compared **between** the receipts, not authenticated against original
source files, filesystem identities, licenses or a trusted external signature.
A forged pair of consistent receipts can still lie about the inputs. The
optional API is therefore a quality-evidence **consistency check**, not
authenticated provenance, a chain-of-custody certificate or blind preference
proof. Private receipts should never be logged or put into public CI artifacts.
The CLI deliberately accepts no receipt JSON path to avoid unexpectedly
uploading/rendering path-bearing sensitive metadata.

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
