# ADR: BS.1770-4 loudness matching for blind A/B packs

Status: accepted for development pilots, 16 October 2026. Not milestone evidence by itself.

## Context

Renders share one common gain, but transition families differ in energy (echo tails add level, bass swaps and hard cuts remove some). Listeners reliably prefer the louder of two otherwise similar clips, so a common-gain pack confounds preference with level. The architecture, milestone audit and benchmark report all required this confound to be resolved before preference interpretation. RMS (the existing `mixlab.quality` diagnostic) is not perceptual loudness.

## Decision

- `mixlab.loudness.measure` implements ITU-R BS.1770-4 integrated loudness in the standard library with bounded streaming memory: K-weighting (high shelf + RLB high-pass) derived for any 8–96 kHz rate, 400 ms gating blocks at 75 % overlap, -70 LUFS absolute gate and -10 LU relative gate, channel weight 1.0 for mono and stereo. At 48 kHz the derived coefficients equal the published BS.1770-4 table to 12 decimals.
- `benchmark` keeps rendering at common gain (the renderer and its clipping policy are unchanged), then, per pair, **attenuates every family to the quietest family's integrated loudness** and packages those files. Attenuation-only means matching can never introduce clipping. Matched files are re-measured; a miss above 0.1 LU aborts the pack.
- Evidence keeps the unmatched `render_sha256` and binds `output_sha256` (and therefore `pack_id`) to the exact listening bytes. Each render records the target, applied gain and before/after loudness.
- `mixlab.evaluation` re-measures both review files per trial and flags `integrated_loudness_mismatch` above 0.5 LU. The RMS-mismatch hint is dropped from confounds; clipping and silence hints remain.
- `--no-loudness-match` exists only for regression and diagnostics; its evidence keeps the "not loudness-normalized" limitation.

This refines `renderer-quality.md`: the renderer still never normalizes. A separate, recorded, BS.1770-based packaging step equalizes listening level, which is the comparison that ADR's rule protected.

## Verification

- Reference sines: 997 Hz in both stereo channels at amplitude 0.1 reads -20.00 LUFS; mono -6 dBFS reads -9.03 LUFS (44.1 and 48 kHz).
- Cross-check against pyloudnorm 0.2.0 (scratch environment only, not a dependency) on 30 signals (noise with gaps, 55 Hz bass, mixed tones; mono/stereo; 16–96 kHz). Differences were +0.007…+0.128 LU and scale with 1/rate: pyloudnorm normalizes the RLB high-pass numerator, while the BS.1770-4 table (and libebur128) keep `1, -2, 1`, which raises high-frequency gain by `20·log10(a0)`. After subtracting that known term, the residual was at most 0.016 LU.
- 32 s, 48 kHz stereo measurement: about 1.1 s on the development container.

## Limitations

- Sample peak, not 4x-oversampled true peak; inter-sample overs are possible but matched files are attenuated, never boosted.
- Integrated loudness equalizes the whole clip. Short-term loudness during the transition window can still differ between families; that is part of what listeners judge.
- Matching does not make a transition musically better and is not a preference score. M1 still needs real permitted audio and independent human listeners.
