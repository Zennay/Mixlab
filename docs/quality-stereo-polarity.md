# ML-07 — Single-channel stereo polarity reuse screening (draft)

## Evidence gap

The ML-07 streaming PCM16 comparator previously caught exact PCM reuse, whole-file
polarity inversion and swapped stereo channels, but a candidate that inverted
**only left or only right** was treated as distinct PCM. A review pack can
therefore repeat the same recording with a channel-polarity edit while giving
the appearance of an independently generated transition.

The new independent check computes two private SHA-256 fingerprints for each
stereo candidate: the original PCM with exactly one channel negated. These are
compared with the baseline and previously accepted neutral candidate digests.
A match is reported as a **review warning only**:

- `single_stereo_channel_polarity_flip_inspect_for_reused_audio` in warnings.
- `single_channel_polarity_inverted_pcm_of` references `baseline` or an
  opaque `candidate-NN`. No left/right assignment, PCM bytes, source filenames
  or digest values are emitted to JSON.
- Exact duplicates retain their prior primary duplicate warning; mono audio
  does not create stereo fingerprints.

Only 4096 decoded frames are kept per read, plus bounded temporary interleaved
arrays and digests. PCM16 `-32768` is not representably negatable: the
corresponding transformed digest becomes unavailable instead of clipping
or pretending to be an exact match. Inverting the *other* channel is still
valid. The 32-MiB / 2-million-frame source restrictions are unchanged.

A single-channel polarity change can audibly affect stereo imaging or mono
fold-down; this check must **not** label the audio identical perceptually,
pick a winner, edit WAVs, or imply that the transition is good. Independent
DJ/technical review remains necessary.

## Bounded synthetic evidence

The isolated `tests/test_stereo_polarity.py` suite covers both inversion
directions, 4096-frame block boundaries, candidate-to-candidate reuse,
nonmatching samples, exact-duplicate precedence, saturation at PCM16
minimum, path/digest non-disclosure in JSON and CLI, read-only files,
and unchanged mono diagnostics. It requires Python standard library only.
Run from the root of the exact source checkout:

```sh
python3 -m unittest discover -s tests -p 'test_stereo_polarity.py' -v
python3 -m unittest discover -s tests -p 'test_quality.py' -v
```

The already-merged companion-suite check from PR #54 invokes
`python3 -m unittest discover -s tests -p 'test_[!q]*.py' -v`
within the quality suite; this pattern **includes** the new
`test_stereo_polarity.py` module. The PR branch now contains a merge of that
change, so an ML-07 quality Actions result for the **exact integrated PR
head** exercises both the quality suite and this six-case regression.
A green run for the older pre-merge head is *not* sufficient. Verify exact
checkout SHA, the companion suite test count, and the hosted run conclusion
before removing the draft gate. A later squash-merged main still requires
independent exact-main proof.

This is **synthetic DSP/quality QA only**. No private music, human preference
ratings, sample-rate pitch proof or authorization for publication is claimed.
M1 remains open, including real rights-safe A/B listening and independent
audit. No VPS workload has been added while memory/swap pressure is high.

## Private WAV format integrity (additional ML-07 improvement)

The direct `scan_wav` / `compare_wavs` quality commands previously relied
only on Python `wave.open` to interpret the PCM16 header. That reader may
tolerate a bogus `byte_rate`/`block_align`, a partial stereo data frame, or
a malformed RIFF chunk extent. A preflight could have reported legitimate
technical metrics for a recording whose playback interpretation differs in
another audio client.

The new `mixlab/quality/riff.py` checks the private WAVE container **before
PCM decoding**: RIFF/WAVE identity and declared bounds; sane unique `fmt`;
PCM16 mono/stereo and 8–96 kHz; arithmetic consistency for bit depth,
channel block alignment and byte rate; valid optional `fmt` extension size;
and integral PCM frames within the declared RIFF boundary. Only chunk headers
and 16–18 bytes of format metadata are read. Parsing is capped at **4096**
RIFF chunks per input to reject pathological metadata-heavy files before
full PCM decoding. Unknown private metadata chunks
are skipped using RIFF padding rules, never copied to the report. Private
trailing data outside the declared RIFF is deliberately still tolerated for
the existing metadata-insensitive PCM fingerprint contract. This is **not**
a general-purpose WAV verifier, authoring tool, nor permission to ship that
metadata inside public listener packs: `quality.pack` continues to enforce
the stricter canonical metadata-free public-WAV contract.

