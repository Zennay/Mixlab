# Full-track cue compiler (M1 product delivery)

MixLab's renderer deliberately accepts at most 2 million PCM frames / 32 MiB per
input. You can now prepare transitions from **ordinary full-length tracks**
without raising those limits or uploading any media. The independent
`mixlab.cueprep` package reads bounded uncompressed WAV sources privately,
extracts manually selected cue windows, and generates an ingest-compatible
`library.json` plus a private cue provenance receipt.

**This is real audio preparation, not automatic mixing or proof of musical quality.**
There is no tempo matching, beat detection, key estimation, stemming, format conversion,
DJ quality scoring or license verification. Track BPM and cue positions are supplied
and verified by a person. The established renderer still needs matching BPM, sample
rate and channel count.

## Offline workflow

1. Keep all source WAVs and both manifests in a **private directory outside
   the Git checkout**. Only use local music for which analysis and derivative
   processing are permitted. Uncompressed PCM16 WAV, mono/stereo, 8–96 kHz,
   <=15 min and <=256 MiB are accepted.
2. Get each track's SHA256 with a local checksum utility and add it to the
   source spec. Declare `rights`, `provenance`, measured-by-human `bpm`,
   and optional `recording_id` / `partition`.
3. Create a private JSON spec like:

```json
{
  "schema_version": 1,
  "purpose": "development-pilot",
  "tracks": [
    {
      "id": "song-01",
      "path": "track-one.wav",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
      "bpm": 120,
      "rights": "licensed",
      "provenance": "Private licensed library",
      "recording_id": "recording-01",
      "partition": "development"
    },
    {
      "id": "song-02",
      "path": "track-two.wav",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
      "bpm": 120,
      "rights": "licensed",
      "provenance": "Private licensed library",
      "recording_id": "recording-02",
      "partition": "development"
    }
  ],
  "pairs": [
    {
      "id": "pair-001",
      "a": "song-01",
      "b": "song-02",
      "a_start_seconds": 125.5,
      "b_start_seconds": 29.0,
      "beats": 16
    }
  ]
}
```

4. Run locally from a checkout containing MixLab:

```bash
python3 -m mixlab.cueprep /private/tracks/sources.json /private/mixlab-cue-pack
python3 -m mixlab validate /private/mixlab-cue-pack/library.json
python3 -m mixlab benchmark /private/mixlab-cue-pack/library.json /private/my-transition-review-pack
```

The destination **must not exist**, must be outside the source library,
and its parent directory must already exist. It is created mode 0700.
No WAV, source path, or listening result is committed or transmitted.

A pair becomes `pair-001-a.wav` and `pair-001-b.wav`, beginning
at the chosen positions, with exactly `round(beats * 60 / bpm * sample_rate)`
frames. The generated library uses local relative excerpt paths, original
permission declarations, source recording IDs, SHA256 hashes of the extracted
WAVs, zero-based excerpt cues, and the original pair ID and beat duration.
For 10 pairs the compiler emits 20 excerpts (within the established
50-track/10-pair manifest limits).

`cue-provenance.private.json` records original file checksums, manual source
cue positions, exact frame offsets and the checksum of `sources.json`. The
existing `mixlab.ingest.validate_library` is invoked before the compiler reports
success; on errors a newly created incomplete destination is removed.

## Source specification and boundaries

- `tracks`: 2–20 unique declared WAV recordings, IDs using letters, digits,
  period, underscore or dash; explicit rights declaration
  (`synthetic`, `licensed`, `user-permitted` or `public-domain`);
  nonempty provenance; SHA256; manual BPM 30–300. The optional
  `partition` must be given on *every* track if supplied on any track.
  The optional `recording_id` follows the original recording across cues.
- `pairs`: 1–10 unique pairs, each selecting **two distinct source IDs**,
  `a_start_seconds` / `b_start_seconds` (zero-based exact manual timestamps)
  and optional `beats` (1–64, default 8). Cross-partition pairings and
  format/BPM mismatches are rejected. Cue + transition must fit both tracks.
- Strict frame output <=2 million frames and <=32 MiB per excerpt, even if
  the source file is longer. All PCM is copied in 4096-frame blocks. Byte
  identity is checked against declared source SHA256; ordinary on-disk source
  replacement/modification is rejected by size, inode and timestamps.
- Reject absolute, parent-traversing or symlinked source paths, unsupported
  WAV coding, duplicate IDs/JSON keys, malformed input and pre-existing
  output. There is no download, transcoding, auto-overwrite, and no network.
- These file checks are not a defense against a malicious concurrent writer
  who can manipulate source file metadata or access the private output
  directory. Treat the input directory as trusted local storage.

**Frozen studies:** compile/freeze source and output manifests *before* any
listener ratings. The generated clips of the same original recording inherit
one `recording_id`, so MixLab's track-level split checker can reject known
recording reuse across partitions. This cannot infer alternate masters;
curate recording IDs carefully. Do not promote synthetic or ad-hoc rehearsal
pack output as human preference evidence.

## Integration status

This tool is an additive M1 precursor: it supplies renderable audio for real
manually chosen track segments without changing `mixlab.cli`, the renderer,
analysis providers, evaluation tools or their in-flight PRs. Future work:
verified beat/phrase/key suggestions, licensed real-track pilot and the
independent blind listening review. No automatic discovery or whole-set
planner is claimed.
