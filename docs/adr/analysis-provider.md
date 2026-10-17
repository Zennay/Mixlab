# ADR: replaceable CPU-first analysis, 15 October 2026

Decision: analysis produces versioned source-hash-addressed records, separate from manually verified rendering recipes. No model download or new dependency is needed for the initial regular-percussion estimator. Streaming channel-energy envelopes, onset lag correlation, observed-gap refinement and phase support generate a **proposal**. Low evidence causes abstention. The score is a heuristic, not calibrated probability; octave errors, syncopation, live drums and tempo drift remain limitations. Downbeats, phrases and vocals stay unavailable unless explicitly annotated; a global key may be *proposed* by `chroma-key` (below), never silently adopted. Never infer them by renaming every fourth beat.

ManualProvider retains annotation provenance through its configuration hash and labels every manual value. It validates ordered on-grid downbeats and phrase starts. The private cache is keyed by source bytes, provider class, version and settings. Beat evaluation uses one-to-one matching and penalizes extra beats.

## Provider comparison / next decision

- [librosa 0.11 beat_track](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html): dynamic-programming beat tracker using onset strength, tempo and peak selection. Suitable next CPU benchmark provider, with pinned scientific-Python dependencies. No downbeat guarantee; actual RSS/time must be measured on the same private set.
- [Essentia RhythmExtractor2013](https://essentia.upf.edu/reference/std_RhythmExtractor2013.html) and [KeyExtractor](https://essentia.upf.edu/reference/std_KeyExtractor.html): broader rhythm and tonal analysis. [Official licensing](https://essentia.upf.edu/licensing_information.html) describes AGPL/proprietary routes; evaluate distribution terms before adopting it into a commercial product. No installation made.
- Built-in energy-onset: no packages/models, streaming PCM input, short excerpts only; useful diagnostic baseline, insufficient as the final wedding/club analyzer.

Run `python3 -m mixlab.analysis clip.wav --cache /private/features`. Automatic output never silently changes a render recipe. Compare providers against manually annotated real audio, report beat error and abstention/coverage before automatic mixpoint acceptance. Synthetic regular-click regression only verifies timing mechanics.

## Key proposal — 17 October 2026

`ChromaKeyProvider` (`chroma-kk-v1`, `--provider chroma-key`) adds a stdlib, streaming global-key proposal. Mono mix, integer box-filter decimation to about 11 kHz, 4096/8192-point Hann FFT at 50 % hop, then only *tonal peaks* vote: local maxima at least 3x their ±8-bin mean, folded into pitch classes over C2–C7 at A4 = 440 Hz. The magnitude chroma is Pearson-correlated with the 24 rotated Krumhansl–Kessler profiles. Output: key, Camelot code via `camelot()`, top-3 candidates, correlation and best-minus-second margin (stored as `key_confidence`, a heuristic margin and not a probability), with `key_source = "measured-heuristic"`.

It abstains with a reason for: fewer than 4 frames, RMS below -50 dBFS, less than 3 % of in-band magnitude in tonal peaks (noise, percussion), best correlation below 0.55, or a margin below 0.02. Thresholds come from synthetic material only and must be re-checked on annotated real audio.

Synthetic evidence (local container, not VPS): 24/24 keys for I–IV–V–I and harmonic-minor i–iv–V–i progressions with three harmonics, at 8 and 22.05 kHz. Correct with drums at 44.1 kHz, mono 48 kHz and +30/+45 cents detuning. Noise, click trains, silence and sub-frame clips abstain. Noise had a tonal fraction of 0.0007 against at least 0.32 for the chords. A 32 s 48 kHz stereo clip took about 2.3 s at 19.6 MiB peak RSS.

Known limits: one key per clip (modulations, DJ edits and mashups are not segmented); modal, atonal and heavily detuned material; relative major/minor and fifth confusions remain likely on real music; box-filter decimation aliases content above about 5.5 kHz. Evaluate with `key_score` (MIREX weights: 1 exact, .5 fifth, .3 relative, .2 parallel, abstention 0, plus coverage reported separately) against manually annotated keys before any harmonic-mixing rule relies on it. Essentia's KeyExtractor remains the stronger candidate if its licence fits.