`tests/test_private_riff.py` adds deterministic positive and adversarial
cases for valid mono/stereo, private metadata before/after PCM, forged
byte rate, block alignment, bit depth, partial-frame truncation, invalid
RIFF extents, duplicate/misordered `fmt`/`data` chunks, legitimate optional
`fmt` extension and corrupt extension size, and sanitized strict/default
CLI failures without source paths. The existing public pack and blind-rating
code are untouched.

Exact-head quality Actions proof must include both
`test_stereo_polarity.py` and `test_private_riff.py` via the companion
suite. Do not promote the draft PR on a CI run for an earlier SHA.

## Signed stereo channel swaps — further ML-07 blinding protection

A stereo variant can reuse exact PCM under a *combination* of channel
swapping and channel polarity inversion. Earlier ML-07 heuristics detected
plain L/R swap, full polarity inversion and individual L/R polarity inversion
separately, but not the three composite cases `(-R,L)`, `(R,-L)` and
`(-R,-L)`. A supposedly independent listening option may therefore be
nothing more than a signed swap of an earlier recording.

The streaming scan now derives three additional **private** bounded digests
per stereo PCM16 read, with the same sample-rate/frame/channel checks and
the same strict `-32768` cannot-be-negated rule. The public neutral diagnostic
is `signed_stereo_swap_pcm_inspect_for_reused_audio` and
`signed_stereo_swap_pcm_of` references only `baseline` or the prior
anonymous `candidate-NN`. Exact duplicate-PCM diagnostics remain separate;
no samples, fingerprints, source files, trial answer keys, left/right mapping,
or audio are included in output.

Six new deterministic tests in `tests/test_signed_stereo_swap.py` cover
all three transformations (crossing 4096-frame boundaries), previous-candidate
reuse, single-sample mismatch, the PCM16 `-32768` edge and legal opposite
channel case, exact duplicate/mono non-regression, and CLI privacy with
read-only input verification.

These are *exact transformed-PCM equality* warnings for possible A/B
recognition confounds, not proof of perceptual identity or bad mixing;
intentional phase and stereo manipulations may sound different.
M1 still needs rights-approved real audio and blind listener evidence.

## Full RIFF traversal after the first audio chunk

The original new private WAV validator initially returned after verifying the
first `data` chunk. As a result, a file could append another `data` chunk,
a duplicate `fmt` section or truncated RIFF bytes *inside* the declared RIFF
without a fail-closed format verdict. Different WAV players may disagree about
which samples those ambiguous containers represent.

The validator now traverses **every** chunk header through the declared RIFF
boundary, under the existing 4096-chunk limit; rejects duplicate/misordered
audio/format chunks, oversized chunk claims and incomplete RIFF trailers;
and still accepts correctly padded local metadata after playable PCM. Source
media is never modified and the existing direct CLI error suppression remains.

Two new deterministic regression methods check duplicate `data` and
`fmt` after audio, malformed 2-byte/truncated RIFF trailers, a corrupted
post-data chunk-size declaration and a valid odd-length `LIST` payload with
padding. This has **no effect** on the stricter listener-public WAV policy:
published packs still cannot contain any RIFF metadata chunks.

## Same-file-descriptor validation (private PCM16)

The previous private quality scanner called `Path.stat`, opened the path
once to validate RIFF and then reopened the filename through
`wave.open(path)` for PCM analysis. A cooperating local process could
replace the file in that gap, so the validated header and measured audio
might not belong to the same recording. The standalone library also needed
stronger nonregular-file admission than the CLI-only guard in PR #56.

