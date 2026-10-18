# Offline Rehearsal Desk — practise the real rendered MixLab set

The Event Publisher now creates `final-set.rehearsal.private.html` alongside the canonical PCM16 WAV, offline chapter player, runbook and event dashboard. The dashboard links to the rehearsal page, and `--bundle` includes it in the private ZIP when available.

**This is playback practice, not DJ mixing.** The audio comes from the final canonical WAV, and the chapter positions come only from its actual receipt-verified render. The Rehearsal Desk never recomputes a beatgrid, edits the mix, infers licensing or requests any network service. Unsupported browsers can still play the WAV in a local media application.

## Create everything from an already approved private journey

```bash
python3 -m mixlab.event_publish \
  /private/music \
  /private/music/approved-journey.private.json \
  /private/music/mixlab-approved.private.json \
  /private/event-2026-10-18 \
  --start 20:00 --delivery mp3 --bundle
```

The existing music source admission, human source-rights/cue approval, SHA-pinned original renderer and final WAV receipts are unchanged. Publishing rehearsal HTML is optional: if it fails, the completed WAV remains available and the result contains a warning. The Event Dashboard shows a **Rehearse transitions offline** link when the page was published.

## Add rehearsal to a previously rendered and verified set

```bash
python3 -m mixlab.event_rehearsal \
  /private/event-2026-10-18/studio-session \
  /private/event-2026-10-18/final-set.wav \
  /private/event-2026-10-18/practice.private.html
```

The output must be a **new** HTML filename in the **same private directory** as the existing completed WAV. It cannot overwrite another page or live under Git/symlinked directories. The canonical `build_chapters` check must validate all source/render receipts, final WAV SHA and playback chapter metadata before any practice page is created.

For an existing manual bundle command, pass `--rehearsal /private/event-2026-10-18/practice.private.html`. The packaged page and the WAV must be siblings. The internal ZIP SHA manifest covers it as a normal page. There are at most nine existing approved files in the portable ZIP; original source tracks and source manifests stay outside it.

## Practice workflow

1. Open the private HTML directly from the event directory; the local WAV file must remain beside it.
2. Choose a track passage or a transition from the actual rendered chapter list. **Rehearse excerpt** starts a short segment before and after the chapter; change the before/after controls or repeat it with **Loop excerpt**.
3. Use Space to play/pause, N/P to move between chapters and L to toggle looping while not editing text. Browser playback is best-effort and may be imprecise by a fraction of a second.
4. Enter notes for as many chapters as you like. **Export all practice notes** creates a local private JSON file; reload it with **Import notes** on the same exact master. Notes do not go to a server or browser storage.

You can open the Event Publisher's `final-set.runbook.private.html` and
choose **Import notes from Rehearsal Desk**. Only the exact source WAV
SHA-256 and chapter count can populate the runbook's operator note fields.
Imported notes immediately appear in **print/PDF and the CSV cue sheet**;
you can also export notes JSON from the runbook to continue practising.
No server, shared storage or automatic browser persistence is involved.

Imported notes have a size limit of 128 KiB, at most 1,000 characters per chapter, and must match the original WAV SHA-256 and chapter count. A different mix is rejected even if chapter labels look identical.

## Privacy and live boundary

No music, lyrics, private approval documents or notes are sent to a network service. The HTML includes only the local final WAV filename, SHA-256 and chapter metadata; audio stays on disk. It does **not** store notes automatically: export before closing. An offline browser may not support every WAV codec or `file://` playback workflow.

This rehearsal interface does not prove musical preference, automatic downbeat/key accuracy, rights to distribute audio or reliable professional event playback. Keep a separate permitted master/fallback player for a real event. M1 remains open until independently admissible real-audio listening and relevant analysis evidence exist.
