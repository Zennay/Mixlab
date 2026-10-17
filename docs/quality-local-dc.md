# ML-07 | Persistent local DC-bias preflight (draft)

A transition may accumulate a positive DC offset for several seconds and a
negative DC offset later. Its **whole-clip DC average can be near zero** even
though both regions consume headroom and can introduce playback pops.
`mixlab.quality.__init__` already reports whole-file DC; this **separate,
optional check** adds local sustained-bias evidence without changing it.

## How to use

```sh
python3 -m mixlab.quality.local_dc BASELINE.wav CANDIDATE.wav
python3 -m mixlab.quality.local_dc BASELINE.wav CANDIDATE.wav --strict
```

The tool **never uploads or writes audio**, never prints private file names,
and uses only Python stdlib. It opens regular read-only sources with
`O_NOFOLLOW` and `O_NONBLOCK`; each input is capped at 32 MiB and 2,000,000
frames; allowed PCM is 16-bit uncompressed mono/stereo at 8–96 kHz. Shape
must match exactly. Reads are bounded to 4096 frames/chunk. Window sums
consume only O(channels × floor(frames / 250ms)) memory. Per-source and
pair-wide device/inode/size/mtime/ctime freeze checks reject detectable source
changes, including path swaps. This is best effort and **not** an atomic
filesystem snapshot.

## Evidence and limits

* Inspect 250ms non-overlapping full windows, per channel. Ignore the final
  incomplete window.
* **Baseline DC:** absolute 250ms mean >=3% of full scale for at least four
  successive windows (one second).
* **Candidate excess:** absolute candidate window mean >=3% **and** the
  absolute difference from the same baseline window >=2.5% of full scale,
  again in at least four successive windows.
* Return `true` for sustained evidence, `null` for too little evidence
  (including a suspicious sub-second run), otherwise `false`. An aggregate
  `warning` is true if either side warns, unknown if any side is unknown
  without a warning, and false only if all per-channel checks are clear.
* JSON contains only format properties, threshold definitions and booleans;
  **no source paths, hashes, waveform data, sample positions or audio**.
  Descriptive exit code 0, `--strict` exit 2 when warning/unknown, malformed
  source/options exit 3 with a generic private-path-free error.

False positives are possible for intentional near-DC, low-frequency modulation
or source mastering quirks. A clean result does not prove perceptual quality,
loudness parity, absence of clipping, or safe licensing. This is neither an
audio repair nor an integrated blind-pack release gate. A rights-permitted,
preregistered blind study with three or more listeners, M1 beat/key/phrase/stem
requirements, owner integration and independent review still apply.

## Nonoverlap and release policy

Only `mixlab/quality/local_dc.py`, `tests/test_quality_local_dc.py`,
`docs/quality-local-dc.md` and `.github/workflows/ml07-local-dc.yml` are
owned by this proposal. Do not touch the concurrent PCM core, spectral,
dynamics, time-shift, precision, reuse, format guard, DSP, review-pack,
analysis or evaluation scopes. Keep the PR **draft**; no queue/worker/VPS
changes, merge, deployment or synthetic-to-musical quality claim.

Synthetic regression evidence from CI must be linked to the **exact PR
HEAD SHA** before human review. CI uses GitHub-hosted ephemeral workers
because the always-on VPS currently has no free swap; this does not prove
a production VPS render budget.
