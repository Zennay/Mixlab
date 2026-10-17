# Interactive MixLab Studio — from your own songs to real WAV transitions

The **interactive session** connects the fully private source importer, new
visual waveform cue editor, canonical bounded clip compiler and actual
Transition Studio renderer. A real person reviews all pair cue positions
before any final audio is generated.

It intentionally uses TWO actions, because unattended automatic cue
approval would pretend the system knows real musical beats and phrases.
M1 still requires actual beat/downbeat/key analysis and human blind
listening evidence before further scientific claims.

## First create your source library

Use the existing local guided wizard to select 2–20 permitted source
music files (MP3, FLAC, M4A, WAV) and set real source metadata:

~~~bash
python3 -m mixlab.project_wizard /private/my-music /private/my-music/source-spec.json
~~~

Declare rights and provenance honestly. BPM and initial cues remain
human-verified. For energy-based optional suggestions, also provide the
first manual downbeat on every track.

## Step 1 — import and visually choose cues

~~~bash
python3 -m mixlab.interactive_session start /private/my-music/source-spec.json /private/mixlab-interactive-01
~~~

This creates a new private project and does not alter the source library.
It:
- Converts supported audio with an already installed local FFmpeg and FFprobe
  into canonical PCM16 WAV.
- Generates locally playable waveform data with normalized channel-safe
  energy and a visually editable two-deck cue editor.
- Writes a private project receipt tying the original source checksum,
  converted manifest checksum, and cue-editor HTML checksum together.

Open /private/mixlab-interactive-01/sources/cue-editor.html in your local
browser. Pick the A/B passage, preview it, use beat- or bar-nudges and
save the browser's small selection file as
mixlab-cue-selections.json. No source audio is uploaded.

To also calculate private, purely energy-based manual-grid cue suggestions:

~~~bash
python3 -m mixlab.interactive_session start /private/my-music/source-spec.json /private/mixlab-interactive-02 --suggestions
~~~

Suggestions never automatically overwrite your manually approved cues.
They are a separate local reference JSON and do not imply machine-learned
beat or phrase knowledge.

## Step 2 — finalize the approved cues and render

~~~bash
python3 -m mixlab.interactive_session finish /private/mixlab-interactive-01 /private/mixlab-cue-selections.json
~~~

Now open /private/mixlab-interactive-01/studio/index.html.

Finishing does the following:
- Checks the session's original source manifest, converted library manifest
  and cue-editor checksum have not changed.
- Accepts **only complete, unique** pair choices bound to this exact input
  manifest SHA256, verifying chosen starts are legal for actual source
  frame lengths and the established PCM16 resource budget.
- Writes a NEW approved cue manifest in the converted source library,
  compiles all A/B excerpts with the canonical permitted PCM reader, and
  renders four actual transition families.
- Produces a local playable and downloadable Transition Studio plus private
  receipt hashes for the approved manifest, compiled excerpts and audio.
- Leaves the original source music and original manifests unmodified.
  Completion can happen only once per private project folder. A second
  experimental attempt should be a new project / version.

To reduce render work while iterating with many pairs:

~~~bash
python3 -m mixlab.interactive_session finish /private/mixlab-interactive-01 /private/mixlab-cue-selections.json --pair pair-001
~~~

The selected pair alone is audition-rendered while the excerpt library
retains the declared registered pairs and manual provenance.

## Project structure

~~~text
/private/mixlab-interactive-01/
  sources/
    audio/*.wav
    source_manifest.json
    cue-editor.html
    approved-cues.json                 # after finish
    import-receipt.private.json
  excerpts/
    library.json
    *.wav
    cue-provenance.private.json
  studio/
    index.html
    auditions/<pair>/*.wav
    studio-receipt.private.json
  project-receipt.private.json
  completed-receipt.private.json        # after finish
  cue-suggestions.private.json         # optional
~~~

## Design and permission boundaries

- Standard-library orchestration around existing M1 features;
  FFmpeg/FFprobe need to be already installed locally for MP3/FLAC/M4A
  conversion, but are never installed automatically.
- 2–20 registered tracks, 1–10 declared pairs and the upstream
  maximum file, duration, CPU and frame budgets remain enforced.
- Offline file-based editor and Studio. No HTTP server, public endpoint,
  Spotify API, model download, internet sync, remote renderer or service.
- All output directories are new and private; existing audio, manifests,
  source rights declarations and experimental packages are never
  overwritten. An incomplete preparation removes only its newly created
  session. A failed finalization only removes the files it created for
  that unfinished stage, preserving normalized source audio and the
  original browser/editor project.
- This is a **manual, unblinded creative workflow**. It is distinct from
  the independently governed frozen evaluation pack; it does not claim
  source separation, automatic downbeat/key/phrase detection or human
  preference against baseline.

No active owners of analysis, DSP, evaluation/QA or zCloud shared runtime
files are replaced or overridden; the package is an isolated product
entry point.


## NEW: make a complete two-song mix while finishing the session

The finish step can now produce a **full-length WAV in the same
private interactive project**, instead of only short transition previews.
Choose the exact pair and one of the existing four DSP families:

~~~bash
python3 -m mixlab.interactive_session finish \
  /private/mixlab-interactive-01 \
  /private/mixlab-cue-selections.json \
  --pair pair-001 \
  --full-song \
  --full-song-family bass_swap \
  --full-song-gain-db -9
~~~

The normal private transition audition remains available at
studio/index.html. The newly connected full-song output appears at:

~~~text
full-song/
  full-song-mix.wav
  index.html
  full-mix-receipt.private.json
~~~

Open full-song/index.html to hear track A from its beginning through the
chosen transition into the remaining part of track B, then download the
whole private WAV.

This is a complete M1 two-track creative export, not M3 autonomous
multi-song set planning. The workflow still requires manually checked
pair BPM and cue points, explicit local music rights, and exact PCM
format compatibility. It never infers automatic DJ alignment or
publishes source music. The session's final receipt now also binds
the full-song export receipt SHA256 when this option is enabled.

Without --full-song, the default finish behavior is unchanged. When
using --full-song, --pair is required; this avoids unexpectedly exporting
every source recording in a 10-pair project. Each project is finalized
once; create a new project to try another full-song family.
