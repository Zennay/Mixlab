# ML-07 — development/evaluation PCM holdout isolation

**Purpose.** A technically correct blind-rating aggregator can still report
misleading apparent candidate preference if the same underlying recording
was used to tune transitions and subsequently occurs in the frozen evaluation
set under a second filename, WAV container or source ID. Existing ML-02
`validate_library` checks leakage **within one partitioned manifest**. This
additional, non-mutating private preflight tests two independently validated
development/evaluation libraries **against each other**, and binds the
evaluation selections to the externally pinned frozen ML-05 study.

## Private command

```bash
python -m mixlab.quality.holdout_isolation \
  /private/development/library.json \
  /private/evaluation/library.json \
  /private/frozen-study.json \
  --expected-study-id <64-lowercase-hex-preregistered-outside-the-pack>
```

All four inputs remain private, are opened locally only and must be frozen
before a real listener evaluates transitions. The command refuses invalid
inputs with a generic message and exit 2; a technical preflight succeeds
with exit 0 and an **anonymous count-only JSON** that always includes
`milestone_pass: false`.

The independently pinned study SHA is mandatory. Simply recomputing an
edited `study_id` inside a mutable study document does not demonstrate
preregistration. The caller must maintain the expected digest outside the
tool, pack and tuning pipeline.

## What it actually checks

1. Both manifests and **actual PCM16 WAV sources** pass the existing 32 MiB /
   2-million-frame-per-source ingest SHA-256, format, path, rights-declaration
   and recording-identity checks. Both files have distinct private paths,
   explicit separate development/evaluation partitions, and at most 50
   sources across the two; evaluation has at least ten sources.
2. Development and evaluation have **no overlap** on track ID, `recording_id`,
   actual whole-WAV SHA-256 or SHA-256 of decoded PCM including sample rate /
   channels. Re-encoded or renamed copies cannot silently become holdouts.
   The `recording_id` metadata catches known same-song remasters/edits
   with changed PCM when the user supplies the correct lineage.
3. A separate bounded CPU-only **exact audible excerpt reuse** screen
   samples up to five non-silent PCM windows per source (at most 4,096
   frames and 200 ms; at 96 kHz this is ~43 ms). Windows are anchored
   at 0%, 25%, 50%, 75%, and 100% of the valid start-frame interval;
   the checker then scans the other
   sources through bounded, overlapping PCM read blocks. Stereo whole-frame
   excerpts and their exact L/R channel projections are checked separately,
   including against mono sources of the same sample rate. A byte-for-byte reused
   cropped excerpt is held even when neither full-file checksum, complete
   decoded-PCM hash nor declared recording ID agrees. The bounded anchor
   matcher additionally catches **exact** PCM16 variants from polarity
   inversion, stereo L/R swapping, doubling gain, or their combinations
   (only when multiplication remains in signed-16-bit range). This is an
   integer-identical reproduction check, not a fuzzy perceptual fingerprint.
   It also detects an isolated copied left or right channel when the rest
   of the stereo file differs, including mono/stereo copies.
   Development-development
   reuse is outside this gate; development-evaluation and evaluation-evaluation
   reuse are screened. Common silence, quiet spacers and even substantial
   **constant channel DC bias** are intentionally not treated as musical
   duplicates. Each mono/stereo-channel view must have at least 512 average
   absolute PCM16 counts of modulation **after removing its DC mean**; this
   avoids false exclusions when two unrelated recordings share a zero-filled
   or flat ±2,400-count stereo channel. An actual copied audible channel is
   still rejected when whole WAV fingerprints differ. All PCM reads finish the underlying
   source-identity check before a collision is reported. Equal anchor
   bytes from repeated windows are indexed only once per format while their
   originating source identities are retained. This reduces duplicate
   comparisons on repetitious material without incorrectly counting the
   track against itself or allowing an evaluation source to borrow a
   development source's identity.
4. The externally pinned 5–10 pair study is validated using MixLab's existing
   strict study proof. **Every evaluation track** must appear in that frozen
   study and its ID, full-WAV SHA-256 and BPM must agree exactly. Every
   evaluation pair must preserve the frozen ordered source assignment.
   Unselected evaluation tracks are deliberately excluded to prevent a
   changing study population from being presented as frozen.
5. Different IDs in the evaluation subset may not claim the same underlying
   `recording_id` or decoded PCM fingerprint. Both libraries and the
   externally pinned study are revalidated before reporting an outcome to
   detect ordinary observed source changes during the preflight.

This is an optional *pre-listening* methodological gate. It neither writes,
renames nor publishes manifests, WAVs, study IDs, rating files or answer
keys. It does not select transitions or compare audible musical quality.

## Proof and limitations

`tests/test_quality_holdout_isolation.py` creates two rights-free private
libraries containing short original tones, checks a legitimate five-pair
study, and mutates one input at a time: same WAV; different container
checksum but same decoded PCM; altered recording with reused recording ID;
reused track ID; repeated evaluation recording; rehashed frozen-source
forgeries; wrong pair orientation; identical audible PCM cropped into a distinct longer WAV inside either library, and shared silence that must not trigger a false positive; unselected evaluation additions;
missing partitions or rights metadata; bad pinned ID; malformed JSON;
stream-block-spanning reused PCM; actual source mutation after substring
screening but before the final rescan; polarity inversion, exact doubled
positive/negative gain, stereo-channel exchange, mono copies of stereo channels
and one-channel copies between stereo files, integer overflow in PCM16
transformations, a 1.5x nonmatching-gain control, copied excerpts
at 25% and 75% in two distinct longer recordings, the exact upper
2,000,000-source-frame limit and rejection of 2,000,001 frames, and
per-channel silence, common ±2,400-count DC offsets and preserved
  rejection of an actual audible copied channel; plus redaction in CLI subprocesses.

The dedicated GitHub-hosted workflow pins exact source revision, runs this
focused suite on Python 3.13 and 3.14 under a 192 MiB virtual-memory cap
and does not mount private music or access the production VPS/queue.
The capacity matrix now also verifies **40 development plus 10 evaluation
sources with actual independently synthesized stereo PCM16 WAV frames**,
including the real five-window scan. These are *short 0.5-second, 8-kHz*
test tones, not a worst-case 50 x 2,000,000-frame / 96-kHz production
benchmark: peak memory and latency observed here must not be presented
as production audio throughput proof. The per-source 2,000,000-frame limit
is separately verified on one genuine long WAV.

**Boundary:** This sparse exact-sample screen does not detect time-stretched,
resampled, non-integer-amplified (e.g. 1.5x), lossy-compressed, DC-shifted,
acoustically re-mastered or most other transformed copies, nor every small
reused fragment. It detects exactly inverted polarity, exact gain x2 and
stereo channel swaps within PCM16 bounds; it is not a generalized gain,
phase or timbre invariant audio matcher. It is a contamination **preflight**, not a music-identification
system. File hashes cannot identify all perceptually identical
remasters or bootleg versions. `recording_id`, provenance and rights are
self-declared and must be audited by a person. Technical pass is **not**
license verification, an assurance of sampling independence, experimental
statistical power, a human preference result or M1 completion. No real
recordings were accessed or copied to GitHub. The live study protocol and
integration-owned data/CLI modules remain unchanged. This independent
quality-only PR must remain draft until the current zCloud owner and
integrator review its compatibility with live preregistration.
