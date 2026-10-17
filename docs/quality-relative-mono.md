# ML-07 — candidate-vs-baseline stereo-to-mono cancellation (17 Oct 2026)

**Stage:** MixLab M1 Transition Lab **OPEN**. Opt-in, CPU-first **technical** screening only; never infer DJ quality, audience preference, legal track rights, stems, or release readiness from this gate.

## Problem

The existing `mixlab.quality.compare_wavs` reports absolute stereo fold-down cancellation per WAV. A candidate can have much worse mono playback than the matched baseline while both have similar stereo RMS. Merely subtracting per-file risky-window fractions is **not** trustworthy: two individually loud clips can alternate their samples with **zero jointly audible frames**. The companion retains the canonical streaming scanner as its initial format/level check, then performs a second bounded **synchronous** pass for stereo excerpts with adequate duration, non-silent activity and meaningful RMS. Clearly ineligible sources (mono, <1s or excessive silence) abstain without the extra CPU scan. A large RMS difference **alone** cannot skip the aligned pass: it may coexist with insufficient shared-frame evidence, which takes priority. Only a sufficiently evidenced pair receives the explicit `rms_level_confound` HOLD. Only samples simultaneously above 512/32768 absolute PCM amplitude contribute to the relative fold-down estimate. No audio is retained or emitted.

## Interface

```bash
python -m mixlab.quality.relative_mono --baseline /private/baseline.wav --candidate /private/candidate.wav
```

Up to four candidates; main scanner enforces the existing PCM16 mono/stereo 8–96kHz, 2M frames, 32MiB per WAV. Use only permitted local synthetic or explicitly authorized audio. No network or packages; source paths/PCM/hashes are not emitted by this module. **Only the reported CLI output is redacted.** The companion adds a static pre-read no-symlink check for every parent and leaf component, rejects FIFOs and oversized/nonregular files before decoding, and does not write audio. It is still **not** an atomic descriptor-bound sandbox: concurrent hostile rename/path replacement between admission and the existing scanner is out of scope. Operate on a trusted private local workspace.

Exit `0`: no *new sustained* mono cancellation detected **on RMS-comparable, aligned, locally level-comparable, independently rendered PCM**, **not** an M1 pass. Exit `3`: candidate-specific cancellation, already problematic baseline, insufficient evidence, **candidate/baseline RMS gap above 1.5dB, sustained short-window level gap, 75ms prominent-onset mismatch, 200ms edge-silence mismatch**, or **non-independent A/B audio** (exact no-op waveform, repeated candidate, swapped stereo channels, or sample-wise polarity inversion); human/DSP review required. Exit `2`: rejected private PCM or invalid command inputs, with generic path-free JSON and no diagnostics on stderr (including unknown or missing CLI options).

A candidate-specific risk requires at least 25% of **jointly active** 100-ms windows with ≥9dB candidate fold-down loss **and** at least 25 percentage points increase over the baseline measured on the *same jointly active frames*. Each accepted 100-ms interval must contain ≥50% simultaneous source activity; the full pair needs ≥4096 common high-level frames, ≥4 accepted intervals and at least four **consecutive** accepted intervals. Partial trailing windows cannot establish evidence. The gate abstains on mono audio, duration <1s, >20% silent canonical 100-ms windows, insufficient common-frame evidence or absent RMS metrics. It also emits the explicit `rms_level_confound` HOLD when the existing canonical A/B loudness-tolerance gate rejects the pair; valid stereo phases must never override a roughly 6dB candidate-vs-baseline mismatch. A baseline already at or above 25% cancellation on aligned evidence requires review. This remains a technical proxy, not perceptual mono loudness or phase coherence. The output includes only opaque candidate ordinal, category and risk-fraction delta.

## Source PCM integrity gate (technical HOLD only)

A blind listening comparator must not present a source with an unreviewed audio artifact as a clean condition merely because its *stereo-to-mono fold-down* metric is unchanged. After evidence of sufficient jointly audible PCM, this companion now uses the **already-computed**, bounded canonical baseline/candidate artifact flags to return `ab_audio_integrity_confound` (exit **3**, human/DSP review) when **either** audio variant shows:

- a recovered interior silence ≥200ms or a whole-stereo PCM dropout ≥50ms;
- a single-channel interior dropout ≥50ms while the other channel continues;
- an isolated ≥25%-FS click surrounded by ≤6.25%-FS samples, or any >50%-FS sample discontinuity;
- a repeated high-level PCM flat-top plateau of at least four samples (a *clipping proxy*, not clipping proof);
- persistent per-channel DC offset above 3% full-scale, a completely silent stereo channel, or a ≥20% proportion of partial channel loss;
- a ≥100ms difference between the two stereo channels' first prominent (≥5%-FS) samples;
- any already-detected PCM sample close to 0dBFS (≥32760 of 32768 counts); this is a **headroom proxy** and not proof of clipping or poor musical performance.

The prior canonical module remains the owner of these thresholds; no new audio processing or DSP rendering is introduced. Procedural tests exercise recovered 60ms total and channel dropouts, an isolated sample impulse, a high-level plateau, a severe discontinuity, a defective *baseline*, DC offset, near-full-scale samples without a click, a missing stereo channel, and a 125ms channel onset skew. These proxies can also flag deliberate percussion or editing effects, so `HOLD` explicitly **requires inspection** rather than claiming a musical defect. The report never exposes samples, frame positions, track names or source paths. Inadequate duration or joint PCM evidence still takes precedence as `insufficient_stereo_evidence`. These checks do not constitute a complete music-quality review, blind preference result or a release sign-off.

## Blind A/B comparability beyond global RMS

A technically clean stereo fold-down can still be a **biased listening comparison**, even when no integrity artifact is detected. MixLab's canonical 100-ms PCM16 scanner already evaluates three bounded flags that are now enforced as `ab_timing_or_dynamics_confound` (exit **3**, HOLD) **only after adequate jointly audible frames**:

- `short_window_level_mismatch_risk`: a persistent large gain gap in local 100-ms windows even when the *whole-clip* RMS levels are matched.
- `prominent_onset_mismatch_risk`: audible entries offset by at least 75ms on the scanner's >5%-full-scale PCM-onset heuristic.
- `edge_silence_mismatch_risk`: leading or trailing silence differs by at least 200ms, despite the same total duration.

These are **technical listening-validity warnings** rather than judgments of artistic transitions; a deliberate reverb tail/volume fade may still be artistically correct. The gate does not expose onset times, private PCM, source paths, or per-window envelopes. Unreliable shared-frame evidence still takes precedence and results in `insufficient_stereo_evidence`; exact reused sources remain `non_independent_ab_audio`. All statuses retain `milestone_pass=false`. The rest of the specialist gates (spectral balance, intersample peaks, imaging, musical beat/phrase, actual listeners) remain independent responsibilities.

## Independent-audio eligibility

A safe PCM16 fold-down result does **not** mean the candidate is a distinct musical transition. A blind A/B candidate that is sample-for-sample identical to its baseline, a duplicate of another submitted candidate, an exact L/R stereo exchange, or a signed polarity inversion is **not independent audio** and must be held back rather than treated as a valid competing render. The canonical streaming scanner already computes private PCM SHA-256 identities and transformed identities; this companion consumes only its boolean/opaque match signals (`duplicate_pcm_of`, `stereo_swapped_pcm_of`, `polarity_inverted_pcm_of`) and emits only the sanitized category `non_independent_ab_audio`, with no paths, IDs, or hashes. A short or silent pair with inadequate shared PCM evidence continues to abstain as `insufficient_stereo_evidence` first. This detects **exact** PCM transformations only, not lossy encodes, shifted recordings, remasters, pitch/tempo changes or semantically identical tracks.

## Verification / release gates

`tests/test_quality_relative_mono.py` creates procedural 8 kHz stereo PCM: correlated stereo, equal-power anti-phase stereo, half-clip anti-phase, already broken baseline, silence/short excerpts, sample-count mismatch, batch abuse, and subprocess privacy checks. The dedicated hosted workflow pins triggering HEAD on Python 3.13 + 3.14 and reruns canonical quality + CLI privacy regressions under a 192MiB virtual memory budget. Source admission and path identity are rechecked after the two read phases; this is **not atomic under adversarial concurrent renames**. A deliberately red CI run demonstrated two actual false verdicts before the synchronous PCM correction. The second pass uses at most 4096 frames per file/read and retains only window accumulators; the canonical 32MiB/2M-frame input caps still apply.

This is a heuristic from 100ms RMS windows, **not** perceptual mono/LUFS or a full phase-coherence test. Sparse speech/percussion, musical intentional stereo effects, and other playback conditions require listening review. The release gate remains real rights-safe tracks, frozen study and independent blinded listeners (ML-05); no preview or model download and no shared engine, CLI, evaluator, VPS, queue, or worker branch mutation. Do not merge a draft without exact-head CI, independent integration review and lease coordination.
