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

Output is one path-free JSON object. Exit 0: technical result (flag may be true).
Exit 2: invalid, changed or unavailable input; stderr is generic. Run this
locally against rights-permitted audio, not on publicly uploaded recordings.

## Policy / limits

- Stereo uncompressed PCM16 **canonical 44-byte** little-endian RIFF WAV only.
  Mono, WAVE_FORMAT_EXTENSIBLE, metadata chunks, noncanonical headers, and
  mismatch in rate or frame count are deliberately unsupported here; a
  separate main scanner has broader format coverage.
- 8–96 kHz, 1–2,000,000 frames, <=32 MiB each, two unique regular files.
  One descriptor per source, last-component no-follow/nonblocking admission,
  and pre/post descriptor+path stat identity checks. Parent directory symlink
  traversal is **not** protected by this independent tool; use a trusted
  private directory. This is not a filesystem-snapshot or adversarial-FS
  proof; it does not authenticate source rights.
- Read at most 4,096 stereo frames per input block. Compute independent
  left/right energy for each aligned 250 ms window. Ignore windows unless
  **both channels in both samples** exceed -45 dBFS RMS; otherwise abstain.
  Remaining partial windows (<250 ms) are not decisive.
- Compare each candidate window's 10log10(L power / R power) with the
  corresponding baseline ratio. Flag review when the **absolute tilt delta
  >=6 dB** persists at least 1,000 ms continuously. Return only aggregate
  active-window count, maximum delta, longest streak and Boolean flag; no
  raw PCM, file hashes, audio paths or window coordinates leave the process.
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
