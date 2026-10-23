# MixLab cue suggestions — local, energy-informed audition candidates

Manual DJ cue selection is now supported by a lightweight, **CPU-only,
offline** suggestion tool. It reads the same full-length private PCM16 WAV
sources as [cue preparation](full-track-cue-preparation.md), scores likely
entry/exit windows using relative energy movement and silence, and writes
a path-free local JSON shortlist. A person decides which suggestions to use.

This is **not automatic beat, downbeat, key, stem or phrase recognition**.
Every suggestion is placed on a beat/phrase grid provided explicitly by the
user; the 4/8/16-bar pattern is an assumption, not inferred song structure.

## Usage

Add a manually verified `first_downbeat_seconds` to each source track in
your private `sources.json`. For example:

```json
{
  "id": "song-01",
  "path": "track-one.wav",
  "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
  "bpm": 120,
  "first_downbeat_seconds": 1.35,
  "rights": "licensed",
  "provenance": "Private licensed library"
}
```

Then run, from a checkout containing MixLab:

```bash
python3 -m mixlab.cue_suggest /private/tracks/sources.json /private/cue-suggestions.json
python3 -m mixlab.cue_suggest /private/tracks/sources.json /private/song-01-cues.json --track song-01 --beats 16 --phrase-bars 8 --max-cues 5
```

`--beats` sets the excerpt duration in the source's declared BPM;
`--phrase-bars` sets the manually assumed anchor interval (4, 8 or 16 bars);
`--max-cues` caps each entry and exit shortlist (1–8). The default
search considers 16-beat transitions anchored every 8 bars.

Each source result contains two ranked lists:

- **entry**: favors a low-energy start followed by increasing energy;
- **exit**: favors a relatively energetic start followed by decreasing energy.

Every recommendation includes the proposed start time in seconds, exact
sample-frame anchor, declared transition duration, sampled-RMS starting and
ending dBFS, overall RMS, energy slope, silent-window fraction and an
**internal heuristic score** used only to order the proposals. This score
does not measure musical quality or calibrated confidence.

## From suggestion to actual mixed audio

Copy a selected `start_seconds` from a source's entry or exit list into
that track's `a_start_seconds` or `b_start_seconds` in the private
`sources.json` pair definition. Then use:

```bash
python3 -m mixlab.cueprep /private/tracks/sources.json /private/excerpt-library
python3 -m mixlab.studio render /private/excerpt-library/library.json /private/studio
```

Open `/private/studio/index.html` to audition actual rendered families.
A matched energy shape does *not* imply a good beat, key or vocal handoff;
human checking remains necessary.

## Technical and privacy limits

- Uses the existing full-track checksum/format admission and ordinary
  inode/mtime change checks. Only local permitted PCM16 WAVs are read,
  <=15 min / 256 MiB each, mono/stereo at 8–96 kHz. No audio is uploaded.
- Reads 250-ms blocks and inspects up to ~4,000 sampled PCM frames/second
  while preserving channel-separated square energy to avoid stereo
  cancellation. Analysis is **sampled RMS** and can miss narrow transients;
  it is neither BS.1770 loudness nor spectral, harmonic, vocal or phrase analysis.
- A candidate must fit the track's actual frame count and the selected cue
  length. 80%+ near-silent candidates are excluded.
- Sources retain their declared rights and hashed identity; results only
  contain opaque track IDs, public-format signal statistics, SHA256s and
  score labels. Paths and audio bytes are not emitted in the JSON.
- Output must be a *new* `.json` outside Git. It is created exclusively
  with mode 0600, at most 1 MiB. No shared renderer, study files, CLI,
  QA suites, automation or worker leases are modified.
- If no suitable window is proposed, the result may contain empty candidate
  lists. Do not label this as an analyser defect without manually inspecting
  the song; zero windows is an intentional abstention.

This independent product tool is part of the incomplete M1 workflow and
does not close any human-listener, source-rights or autonomous-MIR gate.
