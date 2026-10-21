# ADR: replaceable CPU-first analysis, 15 October 2026

Decision: analysis produces versioned source-hash-addressed records, separate from manually verified rendering recipes. No model download or new dependency is needed for the initial regular-percussion estimator. Streaming channel-energy envelopes, onset lag correlation, observed-gap refinement and phase support generate a **proposal**. Low evidence causes abstention. The score is a heuristic, not calibrated probability; octave errors, syncopation, live drums and tempo drift remain limitations. Downbeats, phrases, vocals and keys stay unavailable unless explicitly annotated. Never infer them by renaming every fourth beat.

ManualProvider retains annotation provenance through its configuration hash and labels every manual value. It validates ordered on-grid downbeats and phrase starts. The private cache is keyed by source bytes, provider class, version and settings. Beat evaluation uses one-to-one matching and penalizes extra beats.

## Provider comparison / next decision

- [librosa 0.11 beat_track](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html): dynamic-programming beat tracker using onset strength, tempo and peak selection. Suitable next CPU benchmark provider, with pinned scientific-Python dependencies. No downbeat guarantee; actual RSS/time must be measured on the same private set.
- [Essentia RhythmExtractor2013](https://essentia.upf.edu/reference/std_RhythmExtractor2013.html) and [KeyExtractor](https://essentia.upf.edu/reference/std_KeyExtractor.html): broader rhythm and tonal analysis. [Official licensing](https://essentia.upf.edu/licensing_information.html) describes AGPL/proprietary routes; evaluate distribution terms before adopting it into a commercial product. No installation made.
- Built-in energy-onset: no packages/models, streaming PCM input, short excerpts only; useful diagnostic baseline, insufficient as the final wedding/club analyzer.

Run `python3 -m mixlab.analysis clip.wav --cache /private/features`. Automatic output never silently changes a render recipe. Compare providers against manually annotated real audio, report beat error and abstention/coverage before automatic mixpoint acceptance. Synthetic regular-click regression only verifies timing mechanics.

## Addendum — measured key and bar/phrase proposals, 17 October 2026

Decision: add two standard-library, CPU-only proposal providers beside the beat estimator, without changing the `Analysis` record, cache schema or provider-specific cache rules owned by `mixlab/analysis/__init__.py`. Both emit their own versioned records (`schema_version` 1) labelled `measured-heuristic` and abstain rather than guess.

- `mixlab/analysis/tonal.py` · `ChromaKeyProvider` (`chroma-kk-v1`): channel-averaged PCM is boxcar-decimated to about 4 kHz; Hann-windowed single-bin DFTs at equal-tempered pitches C2–B5 (A4 = 440 Hz) build a per-frame normalized, octave-folded pitch-class profile (at most 240 frames of 4096 samples). Pearson correlation against rotated Krumhansl–Kessler major/minor profiles ranks the 24 keys. A key is proposed only with correlation ≥ 0.6, margin ≥ 0.04 over the runner-up and ≥ 3 non-silent frames. `key_score`/`key_report` give MIREX-style weighted scores (exact 1, fifth 0.5, relative 0.3, parallel 0.2) plus abstention rate against manual references.
- `mixlab/analysis/meter.py` · `AccentMeterProvider` (`accent-phase-v1`): takes a supplied beatgrid (energy-onset proposal or a verified manual grid). Per beat it measures low-band (150 Hz one-pole) energy, onset contrast and harmonic change, z-normalizes and averages them, and compares each bar phase. Downbeats are proposed only when the best phase has contrast ≥ 0.75, margin ≥ 0.5 and is the bar maximum in ≥ 60 % of whole bars. Phrase starts use a checkerboard novelty over half-phrase windows (energy jump + harmonic distance), so chord changes repeating inside a phrase cancel; they need ≥ 2 whole phrases and the same thresholds pattern (contrast ≥ 1.0, margin ≥ 0.5, consistency ≥ 0.6). Phrase starts are always a subset of proposed downbeats.

This is not "renaming every fourth beat": a uniformly accented click track abstains. Assumptions remain explicit in every record: fixed meter (default 4/4), fixed phrase length (default 8 bars), one global key, standard tuning, no modulation or modal detection. Opposite-polarity stereo cancels in the channel average and therefore abstains. Boxcar decimation is a crude anti-alias filter. Energy-onset octave errors propagate into bar phases; verify the beatgrid first.

Evidence boundary: deterministic synthetic chords, cadences and drum/harmony loops verify mechanics, transposition invariance and abstention only. They are not accuracy on music. Acceptance for M1 still requires a permitted, manually annotated real-track set, reporting `key_report` and downbeat `beat_errors` F-measure with abstention per provider. Proposals never change a render recipe automatically; a human confirms them through `ManualProvider`, which re-validates them on the grid.

```bash
python3 -m mixlab.analysis.tonal /private/library/clip.wav
python3 -m mixlab.analysis.meter /private/library/clip.wav --bpm 128 --first-beat 0.31
```

### Reference benchmark harness

`python3 -m mixlab.analysis.benchmark /private/annotations/refs.json` scores the three measured providers against private manual references. Schema v1: `{"schema_version": 1, "items": [{"id", "path" (relative, beside the JSON), "sha256", "bpm", "first_beat"?, "downbeats"?, "key"?, "annotator"}]}`. Every provider record (beat, both meter runs, key) must carry the annotated `sha256`, and the file is re-hashed after the last provider, so a recording replaced between providers fails closed. This is a consistency check, not an immutable snapshot. Output has track IDs and scores only: beat F1/abstention, downbeat F1 on the verified grid (bar-phase error only) and on the estimated grid (end-to-end), and `key_report`. Annotate the whole excerpt, because unannotated trailing bars count as false positives. This harness is the M1 analysis gate measurement; synthetic references only exercise it.


### Private musical-cue preview and side-by-side overview (21 October)

Measured key/beat/meter estimators are now usable together **without modifying the core cache or a render recipe**. Both new operator routes read explicitly chosen permitted short PCM16 files locally; nothing is uploaded and neither route infers licensing, human confirmation, musical preference or release-readiness.

```bash
# One local clip: all available rhythm/key/structure proposals as JSON
python3 -m mixlab.analysis.preview /private/library/clip.wav

# Optional human-supplied timing input; it is never treated as a verified key/bar
python3 -m mixlab.analysis.preview /private/library/clip.wav \
  --verified-bpm 128 --first-beat 0.31 --format html > /private/cue-preview.html

# Compare at most eight selected clips without filenames or PCM in the report
python3 -m mixlab.analysis.playlist_preview /private/library/a.wav /private/library/b.wav \
  --format html > /private/cue-overview.html
python3 -m mixlab.analysis.playlist_preview /private/library/a.wav /private/library/b.wav \
  --format json > /private/cue-overview.json
```

`mixlab.analysis.preview` reports BPM, source-labelled beatgrid, heuristic key with correlation **not probability**, and bar/phrase cues where enough evidence exists. Cue displays are capped at 64 timestamps per type while preserving the complete count and an explicit truncation flag. It validates equality of each provider's content hash and re-hashes the source at the end to reject ordinary changes between reads; this remains weaker than one immutable source descriptor, so the output is advisory. HTML is offline, no JavaScript or network, and excludes audio paths. JSON contains a source SHA-256 so the operator can privately pin the actual excerpt; do not publish this private output as rights evidence.

`mixlab.analysis.playlist_preview` uses the same source-bound preview for up to eight explicitly passed files, rejects duplicate audio hashes, labels entries only as `clip-01`, `clip-02`, etc., and indicates missing key/tempo/downbeat proposals as **unknown**. It preserves input order, not an inferred DJ set order. HTML excludes filenames, local paths and file hashes; JSON retains source hashes for private matching and omits paths. All audio rights checks, human musical assessment and M1 evidence gates remain independent.

These are production-facing **operator features in an existing draft PR**, not a synthetic QA study, claimed accuracy improvement, proof of a permitted music evaluation dataset or approval to run automatic mixes. CI, review and merge gates still apply.


### 21 October · Verified source identity for independent cue providers

The single-clip preview, up-to-eight-clip comparison and human-annotation
benchmark now share `source_receipt.py`: a bounded regular-file `lstat`
identity (device/inode/size/mtime/ctime) captured **before** any provider read.
Every independently opened beat/key/meter provider must report the same original
content SHA-256 and leave that file identity unchanged. After all reads,
`inspect_wav_and_digest` checks PCM16 and hashes the source through **one
regular-file descriptor**, followed by a final pathname-identity comparison.
Ordinary swaps or in-place edits between provider passes fail closed instead
of mixing cue fields from different recordings. It is deliberately not a
cryptographic immutable filesystem snapshot against a hostile writer forging
the same metadata. Do not use it as rights, benchmark quality, or release proof.

The manual benchmark CLI also emits **fixed private-error messages** for invalid
references, unavailable files and changed PCM, rather than reflecting potentially
sensitive user paths/annotation identifiers back into stderr. The returned
aggregate JSON still contains the operator's explicitly supplied reference IDs,
not audio paths. These are privacy/product-integrity changes, not a completed
real-music evaluation; the separate ML-03/M1 human evidence gates remain intact.


### 21 October · Inspectable multi-clip cue details

The multi-clip HTML report now has **per-clip expandable panels** under the
comparison table: up to 64 proposed beat timestamps, downbeats and phrase
boundaries per clip, plus key correlation/margin, bar/phrase consistency and
source-specific provider warnings. The full observed cue count and truncation
notice remain present. JSON carries the same `cue_details` and
`provider_warnings` alongside exact source hashes for private audit. Neither
output guesses a compatible next song or promotes a proposed cue to a verified
manual annotation; the HTML still omits file paths and SHA values. A human
reviewer can inspect exactly where the heuristic suggests a transition without
generating an audio render.


### 21 October · Human confirmation handoff (manual only)

The private operator can now explicitly confirm a proposal **on the same SHA-256
source** and obtain an independent, manually labelled JSON receipt. The input
is the content hash from the initial private `analysis.preview` JSON, the
human's own BPM and chosen cue fields, a private annotator label, and the
`--confirm-manual-cues` switch. The command refuses source hash mismatches,
replaced files, unsupported keys, non-grid/unsorted marker timings, missing
human identity/confirmation, and empty key-and-structure reviews. It uses the
pre-existing immutable `ManualProvider` (human annotation) rather than
promoting measured-heuristic provider output automatically.

```bash
# Human inspects own track and copies source_sha256 from its private preview.
python3 -m mixlab.analysis.preview /private/library/clip.wav > /private/cue.json

# Only AFTER personally confirming BPM, first beat, key and selected markers:
python3 -m mixlab.analysis.manual_review /private/library/clip.wav \
  --source-sha256 <64-hex-from-cue.json> --bpm 128 --first-beat 0.25 \
  --key "C major" --downbeat 0.25 --downbeat 2.125 \
  --annotator "private-operator" --confirm-manual-cues > /private/confirmed-cues.json
```

The source SHA-256, user-entered BPM, exact operator-declared cue times,
manual source labels and explicit non-authorization flags go into the private
receipt. The approval switch is a **self-declaration**, never evidence that
someone actually listened to or correctly annotated the recording. Neither path, media, annotator label nor its deterministic internal
config fingerprint are exported; the receipt exposes only `manual-v1` as the
provider label. `ManualProvider` still uses its internal configuration hash
for identity, but an unkeyed label-derived hash must not be advertised as
anonymization. Empty cue categories stay unavailable, not magically
verified. Nothing automatically updates recipe/cache, rights, public research
evidence or production mixes. These are **product-facing manual controls**,
not a substitute for real-track evaluation or blind listener review.


### 21 October · Reopen your saved manual cue receipt

A receipt produced by the explicit manual-review CLI can be saved privately and
later inspected against its **original PCM16 audio** without activating any
render or research gates:

```bash
python3 -m mixlab.analysis.receipt_reopen \
  /private/library/clip.wav /private/confirmed-cues.json \
  > /private/reopened-cues.json
```

The importer uses the existing bounded, duplicate-key-rejecting, regular-file
JSON admission. It requires the complete v1 self-declaration contract with
`rights_verified=false`, `render_authorized=false`, and
`human_confirmation_independently_verified=false`. It reconstructs the
original `ManualProvider` timing/key admission, checks strict ordered
on-beat markers, validates the exact source bytes with the single-descriptor
PCM reader, and refuses a replaced audio file. Paths and annotator identity are
not emitted. The output is a **reopened, self-declared private cue note**, not
proof that the original operator listened, that the original document was
authentic/signed or that an audio excerpt may legally be published. Existing
M1 rights and human musical-quality gates are still required.

### 21 October · Offline cue timelines (single and up to eight clips)

The existing `analysis.preview --format html` and
`analysis.playlist_preview --format html` operator screens now include a
**static, accessible three-lane timeline** for beats, bar starts and phrase
starts. The timeline uses only the already calculated private cue values:
no additional PCM reads, models, external network requests, JavaScript,
browser permissions, auto-DJ decisions or render-side mutations.

Each lane displays the actual total number of proposed cues. Only the
previously bounded first 64 timestamps are plotted; if more exist, the
screen says so, rather than implying a complete visualization. In the multi-clip view, **all clips use one shared absolute-seconds axis**
(maximum of the selected durations): shorter excerpts display a clear dashed
end boundary and shaded out-of-source time rather than falsely filling the
whole panel. The single-clip preview still uses its own full duration. The timestamp list remains visible
below each chart for manual cross-checking. No source SHA, path, track
name, audio or annotator identity is embedded in the HTML. The private
JSON still carries the source SHA for operators who need to match the
correct source locally; HTML is **not** an independently signed review
receipt. Even an apparently aligned beat/bar/phrase image is not proof
of a musically usable transition or of legal rights. The human/manual
cue-review and real-audio evidence gates remain unchanged.
