# Private show rehearsal review — compare real manual takes

This offline, **operator-only** feature compares 2–6 previously exported
Show Conductor rehearsal journals. All takes must refer to exactly the same
2–6 original finished MixLab WAV sets, with valid original Studio/source
receipts, complete SHA-256s, and identical set order. It does **not** generate,
re-render, rank or play audio; it does not upload anything.

## Generate a private comparison page

Use new output HTML in a private folder **outside** the WAV/session folders,
the journal folders and the Git checkout. Replace names with your original
actual sessions and corresponding completed WAVs:

```bash
python3 -m mixlab.show_rehearsal_compare \
  /private/rehearsal-review/mixlab-takes.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav \
  --journal /private/rehearsals/take-01/mixlab-show-rehearsal.private.json \
  --journal /private/rehearsals/take-02/mixlab-show-rehearsal.private.json
```

The CLI rejects repeated/foreign journals, changed source hashes, invalid
events, unsuitable output destinations and oversized private data. The output
contains only user-authored cue annotations, cue positions, source chapter
details, and SHA fingerprints; **no WAV bytes or private absolute source
paths**. Journal SHA fingerprints are over canonical JSON values (independent
of indentation), not file-byte hashes. Use the same ordered journals when
reopening/revalidating an exported selection.

Open the new HTML locally, switch between source sets and takes and inspect
the original-source chapter that was nearest to a manually marked WAV seek
position, plus the signed offset. A take's event count is descriptive; it
is not an accuracy or musical-quality score. Click **Select Take** on the
version you want to carry forward and explicitly download
`mixlab-rehearsal-take-selection.private.json`.

The selection includes the ordered source WAV SHA list, all canonical journal
SHA identifiers, the selected take index and flags confirming that this
was a human choice. Treat that file as private DJ metadata, not a signed
certificate of ownership or a public blind study. It never changes the
original source material.

**Limitations:** browser monotonic elapsed time and `audio.currentTime`
are browser/operator observations, not measured sound-system output or
venue-clock time. No actual independent listener ratings, model research,
beat/key/stem proof, licence certification or automatic DJ selection is
produced. M1 remains OPEN.

## Turn your human-selected take into a private DJ cuebook

Once the local review page has downloaded
`mixlab-rehearsal-take-selection.private.json`, produce a completely
new, private, printable cuebook:

```bash
python3 -m mixlab.show_rehearsal_cuebook \
  /private/rehearsal-review/mixlab-selected-cues.html \
  /private/rehearsal-review/mixlab-rehearsal-take-selection.private.json \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav \
  --journal /private/rehearsals/take-01/mixlab-show-rehearsal.private.json \
  --journal /private/rehearsals/take-02/mixlab-show-rehearsal.private.json
```

Keep the **same original source/session pairs and the same journal order**
from the comparison. Before writing anything, MixLab rechecks complete
original WAV and source receipt SHA-256s, every journal's original event
contract and canonical JSON SHA, and the explicitly downloaded human
selection's exact flags and selected index. If a source, journal, list order
or selection is changed, it refuses the new cuebook. Output is a new
permission-restricted file in a separate private directory, never written
inside the music, original session or journal folders.

The cuebook lists each set's actual WAV duration and SHA, manual mark
positions in WAV time, nearby real source chapters and signed offsets,
and **only** annotations written by the DJ in the chosen take. Its
full source chapter list is available for reference. A take with no marked
cues has an honest empty entry rather than invented DJ decisions.

This is a handoff/printing aid: an exported selection and SHA-bound receipt
do not prove music licensing, independently measured playback timing,
acoustic output, listener satisfaction, or musical ranking. No WAVs are
embedded, played, modified or uploaded.