The `mixlab/quality/private_source.py` context manager now opens the file
**once**, using nonblocking/no-follow flags where supported, applies
`fstat` regular-file and 32 MiB gates to that descriptor, validates
every RIFF header chunk on the **same open handle**, seeks to frame zero,
and passes that very handle to `wave.open`. The descriptor stays open
through the streaming PCM scanner. A post-scan `fstat` rejects observable
same-inode mutation by size, device/inode, mtime or ctime changes. Failed
opens use a generic path-free message. A renamed/replaced **pathname**
does not silently switch the audio stream to the replacement inode.

`tests/test_private_source_fd.py` adds nine synthetic checks for correct
ordinary WAV and compare behavior, the actual decoder descriptor, pathname
swap between header validation and PCM decoding, same-inode change
rejection, symlink/FIFO/directory denial, sparse oversize admission,
redacted missing-path errors, invalid-header exception privacy, and an
instrumented 9003-frame stereo fixture verifying every scanner read remains
at most 4096 frames (4096 + 4096 + 811 frames per input).

This reduces ordinary local TOCTOU/path-swap exposure but does **not**
provide atomic snapshots against a malicious process mutating sample bytes
and restoring all observable metadata, prevent changes made *after*
the quality command exits, guarantee support for hostile filesystems, or
supply a real-music listener test. Public listener packs retain stricter
container and symlink requirements. Integration with PR #56's separate
CLI-argument hardening remains an owner-reviewed release task.

## Multi-input source-coherence guard for complete A/B comparisons

Single-FD source checking only protects a file **during its own scan**.
A multi-candidate report previously could still compare an earlier
baseline/candidate against later variants after that earlier file had been
modified or replaced: its scan ended successfully before the mutation.

`compare_wavs` now snapshots the neutral `lstat` identity of **all**
input paths before any audio processing, retains those values only in
private process memory, and rechecks the whole inventory before returning
anonymous metrics. Device/inode/size/mtime/ctime and regular-file status
are checked without reopening or rescanning PCM. If a baseline or candidate
changes between individual checks, the entire comparison fails closed
with a generic, path-free error; missing/symlink-replaced inputs are also
rejected. The already-existing per-file descriptor guard continues
to protect each individual WAV read.

Four additional synthetic regressions in `tests/test_private_source_fd.py`
check an in-place baseline rewrite immediately after baseline scanning,
candidate rewrite after its scan, same-PCM path replacement on a new inode,
and a clean multi-candidate report free of source metadata. These are
cooperative best-effort checks against **observable** local modifications,
not an atomic transactional filesystem snapshot; changes made after the
final check or adversarial same-metadata rewrites remain outside scope.

No shareable manifests, answer keys, source paths or fingerprints are added
to result JSON. The added metadata checks read no PCM, leaving the
4096-frame streaming input guarantee unchanged.

## Whole-comparison workload admission (CPU-first, no media exposure)

The original per-WAV hard caps of 32 MiB and 2,000,000 frames do not by
themselves bound the cost of a call accepting up to **20** candidates:
with a large baseline, up to 21 individual PCM scans could still monopolize
a constrained worker. A cheap, path-private admission now runs **before the
first PCM decode**, across baseline **plus every candidate**:

- Total on-disk source size must be at most **128 MiB**, assessed from the
  initial `lstat` identity snapshot; each individual 32-MiB ceiling stays.
- Combined declared PCM frame count must be at most **8,000,000 frames**,
  verified by bounded RIFF header parsing on the same safe regular-file
  descriptor wrapper. This checks only WAV metadata, not audio PCM samples.
- Individual declared frame counts must also fall within **1–2,000,000**,
  and every candidate must match the baseline's **channel count, sample
  rate and exact frame count**, all before the baseline is PCM-decoded.
  Previously these mismatches were only rejected after costly scans.
- After all header probes the complete input identity set must still equal
  its pre-admission snapshot; the existing per-file and end-of-comparison
  identity checks remain active.
