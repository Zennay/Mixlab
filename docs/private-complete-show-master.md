# Complete Show Master — approved set WAVs, real PCM16 and manual silent gaps

This is a **separate, human-approved offline production artifact** after
using MixLab [Show Conductor](offline-multi-set-show-conductor.md).
It does not create DJ-style crossfades between entire event sets or establish
music rights. The existing transition families are already rendered *inside*
each approved complete set.

## From a private show plan to a real full-length show

First prepare the Show Conductor from 2–6 separately approved, already
finished MixLab Studio session + complete WAV pairs. In its offline browser,
set the planned break minutes (0–120 per gap) and your private operator
notes, then **explicitly download**
`mixlab-show-conductor.private.json`. The source filename/size/duration
checks inside the browser are only a convenience. This separate Python
renderer revalidates the **complete original PCM16 WAV SHA** of each set.

Pass the **same ordered source pairs** to the new command:

```bash
python3 -m mixlab.show_master \
  /private/event-ops/mixlab-show-conductor.private.json \
  /private/new-real-show \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav
```

MixLab checks the private JSON schema, the exact ordered list of original
full WAV SHA-256s, each canonical Studio session and source/selection receipt,
the operator's manual break durations and text notes, WAV channel/PCM
format, common sample rate and the exact total future output frame count.
The combined real PCM16 file including **digitally silent breaks** is
restricted to **768 MiB**, so large multihour plans may be refused
*before* creating any output. No automatic time-stretch, sample-rate
conversion, gain changes, tempo matching or rights guessing is performed.

Before making a new master, the tool shows source SHA fingerprints and
breaks and asks you to type exactly **`yes`**. It creates a NEW 0700
private output folder outside any original WAV/session and Git repository.
All original WAVs are read in bounded 16,384-frame blocks; planned silence
is generated as exact zero-valued stereo PCM16 frames. Completed sources are
re-hashed after assembly before the output receipt is published.

## Actual deliverables

- `show.wav`: one physically rendered stereo PCM16 WAV with actual source
  audio segments and the exact manually chosen silent gaps.
- `show.receipt.private.json`: SHA-256 of the final **whole** show file,
  source set SHA-256s, sample rate, actual total frames, each true frame
  boundary, length, selected gap length, manual start clock and private
  operator notes.
- `index.html`: an offline event review player using the actual finished
  `show.wav`; shows source set chapter boundaries, exact planned gaps,
  SHA provenance and operator notes. No browser audio synthesis, uploads,
  analytics, or externally fetched media.

Files are permission-restricted. An incomplete new source-bound render
cleans only its new output folder, never the original approved set WAVs.
If the original source sessions or WAV contents are modified after
planning, the renderer refuses the plan instead of silently substituting
new songs.

## Boundaries and sensible use

This is a manually authored archive, private rehearsal master or single
file for a *fixed* preplanned evening. Its planned breaks are literal silence,
not an autonomous DJ or an interactive crowd-aware mixer. For an actual gig
that needs variable breaks, use **Show Conductor's manual individual-set
playback** instead of a predetermined show-wide WAV.

A WAV hash proves the files did not change; it does not establish music
rights, reliable professional device playback, venue clock accuracy,
artistic mix quality or independent blinded M1 listening results.
