# MixLab ML-07 — isolated spectral balance A/B screening

## Purpose and operator command

`python3 -m mixlab.quality.spectral BASELINE.wav CANDIDATE.wav [OTHER.wav] --fail-on-warnings`

This additional **optional, read-only, CPU-only** screening command identifies
large low/mid/high proxy shifts that equal overall RMS can conceal (for example
an inadvertently missing bass layer, midrange/vocal energy or high-frequency content, including changes hidden by a stereo channel swap). It is
supplemental to the main PCM16 quality, signed-stereo identity, pack, tempo and
LUFS reviews; it does not edit them or write media. No external packages,
models, downloads or uploads.

Only private, locally authorized PCM16 uncompressed mono/stereo WAV sources
are accepted. Read caps match ML-07: <=32 MiB, <=2,000,000 frames, rate
8–96 kHz, **at most 8 candidates and 8,000,000 aggregate frames across
baseline plus candidates**. Each candidate's remaining frame allowance is
checked from its WAV header *before* streaming any PCM. The candidate's
sample rate, channel count and frame count are also checked against the
baseline's verified header before candidate decoding, so an invalid A/B
pair does not consume the candidate's full scan budget. Each source is opened as one no-follow,
nonblocking file descriptor (where supported), must be a regular file, and is
checked for size/inode/timestamp change before closing. It also
checks that the *pathname still names that same regular inode* at the end.
This detects ordinary concurrent pathname replacement, unlink, symlink
substitution or editing while a scan is running, instead of reporting old
FD contents as if they came from the newly named source. This is a
best-effort preflight guard, **not** an atomic immutable filesystem
snapshot, defense against hostile timestamp restoration, or a guarantee
that the pathname remains unchanged after scanning. The same stat identity
of **all** earlier A/B inputs (baseline and each candidate) is also checked
at the end of the *entire* candidate comparison. If an earlier input is
renamed, edited, unlinked or turned into a symlink while a later candidate
is being scanned, the report fails as a whole (sanitized exit 3), rather
than publishing mixed-time evidence. This adds bounded metadata checks
only and does not keep extra PCM in memory. PCM is read in blocks
of 4096 frames, with O(channels) filter state and no waveform retention.
Malformed/truncated/mismatched sources cause sanitized status 3, not a
published partial report. A regular-file snapshot is **not** a hostile
filesystem immutable snapshot or a replacement for the stronger private RIFF
checks under independent review in ML-07 PR #55.

## What the numbers mean

For each channel, first-order, sample-rate-adjusted recursive filters
track a **180 Hz lowpass**, a **180–2500 Hz highpassed-then-lowpassed
midrange proxy**, and a **2500 Hz highpass residual**. After streaming,
the root-mean-square energy of each filtered proxy is normalized by that
source's *unfiltered* RMS. A/B reports compute
`20 log10(candidate_proxy_ratio / baseline_proxy_ratio)`. Ratios are
gain-normalized, but **not** loudness-matched or perceptual loudness.
Importantly, gain normalization can hide that an A/B candidate is simply
much louder. The optional spectral scanner therefore independently reports
the signed whole-file `rms_delta_db_vs_baseline` for two sufficiently audible
sources and adds `rms_level_mismatch_inspect_not_lufs` if the *unrounded*
absolute delta is strictly greater than **1.5 dB**. This warning is
independent of the configurable low/mid/high spectral threshold.
For silence/insufficient audible power the delta is `null`, not 0 dB.
A gain-only change can leave all spectral ratios constant **while still
failing the strict warning gate**. Both sample RMS and these filters are
distinct from EBU/BS.1770 perceptual loudness; the dedicated loudness
evaluation and human blind listening remain required.

A separate **eight-span relative RMS-envelope** check tests when loud and
quiet passages occur, even if the whole-file RMS is equal. For each mutually
audible time span, the per-span sample RMS is divided by its own file's
whole-track RMS before comparing A and B. Thus *constant gain-only* changes
do not produce this envelope warning; the independent 1.5dB whole-RMS
check still catches those. If at least **two** and **25% of at least three**
comparable spans differ by >=**3dB**, the report emits
`temporal_rms_envelope_shift_inspect_not_lufs` and reports only the
`temporal_rms_envelope_mismatch_fraction`. With fewer than three
comparable spans the fraction is `null`, never false 0% evidence.
A/B may legitimately have differently timed transitions; this is a
blind-comparability inspection, not a musical defect verdict or
perceptual loudness calculation. It does not publish time locations or
span amplitudes, only the aggregate mismatch fraction.

