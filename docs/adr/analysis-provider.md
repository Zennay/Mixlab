# ADR: replaceable CPU-first analysis, 15 October 2026

Decision: analysis produces versioned source-hash-addressed records, separate from manually verified rendering recipes. No model download or new dependency is needed for the initial regular-percussion estimator. Streaming channel-energy envelopes, onset lag correlation, observed-gap refinement and phase support generate a **proposal**. Low evidence causes abstention. The score is a heuristic, not calibrated probability; octave errors, syncopation, live drums and tempo drift remain limitations. Downbeats, phrases, vocals and keys stay unavailable unless explicitly annotated. Never infer them by renaming every fourth beat.

ManualProvider retains annotation provenance through its configuration hash and labels every manual value. It validates ordered on-grid downbeats and phrase starts. The private cache is keyed by source bytes, provider class, version and settings. Beat evaluation uses one-to-one matching and penalizes extra beats.

## Provider comparison / next decision

- [librosa 0.11 beat_track](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html): dynamic-programming beat tracker using onset strength, tempo and peak selection. Suitable next CPU benchmark provider, with pinned scientific-Python dependencies. No downbeat guarantee; actual RSS/time must be measured on the same private set.
- [Essentia RhythmExtractor2013](https://essentia.upf.edu/reference/std_RhythmExtractor2013.html) and [KeyExtractor](https://essentia.upf.edu/reference/std_KeyExtractor.html): broader rhythm and tonal analysis. [Official licensing](https://essentia.upf.edu/licensing_information.html) describes AGPL/proprietary routes; evaluate distribution terms before adopting it into a commercial product. No installation made.
- Built-in energy-onset: no packages/models, streaming PCM input, short excerpts only; useful diagnostic baseline, insufficient as the final wedding/club analyzer.

Run `python3 -m mixlab.analysis clip.wav --cache /private/features`. Automatic output never silently changes a render recipe. Compare providers against manually annotated real audio, report beat error and abstention/coverage before automatic mixpoint acceptance. Synthetic regular-click regression only verifies timing mechanics.

## Addendum — measured key and bar/phrase proposals, 17 October 2026

Decision: add two standard-library, CPU-only proposal providers beside the beat estimator, without changing the `Analysis` record, cache schema or provider-specific cache rules owned by `mixlab/analysis/__init__.py`. Both emit their own versioned records (`schema_version` 1) labelled `measured-heuristic` and abstain rather than guess.

- `mixlab/analysis/tonal.py` · `ChromaKeyProvider` (`chroma-kk-v1`): channel-averaged PCM is boxcar-decimated to about 4 kHz; Hann-windowed single-bin DFTs at equal-tempered pitches C2–B5 (A4 = 440 Hz) build a per-frame normalized, octave-folded pitch-class profile (at most 240 frames of 4096 samples). Pearson correlation against rotated Krumhansl–Kessler major/minor profiles ranks the 24 keys. A key is proposed only with correlation ≥ 0.6, margin ≥ 0.04 over the runner-up and ≥ 3 non-silent frames. `key_score`/`key_report` give MIREX-style weighted scores (exact 1, fifth 0.5, relative 0.3, parallel 0.2) plus abstention rate against manual references.
- `mixlab/analysis/meter.py` · `AccentMeterProvider` (`accent-phase-v1`): takes a supplied beatgrid (energy-onset proposal or a verified manual grid). Per beat it measures low-band (150 Hz one-pole) energy, onset contrast and harmonic change, z-normalizes and averages them, and compares each bar phase. Downbeats are proposed only when the best phase has contrast ≥ 0.75, margin ≥ 0.5 and is the bar maximum in ≥ 60 % of whole bars. Phrase starts use a checkerboard novelty over half-phrase windows (energy jump + harmonic distance), so chord changes repeating inside a phrase cancel; they need ≥ 2 whole phrases and the same thresholds pattern (contrast ≥ 1.0, margin ≥ 0.5, consistency ≥ 0.6). Phrase starts are always a subset of proposed downbeats.

This is not "renaming every fourth beat": a uniformly accented click track abstains. Assumptions remain explicit in every record: fixed meter (default 4/4), fixed phrase length (default 8 bars), one global key, standard tuning, no modulation or modal detection. Opposite-polarity stereo cancels in the channel average and therefore abstains. Boxcar decimation is a crude anti-alias filter. Energy-onset octave errors propagate into bar phases; verify the beatgrid first.

Evidence boundary: deterministic synthetic chords, cadences and drum/harmony loops verify mechanics, transposition invariance and abstention only. They are not accuracy on music. Acceptance for M1 still requires a permitted, manually annotated real-track set, reporting `key_report` and downbeat `beat_errors` F-measure with abstention per provider. Proposals never change a render recipe automatically; a human confirms them through `ManualProvider`, which re-validates them on the grid.

```bash
python3 -m mixlab.analysis.tonal /private/library/clip.wav
python3 -m mixlab.analysis.meter /private/library/clip.wav --bpm 128 --first-beat 0.31
```
