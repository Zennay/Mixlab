# ML-07: single-descriptor private WAV admission (integration candidate)

## Scope and purpose

`mixlab.quality.fd_guard.admitted_pcm16(path)` is a **standalone** CPU-only
context manager for later ML-07 scanner integration. This branch intentionally
does **not** modify `mixlab/quality/__init__.py` (PR #55), the existing CLI (PR
#56), blind HTML evaluation (PR #40), the DSP, the zCloud registration or any
other worker-owned file. It currently protects only **callers that explicitly
choose to use the new helper**. In particular, it does not fix the existing
quality CLI's path-stat/open race until its integration owner adopts it.

## Admission contract

- POSIX/Linux `O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC` opens the
  source **once**, without checking the path beforehand.
- The descriptor must identify a regular file of 44 bytes through 32 MiB.
  Symlink, FIFO, device, directory, missing and oversized inputs fail closed.
- An up-front, same-descriptor RIFF walk admits **at most 4,096 headers up to
  and including the first `data` chunk**. Every pre-data chunk fits inside
  the RIFF-declared and physical bounds; malformed lengths or header floods
  fail closed before Python's WAV parser can do unbounded header work.
- Python `wave` must recognize uncompressed PCM16, 1–2 channels, 8–96 kHz,
  1–2,000,000 frames with an **exact integral-frame data chunk** at the actual
  `data` offset. Legal odd-size padded `JUNK`/metadata chunks remain supported.
  A fixed 44-byte assumption could wrongly admit truncated audio.
- Only the caller sees PCM frames, while the context is live. The helper does
  not retain or output PCM, source paths, digests or listener identities.
- Successful exit compares device, inode, size, nanosecond mtime and ctime
  on the opened descriptor and the original *non-followed* named path.
  In-place edits and named-file swaps cause a redacted `ValueError`.
- The helper never writes to the WAV, spawns processes, downloads a model or
  activates any VPS worker.

This is a TOCTOU mitigation for ordinary Linux filesystems, **not** a
filesystem integrity proof or full RIFF/PCM parser. The initial bounded chunk
walk stops at the first `data` chunk. Validating **all** RIFF chunks,
unexpected trailing data, duplicate chunk declarations, truncation during
streaming and unreadable PCM content remains the calling scanner's duty.
A concurrent edit followed by restoring identical filesystem metadata is out
of scope. A missing source cannot be treated as a silent track. A successful
admission is not LUFS, musical quality, stem analysis, source-rights validation
or evidence that a blind human review happened.

## Immediately usable offline preflight

The isolated module is directly runnable even though the existing MixLab
quality CLI is intentionally unchanged:

```sh
python3 -m mixlab.quality.fd_guard /absolute/private/path.wav
```

This preflight validates admission, then **reads every declared PCM16 frame**
in <=4,096-frame blocks from the same opened descriptor. It rejects truncated
reads and file/path mutation; it never writes media. On success it returns only
shape metadata (`sample_rate`, `channels`, `frames`) and the truth-valued
`pcm16_payload_complete`; no path, PCM, hashes, source identity or rating.
Run locally on permissioned/private files: even shape metadata can be sensitive
and must not be published as listener evidence. Exit codes: 0 complete, 2
invalid/redacted arguments, 3 invalid/redacted source. Never interpret the
result as RIFF forensic inspection, licensed media, musical quality, loudness
matching or an M1 acceptance signal.

Callers can instead import `validate_private_pcm16` for a read-only
bounded check without invoking another subprocess. Its block-frame
parameter accepts integers 1..4096 only. It never automatically replaces
the current shared scanner.

## Blinded A/B group preflight

```sh
python3 -m mixlab.quality.fd_guard --ab-group /private/baseline.wav /private/candidate-a.wav /private/candidate-b.wav
```

The optional group mode accepts **one baseline and 1..7 candidates**, and
keeps all 2..8 regular descriptors open concurrently until they have passed
file-identity checks. It verifies every admitted header before decoding
**any** source, enforces an aggregate **8,000,000-frame** scan budget and
identical sample rate, channel count and frame count, then streams all PCM
in <=4096-frame chunks. Missing, symlink, FIFO and malformed sources fail
closed. An A/B candidate naming the same inode as another source is refused,
including a different hardlink to the same WAV.

Results contain only anonymous shape, candidate count, boolean integrity and
`human_listening_required`. They do **not** contain filenames, hashes,
timestamps, frame coordinates, audio or an automatic pass/fail musical score.
Exit 0 means syntactically complete, shape-comparable **PCM** only; exit 2
means invalid private/redacted arguments; exit 3 means invalid/redacted inputs.
Distinct inodes may still contain exactly the same PCM: use the separate
owned ML-07 exact-PCM reuse screen (#68), not this reader, to investigate that
bias. Identical global shape does **not** prove matched LUFS, equivalent
musical context or unbiased human review.

All source files remain private; do not run this workflow against public
music or log operator-provided paths. Avoid additional VPS work while
PWQ-320 is ineligible or admission/capacity is uncertain.

## Reproducible acceptance

```sh
python3 -m compileall -q mixlab/quality/fd_guard.py tests/test_quality_fd_guard.py
python3 -m unittest discover -s tests -p 'test_quality_fd_guard.py' -v
python3 -m mixlab.quality.fd_guard /path/to/permitted-private.wav
python3 -m mixlab.quality.fd_guard --ab-group /private/baseline.wav /private/candidate.wav
python3 -m unittest discover -s tests -p 'test_quality.py' -v
```

Use the isolated GitHub-hosted workflow on the **exact proposed PR HEAD**;
the command above is documented, not a claim of a completed VPS render.
No private music in test fixtures, artifacts or public CI. The synthetic
tests exercise FIFO nonblocking behavior, symlink rejection, 32-MiB admission,
2-Mframe shape, mono/stereo, corrupt headers, the 4096-chunk admission fence,
partial-frame rejection, same-inode modification, path
replacement, pre-data RIFF metadata offsets, a full-frame standalone
integrity probe, CLI path redaction and retained-source immutability.

## Integration handoff (not yet authorised)

Coordinate with the owners of #55 (PCM/RIFF), #56 (CLI), and #7 (ML-07) to
transfer one tightly scoped integration change after the present draft PRs
settle. The reviewer should explicitly check: RIFF-chunk traversal after
admission, single-FD reuse across both parsing and scanning, stream mutation
detection even on rejected candidates, and sanitized CLI errors. Do not
merge this helper merely to imply the live scanner is protected.

M1 remains open: rights-permitted audio, original automatic analysis/stems
proof, 5–10 frozen track pairs, >=3 blinded listeners and independent owner
review are separate gates. Synthetic security tests alone close none of them.
