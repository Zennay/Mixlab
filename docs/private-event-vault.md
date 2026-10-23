# Private Event Vault — all your finished DJ sets offline

MixLab's **Event Vault** is one searchable local HTML index for the private
full sets you have already produced using Event Publisher, or unpacked from
your own trusted portable ZIPs using Event Restore.

It also supports **Event Marathon** folders created using
[`mixlab.event_marathon`](private-event-marathon.md), which contain a single
joined `marathon.wav`, a new original compilation receipt and an offline
programme player. The Vault verifies that joined WAV's actual SHA-256, frame
count, sample rate and contiguous source-event boundaries against the local
receipt. It labels a Marathon separately because that unsigned receipt is
**not** a new authentication of all underlying original source songs.

Unlike the [full-set family gallery](offline-full-set-gallery.md), which
compares 2–4 alternative mixes **for the same set**, this vault manages
**multiple distinct events**. It does not create new music, rescan source
tracks, render transitions, upload audio or auto-publish anything.

## First create or restore private events

A typical private layout is:

~~~text
/private/mixlab-events/
    party-01/
        index.html
        studio-session/
        final-set.wav
        final-set.wav.receipt.private.json
        final-set.rehearsal.private.html
    party-02/
        index.html
        final-set.wav
        final-set.wav.receipt.private.json
        mixlab-bundle-manifest.private.json  # if restored from trusted ZIP
~~~

The original event already has its Studio session and rendering receipts.
Restored events have the original unsigned bundle manifest and WAV receipt;
their underlying original music sources are *not* copied over.

## Build your event vault

~~~bash
python3 -m mixlab.event_vault \
  /private/mixlab-events/my-vault.private.html \
  /private/mixlab-events/party-01 \
  /private/mixlab-events/party-02
~~~

Open the **new** `my-vault.private.html` directly in a local browser.
Search by event folder name, sort by actual runtime or rendered chapter count,
play an event's complete local PCM16 WAV or open its own Event Dashboard.
Through the Dashboard you can also open the event's chapter player, Rehearsal
Desk and printable operator runbook, if the original package provided them.

All event folders must be **unique siblings** beside the new vault HTML;
the private vault lives outside Git and symlinked paths. You explicitly
name 1–16 event folders; the tool does not recursively scan your filesystem
or search online. It never overwrites an existing index.

### How source evidence is handled

- **Original Event Publisher directories:** the vault calls MixLab's
  canonical `build_chapters` on the original Studio and final WAV. This
  re-checks the source/transition receipts and final master SHA before
  recording the true runtime and chapter count.
- **Continuous Event Marathon folders:** the private
  `marathon.receipt.private.json` must name `marathon.wav`, identify
  consecutive 2–8 joined event boundaries and match the actual streamed
  WAV SHA-256, sample frame count and 2-channel PCM16 format. The Vault
  labels this a *joined WAV SHA match*; the original event approvals
  remain at the source and do not accompany the joined folder.
- **Previously restored ZIP directories:** the vault reads the existing
  `mixlab-bundle-manifest.private.json`, requires the final WAV SHA claim
  and original private receipt, and streams the entire local final WAV
  through SHA-256 checking before reading its PCM16 header for duration.
  It labels such entries as *Bundle SHA match*, not a reauthenticated
  original Studio session.

The code reads one event at a time in bounded 64 KiB blocks, with a 512 MiB
master file limit and a 16-event index limit. The generated HTML is capped
at 512 KiB and created as a private `0600` file. It links **only** to
the user-selected sibling event folders. No original source songs or
private source manifest paths are embedded in the vault.

## Boundaries

This is a local operator catalogue, not a public music hosting site.
You still need permission for any playback or distribution.
A restored ZIP's internal unsigned SHA manifest is self-consistent but
**not evidence of who created it**. Use only your own or explicitly trusted
private bundles. The vault makes no claim about real-DJ preference,
automatic beat/key/phrase analysis or professional hardware reliability.
M1 remains open.
