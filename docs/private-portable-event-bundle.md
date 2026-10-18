# MixLab Private Portable Event Bundle

A successfully rendered DJ set may contain a large PCM16 master, one
portable MP3/FLAC file, separate private receipts, the offline chapter player,
an offline event homepage and the operator show runbook. The **Private Portable
Event Bundle** gathers these existing outputs into **one private ZIP** that
can be copied to your own USB drive or trusted backup storage.

It does not re-render media, install anything, upload audio, query cloud
music catalogues or grant distribution rights.

## Recommended: one existing Event Publisher command

Add `--bundle` to your normal **human-approved** private export:

~~~bash
python3 -m mixlab.event_publish \
  /private/music \
  /private/music/event-plan.private.json \
  /private/music/mixlab-event-approved.private.json \
  /private/mixlab-party-01 \
  --delivery mp3 --start 19:30 --bundle
~~~

This first creates the actual canonical WAV and SHA-bound receipt using the
original permitted local sources, then optional compressed audio, offline
player, runbook and dashboard. The last step creates
`/private/mixlab-party-01/final-set.private.zip` only when requested.

The ZIP includes, when they exist and belong to this real event:

- The **real** complete `final-set.wav` PCM16 master and its canonical
  `.receipt.private.json`.
- The chaptered WAV offline player, private Event Dashboard
  `index.html` and printable operator show runbook.
- Optional official output `final-set.mp3` or `final-set.flac`,
  its exact official delivery receipt, and its offline player.
- An internal `mixlab-bundle-manifest.private.json` with SHA-256 and
  byte count of every included item plus the original WAV's exact SHA.

Crucially, the ZIP **never** contains the original source songs,
private music source paths, rights declaration JSON, original source
manifest, or other private research/evaluation data. It may contain the
**rendered private mix**, which itself can be copyrighted. Keep this ZIP
private unless you have independently checked all sharing/distribution
rights. Never upload it to an untrusted public host.

## Package an existing official set later

~~~bash
python3 -m mixlab.event_bundle \
  /private/mixlab-party-01/studio-session \
  /private/mixlab-party-01/final-set.wav \
  /private/mixlab-party-01/another-new-event-bundle.private.zip \
  --player /private/mixlab-party-01/final-set.wav.player.html \
  --dashboard /private/mixlab-party-01/index.html \
  --runbook /private/mixlab-party-01/final-set.runbook.private.html
~~~

You may add `--compressed PATH --compressed-receipt PATH` and optional
`--compressed-player PATH` when you have a real previously exported
compressed delivery. The portable audio is admitted only when its actual
file SHA matches its official private receipt and the receipt refers to
**the exact same canonical WAV SHA**. You cannot sneak in an unrelated
MP3, an arbitrary file outside the real event directory or a symlink.

## Restore the ZIP on another offline computer

Copy your trusted, already-created ZIP to a USB drive, then extract it to
a **new** private directory using the standard-library restore command:

~~~bash
python3 -m mixlab.event_restore \
  /media/usb/final-set.private.zip \
  /home/dj/restored-event
~~~

The restore command validates the bundle's own flat-file inventory,
uncompressed ZIP layout, byte sizes, internal SHA-256 entries and original
WAV/receipt pairing while streaming at most 64 KiB per read. It creates a
new private folder, never overwrites an old event, and cleans up only its
own partial extraction on failure. Open `restored-event/index.html` for
the actual offline event player, printable showbook and, for newer bundles,
the Rehearsal Desk with repeatable transition excerpts and local notes.

**Use only ZIPs you made or received from a trusted source.** The manifest
is not digitally signed; a forged ZIP can carry malicious HTML with forged
self-consistent checksums. Verifying a ZIP against its *own* manifest is
not external authentication, licensing proof or a real-audio quality gate.
See [Private Event Restore](private-event-restore.md).

## Format, bounds and safety

- The exporter uses Python's standard-library ZIP format with
  **ZIP_STORED**, Zip64 support and bounded **64 KiB streaming blocks**.
  There is no huge RAM buffer, no extra compression CPU demand and
  no new runtime dependency.
- At most **nine** eligible existing files and **896 MiB of combined
  input bytes** are admitted. Each file must be a regular 1..512 MiB
  file, the new ZIP must be beside the real WAV and no Git/symlink
  destination or existing output may be overwritten.
- Each file is read via a no-follow descriptor. Stable inode, size,
  change timestamps and expected canonical WAV/portable hashes are
  checked while streaming. If packaging fails, only the newly created
  incomplete ZIP is cleaned up. **The original verified WAV, receipts,
  offline players and original music are never removed.**
- The ZIP must be **explicitly requested**; an ordinary Event Publisher
  command does not consume extra disk space by automatically duplicating
  a large WAV. A failed optional ZIP adds an explicit warning but does
  not change the success of a previously published real WAV.
- This feature does not establish music quality or listener preference,
  live mixer reliability, independent music rights or the M1 milestone.
