# ML-07 · full-path nofollow admission for frozen-study JSON

## Reproduced defect and independent repair path

The existing evaluation JSON loader (`mixlab.evaluation.json_admission.load_bounded_json`)
opens a regular file with `O_NOFOLLOW | O_NONBLOCK`, after an
`os.stat(..., follow_symlinks=False)` check. Those protections apply to
the **final filename**, not symlinked parent directories. A caller can
successfully load `linked-parent/study.json` even when `linked-parent`
is a symlink. This is a real admission gap, not a bypass of the unrelated
PCM renderer.

The new, independent `mixlab.quality.study_json_path_guard` provides an
**immediately runnable** preflight with no edits to the shared evaluator.
It reuses the already accepted ML-07
`repeatability._open_no_symlink_components` descriptor-walk primitive
(which opens every ancestor with `O_DIRECTORY|O_NOFOLLOW|O_NONBLOCK`),
captures stable device/inode/size/mtime/ctime before and after, then runs
the **real** `verify_study_pack_binding` against an independently pinned
study ID and checksum-bound synthetic PCM pack. It rejects final and
ancestor symlinks for study, public receipt, private evidence, private
answer key and pack/review directories; refusing FIFOs, oversized JSON,
deleted names and observed mid-scan directory/content changes.

Run on your local **private** pack, no audio uploads:

```bash
python -m mixlab.quality.study_json_path_guard \
  /private/study.json /private/frozen-pack \
  --expected-study-id 64_lowercase_hex_study_id_from_external_prereg
```

Exit **0**: paths, the externally pinned study metadata and actual pack
PCM checks are consistent. Exit **2**: refuse invalid/unreadable/mutated
inputs; output and stderr never include private paths, content, ID or
audio. This does **not** check browser accessibility or authorize the
pilot's release, independently validate rights or count human preferences.
It is not a cryptographic authentication of the original source recording
and is not a substitute for the composed PR #84 gate.

The public Python entry point also **captures each supplied PathLike once** before validation. Otherwise a custom `__fspath__()` could provide a benign source during the nofollow check and another source when the shared validator opens the file. PathLike exceptions and NUL-containing pathnames return the same sanitized refusal. A further regression exercises `linked-parent/../study.json`: the symlink must be rejected **before** the lexical `..` traversal can normalize it away. Relative paths are also bound to one absolute, *lexical* starting path (without resolving symlinks), so a concurrent working-directory switch between the real pack scan and final identity recheck cannot silently redirect input validation.

The existing `load_bounded_json` remains usable in its owner's context;
its owner should adopt the same full-path descriptor admission when that
scope is safely transferred. Until that change, the composed study gate
can call this narrow additional preflight. It does not silently patch or
take ownership of ML-05's parser or zCloud worker claim.

## Evidence and scope

The focused regression suite performs a real POSIX ancestor-symlink
reproducer against the existing loader (which accepts it), then confirms
the new gate rejects it. Other tests cover linked pack and
private/review dirs, linked leaf, FIFO without waiting for a writer,
oversized/missing study, wrong external ID, after-scan JSON replacement,
after-scan directory replacement, valid synthetic five-pair PCM binding,
and CLI argument/path privacy.

The exact triggering GitHub SHA is checked in a dedicated Python 3.13 /
3.14 CI matrix under a 192 MiB virtual-memory limit. All packs are
ephemeral original synthetic PCM tones; no copyrighted music, real
listener information, production VPS jobs, queue leases, external
services or downloads. M1 remains open until legal real audio, measured
musical features, frozen pairs and independent blinded human preference
have been obtained and independently reviewed.
