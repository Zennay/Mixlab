# MixLab Event Brief Studio — build a set by describing the evening

The **Event Brief Studio** is an offline, local-first DJ planning screen. It
takes SHA-pinned **human** BPM/energy/tag notes about permitted local songs and
offers a responsive, editable set proposal. It has no uploaded tracks, remote
services, models, inferred key/phrase/cues or automatic tempo matching.

## 1. Prepare permitted local notes once

Put 2–20 permitted local WAV/MP3/FLAC/etc. songs in a private folder outside
Git and record real, manually verified BPM, subjective energy 1–10 and optional
genre/mood tags:

~~~bash
python3 -m mixlab.journey notes \
  /private/music \
  /private/music/energy-notes.private.json
~~~

MixLab computes a SHA-256 content hash of each selected local song but does
not copy it. The resulting human notes are private (0600) and must not be
committed or shared. Audio formats other than canonical WAV may require
already-installed local FFmpeg at the subsequent rendering stage.

## 2. Launch an offline, editable event brief

~~~bash
python3 -m mixlab.journey_workspace \
  /private/music \
  /private/music/energy-notes.private.json \
  /private/music/my-event-studio.private.html
~~~

Open `/private/music/my-event-studio.private.html` in a browser on your own
computer. It is **a standalone file, not an internet app**. There are no
network requests or remote scripts.

Choose your **energy storyline** (build / peak / late peak / release), desired
number of tracks (2–11), optional exact manually verified BPM group, mood/genre
preference, opening song, closing song and excluded songs. Press **Generate my
set order**. MixLab uses a bounded local beam search through at most 20
annotated songs to prefer the chosen energy shape while penalizing abrupt
jumps. Every selected song is in one **same-BPM** group; the planner cannot
time-stretch music, derive key from sound or rank actual transition quality.

The result includes an energy chart (dashed target, solid annotated energy),
individual local filenames and each song's difference from the desired
energy. Move tracks with up/down controls. A fixed requested opening/closing
song is locked while editing; to change an anchor, update the brief and
regenerate. Change the brief as often as needed; this changes only in-memory
planning, never the original annotations or media.

Choose **Save private set plan** to download a new
`mixlab-event-journey.private.json`. Move it alongside the original
music files. The JSON contains filenames, source SHA-256 hashes,
manually supplied BPM, energy, tags, target energy and selected brief
constraints. It contains **no audio** and no inferred rights.

## 3. Approve, annotate exact cues and render the real full set

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/confirmed-event-playlist.private.json \
  /private/confirmed-event-session \
  --journey-plan /private/music/mixlab-event-journey.private.json \
  --beats 16 \
  --full-set-wav /private/confirmed-event.wav \
  --family bass_swap
~~~

Playlist Studio reopens **every selected source** and rejects changed SHA
hashes, an invalid schema or a cross-tempo route. It asks **Accept this exact
suggested order? Type yes**, followed by explicit source rights and
provenance for each song, and *manually checked* incoming/outgoing cue
seconds. Until this is completed there is no approved DJ set, and no WAV.
When opted into, an existing offline FFmpeg/FFprobe can also produce a
private MP3/FLAC via `--delivery NEW.mp3|NEW.flac`.

For `--manifest-only` and later `--resume`, follow the existing
[guided playlist studio](guided-playlist-studio.md) conventions.

## Evidence and boundaries

- The browser only receives source hashes and **manual metadata** already
  explicitly prepared by the user. The page is written to a **new** local
  0600 HTML, next to the music and outside Git. No filenames, private paths,
  SHA data or audio should be uploaded.
- The browser-generated plan is **never** considered automatically approved.
  Existing MixLab source, rights, hash and renderer gates remain authoritative.
- A profile shape is a creative suggestion. No reliable automatic beat, key,
  downbeat, phrase or crowd intelligence is implied; the M1 Transition Lab
  remains open pending real, rights-safe listening evidence and owner review.
- The workspace cannot save a rendered full mix without the explicitly
  separate, approved, CLI-based Playlist Studio run. This is intentional
  to prevent implied source licenses and accidental private media exposure.
