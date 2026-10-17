# MixLab Offline DJ Demo — hear the product without providing music

The MixLab M1 demo is a **product entry point**, not a QA/test suite.
With one command, it synthesizes two original short musical recordings
entirely on your machine, then exercises the ordinary user-facing
music importer, real four-family DSP Transition Studio, visual cue editor
and complete two-track WAV mix exporter.

It needs **only Python 3.10+**, no FFmpeg, internet connection,
AI model download, music subscription or copyrighted sample files.

## Start the demo

From a local checkout of Zennay/Mixlab, pick a new private directory
outside the checkout:

~~~bash
python3 -m mixlab.demo /private/mixlab-demo-01
~~~

Open /private/mixlab-demo-01/index.html in your local browser.

You can now choose:

1. **Hear the transition styles** — the standard M1 local Transition
   Studio renders baseline, bass swap, echo exit and hard cut on real
   generated PCM16 audio, not mock UI.
2. **Play the complete two-song mix** — a continuous WAV with a
   song-A lead-in, actual bass-swap DSP transition and remainder of song B.
   Download the private WAV from the local listening page.
3. **Edit cue positions visually** — see each track's actual RMS
   energy waveform, click to change the start, nudge by beats and
   audition the selected segment. Saving exports a JSON with the
   original source checksum rather than embedding audio.

The two source recordings are 24 seconds each, 120 BPM in 44.1 kHz
PCM16 stereo. They contain original procedural kick, snare, hats,
bass and chord/pad tones. They use no commercial recording or
downloaded samples, with a 16-beat declared transition from
song A at 16 seconds to song B at 8 seconds.

## Generated private files

~~~text
/private/mixlab-demo-01/
  index.html                         # Open this
  sources/
    demo-song-01.wav
    demo-song-02.wav
    demo-source-spec.json            # Rights: synthetic
  audition/
    sources/
      source_manifest.json
      audio/*.wav
      cue-editor.html
    excerpts/
      library.json
      *.wav
    studio/
      index.html
      auditions/demo-pair-001/*.wav
  full-song/
    full-song-mix.wav
    index.html
    full-mix-receipt.private.json
~~~

All music and rendered assets are local, private and stored outside Git.
The generator does not open ports or upload files, and never touches
or overwrites an existing directory. A failed first run removes only
its newly created demo folder.

## What this does — and does not — establish

This is a **playable product demonstration** showing the creative
capabilities with synthetic, automatically generated source material.
It makes no claims about actual artist recordings, musical transition
quality preferences, rights to external tracks, learned beat/downbeat
models, source separation or autonomous set planning.

The M1 milestone remains open until its predeclared, externally
rights-cleared real-track and blind-listener comparison gates are
actually satisfied. A functional demo is not a scientific preference
result or permission to distribute other people's copyrighted music.

To switch from this safe synthetic example to real local music,
follow docs/guided-local-project.md and
docs/interactive-private-studio.md. For supported native PCM16 WAV the
entire pipeline stays Python-only. MP3, FLAC and M4A still require
preinstalled local FFmpeg and FFprobe.
