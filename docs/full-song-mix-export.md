# Full-song Mix Export — complete two-track DJ playthrough

The full-song exporter makes a genuine continuous private music mix using
the existing M1 DSP transition, instead of stopping at short audio
previews. It starts with source song A, inserts the rendered A→B transition
at the manually approved moment and then plays song B to the end.

Incoming song B material before its chosen transition start is skipped.
Outgoing song A material after the chosen transition is skipped. This
is overlap mixing, not simply concatenating songs.

## Create a full-length local mix

First use the existing guided local project wizard and either
media_import or interactive_session to prepare rights-declared full-length
PCM16 WAVs with manually verified BPM and cue positions. If you used the
new browser waveform editor, finish that session and use its
approved-cues.json as the input to this command:

~~~bash
python3 -m mixlab.full_mix \
  /private/mixlab-interactive-01/sources/approved-cues.json \
  /private/mixlab-song-mix-01 \
  --pair pair-001 \
  --family bass_swap \
  --gain-db -9
~~~

Input can also be any standalone approved full-length PCM16 source manifest.
The output directory must not exist yet and must be outside the source
music directory and all Git worktrees.

This creates exactly:

~~~text
/private/mixlab-song-mix-01/
  full-song-mix.wav
  index.html
  full-mix-receipt.private.json
~~~

Open index.html to play the whole mix and download the generated WAV.
All original tracks remain untouched and local; no web server, external
model, upload or new package is used.

## Supported DJ controls

Use --family baseline, bass_swap, echo_exit, or hard_cut. Every family
uses the same established mixlab.dsp.render engine, on strictly bounded
A/B excerpts. The remainder of both songs is streamed using 4096-frame
PCM16 chunks, not held in memory.

Use --gain-db from -24 to 0; default -9. The common manual gain is applied
to the full song portions and the established transition to avoid an
artificial loudness jump around the splice. This is not measured loudness
matching or automated mastering.

The selected pair requires manually confirmed source BPM and
a_start_seconds/b_start_seconds. Both songs must have equal declared
BPM, matching PCM sample rates and channels. No pitch-preserving time
stretch, automatic beat matching, downbeat inference, key detection or
automatic style selection is implied.

Maximum source length is 15 minutes per track, source WAV size 256 MiB;
transition excerpts are limited to 2 million frames and 32 MiB, and the
whole private WAV to 512 MiB. These protections keep the workflow bounded.
The output WAV, browser page and SHA256-bound source/render receipt are
owner-private; failures clean only their freshly created project directory.

This produces a creative offline mix, not a frozen blind preference
study or verified copyright permissions. Users must independently have
the right to process and export each source recording. Do not upload
protected recordings to a public repository or service.

This additive product workflow does not change the established
renderer, MIR, ingest, research or quality-validation components.