An additional **eight-span temporal proxy** checks whether the same
low/mid/high content occurred at the same *time* in both variants.
A/B silence alignment is screened independently: when one source is audible
(>=-55 dBFS RMS) in a time span but the other is not, the report includes
`temporal_audibility_alignment_inspect` and publishes only the aggregate
`temporal_audibility_mismatch_fraction` (0..1). If fewer than **three**
spans are mutually audible while both sources are globally audible,
`insufficient_temporal_spectral_coverage_inspect` is emitted and any
under-supported band-mismatch fractions remain `null`, never falsely
reported as 0% agreement. This catches equal-energy sources whose music
occurs in opposite halves; they have zero overlapping audible windows.
Intentional silence and cuts can trigger warnings, not quality verdicts. The source
is divided into eight deterministic equal-duration bins, with a fixed eight
aggregate-energy buffers regardless of excerpt length. For each bin the
same RMS-normalized low/mid/high proxies are compared in A/B order; any span
below -55 dBFS or with unresolved proxy energy is skipped. If at least
three bins are comparable and at least two bins (and at least 25% of
comparable bins) differ by >=9 dB, the corresponding
`low_temporal_spectral_shift_inspect`, `mid_temporal_spectral_shift_inspect`
or `high_temporal_spectral_shift_inspect` warning is produced. JSON exports
only the aggregate mismatch fraction (or `null` if no bins compare);
the eight source-specific ratios, exact span energies, times, waveforms
and candidate filenames remain private. A one-span change can still
warrant human inspection; this deliberately conservative persistence
gate is not a claim of perfect artifact detection. Eight large bins
are not a time-frequency spectrogram.

For stereo sources, the scanner additionally keeps two private
per-channel low/mid/high energy summaries. It flags a
`stereo_channel_<band>_spectral_shift_inspect` when any *audible* L/R
channel's gain-normalized proxy shifts by the configured threshold
(default 6 dB) relative to the corresponding baseline channel. This catches
a bass/treble **channel swap** that has *identical global stereo
frequency-balance energy*. The report publishes only three band-specific
booleans, not private channel frequencies, per-channel energies,
channel positions, or source filenames. Mono sources have no stereo flag.
Stereo swaps may be creative or intentional; the output is an inspect
warning, not an acoustic quality verdict, and it supplements (does not
replace) the main PCM signed-swap and mono-fold-down checks.

A separate **stereo L/R level-balance** check finds a perceptually
important A/B confound that band-normalized spectral measurements
cannot see: the quiet and loud channels can exchange their relative
levels even while whole-stereo RMS, mono-folding RMS and each channel's
low/mid/high energy ratios remain *identical*. The scanner compares
private `20log10(RMS(L)/RMS(R))` values between A and B and emits
`stereo_channel_level_balance_shift_inspect` at a >=6dB change.
Its output is only a `stereo_channel_level_balance_shift_risk`
boolean, or `null` if any required channel is inaudible; neither
direction nor absolute source-channel levels are published.

The **eight-span temporal level-balance** check similarly compares the
relative L/R RMS ratios in each mutually audible span. A >=9dB change
in >=2 and >=25% of >=3 comparable spans emits
`stereo_temporal_level_balance_shift_inspect`; only an anonymous
`stereo_temporal_level_balance_mismatch_fraction` is published,
or `null` for insufficient comparable channel energy. This catches
panning movements exchanged between A and B even when each channel's
whole-track RMS is *unchanged*. Both comparisons are invariant under
uniform gain changes and are independent of the separate RMS, mono-fold,
band-content and channel-silence screens. Deliberate panning remains
a creative choice, not a proven fault.