- Repeated pathname operands still cost per occurrence: decoding twenty
  copies requires twenty frame budgets, not one. Twenty *small* candidates
  remain supported, while a batch of many maximum-length files must be
  split into smaller requests. These limits gate **technical QA workload**,
  not a claim that a musical transition is poor.
- The new `tests/test_batch_budget.py` suite checks early byte/frame
  rejection without PCM scanning, exact inclusive budget acceptance,
  twenty small candidates, repeated inputs, changing inputs during the
  header admission, path-redacted budget failure messages, and per-file
  frame/channel/rate compatibility before decoding.

This is best-effort filesystem admission, not a promise of precise CPU time,
thread isolation, atomic snapshots or listener preference. No private source
names, bytes, fingerprints or RIFF metadata are added to anonymous reports.

## Exact shifted-PCM reuse under silent edge padding

An A/B option can reuse **all** audible PCM samples but move the excerpt a
few frames earlier or later, adding compensating fully-zero frames at its
start/end so the published duration is identical. Raw PCM SHA-256 and
previous stereo sign/swap fingerprints then differ, so the same source
could misleadingly enter a supposedly novel comparison.

The new private `mixlab/quality/pcm_identity.py` maintains a streaming
SHA-256 of the **contiguous interleaved PCM sequence from the first to last
nonzero whole frame**. It drops only *fully-zero* frames outside that span;
any silence inside the span, mono/stereo channel contents, and every
nonzero sample remain byte-exact. Its bounded implementation buffers no
source audio or pending silence, only a zero-frame count; flushing occurs
in at most **4096-frame** chunks. The digest is **never** included in JSON,
logs or review packs, and totally silent clips yield no such identity.

`compare_wavs` now issues the neutral
`edge_silence_shifted_pcm_inspect_for_reused_audio` warning with
`edge_silence_shifted_pcm_of` equal only to `baseline` or an anonymous
earlier `candidate-NN` for distinct raw PCM with identical trimmed audio.
Original raw duplicates and stereo transformations keep their existing
separate warnings; no exact shift *amount*, start coordinate, original
source identity, fingerprint or answer key is returned. A shifted clip
may genuinely sound different because of timing, so this is an
**inspection hint**, not an automatic invalidation or musical preference.

Nine synthetic tests in `tests/test_edge_pcm_identity.py` cover stereo
and mono padded time shifts, >4096-frame streaming boundaries, earlier
candidate reuse, single-sample and interior-silence mismatch, full silence,
raw duplicate distinction, private digest behavior and strict CLI
anonymization. The existing same-inode/source-identity and batch budgets
continue to gate all inputs. This does not detect time stretching,
nonzero-value padding, pitch changes, partial edits or perceptual
near-duplicates.


## Combined edge-padding and signed stereo/polarity reuse

A second exact-reuse confound combines **two** otherwise separately
detectable operations: move a PCM excerpt within an equal-duration file by
adding/removing fully-zero edge frames, **and** apply a reversible channel
swap or polarity inversion. The original full-length stereo-transform
fingerprints do not match when edge timing changes; the untransformed
edge-trimmed fingerprint also differs.

The quality scanner now hashes edge-trimmed PCM for the seven existing
stereo signed permutations (plain L/R swap, full polarity inversion, each
single-channel inversion and the three signed swaps), or one mono sign
inversion. It updates these streaming digests from the **same existing**
bounded per-read transformed PCM arrays, without source reopens, new sample
reads, unbounded buffers or media export. A transformation requiring the
unrepresentable PCM16 negation of `-32768` is disabled, never saturated.
The new `edge_silence_transformed_pcm_inspect_for_reused_audio` warning
and `edge_silence_transformed_pcm_of` value identify only `baseline`
or a prior anonymous `candidate-NN`, not the transform, shift offset,
source name, samples or hash. Existing raw-duplicate and zero-edge-shift
warnings are retained separately. A match is **exact PCM reuse requiring
human inspection**, not a claim of music quality or automatic rejection.

