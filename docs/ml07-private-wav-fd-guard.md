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
- Python `wave` must recognize uncompressed PCM16, 1–2 channels, 8–96 kHz,
  1–2,000,000 declared frames with sufficient file bytes.
- Only the caller sees PCM frames, while the context is live. The helper does
  not retain or output PCM, source paths, digests or listener identities.
- Successful exit compares device, inode, size, nanosecond mtime and ctime
  on the opened descriptor and the original *non-followed* named path.
  In-place edits and named-file swaps cause a redacted `ValueError`.
- The helper never writes to the WAV, spawns processes, downloads a model or
  activates any VPS worker.

This is a TOCTOU mitigation for ordinary Linux filesystems, **not** a
filesystem integrity proof or full RIFF/PCM parser. Validating all RIFF chunks,
unexpected trailing data, duplicate chunk declarations, truncation during
streaming and unreadable PCM content remains the calling scanner's duty.
A concurrent edit followed by restoring identical filesystem metadata is out
of scope. A missing source cannot be treated as a silent track. A successful
admission is not LUFS, musical quality, stem analysis, source-rights validation
or evidence that a blind human review happened.

## Reproducible acceptance

```sh
python3 -m compileall -q mixlab/quality/fd_guard.py tests/test_quality_fd_guard.py
python3 -m unittest discover -s tests -p 'test_quality_fd_guard.py' -v
python3 -m unittest discover -s tests -p 'test_quality.py' -v
```

Use the isolated GitHub-hosted workflow on the **exact proposed PR HEAD**;
the command above is documented, not a claim of a completed VPS render.
No private music in test fixtures, artifacts or public CI. The synthetic
tests exercise FIFO nonblocking behavior, symlink rejection, 32-MiB admission,
2-Mframe shape, mono/stereo, corrupt headers, same-inode modification, path
replacement and retained-source immutability.

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
