# MixLab ML-07 — CPU-first audio preflight

## Purpose
This is a **technical smoke/level-confound screen**, not a musical score,
automatic DJ, beat/key detector, signal repair tool, or substitute for a
blinded A/B human preference test. The listener decides whether a transition
is good; this tool catches incomparable / suspicious renders before a test.

## Run locally (Python 3.10+, standard library only)

Use the existing renderer / benchmark to produce two or more short, private
PCM16 WAV renders. Preserve the neutral A/B and private answer-key boundary.

    python3 -m mixlab.quality /private/baseline.wav /private/candidate.wav
    python3 -m mixlab.quality /private/baseline.wav /private/a.wav /private/b.wav --window-ms 100 --loudness-tolerance-db 1.5
    python3 -m mixlab.quality /private/baseline.wav /private/candidate.wav --fail-on-warnings

The command reads the WAVs and prints JSON to stdout. It **does not change audio**
or automatically select a winning transition. Redirect locally to a
restricted destination if retention is needed. It emits opaque candidate IDs
rather than source paths, samples, source hashes or private recording metadata.
Without `--fail-on-warnings`, a well-formed report exits 0 even if it warns.
The opt-in flag returns 0 for a clean report and 2 for any candidate **or
baseline** warning, but always prints the full anonymized JSON to stdout
before exiting. Treat this as an optional technical CI gate: musical hard
cuts, phase effects and intentional silence may need human override, and
a clean report never proves a musically good transition.
CLI failures may mention an invalid argument path via normal Python errors;
keep CLI logs private when passing confidential file locations.

## Contract and interpretations
- Bounded per input: at most 32 MiB and 2,000,000 PCM16 frames; supported
  sample rate 8–96 kHz, one or two channels; reads at most 4096 frames per
  chunk. Reuses existing bounded WAV constraints, no numpy/torch or GPU.
- Exact same rate, channels and frame count are required for candidates.
  Mismatches fail closed instead of silently time-stretching or resampling.
- RMS and peak are basic sample-domain dBFS, **not** integrated loudness (LUFS).
  An RMS delta above 1.5 dB is a *possible level confound*, not a proof
  of audible bias and not a suggested gain change. Check a real loudness
  standard before frozen tests; do not simply boost into clipping.
- Consecutive below -55 dBFS RMS windows are tracked in streaming mode.
  A gap >=200 ms **between** audible sections raises
  `interior_silent_gap_inspect_for_dropouts`, even when fewer than half of
  the windows are silent. Leading/trailing silence, an entirely silent file
  and sub-200 ms interior gaps do not raise this specific warning. Durations
  are window-resolution estimates; intentional dramatic silence remains a
  creative choice for human review, not a quality failure verdict.
- The baseline receives `baseline_warnings` using the same artifact checks
  applied to candidates. An apparently clean candidate cannot hide a
  clipped, silent, phase-cancelling or interrupted baseline.
  Both sides flag a likely lost stereo channel when its whole-file RMS is
  below -55 dBFS while the other exceeds -35 dBFS; deliberate hard panning
  is not automatically rejected. `channel_rms_dbfs` is diagnostic only.
- On stereo inputs, phase correlation and mono-fold-down loss (positive dB)
  are measured from streaming PCM samples. Each non-silent RMS window with
  >=9 dB mono-fold-down loss raises a technical warning, including brief
  anti-phase passages hidden by otherwise healthy overall RMS. Fully silent
  windows are excluded. The rule is a screening heuristic, **not** a measured
  listener preference, true-peak measure, phase correction or guaranteed
  mono-compatibility score. Complete cancellation reports a null global loss
  with a true risk flag; mono files also use null where not applicable.
- Unexpected adjacent-sample jumps >=50% full scale are counted, including
  across the internal 4096-frame read boundary, and receive a technical pop
  warning. DC offset exceeding 3% full scale on any channel receives an
  inspect-for-headroom warning. Both diagnostics apply equally to baseline and
  candidates; intentional hard cuts, asymmetrical signals and drums may
  produce legitimate results, so they never auto-reject music.
- A sample near digital full-scale is flagged for inspection, not labeled
  proven clipped; intentional silence and percussive jumps can be musical.
  No psychoacoustic, phase, low-end-masking, key, phrase or crowd-response
  judgment is inferred.
- Every result retains "requires_human_review" and
  "human_preference_test_required". There is deliberately **no quality
  winner, model score or automatically fabricated DJ preference**.
- Treat synthetic tests as engineering proof only. A natural-music benchmark,
  blind listener data and independent review remain [ML-05](https://github.com/Zennay/Mixlab/issues/5)
  / [ML-06](https://github.com/Zennay/Mixlab/issues/6) acceptance gates.

## Reproduce the tests

    python3 -m unittest -v tests.test_quality
    python3 -m unittest discover -s tests -v

No music sources, copyrighted stems or real render recordings are checked into
this repository or uploaded to GitHub Actions. The module is isolated from
shared ML-02 ingest, ML-03 analysis, ML-04 renderer and ML-05 A/B code.

## CPU-first milestone linkage
- [Notion execution plan](https://app.notion.com/p/3f89e19ac95581299d47f11dffb12266)
- [MixLab HQ](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
- [Existing roadmap](https://app.notion.com/p/3e79e19ac9558150a32cf32a96fb1f64)
- [ML-07 issue](https://github.com/Zennay/Mixlab/issues/7)

ML-07 is an independent preflight slice. It does not complete M1. Later,
after the approved private library and matched-loudness method exist, the
integration owner may explicitly wire this into evaluation preflight. Until
then it remains an optional read-only CLI; no zCloud worker launch or
production deployment is implied by merging the code.