`tests/test_shifted_transformed_pcm.py` covers every stereo permutation,
mono sign inversion, earlier-candidate reuse, one-sample differences,
nonrepresentable signed minimum, unmodified inputs and privacy. The
existing `test_private_source_fd.py` asserts scanner reads remain
bounded to 4096 frames with all fingerprints enabled.


## Multi-window RMS preflight readiness (technical only)

The legacy `level_comparable_for_blind_ab` flag means **only** that
whole-file RMS values differ by no more than the configured threshold
(default 1.5 dB). A pair can pass it while most aligned 100-ms windows
differ strongly, a common loudness/timing confound for blinded listeners.
Treating that single legacy field as complete A/B readiness is unsafe.

The additional `rms_and_window_level_preflight_pass` boolean now requires
**all** of: finite non-silent whole-file RMS on both sides, the existing
RMS threshold, at least three **audible aligned RMS windows**, and no
sustained >=9 dB short-window level discrepancy in >=25% of audible
windows. The original per-window mismatch fraction and warning remain
unchanged, as does the backwards-compatible RMS-only field; short clips
or unusually large `window_ms` settings cannot claim sufficient
short-term evidence from a single window. The new gate requires no
second audio scan, stores no extra envelope, and never asserts LUFS
equality or musical preference. It is a **conservative technical
check** for human inspection, not an automatic review/release decision.

`tests/test_level_preflight_gate.py` exercises equal-level success,
the masked equal-whole-RMS/different-temporal-energy failure, uniform
6 dB mismatch, insufficient 1-window evidence, short 100-ms clips,
fully silent candidate, anonymized output and existing field
compatibility. Even a passing technical gate does not override
M1 rights, licensed-audio, DJ or >=3-human-blind-listener requirements.


## Hidden stereo channel-level confounds in blind listening

Equal whole-file **and** equal short-window combined RMS can still hide a
substantial change in stereo balance (for example, a strongly attenuated
right channel counterbalanced by a louder left channel). This matters for
headphone listening comparisons even when the overall power is unchanged.

The ML-07 scanner now derives a `stereo_channel_level_confound_risk`
boolean from already-present **per-channel whole-file RMS dBFS**. A difference
of at least **9 dB** in an audible channel, or changing a channel from
digital silence to audible (> -55 dBFS), triggers the neutral
`stereo_channel_level_mismatch_inspect_not_lufs` warning. Mono remains
unaffected and two silent channels do not fabricate a stereo imbalance.
A detected difference makes
`rms_and_window_level_preflight_pass=False`, while preserving the
old backwards-compatible whole-RMS-only `level_comparable_for_blind_ab`
meaning. This is a channel-level **technical listening confound**,
not integrated LUFS, a phase/pan quality score, or a demand that two
artistic mixes must have identical channel balance.

The independent `tests/test_stereo_level_confound.py` exercises
energy-balanced yet strong left/right level changes, both directions,
digital channel silence, modest adjustment, mono and fully silent
clips. No second audio read, private channel envelope, absolute
filename or new music asset is produced. Music preference still needs
licensed audio and human blind-review evidence.


## Time-varying stereo channel levels with globally identical RMS

Whole-recording per-channel RMS can match perfectly even when a transition
moves a channel's energy to the opposite side for a substantial portion of
the excerpt. Equally, each **combined stereo** short-window RMS can match
while individual channel windows differ by more than 9 dB. The earlier
global channel-level check would not detect this temporal confound.

During the existing single PCM scan, ML-07 now records only two **private
per-window channel RMS values** (never samples/paths) per stereo window,
aligned with the existing global RMS windows. The new
`stereo_window_channel_level_mismatch_fraction` is the aggregate fraction
of audible windows in which either channel differs by at least 9 dB or
one audible channel becomes effectively silent. At least three audible
windows and a mismatch fraction of at least 25% raise the neutral
`stereo_window_channel_level_mismatch_inspect_not_lufs` warning and
`stereo_window_channel_level_confound_risk=True`. The additive
`rms_and_window_level_preflight_pass` then fails, while older
whole-RMS-only diagnostics retain their meanings. Mono reports `None`
for the fraction and `False` for stereo risk; silent stereo does not
invent a mismatch.