A **temporal stereo channel-dropout** screen adds eight private L/R energy
accumulators (at most 16 additional floating-point sums). It detects when
one channel is nearly silent (<-55 dBFS RMS) and the other remains active
(>-35 dBFS RMS) in **at least two** eight-way spans in either source.
This catches alternating L/R dropouts that can leave both *whole-file*
channel RMS levels, global low/mid/high ratios and arithmetic mono-fold
RMS apparently healthy. It publishes only the neutral
`stereo_temporal_channel_dropout_inspect` warning and one
`stereo_temporal_channel_dropout_risk` boolean; no per-source channel,
segment position, amplitudes, envelope or identities are exposed.
One isolated segment is deliberately below the persistent-risk gate and
should still be checked by ear if relevant. Full-track stereo-silence
and mono-fold tests remain separate, complementary checks.

A fully or nearly silent stereo channel can also produce globally plausible
relative band-energy ratios when the other channel remains audible. If
either baseline or candidate has one channel below -55 dBFS RMS while the
other is above -35 dBFS RMS, the supplemental check emits the neutral
`stereo_channel_near_silence_inspect` warning, even when both A/B files
have the same defect. The report does not reveal which channel or which
source caused the warning. This is a technical listening prompt, not a
claim that all intentional single-channel mixes are invalid.

A fourth, **stereo mono-folding risk** inspection uses a single
constant-space left/right cross-energy accumulator over the same PCM frames.
It estimates the RMS ratio of arithmetic mono `(L+R)/2` to stereo RMS,
**not** frequency-dependent phase, stereo imaging or perceptual quality.
A risk warning `stereo_mono_fold_cancellation_inspect` is raised whenever
either audible source has a fold ratio <=-10 dB (<=0.316 of stereo RMS).
If both ratios are resolvable (greater than 1e-4), the signed A/B
`stereo_mono_fold_ratio_delta_db` is reported and magnitude >=6dB
triggers `stereo_mono_fold_change_inspect`; extreme cancellation remains
`null` instead of pretending a finite ratio. Silence/unresolved scans
give `stereo_mono_fold_unresolved_inspect`. Left/right polarity inversions
leave the whole-file and each-channel energy proxies **unchanged** but
can erase the mono downmix: the new separate warning prevents such a
false clean result. The global crossing energy, absolute fold ratios
and channel identity remain private; only neutral codes and the
bounded A/B delta are published.

Whole-track mono-fold numbers can **also mask a local defect**: e.g.
four 6000-frame segments in phase, four opposite-phase leave a global
fold difference near -3dB, which does not trigger the 6dB whole-track
change or the -10dB full-track cancellation thresholds, but half the mix
is absent in mono. Therefore each of eight private time spans also
accumulates L/R cross-energy. If at least **two audible spans** in either
source have a mono-fold ratio <=-10dB, a single
`stereo_temporal_mono_fold_cancellation_inspect` warning and
`stereo_temporal_mono_fold_cancellation_risk: true` are returned.
A single short span is not claimed to be persistent; it can still
warrant human review. No span coordinates, raw correlation, source audio,
or individual fold ratios are published. The eight additional floats
are constant-space and computed in the existing 4096-frame stream. It does not prove an intentional
creative anti-phase signal is defective. The primary ML-07 PCM/phase
scanner remains necessary.

A further **eight-span stereo channel-band timing** screen catches a
different blind-comparability confound: bass and treble may trade sides
over time, even though each channel's *whole-track* band energies and
each span's *overall stereo* spectrum remain unchanged. For each of the
8 private spans, each stereo channel retains only running low/mid/high
energy sums and total energy (at most 64 floating-point accumulators).
A/B matched, mutually audible, resolved channels are compared using
the existing >=9dB temporal proxy threshold. At least 2 changed spans
and >=25% of at least 3 eligible spans produce an anonymous
`stereo_temporal_<band>_channel_spectral_shift_inspect` warning and
a single aggregate mismatch fraction per band (or `null` when there
is insufficient comparable evidence). No L/R direction, exact time
position, PCM, source path, envelopes or per-source channel details
are published. Intentional stereo automation is permitted creatively;
this is an inspect-only warning.

These filters are deliberately cheap, have gradual/overlapping responses,
and are sensitive to DC, onsets and very short excerpts. The numbers are
**not** disjoint frequency-band percentages, calibrated spectrum, true peak,
LUFS, stem analysis, tonal balance judgments or guaranteed audible defects.
Use the main quality DC, RMS, discontinuity and duration screens alongside
this one; inspect flagged candidates by ear. It makes no music-preference
or release decisions.

