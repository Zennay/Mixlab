# ML-07: bounded stereo balance A/B confound check

## Why

Two candidate renderings may have identical duration, RMS, and healthy overall
channel levels while **one is systematically panned away from the baseline**.
Such a persistent stereo image change can prejudice a blind preference test
or reveal which renderer produced which clip. Global stereo phase correlation
and channel-dropout tests do not, on their own, detect this relative left/right
level tilt. This optional preflight flags it for *human review*.

## Offline use (private media only)

```sh
python3 -m mixlab.quality.pan_balance /private/baseline.wav /private/candidate.wav
```

Output is one path-free JSON object. Exit 0: technical result. The
`stereo_pan_confound_review` field is explicitly tri-state: `true` when a
persistent >=6dB shift is found, `false` only when at least one continuous
second of active stereo audio was available without that defect, and `null`
when there is insufficient active evidence to conclude either way. Also
inspect `evidence_status` (`review_pan_balance`,
`no_sustained_pan_bias_detected`, `insufficient_active_audio`).
Exit 2: invalid, changed or unavailable input; stderr is generic. A private
argument parser also rejects missing, unknown or extra operands without echoing
any supplied path or secret. The CLI does not expose its input filenames even
when the command line itself is malformed. Run this
locally against rights-permitted audio, not on publicly uploaded recordings.

## Policy / limits

- Stereo uncompressed PCM16 **canonical 44-byte** little-endian RIFF WAV only.
  Mono, WAVE_FORMAT_EXTENSIBLE, metadata chunks, noncanonical headers, and
  mismatch in rate or frame count are deliberately unsupported here; a
  separate main scanner has broader format coverage.
- 8–96 kHz, 1–2,000,000 frames, <=32 MiB each, two unique regular files.
  Two source descriptors, Linux `O_DIRECTORY|O_NOFOLLOW` dirfd traversal
  of **every** parent component and no-follow/nonblocking final-source open,
  with post-scan complete-path re-open and descriptor/path identity checks.
  Lexical `..` is deliberately not normalized before component validation:
  `symlink/../source.wav` must still be rejected. Paths exceeding 64
  components or 4096 filesystem bytes fail before opening even the root.
  Intermediate dirfds are closed on success and every error.
  This does not provide a filesystem snapshot, cryptographically authenticate
  source provenance, or guarantee protection from an adversary with arbitrary
  access to the process's file descriptors; it does not verify music rights.
- Read at most 4,096 stereo frames per input block. Compute independent
  left/right energy for each aligned 250 ms window. Ignore windows unless
  **both channels in both samples** exceed -45 dBFS RMS; otherwise abstain.
  Remaining partial windows (<250 ms) are not decisive.
- Compare each candidate window's 10log10(L power / R power) with the
  corresponding baseline ratio. Flag review when the **absolute tilt delta
  >=6 dB** persists at least 1,000 ms continuously. Return only aggregate
  active-window count, maximum delta, longest streak and Boolean flag; no
  raw PCM, file hashes, audio paths or window coordinates leave the process.
  Discontinuous or under-one-second audible segments cannot be labelled a
  clean pass; the tool abstains (`null`) in those cases.
- A changed pan balance is not a broken render: creative panning, unequal
  instruments, and transitions can produce legitimate flags. This is not
  a stereo width metric, ITU true peak, LUFS, beat/key measurement, A/B
  musical-preference score, or a release gate. Do not infer subjective
  superiority from these diagnostics.

## Validation

Run `python3 -m unittest discover -s tests -p 'test_quality_pan_balance.py' -v`.
The dedicated hosted workflow exercises deterministic generated PCM, shape
rejects before read, 2M-frame capacity, mutation and CLI privacy, plus the
existing main quality regression suite. Require exact SHA workflow success
before reviewer consideration. Since the production VPS swap is heavily
utilized, no new process is launched there.

Original M1 release obligations remain: rights-safe real music/stems, measured
beat/downbeat/phrase/key, a preregistered blind study and independent listeners.

## Ancestor-symlink regression evidence

The original admission checked `lstat()` on the final filename and
`O_NOFOLLOW` only at the basename. A symlinked parent was traversed and
real PCM decoded, including a lexical `shortcut/../track.wav` bypass.
A rename of the source directory followed by substituting a symlink to
the *same* inode also passed the old after-scan pathname check.

The independently committed regression tests were RED on the old code at
[hosted run 39032711669](https://github.com/Zennay/Mixlab/actions/runs/39032711669):
3 symlink-related assertion failures, two path-bound exceptions.
The fix uses root-to-leaf no-follow descriptor traversal both before reading
PCM and again after reading, and validates path components before opening any
directory. Always bind final release evidence to the latest code SHA instead
of using the RED or an earlier hosted-green commit.
