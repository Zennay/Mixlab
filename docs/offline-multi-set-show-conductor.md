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


## Capture a private manual rehearsal journal

During the **offline manual** multi-set stage, MixLab records only local browser
operator actions after an approved set has been SHA-verified and armed:
arm, playback start, manually marked WAV cue position, Stop, and WAV end.
Write an optional
**private 120-character cue annotation** next to the player (for example
lighting, speech, or handoff context) before pressing **Mark local WAV cue
position**. That annotation is intentionally included in the explicitly
exported private journal and its rendered private report, never in public
music delivery ZIPs or set-level plan exports.
Entries carry the exact source set index, native browser seek position and a
page-relative monotonic elapsed time. They do **not** prove what speakers,
attendees, a venue clock or a human DJ actually heard. Nothing is stored
persistently until you deliberately choose **Download private rehearsal
journal**. Maximum 256 records per page (48-hour elapsed ceiling).

To create a **new** private, printable report in a separate approved folder:

```bash
python3 -m mixlab.show_rehearsal \
  /private/event-operations/mixlab-show-rehearsal.private.json \
  /private/event-operations/mixlab-rehearsal-report.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav
```

Use the same original ordered source-session/full-WAV pairs as Show Conductor.
The CLI independently verifies every original WAV SHA, studio/source receipts,
and exact event set indices and WAV positions. It refuses a foreign source list,
extra/incorrect fields, out-of-order entries or invalid private output
location. The report shows elapsed page time, action, set and WAV position,
plus full original SHA fingerprints. For a manual cue mark it additionally
shows the closest real source-receipt chapter within 60 WAV seconds and
the signed WAV-position difference; marks farther away stay unpaired.
A per-set browser-event overview counts play actions, manual marks and
ended events. None of those counts prove audible performance or chapter timing. It includes **no audio bytes, local file
paths or unrelated set-level operator notes**; **your deliberately entered
per-cue annotations are included** in this private document. Handle the exported JSON and report as
private operational materials. This is a rehearsal annotation workflow, not
independent human blind listening, real-world venue evidence, playback timing
certification or permission to use the music.

## Reopen an actual full Show Conductor with human-selected rehearsal cues

After exporting a private selection from the offline multi-take comparison
(`mixlab.show_rehearsal_compare`), you can load those manually selected
cue positions **directly inside the full Show Conductor**. The existing
show schedule, breaks, manual set controls, planned times, rehearsal-log
export and full SHA-256 original-WAV file admission all remain unchanged.

```bash
python3 -m mixlab.show_conductor prepare \
  /private/event-operations/mixlab-show-with-selected-cues.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav \
  --rehearsal-selection /private/rehearsal-review/mixlab-rehearsal-take-selection.private.json \
  --journal /private/rehearsals/take-01/mixlab-show-rehearsal.private.json \
  --journal /private/rehearsals/take-02/mixlab-show-rehearsal.private.json
```

The same optional flags also work with `show_conductor resume` and an
existing saved private schedule. The official source/WAV receipt is
checked for **every complete original set**; each journal and original
canonical SHA, human-selected index and exact source order are checked
again. The HTML displays the chosen manually marked cue positions,
nearest source chapter and explicitly written private cue annotations
under the existing chapter buttons. Those buttons **seek only** after
the browser locally verifies the attached complete WAV SHA-256. Nothing
autoplays or changes the original recorded audio.

The page contains private operator annotations; do not publish it or add
it to a media USB package. The ordinary exported Show Conductor schedule
keeps its unchanged source-locked JSON schema and does not silently
include past private rehearsal cue notes. This is not independent
performance measurement or a substitute for actual approved audio,
human listening/rights evidence or professional live DJ equipment.