The temporary arrays scale with **window count**, not audio frames, and
contain no audio samples. They are never returned by the public report,
nor placed in logs or files. `tests/test_stereo_window_balance.py`
compares a synthetic locally varying stereo pattern with a globally
RMS-equivalent channel-flipped pattern, a below-threshold one-window
change, sustained multi-window changes, clean stereo, silence and mono.
This is a conservative technical listening/confound flag and **not** a
musical quality, LUFS, preference or production-readiness verdict.


## Relative mono fold-down A/B confounds (whole-file and time-local)

Equal stereo RMS, per-channel RMS and stereo RMS window values cannot
ensure equal **mono playback** level. A stereo candidate with inverted
phase can disappear when summed to mono while retaining its full stereo
energy. This is a concrete blinded-listening level confound and does
**not** establish any preference, integrated loudness or DJ mix quality.

The quality preflight now compares already-computed
`mono_fold_down_loss_db` across baseline and candidate. The additive
`mono_fold_down_level_delta_db_vs_baseline` is the signed difference
in decibels **only when both have finite audible downmix RMS**. A loss
difference >=6 dB, or a fully cancelling (undefined / infinite loss)
stereo file compared against one with finite loss, emits the neutral
`ab_mono_fold_down_level_confound_inspect_not_lufs` warning and the
`ab_mono_fold_down_level_confound_risk` boolean. Two fully cancelling
clips have **no relative difference**, but **cannot pass** the technical
`rms_and_window_level_preflight_pass` gate because neither yields a
usable mono playback. Mono input and silent stereo input have no
comparable stereo-to-mono delta.

Global downmix energy may still be identical while cancellation moves
between the beginning and end of a transition. The existing stereo
`window_mid_sum_squares` is now accumulated into a **private per-window
mono-downmix RMS summary**, never exposed as a time series, audio samples
or raw path. The same >=9 dB discrepancy in >=25% of >=3 audible
aligned windows raises
`ab_mono_fold_down_window_confound_inspect_not_lufs`,
`ab_mono_fold_down_window_level_confound_risk=True`, and an aggregate
`ab_mono_fold_down_window_level_mismatch_fraction`.
Both comparative flags make the conservative *technical* level pass
false, without changing the original RMS-only
`level_comparable_for_blind_ab` definition.

`tests/test_fold_down_ab_level.py` covers full and partial cancellation,
small panning differences, baseline/candidate reversal, equally cancelling
files, silence, mono, privacy and the non-greenlighting of completely
cancelled stereo. `tests/test_fold_down_windows.py` covers swapped
time-half cancellation that preserves global downmix RMS, 1/10 vs 3/10
window warning limits, identical tracks, silence and mono. Both suites
are mandatory in `tests/test_discovery_contract.py`.

These are deliberately **signal-level heuristics**, not integrated
BS.1770/LUFS or human preference evidence. No private media enters GitHub
or CI and no audio changes are made.


## Computed mono-playback RMS versus configured A/B tolerance

Even a **4 dB** relative mono playback difference can slip below the
conservative **6 dB fold-down loss warning** while both stereo channel
and whole-file RMS look level-matched. For example, identical-amplitude
stereo sine channels with a phase angle of ~103 degrees between L/R
retain equal per-channel and combined stereo power but lose ~4 dB when
summed to mono. This also falls below the 9 dB short-window warning.

The additive `mono_playback_rms_delta_db_vs_baseline` now combines
the already-measured **stereo RMS dBFS and mono fold-down loss dB** for
both baseline and candidate. The difference is measured against the
same configurable `loudness_tolerance_db` used by the whole-stereo RMS
gate (default **1.5 dB**). A mismatch raises
`mono_playback_level_confound_risk` and neutral
`ab_mono_playback_rms_level_mismatch_not_lufs`; it also prevents
`rms_and_window_level_preflight_pass` from claiming a level-balanced
technical comparison. No second audio scan, PCM, per-window envelope
or source path is added to the report. Mono sources and fully silent
stereo remain inapplicable; an exactly cancelling stereo clip has
**undefined** finite mono-playback delta (JSON null), not a fabricated
gain value.

