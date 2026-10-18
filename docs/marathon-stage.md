# Offline Marathon Stage & private cue sheets

The existing verified `index.html` for a MixLab Event Marathon is also an
offline operator's **Stage**. This uses the **actual** local
`marathon.wav`; the stage controls the same audio element as the ordinary
chapter player. It does not remix, analyze or upload music.

## From a finished Marathon to a show

1. Produce a private Event Marathon with `python3 -m mixlab.event_marathon`
   or a manually crossfaded one with `python3 -m mixlab.marathon_blend`,
   following [the official event workflow](marathon-event.md). Retain the
   original `marathon.receipt.private.json` and `marathon.wav` together.
2. Open that output directory's `index.html` on your offline computer.
   The **Stage** section shows the current completed event, the next event,
   seconds remaining to that handoff and a progress bar. Blended marathons
   also show each actual rendered fade-in duration. The display follows
   playback and seeking; the wall clock is not estimated from a browser timer.
3. Use the Stage Play/Pause button or press **Space** when focus is outside
   inputs and buttons. Press **F** for full screen, **M** for a cue marker.
   The normal Next/Previous buttons remain available in the main player;
   the Stage doesn't automatically jump ahead.
4. Enter a note and click **Mark cue**. Its position, section number,
   section label and text are stored **in this open browser tab only**.
   Export `mixlab-marathon-cues.private.json` before leaving the page.
   The JSON is bound to the exact master SHA-256, section sequence and duration.
   It contains no original source tracks, audio or file paths.
5. To resume, import that private JSON using the Stage file picker.
   A source or section mismatch is rejected; no network call is made.

To print a stage-ready timecoded show sheet from the notes:

```bash
python3 -m mixlab.marathon_cue_sheet \
  /private/marathon/marathon.wav \
  /private/mixlab-marathon-cues.private.json \
  /private/marathon/marathon.cues.private.html
```

Open the new HTML offline and print it. It includes verified source sections,
manual cue times, offsets from each event and the original master SHA.
The converter validates the actual complete WAV, its original or blended
receipt, the private cue file's exact master binding, timing, size and
section identities. Only a new private HTML destination is allowed; existing
masters and notes are left unchanged.

### Operating boundaries

- 2–8 completed event sections, a bounded local PCM16 stereo master, at most
  200 manually entered markers per sheet and up to 300 characters per marker.
- No browser storage, music upload, server endpoint, audio recording, analytics,
  or automatic source-rights verification.
- The ZIP/restore workflows already carry the standard player; Stage is part
  of that player. Cue files are independently exported by the operator and
  must be copied separately; they are not added automatically to a ZIP.
- The master and cue JSON are not cryptographically signed. Hash binding
  catches accidental mixing with a different master, not a malicious author
  who controls both files.
- Browser WAV playback, fullscreen and keyboard behavior vary by browser and
  OS. **Keep a separate local audio player and hardware backup for events**.
  Do not treat a browser countdown as a certified DJ/live system.
- Browser Stage is an operational affordance, not evidence that transitions
  sound good. M1 remains open pending private licensed music and human
  blind-listening evidence.
