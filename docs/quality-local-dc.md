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
# Batch mode (1–8 distinct candidates): decode baseline only once
python3 -m mixlab.quality.local_dc BASELINE.wav A.wav B.wav --batch
python3 -m mixlab.quality.local_dc BASELINE.wav A.wav B.wav --batch --strict
```

The tool **never uploads or writes audio**, never prints private file names,
and uses only Python stdlib. It opens regular read-only sources with
`O_NOFOLLOW` and `O_NONBLOCK`; each input is capped at 32 MiB and 2,000,000
frames; allowed PCM is 16-bit uncompressed mono/stereo at 8–96 kHz. Shape
must match exactly; baseline and candidate must also resolve to **distinct
regular-file identities** (same path or hardlinks are rejected; independent
identical copies remain admissible). Reads are bounded to 4096 frames/chunk. Window sums
consume only O(channels × floor(frames / 250ms)) memory. Per-source and
pair-wide device/inode/size/mtime/ctime freeze checks reject detectable source
changes, including path swaps. Single-pair and batch execution both
pre-admit every source **before any PCM decoding**. The RIFF/WAVE physical
container length must match the declared RIFF size exactly. A bounded
**1,024-header maximum** then checks all RIFF chunk offsets, sizes, required
alignment padding, unique ordered `fmt `/`data` chunks and PCM payload length
against complete decoded frames. Forged outer or inner chunk lengths, duplicate
`fmt `/`data`, trailing orphan bytes, sub-frame PCM and oversized chunk graphs
fail closed before PCM decoding; properly accounted metadata/JUNK chunks,
including odd-sized chunks with a pad byte, remain valid. The check only reads RIFF *headers* during admission, not private PCM; the
full PCM scan remains bounded and read-only. The header limit is deliberately
conservative for CPU-first admission. This guards misleading technical screening
on malformed private clips, but is not a complete RIFF consistency, codec,
or musical quality audit.
This is best effort and **not** an atomic filesystem snapshot.

## Batch input contract

The optional `--batch` switch is **isolated** to this local-DC tool; it does
not change the already-active ML-07 precision batch PR or the shared renderer,
review pack, audio scanner, or evaluation contract.

Before **any PCM is decoded**, the batch admits all 2–9 regular, non-symlink
WAV inputs with `O_NOFOLLOW` and validates individual physical size, PCM16
mono/stereo shape and version-independent wave headers. All candidates must
match the baseline sample rate, channel count and frame count. The baseline
and candidates must have **distinct device/inode IDs**, rejecting both
same-path reuse and hardlink aliases. Hard caps for the **whole batch**:
**8,000,000 total PCM frames**, **128 MiB total physical WAV bytes**,
**at most eight candidates**, plus individual 2M-frame/32MiB limits. A
batch is rejected before streaming any PCM if *any* header, format, alias or
aggregate budget violates the contract. The synthetic suite also scans a
real **8,000,000-frame aggregate** (eight distinct 1M-frame mono WAVs) and
rejects **8,000,008 frames** before reading audio. Non-mutating scan then reads baseline
PCM exactly once, scans each candidate once, and verifies all identities,
sizes and timestamps again after the last candidate. An invalid, late-changed
or missing input fails the **whole batch** without partial JSON.

Results use ordered neutral IDs (`candidate-001` etc.) with per-channel
`candidate_excess_bias_warning`, baseline flags, exact `complete_windows`,
identical explicit `thresholds` as single-pair mode, and overall tri-state.
The single-candidate batch result is cross-tested against the single-pair
contract; clips too short for four complete windows never report clear.
Source paths, audio,
sample data, inode numbers and source hashes never appear in the public
result or stderr. `--strict` returns 2 on any true/unknown warning; invalid
input returns 3 with empty stdout. The same code and diagnostic thresholds
also apply in single-pair mode.

## Evidence and limits

* Inspect two grids of **250ms non-overlapping full windows**, per channel.
  The second grid starts **125ms later** (half a window, using integral sample
  rounding). Both sets of means are collected in **one single PCM read**; no
  additional private audio scan. Ignore incomplete windows on either grid.
  The phase shift prevents a low-level, sustained one-second offset starting
  halfway between fixed boundaries from being marked inconclusive merely
  because the first grid contains only three full biased windows.
* **Baseline DC:** absolute 250ms mean >=3% of full scale for at least four
  successive windows (one second).
* **Candidate excess:** absolute candidate window mean >=3% **and** the
  absolute difference from the same baseline window >=2.5% of full scale,
  again in at least four successive windows.
* Evaluate four consecutive **complete 250ms windows in either grid**
  (one full second). No credit is given for half-windows. The delayed grid
  contributes **nothing** if fewer than four complete windows exist, so a
  clean one-second recording still returns a conclusive `false`.
* Return `true` for sustained evidence, `null` for too little evidence
  (including a suspicious sub-second run), otherwise `false`. An aggregate
  `warning` is true if either side warns, unknown if any side is unknown
  without a warning, and false only if all per-channel checks are clear.
* JSON includes `window_phase_shift_ms: 125` with the original
  `complete_windows` count describing the unshifted grid. No time positions
  or audio samples are published. Both the single and batch reports use the
  same shifted-grid logic and thresholds.
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
HEAD SHA** before human review. Coverage includes a genuine 2-million-frame,
96 kHz stereo boundary fixture (not mocked metadata), exact one-second and
sub-second signals, duplicate/hardlink admission and input mutation. These
synthetic samples are not rights-permitted music or human listening proof. CI uses GitHub-hosted ephemeral workers
because the always-on VPS currently has no free swap; this does not prove
a production VPS render budget.
