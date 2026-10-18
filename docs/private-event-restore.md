# Restore a private MixLab Event Bundle on another computer

**Bring a completed private DJ set from one machine to another without reinstalling a model or uploading music.**

MixLab's Event Publisher can create `final-set.private.zip` using `--bundle`. The separate **Event Restore** command opens a trusted local copy of that ZIP, verifies every recorded SHA-256 while streaming, and extracts it into a **new private directory**. It does not recompute DSP, read original music sources or change the source event.

## Example: laptop → USB → event machine

On the first computer, use the existing human-approved Event Publisher:

~~~bash
python3 -m mixlab.event_publish /private/music \
  /private/music/event-plan.private.json \
  /private/music/mixlab-event-approved.private.json \
  /private/event-1 --delivery mp3 --bundle
~~~

Transfer the resulting `/private/event-1/final-set.private.zip` using **your own trusted storage device**. On the receiving computer, with the same MixLab Python package available:

~~~bash
python3 -m mixlab.event_restore \
  /media/usb/final-set.private.zip \
  /home/dj/private-event-1
~~~

`/home/dj` must already exist; `/home/dj/private-event-1` must **not**. Then open `/home/dj/private-event-1/index.html` in a local browser. The dashboard, WAV player, offline rehearsal page, printable operator runbook and any receipt-backed MP3/FLAC remain adjacent to their referenced final WAV. If your browser cannot play local WAV, open the extracted WAV in an ordinary offline media player. No web server is required.

The printed command result tells you the exact restored WAV, event dashboard and Rehearsal Desk paths, if present. Bundles created before the rehearsal feature simply restore without that optional page.

## Marathon ZIPs

The same `mixlab.event_restore` command also accepts a trusted
**Event Marathon** ZIP produced by `python3 -m mixlab.marathon_bundle`
or `python3 -m mixlab.event_marathon --bundle ...`.

A restored Marathon contains `marathon.wav`,
`marathon.receipt.private.json`, and `index.html`, plus the optional
`marathon.runbook.private.html` operator showbook when included in the
original trusted package, rather than an original Playlist Studio session. The restore command checks the
three expected members, private archive SHA inventory, the exact joined
WAV SHA, PCM16 stereo frame count, sample rate and contiguous 2–8
subevent frame boundaries before admitting the new output folder.

A restored Marathon can then be indexed in the
[private Event Vault](private-event-vault.md).
The 768 MiB Marathon WAV bound differs from the existing per-file
512 MiB original single-event bundle bound, but both use the overall
896 MiB ZIP package budget. The manifest is still **unsigned** and
proves no external authenticity or additional music distribution rights.

## Protections and limits

- The ZIP must be an original-style **uncompressed** MixLab bundle with its private manifest. ZIP paths, directories, symlinks, absolute filenames, traversals, duplicates, unlisted entries, unknown compression and extra files are refused.
- The original package limits still apply: at most nine private output files, up to **896 MiB** of input payload and **512 MiB** per file. Extraction uses bounded **64 KiB** chunks, exclusive new regular files with permissions `0600` and new directory permissions `0700`.
- The ZIP manifest must name the original final WAV and its canonical receipt. Every extracted file is checked against the file size and SHA-256 in that manifest, and ZIP CRC is checked by the standard library.
- If extraction is interrupted or a member is inconsistent, the command removes the **new partial destination** where possible. It never deletes or overwrites the input ZIP or an existing event folder.
- Restored HTML pages are offline; no remote audio uploads or automatic metadata collection are performed by the restore utility.

## Important authenticity and legal limits

**An unsigned ZIP hash manifest is self-consistent, not proof that the source is trustworthy.** A malicious person can alter all files and recompute the manifest. Accept ZIP files only from your own trusted, previously produced MixLab events. Do not execute untrusted bundled HTML just because its SHA matches the unsigned manifest.

The bundle may contain copyrighted rendered music. Source declarations, raw music stems, the original private source manifest and local machine source paths are intentionally excluded. The restore command **does not** grant usage/distribution rights, establish human musical preference or prove live playback reliability. M1 remains open.
