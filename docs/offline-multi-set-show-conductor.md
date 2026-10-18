# Offline Show Conductor — several completed real sets, one manual event

**MixLab M1 product workflow, not M1 sound-quality evidence.** The Show
Conductor arranges **2–6 independent, already rendered, privately permitted**
full-length MixLab WAV sets into one planned show. It neither mixes the sets
together nor downloads music. A person controls when a set starts, stops,
changes, or skips chapters.

## Create your event cockpit

First finish at least two real approved MixLab sessions using Playlist Studio
or Event Publisher, with their canonical full WAV and private output receipts.
For example, each Event Publisher output contains
`studio-session/` and `final-set.wav`:

```bash
python3 -m mixlab.show_conductor prepare \
  /private/event-operations/mixlab-show-control.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav \
  /private/encore/studio-session /private/encore/final-set.wav \
  --start 19:30 --break-minutes 10
```

The standalone new HTML must be in a trusted folder outside your recordings,
Git and the original sessions. The CLI reopens every original MixLab Studio
session and PCM16 output receipt, re-hashes the full real WAV and checks the
original source/selection provenance and exact chapter positions. Missing,
duplicate, or symlinked original files are rejected.

The output HTML contains only **labels, actual durations, exact chapter
timestamps, output byte counts and full WAV SHA-256 fingerprints**. There is
no audio byte, absolute local path, rights document or recording inside it.
This helps keep the operator desk easy to carry separately from the media.

## Manually perform or rehearse the planned show

Open the HTML locally on the machine with permission to play your recordings.

1. Every set appears in the real source order, with a private note field and
   an adjustable planned changeover break (0–120 minutes). Change the local
   start clock to preview planned show timing.
2. Attach each set's **actual** `final-set.wav` using its own local file picker.
   The browser now checks **filename, exact byte length and complete SHA-256**
   against the original exported source receipt **before enabling playback**.
   WAV content is read in bounded 1 MiB pieces, not uploaded or cached.
   Watch the verification progress. A wrong file with the same name, duration
   and byte length is rejected; a file-read failure also leaves playback
   locked. Use the original approved recording, never a substitute.
   **Alternative for a complete event:** click **Load a full local show folder**
   and choose a parent folder containing the original completed set-WAVs in
   subfolders. The browser only considers candidate files with the exact
   approved filename and byte size, then computes their entire SHA-256
   offline; **only a full hash match** attaches a file to a set. This avoids
   selecting 2–6 identically named `final-set.wav` files one by one.
   The folder scan is bounded to 1,000 entries and 24 plausible WAV
   candidates, reports what was verified or rejected, and never switches
   currently playing audio. Use individual pickers when directory selection
   is unavailable or the folder is too large. No folder paths are exported.
3. Wait until **Verified full SHA-256** appears for that local WAV.
   Click **Arm set**, then use the native audio controls to start it yourself.
   Chapter buttons seek to **receipt-verified** positions. The Show Conductor
   never automatically crossfades, starts the next file or plays a cue on a
   timed schedule.
4. Press **Arm next set** for an operator-controlled changeover. It stops the
   previous player's object URL first. **Stop / detach file** immediately
   stops and detaches the current local playback URL. Fullscreen is an
   optional display action, not a guarantee of low-latency professional audio.

The stage view gives current set, next cue and total planned show duration.
These are playback and timetable aids, **not evidence of real performance
timestamps, speaker routing, a mixing desk failover or human preference**.

## Export a source-bound private run-of-show

Press **Download source-locked run-of-show plan** to save
`mixlab-show-conductor.private.json` into your private files. That file
contains only the complete SHA-256 list, local planned HH:MM start, explicit
break durations, and up to 300 characters of user-written operator notes
per set. Nothing is uploaded, logged, or persisted in the browser before
this explicit export. No audio is included.

To make a separate print-friendly runbook, repeat **the exact original
SESSION WAV argument pairs in the exact same order**:

```bash
python3 -m mixlab.show_conductor print \
  /private/event-operations/mixlab-show-conductor.private.json \
  /private/event-operations/mixlab-printed-show.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav \
  /private/encore/studio-session /private/encore/final-set.wav
```

The CLI re-hashes and validates **every original entire WAV and session**
again, and refuses a changed source order, mismatched output hash, unknown
notes fields, unexpected breaks, no rights provenance or unsafe output
location. The new report shows planned start/end, exact audio runtime,
actual source SHA, transitions, chapters, chosen breaks and private notes.
It is not silently included in music ZIPs.

**Boundary:** This is a human-operated offline production aid. Browsers
cannot guarantee gig-critical playback, failover, sync, latency or reliable
real-world clocks. Bring an approved backup audio player, licensed/consented
recordings, an operator and an appropriate live sound setup. Existing M1
beat/downbeat, key/stems and independent blinded listening requirements
remain open; a SHA verifies internal provenance rather than music rights or
musical superiority.

## Resume a saved show without re-entering operator notes or breaks

To return to a show plan you explicitly downloaded earlier, use:

```bash
python3 -m mixlab.show_conductor resume \
  /private/event-operations/mixlab-show-conductor.private.json \
  /private/event-operations/mixlab-resumed-show.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav
```

This creates a **new offline stage HTML** with the original human-noted
planned HH:MM start, per-set 0–120 minute gaps and private cue notes already
filled in. It does **not** automatically start music or use browser storage.
The exact original order and complete WAV/source receipt SHA fingerprints are
fully revalidated against the saved plan, with the same canonical source
checks as initial creation. A changed/replaced WAV, foreign JSON, missing
original session, symlinked source or unsafe output path is rejected. You
can continue editing and explicitly download an updated SHA-bound show plan,
then use that exact revision with `show_conductor print` or
`show_master`. The old plan, source sessions and WAVs stay untouched.
