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
# Optional fail-closed automation mode; does not modify either WAV:
python3 -m mixlab.quality.pan_balance /private/baseline.wav /private/candidate.wav --fail-on-review
# Bounded group: one baseline and 2..7 candidate files; optional strict gate.
python3 -m mixlab.quality.pan_balance /private/base.wav /private/candidateA.wav /private/candidateB.wav --fail-on-review
```

Output is one path-free JSON object. Exit 0: technical result. The
`stereo_pan_confound_review` field is explicitly tri-state: `true` when a
persistent >=6dB shift is found, `false` only when at least one continuous
second of active stereo audio was available without that defect, and `null`
when there is insufficient active evidence to conclude either way. Also
inspect `evidence_status` (`review_pan_balance`,
`no_sustained_pan_bias_detected`, `insufficient_active_audio`).
Exit 2: invalid, changed or unavailable input; stderr is generic.
The public Python API also converts filesystem `OSError` messages into a
source-name-free `ValueError`, including missing paths and symlinked parents.
API callers should handle that generic refusal rather than log native file errors. A private
argument parser also rejects missing, unknown or extra operands without echoing
any supplied path or secret. The CLI does not expose its input filenames even
when the command line itself is malformed. By default, a successful technical
report returns exit 0 even when the report contains a review flag or null
(inconclusive evidence). The opt-in `--fail-on-review` returns **3** for
either a technical review flag **or** inadequate stereo evidence, **0** only
for sufficiently active evidence without the sustained tilt, and **2** on
input/admission errors. Strict mode still emits the identical anonymous
JSON; it is a scripting aid, not proof of musical quality. Run this
locally against rights-permitted audio, not on publicly uploaded recordings.

## Multi-candidate group semantics

When two or more candidates are passed, the tool returns one anonymous
`candidates` array with neutral `candidate-01`, `candidate-02`, ... IDs
and each candidate's ordinary single-pair technical metrics. Nothing from
private paths or PCM samples is published. `inspect_batch(baseline, paths)`
also supports exactly one candidate through the Python API.

The input group is **strictly bounded** to one baseline plus 1–7 candidates,
no more than **8,000,000 aggregate source frames** in addition to the
per-file 2-million-frame/32MiB limits. All source descriptors stay open
through the entire group; shape, alias identity and aggregate frame budgets
are checked for *every source* **before any PCM payload** is decoded. The
same pinned baseline file descriptor is rewound and rescanned for each
candidate, and every file descriptor plus original full pathname is
re-checked after the *last* candidate. If an earlier source changes later,
the whole result is rejected without any partial JSON.

Default group-mode CLI exit is 0 on a valid diagnostic report; optional
`--fail-on-review` gives 3 if **any** candidate is flagged **or** has
insufficient active stereo evidence, 0 only if **all** are technically clear,
and 2 if *any* group file is invalid or changed. This is an optional
technical screen, never a certification of musical superiority.

## Policy / limits

- Stereo uncompressed PCM16 **canonical 44-byte** little-endian RIFF WAV only.
  Mono, WAVE_FORMAT_EXTENSIBLE, metadata chunks, noncanonical headers, and
  mismatch in rate or frame count are deliberately unsupported here; a
  separate main scanner has broader format coverage.
- 8–96 kHz, 1–2,000,000 frames, <=32 MiB each, 2–8 unique regular files with a total <=8M-frame budget.
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
  left/right energy for each aligned 250 ms pan window. A window counts as
  usable **only if both channels of BOTH sources** are at least -45 dBFS
  RMS in the whole 250 ms window **and in every aligned 50 ms subwindow**.
  Four 250 ms windows containing just one short loud pulse each do **not**
  amount to a continuous second of audible stereo. Missing evidence is
  `null` (and exit 3 with `--fail-on-review`), not a green pass. The 50 ms
  guards have rational sample boundaries aligned with the 250 ms ones, and
  remain an RMS-based approximation: they do not certify sample-by-sample
  audibility or continuous music. Trailing incomplete 250 ms windows
  (<250 ms) are not decisive.
- 250ms window boundaries use **cumulative rational sample positions**
  (nearest integer), not independently truncated 250ms widths. Thus the
  complete fourth window ends at exactly 1 second even for sample rates
  such as 8,001, 11,025 and 22,050 Hz; a clip one frame short cannot
  falsely pass the one-second evidence threshold. This is not resampling.
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

## Exact-duration evidence and boundary regression

The original implementation used `floor(rate * 0.25)` frames **for every**
window. Four windows at 11,025 Hz covered just 11,024 frames, causing an
exactly-one-second PCM clip to be marked `insufficient_active_audio`, while
a one-frame-short clip could be incorrectly reviewed or cleared. The new
absolute sample boundaries accumulate fractional window widths while
remaining integer-only, deterministic, streaming and O(1) memory.
Synthetic regression tests cover 8,001, 11,025, 16,001, 22,050 and 44,101 Hz,
for exact-one-second clean and warned stereo signals, one-frame-short abstention
and mixed group output. This is a timing-diagnostic correctness fix, not
measured beat alignment or evidence of music preference.

## Privacy failure reproduced and corrected

A source missing from the private library, or a symlinked ancestor directory,
previously surfaced built-in `FileNotFoundError` / `NotADirectoryError`
exceptions containing the actual private basename when calling the Python
`inspect()` and `inspect_batch()` APIs (the CLI was already sanitized).
The isolated Python API regressions were deliberately RED on
[hosted #39033952850](https://github.com/Zennay/Mixlab/actions/runs/39033952850).
The wrapper now translates native filesystem failures into an anonymous
`ValueError` without exposing the original OS error message. This is a
privacy invariant for callers, not a claim that process-level exception
introspection is equivalent to a sandbox.

## Maximum group-capacity and fail-closed human-review regression

A rights-free stress fixture creates four genuinely distinct 48kHz stereo
PCM16 WAVs of **2,000,000 frames each**: one baseline and three candidates.
This checks the actual complete-read **8,000,000 input-frame** group budget
rather than merely simulating its metadata. The focused GitHub-hosted suite
uses a 192 MiB address-space bound and reports maximum resident memory;
runner measurements must be attributed to the exact source SHA.

The strict group CLI is also verified against a mixed result containing one
technically clean candidate and one with insufficient audible stereo in a
channel. Even though no positive pan anomaly is established for the quiet
clip, the mixed group returns exit 3 (not clean 0) in `--fail-on-review`
mode. Normal diagnostic mode still emits a successful anonymous JSON report,
not a musical-preference judgment.

## Actual M1 renderer integration (rights-free fixture)

The focused suite additionally invokes the **existing real**
`mixlab.engine.render()` for every M1 transition family
(`baseline`, `bass_swap`, `echo_exit`, `hard_cut`) using two
original synthetic stereo source WAVs. It does not fake the renderer,
call a heavy source separator, train a model, or publish music.

Each real output uses the same deliberately balanced left/right source
channels. Group pan preflight compares the rendered baseline with
the other families, proves adequate audible stereo evidence, checks that
there is no false pan imbalance, and verifies that each private render
still matches its original renderer `output_sha256` receipt after
inspection. Families are also checked for distinct PCM outputs so a
stale/reused render cannot trivially pass the integration test.

A complementary renderer fixture uses **genuinely off-centre stereo**
(left/right level ratio 2:1), maintained in both rights-free source clips.
All DSP families must preserve this *relative* balance compared with the
actual M1 baseline, rather than mistakenly treating artistic panning as a
new candidate-specific defect. This is an explicit false-positive control
with the existing DSP and PCM quantization in the loop.

A second real renderer fixture creates a normal `hard_cut` candidate
and a separate intentionally shifted PCM artifact (left x2, right x0.5
within headroom). The normal variant must pass, while the altered
variant must trigger a sustained relative pan review in the API **and**
exit 3 in strict batch CLI mode. Both return only anonymous technical
fields. This is deterministic DSP integration proof, **not** rights
evidence, an acoustic perceptual loudness measurement or independent
human-blinded DJ-preference proof.

## Sparse-pulse false-positive evidence gate (October 2026)

The previous 250 ms integrated-RMS test could count an entire second of
apparently continuous stereo when both channels carried only **20 ms of
sound in each 250 ms** (92% silence). In one regression the brief pulses are
scaled so overall candidate RMS closely matches an uninterrupted baseline,
which shows why a single whole-clip or whole-quarter RMS gate cannot prove
continuous usable listening evidence. The original algorithm produced a
false clear/review instead of abstaining. Dedicated **RED** CI reproduced
both candidate-side and baseline-side failures at
[run 39035489399](https://github.com/Zennay/Mixlab/actions/runs/39035489399).

The tightened algorithm maintains bounded, integer-only **50 ms RMS
subwindow guards** within each original 250 ms pan window and demands
sufficient energy from both channels in both sources in *every* subwindow.
The 250 ms pan-tilt measure and one-second persistence threshold are
unchanged. Synthetic boundary controls require correct behavior at -45 dBFS
for quantized PCM16: amplitude 185/32768 must count as active, whereas
184/32768 must not, checked at 8 kHz, 11.025 kHz and 96 kHz.\nA separate exhaustive synthetic regression also iterates all 20 possible\nresidue classes of `sample_rate % 20` (8,000–8,019 Hz): exactly one second\nof active stereo must pass and one frame less must abstain, proving integer\n50ms subwindow boundaries do not accumulate rounding error. Additional synthetic tests cover near-equal whole-clip RMS,
bursts on either source, 50 ms gaps at 11,025 Hz, strict CLI exit 3, and
existing real-M1-renderer integration. All sample rates remain 8–96 kHz;
no media are retained or uploaded, and the 192 MiB virtual memory limit
is enforced by the hosted test workflow. This remains only a conservative
technical evidence screen, not a music or human-perception score.