The scanner also retains only a **private (device, inode)** pair for
each opened regular WAV. If a candidate reuses the baseline's *same file*
or a previous candidate's inode (e.g. a hardlink), it emits the neutral
`same_input_file_inspect_for_blind_noop` warning. Two independent files
with identical PCM are **not** asserted to be the same file by this
metadata check; the separate ML-07 PCM-identity scanner is required to
catch copied audio or transformed duplicates. Private inode numbers and
paths are excluded from JSON.

The default magnitude warning threshold is **6 dB** for either proxy. A
strictly positive finite `--threshold-db` up to 24 is accepted. Silence
below the existing ML-07 -55 dBFS RMS criterion and unresolved near-zero
proxy ratios produce dedicated warnings; no meaningless dB or successful
comparability is fabricated. All channels are combined in energy without
downmixing; a separate stereo/mono check is still required.

The public Python function `scan_spectral_proxy(path)` returns **only**
the seven explicitly allowed global metrics: rate, channels, frames,
RMS dBFS and the three low/mid/high energy ratios. This is enforced by a **closed seven-field allowlist** in
`_public_metrics`, not an open-ended "anything without an underscore"
rule; a future internally named `source_path`, `future_metadata` or
`PCM_hash` cannot accidentally become part of the public report.
A synthetic canary-injection regression specifically checks this.

Private source inode
and timestamp snapshots, per-channel energies, full precision RMS,
and the eight time-span envelopes are held only inside the internal
A/B implementation, not exported by the standalone scanner or JSON.
Tests assert that both the public function and CLI remain redacted at
8/44.1/96 kHz, on 4096-frame read boundaries and with extreme PCM16
values (-32768 and 32767).
A separate, implementation-independent synthetic tone oracle checks that
40/600/8000 Hz excite the expected low/mid/high proxies in order. A
read-block invariance test verifies that partitioning the same PCM16 into
1, 257, 4096 or 8191-frame decode calls yields the same full anonymous A/B
report. The 8191-frame size is only an adversarial **test override**; the
production cap remains 4096 frames per read. No music is used. There is no file identity or review answer key.

The JSON has only a synthetic candidate-01 numbering, generic warning
codes, format/duration facts, rounded global RMS and three energy ratios
per source, aggregate A/B deltas, eight-span mismatch *fractions*
(not envelopes), and the explicit human-preference gate.
It never outputs source paths, song metadata, candidate identity, PCM
samples, window envelopes or hashes. Invalid CLI arguments are redacted
even when a user supplies a sensitive malformed option value. The
`--fail-on-warnings` switch emits the anonymous JSON and exits **2**
for an inspect warning, **0** otherwise. Invalid file/format fails **3**
and prints no JSON. Argument errors fail **2** with no JSON.

## Validation and release gate

`tests/test_spectral_balance.py` uses deterministic local synthetic
signals for RMS-matched bass/high-content shift, gain-only invariance,
stereo, multiple anonymized candidates, silent comparisons, sample-format
mismatch, finite threshold rules, symlink/FIFO admission, truncated PCM,
same-inode/hardlink reuse, concurrent path replacement/unlink,
full-comparison early-baseline/candidate mutation and symlink-substitution
rejection, non-mutation,\nwhole-file-equal but time-swapped bass/treble, short nonpersistent
shifts, stereo temporal gain invariance, shifted silence and sparse temporal coverage, matched-RMS midrange depletion, independent louder/quieter A/B RMS gate,
midrange time reordering, stereo channel-frequency swaps with
globally identical energies, stereo gain invariance, polarity-inverted L/R mono downmix cancellation
despite equal whole and per-channel spectral energies, symmetric A/B
fold-warning, single-channel silence from either side,\nstrict CLI failure on a shared channel dropout, silent spans, strict warning exit
and CLI canary privacy. It is discovered
by the existing ML-07 companion pattern `test_[!q]*.py`, run on the
exact PR source head; no shared workflow modification is required.

Until exact-head CI and independent review are complete, keep this
change **draft only**. No zCloud queue/lease or VPS render is requested.
The original M1 gate still requires rights-safe real tracks, independent
source/evidence audit, the original analysis/stems criteria and at least
three human blind A/B listeners. Signal screening cannot satisfy those
deliverables.
