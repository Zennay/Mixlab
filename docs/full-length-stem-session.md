# One-command Full Stem Session — full-length stems to real transitions

MixLab M1 can now use **full-length, already separated producer vocal and
instrumental stems**, automatically choose the declared manual cue segment,
upmix mono vocals to true stereo PCM (left and right copied sample-exactly),
and render three private WAV transition styles in a playable local browser.

This is not an automatic source-separation model. A producer, DAW, or a
previously approved/local source-separation workflow must supply the stems.
Only process audio you have the legal right to process.

## Full workflow in one command

Place four WAV files in your private source directory (plain uncompressed
PCM16, 8–96 kHz, up to 15 minutes/256 MiB each):

- song-a-instrumental.wav — accompaniment for track A
- song-a-vocals.wav — separated vocal stem for track A
- song-b-instrumental.wav — accompaniment for track B
- song-b-vocals.wav — separated vocal stem for track B

Invoke the standalone offline workflow:

~~~bash
python3 -m mixlab.stem_session \
  /private/my-stems \
  /private/mixlab-stem-session \
  --a-instrumental song-a-instrumental.wav \
  --a-vocals song-a-vocals.wav \
  --b-instrumental song-b-instrumental.wav \
  --b-vocals song-b-vocals.wav \
  --bpm 120 \
  --beats 16 \
  --a-start 72.0 \
  --b-start 40.0 \
  --rights user-permitted \
  --provenance "DAW stems I have the right to process"
~~~

Then open /private/mixlab-stem-session/studio/index.html.

The new full-track session workflow:
1. Reads each of the four private source WAVs with the existing bounded
   PCM16 admission and SHA256 fingerprinting. Every role must be a distinct
   source file; all must have the same sample rate. Recorded legal permission
   and source provenance are mandatory.
2. Cuts exactly the requested number of manually verified beats at the
   chosen outgoing and incoming time positions. No automatic beat detection,
   tempo shifting, song structure guessing or unseen timing adjustment.
3. Handles common DAW stem layouts: **mono vocals alongside stereo
   accompaniment**. Each mono sample is copied to left and right; stereo
   material is copied verbatim. All four cropped outputs therefore match
   the existing canonical stereo stem renderer.
4. Generates a local, checksum-bound four-stem manifest with positions
   normalized to 0 seconds; invokes the established private
   stem_render engine without modifying its DSP algorithms.
5. Renders three real WAV styles: vocal handoff, instrumental bridge and
   drop swap. Generates a playable HTML page with local WAV download links
   and a private technical receipt.

Private output layout:

~~~text
/private/mixlab-stem-session/
  sources/
    a_instrumental.wav
    a_vocals.wav
    b_instrumental.wav
    b_vocals.wav
    stem-manifest.json
  studio/
    vocal_handoff.wav
    instrumental_bridge.wav
    drop_swap.wav
    index.html
    studio-receipt.private.json
  session-receipt.private.json
~~~

## Resource and privacy rules

- Local PCM16 WAV only; 8–96 kHz sample rate, one or two source channels,
  maximum 15 min/256 MiB per source. All four source sample rates must
  match; mixed source channels are automatically normalized to stereo.
  Sample-rate conversion, pitch-preserving tempo alignment and generation
  of stems from mastered mixes are **not** done.
- Maximum 2,000,000 output frames and 32 MiB per cropped stem; streaming
  4096-frame reads keep memory bounded. Four stems are processed
  sequentially, never by parallel render workers. Default render gain
  is -12 dB; clipping rejects rather than distorts or silently limits.
- No FFmpeg is needed to cut compatible PCM16 WAVs. No external model,
  internet service, GPU or audio upload. Stem audio, origins and the
  local listener page remain outside any Git checkout.
- The new project destination must not exist before invocation, and
  cannot be inside the input directory. The project is created mode
  0700; produced files are owner-only mode 0600.
- This module reuses the existing rights declaration, validated source
  frame boundaries and stem DSP renderer. A private session receipt
  binds the source hashes, manually chosen frame offsets and output
  render receipt hash. Incomplete new projects are removed on failure;
  original stems are never overwritten.

## Milestone truth

Using stem-aware rendering is **not** the same as completing M1 automatic
source separation, key/phrase estimation or blind listening. These still
require properly licensed real music, corresponding data and human
preference evidence. This is a creative product feature, not a quality
test or a new QA suite.
