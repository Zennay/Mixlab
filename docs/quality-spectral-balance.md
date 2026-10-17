# MixLab ML-07 — isolated spectral balance A/B screening

## Purpose and operator command

`python3 -m mixlab.quality.spectral BASELINE.wav CANDIDATE.wav [OTHER.wav] --fail-on-warnings`

This additional **optional, read-only, CPU-only** screening command identifies
large low/mid/high proxy shifts that equal overall RMS can conceal (for example
an inadvertently missing bass layer, midrange/vocal energy or high-frequency content). It is
supplemental to the main PCM16 quality, signed-stereo identity, pack, tempo and
LUFS reviews; it does not edit them or write media. No external packages,
models, downloads or uploads.

Only private, locally authorized PCM16 uncompressed mono/stereo WAV sources
are accepted. Read caps match ML-07: <=32 MiB, <=2,000,000 frames, rate
8–96 kHz, **at most 8 candidates and 8,000,000 aggregate frames across
baseline plus candidates**. Each candidate's remaining frame allowance is
checked from its WAV header *before* streaming any PCM. The candidate's\nsample rate, channel count and frame count are also checked against the\nbaseline's verified header before candidate decoding, so an invalid A/B\npair does not consume the candidate's full scan budget. Each source is opened as one no-follow,
nonblocking file descriptor (where supported), must be a regular file, and is
checked for size/inode/timestamp change before closing. PCM is read in blocks
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

An additional **eight-span temporal proxy** checks whether the same
low/high content occurred at the same *time* in both variants. The source
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

These filters are deliberately cheap, have gradual/overlapping responses,
and are sensitive to DC, onsets and very short excerpts. The numbers are
**not** disjoint frequency-band percentages, calibrated spectrum, true peak,
LUFS, stem analysis, tonal balance judgments or guaranteed audible defects.
Use the main quality DC, RMS, discontinuity and duration screens alongside
this one; inspect flagged candidates by ear. It makes no music-preference
or release decisions.

The default magnitude warning threshold is **6 dB** for either proxy. A
strictly positive finite `--threshold-db` up to 24 is accepted. Silence
below the existing ML-07 -55 dBFS RMS criterion and unresolved near-zero
proxy ratios produce dedicated warnings; no meaningless dB or successful
comparability is fabricated. All channels are combined in energy without
downmixing; a separate stereo/mono check is still required.

The JSON has only a synthetic candidate-01 numbering, generic warning
codes, format/duration facts, rounded global RMS and three energy ratios
per source, aggregate A/B deltas, eight-span mismatch *fractions*\n(not envelopes), and the explicit human-preference gate.
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
non-mutation, whole-file-equal but time-swapped bass/treble, short nonpersistent\nshifts, stereo temporal gain invariance, matched-RMS midrange depletion,\nmidrange time reordering, silent spans, strict warning exit\nand CLI canary privacy. It is discovered
by the existing ML-07 companion pattern `test_[!q]*.py`, run on the
exact PR source head; no shared workflow modification is required.

Until exact-head CI and independent review are complete, keep this
change **draft only**. No zCloud queue/lease or VPS render is requested.
The original M1 gate still requires rights-safe real tracks, independent
source/evidence audit, the original analysis/stems criteria and at least
three human blind A/B listeners. Signal screening cannot satisfy those
deliverables.
