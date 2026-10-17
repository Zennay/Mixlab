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
3. The externally pinned 5–10 pair study is validated using MixLab's existing
   strict study proof. **Every evaluation track** must appear in that frozen
   study and its ID, full-WAV SHA-256 and BPM must agree exactly. Every
   evaluation pair must preserve the frozen ordered source assignment.
   Unselected evaluation tracks are deliberately excluded to prevent a
   changing study population from being presented as frozen.
4. Different IDs in the evaluation subset may not claim the same underlying
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
forgeries; wrong pair orientation; unselected evaluation additions;
missing partitions or rights metadata; bad pinned ID; malformed JSON; and
redaction in actual CLI subprocesses.

The dedicated GitHub-hosted workflow pins exact source revision, runs this
focused suite on Python 3.13 and 3.14 under a 192 MiB virtual-memory cap
and does not mount private music or access the production VPS/queue.

**Boundary:** File hashes cannot identify all perceptually identical
remasters or bootleg versions. `recording_id`, provenance and rights are
self-declared and must be audited by a person. Technical pass is **not**
license verification, an assurance of sampling independence, experimental
statistical power, a human preference result or M1 completion. No real
recordings were accessed or copied to GitHub. The live study protocol and
integration-owned data/CLI modules remain unchanged. This independent
quality-only PR must remain draft until the current zCloud owner and
integrator review its compatibility with live preregistration.
