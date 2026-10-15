# ADR: replaceable CPU-first analysis, 15 October 2026

Decision: analysis produces versioned source-hash-addressed records, separate from manually verified rendering recipes. No model download or new dependency is needed for the initial regular-percussion estimator. Streaming channel-energy envelopes, onset lag correlation, observed-gap refinement and phase support generate a **proposal**. Low evidence causes abstention. The score is a heuristic, not calibrated probability; octave errors, syncopation, live drums and tempo drift remain limitations. Downbeats, phrases, vocals and keys stay unavailable unless explicitly annotated. Never infer them by renaming every fourth beat.

ManualProvider retains annotation provenance through its configuration hash and labels every manual value. It validates ordered on-grid downbeats and phrase starts. The private cache is keyed by source bytes, provider class, version and settings. Beat evaluation uses one-to-one matching and penalizes extra beats.

## Provider comparison / next decision

- [librosa 0.11 beat_track](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html): dynamic-programming beat tracker using onset strength, tempo and peak selection. Suitable next CPU benchmark provider, with pinned scientific-Python dependencies. No downbeat guarantee; actual RSS/time must be measured on the same private set.
- [Essentia RhythmExtractor2013](https://essentia.upf.edu/reference/std_RhythmExtractor2013.html) and [KeyExtractor](https://essentia.upf.edu/reference/std_KeyExtractor.html): broader rhythm and tonal analysis. [Official licensing](https://essentia.upf.edu/licensing_information.html) describes AGPL/proprietary routes; evaluate distribution terms before adopting it into a commercial product. No installation made.
- Built-in energy-onset: no packages/models, streaming PCM input, short excerpts only; useful diagnostic baseline, insufficient as the final wedding/club analyzer.

Run `python3 -m mixlab.analysis clip.wav --cache /private/features`. Automatic output never silently changes a render recipe. Compare providers against manually annotated real audio, report beat error and abstention/coverage before automatic mixpoint acceptance. Synthetic regular-click regression only verifies timing mechanics.
