# Private music importer — MP3, FLAC, M4A to MixLab WAV

MixLab M1 now has an opt-in import pathway for a **real local music collection**.
The first three product features needed uncompressed WAV sources. The importer
normalizes your permitted local media into the PCM16 stereo format consumed by
[manual cue preparation](full-track-cue-preparation.md),
[energy cue suggestions](cue-suggestions.md) and
[Transition Studio](transition-studio.md).

Music files **stay on your computer**. For MP3/FLAC/M4A and other codecs, an already installed local `ffmpeg` + `ffprobe` is required. **Native 44.1kHz PCM16 WAV is imported without FFmpeg**, including mono-to-stereo upmix. MixLab never installs these tools, downloads media,
connects to streaming services or exposes an HTTP server.

## Create a private source manifest

Put a JSON file next to your music files, e.g. `/private/songs/input.json`:

```json
{
  "schema_version": 1,
  "purpose": "development-pilot",
  "tracks": [
    {
      "id": "song-01",
      "path": "tracks/one.mp3",
      "sha256": "REPLACE_WITH_REAL_LOWERCASE_SHA256",
      "rights": "user-permitted",
      "provenance": "My own local permitted music collection",
      "bpm": 120,
      "first_downbeat_seconds": 1.5,
      "recording_id": "recording-01",
      "partition": "development"
    },
    {
      "id": "song-02",
      "path": "tracks/two.flac",
      "sha256": "REPLACE_WITH_REAL_LOWERCASE_SHA256",
      "rights": "user-permitted",
      "provenance": "My own local permitted music collection",
      "bpm": 120,
      "first_downbeat_seconds": 0.25,
      "recording_id": "recording-02",
      "partition": "development"
    }
  ],
  "pairs": [
    {
      "id": "pair-001",
      "a": "song-01",
      "b": "song-02",
      "a_start_seconds": 20,
      "b_start_seconds": 32,
      "beats": 16
    }
  ]
}
```

Compute source SHA256 locally: `sha256sum /private/songs/tracks/one.mp3`.
If the source changes you must deliberately update its checksum in the
manifest. A SHA declaration is **not** a licence: you still need permission
for each recording and must honestly declare `rights` and `provenance`.

Supported local source formats: WAV, MP3, FLAC, M4A, AAC, OGG, OPUS, AIFF/AIF
(using codecs your preinstalled FFmpeg supports). No HTTP URLs, symlinked
source components, absolute paths, path traversal, automatic downloads,
artist/title scraping or playlist service integration.

## Import and make your first real transition

```bash
python3 -m mixlab.media_import /private/songs/input.json /private/mixlab-import
python3 -m mixlab.cue_suggest /private/mixlab-import/source_manifest.json /private/mixlab-cue-suggestions.json
python3 -m mixlab.cueprep /private/mixlab-import/source_manifest.json /private/mixlab-excerpts
python3 -m mixlab.studio render /private/mixlab-excerpts/library.json /private/mixlab-studio
```

Open `/private/mixlab-studio/index.html` to listen to four actual
transitions per pair. Use the independent private Studio export command to
save your chosen mix transition as WAV. Manually edit each pair's
`a_start_seconds` and `b_start_seconds` in the **imported**
`source_manifest.json` if you want to use the ranked energy-based cue
suggestions before generating the excerpts.

The **imported project** is a new private directory containing:
- `audio/song-01.wav` and `audio/song-02.wav`: normalized 44,100-Hz
  stereo PCM16 WAVs, with source tags and cover art removed.
- `source_manifest.json`: input accepted by the other MixLab M1
  modules; contains imported local relative filenames, new SHA256s,
  manual BPM, optional manual downbeat, partition and permission declarations.
- `import-receipt.private.json`: original and converted checksums,
  source format and conversion provenance without private filesystem paths.

## Resource and trust boundaries

- 2–20 source tracks, 1–10 pair declarations per run. Source size <=512 MiB,
  source duration <=15 minutes (must be available from local media metadata),
  normalized PCM16 WAV <=256 MiB. Canonical full-track reader independently
  inspects each output.
- The output rate is always **44,100 Hz stereo**, even if sources have
  another channel count/rate. This is deliberate normalization; it is
  **not** musical beatmatching or pitch-preserving tempo stretching.
- FFmpeg runs sequentially with one codec/filter thread, local file-only
  protocol restrictions, output-byte limit, and per-source default 600-second
  timeout (configurable 30–900 s with `--timeout-seconds`). Any decoder
  failure leaves the source files untouched and deletes the newly created
  incomplete output directory. Output is mode 0700 directory / 0600 files.
- Explicit rights, provenance, source content hashes and recording identity
  are kept. Dataset development/evaluation partitions may not share known
  source hashes or recording IDs; cross-partition pairs fail.
- This protects against ordinary accidental source replacement and limits
  media resource usage. It is **not** a malware sandbox for hostile codecs or
  a guarantee of legal ownership. Only import trusted local files with a
  maintained, trusted FFmpeg installation.
- Keep input, output, cue/Studio sessions and licensing documentation
  **outside GitHub**. Publishing converted music or mixes requires a separate
  rights decision. No cloud processing, external service or listener proof
  is implied by a successful conversion.

## Current M1 boundaries

This is an independent local importer, not an audio-quality or MIR engine.
MixLab still requires manually verified source BPM/beat alignment, and the
existing renderer only handles equal-BPM pairs. The active separate
pitch-preserving tempo PR and source-separation/automatic analysis gates are
not replaced. The actual frozen rights-cleared real-music A/B listener study
remains necessary before any claim that the transitions beat crossfades.


## New: FFmpeg-free native WAV workflow

You can now use the complete source import, visual Cue Editor and private
Transition Studio on a machine with **only Python 3.10+** when your
source files are already **uncompressed PCM16 WAV at 44,100 Hz**, mono or
stereo. Each selected source WAV is validated against the manifest's
SHA256, frame count, maximum 15-minute duration and 256 MiB source limit.
Only source PCM bytes are copied into a newly written canonical WAV;
metadata chunks are not copied. A mono source is duplicated sample-wise
to the two stereo output channels. Source sample rate, pitch, speed and
musical timing are never altered.

The standard-library route is used automatically; no CLI flag or
installation is necessary. When any source is MP3, FLAC, M4A, AAC, OGG,
OPUS, AIFF or a noncanonical WAV requiring conversion, that source still
uses FFprobe + FFmpeg and requires those binaries to have been installed
separately. MixLab does not install a decoder, fetch codecs, download
music or bypass music service DRM.

For a WAV-only library, use the guided project wizard (with real BPM,
rights, and manual cues), then the interactive session:

~~~bash
python3 -m mixlab.project_wizard /private/wav-library /private/wav-library/sources.json
python3 -m mixlab.interactive_session start /private/wav-library/sources.json /private/wav-session
~~~

Open /private/wav-session/sources/cue-editor.html, approve your cue
positions, then finish the session with the exported cue selection file.

The import receipt explicitly distinguishes "stdlib PCM16 stereo at
44100 Hz" from "ffmpeg PCM16 stereo at 44100 Hz". All other private
checksums, provenance, rights and output limits remain in force.