`tests/test_mono_playback_level.py` covers the ~4 dB hidden phase
case, slight phase shift, configurable tolerance, reversing the
baseline/candidate sign of the delta, complete cancellation, silence,
mono inputs and output anonymity. The CI companion-discovery contract
requires the module. This is a technical level preflight only:
integrated LUFS, format playback, artistic panning, and listener
preference demand separate independent real-audio review.


## Whole-file and temporal DC-offset A/B continuity screening

A transition can have **matching total RMS** yet change its waveform's
direct-current centre level when switching between two candidates.
Even if each recording's DC offset is below the existing standalone
3%-full-scale warning threshold, **opposing signed offsets** of +2.1%
and -2.1% produce a relative step above 4% FS. This is a potential
playback/crossfade click or lost headroom, not a musical quality claim.

The preflight now compares the existing `dc_per_channel` aggregate PCM
means for every channel and emits only
`ab_max_channel_dc_offset_delta_fs` (maximum anonymous, normalized
signed-mean difference) and `ab_dc_offset_mismatch_risk`. Differences
**strictly greater than 3% of full scale** produce neutral
`ab_channel_dc_offset_mismatch_inspect_for_clicks`; the conservative
`rms_and_window_level_preflight_pass` stays false. Existing standalone
`dc_offset_risk` behavior and RMS-only legacy flags are unchanged.

A whole-file mean of zero is not enough: +1050 PCM samples of bias
during the first half and -1050 during the second half may cancel in
the global mean, despite strong **local** DC changes. The scanner now
records only a private *per-channel mean per bounded RMS window*
alongside already-collected window RMS values in its existing streaming
pass. Aligned audible windows with >3%-FS *relative* mean difference
count as discrepant; at least **3** audible windows and mismatch in at
least **25%** of them produce
`ab_temporal_dc_offset_mismatch_inspect_for_clicks` and
`ab_dc_window_mismatch_risk`. Only the aggregate anonymous
`ab_dc_window_mismatch_fraction` is returned (or null if no audible
window exists). Neither timing coordinates nor per-window DC means,
samples, track names or audio keys are exported or saved.

Two new wholly synthetic suites, `tests/test_dc_pair_shift.py` and
`tests/test_dc_window_shift.py`, cover opposing low individual offsets,
stereo one-channel variation, no-op/subthreshold differences, a masked
zero-global-mean half-window shift, 2/10 vs 3/10 transient tolerance,
stereo, silent/mono and minimum-window evidence. Both files are required
by the companion CI discovery contract. The 4096-frame read bound and
batch-wide resource admission remain unchanged.

These checks diagnose **signal continuity risk** only. They are not
LUFS, a mixing aesthetic score, or a replacement for licensed music,
human blind A/B tests or an independent M1 quality audit.


### Independent mathematical DC validation and threshold boundaries

The additive `tests/test_dc_independent_oracle.py` does **not** reuse
quality-module DC-window implementation. It computes a window's exact
integer sum of `candidate_sample - baseline_sample`, normalizes it by
window frame count and the PCM16 full-scale denominator, and checks the
strict **3% FS** threshold independently, for both one- and two-channel
fixtures. A fixed seed tests clips with **800, 801, 4095, 4096, 4097
and 9003 frames**, with both **20ms and 100ms** RMS-window settings, plus realistic **44.1 kHz and 96 kHz** rate-scaled 20ms/50ms windows,
including short last windows and multiple PCM streaming blocks. One
stereo fixture independently checks a signed global DC difference,
and all fixtures assert private path/filename suppression and source
immutability. This is deterministic synthetic arithmetic only.

The companion CI discovery contract requires this oracle alongside both
relative DC regression modules. The corresponding stress is confined
to GitHub-hosted small synthetic fixtures; no private real music is
published and no resource-limited VPS worker is exercised.
