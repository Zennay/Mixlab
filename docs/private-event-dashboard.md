# MixLab Event Dashboard — open your complete DJ set in one local page

A **real MixLab event package** is more useful when the operator does not
need to hunt through individual source/receipt files. The new private
**Event Dashboard** presents a finished local WAV as a single responsive
landing page with direct chapter-player, portable audio and runbook links.

## Recommended: automatic with Event Publisher

Generate a real complete set from your exact, approved private event plan:

~~~bash
python3 -m mixlab.event_publish \
  /private/music \
  /private/music/event-plan.private.json \
  /private/music/mixlab-event-approved.private.json \
  /private/mixlab-party-01 \
  --delivery mp3 --start 19:30
~~~

When the canonical WAV, optional MP3 and runbook are actually available,
the Publisher also creates:

`/private/mixlab-party-01/index.html`

Open that file **locally** to see:

- A private set overview with actual number of track sections, rendered
  transition count, and true complete WAV duration.
- An immediately accessible original PCM16 WAV audio player and download.
  For large files/browser-incompatible playback, open the separately
  produced chaptered offline WAV player.
- Links to the separately produced WAV **event-mode chapter player**,
  optional verified MP3/FLAC file and its offline compressed player,
  plus printable private show runbook.
- An amplitude-only sampled waveform and a timestamped real transition
  timeline reconstructed from the original SHA-bound WAV receipt and
  the original permitted Studio session.

The dashboard has **no internet dependency or telemetry**. Only local
relative file names are embedded. It never publishes or embeds original
private source paths, music rights/provenance declarations or raw media
into the HTML. The original WAV and compressed files remain ordinary
local files and must stay beside the HTML; do not put the event bundle
on a public website without independent rights clearance.

## Create a dashboard for an earlier completed set

If you already have an exact, valid Studio session and completed WAV,
create a **NEW** private HTML beside the WAV:

~~~bash
python3 -m mixlab.event_dashboard \
  /private/session-01 \
  /private/complete-event.wav \
  /private/complete-event.dashboard.private.html \
  --player /private/complete-event.wav.player.html
~~~

The dashboard creation uses the **existing canonical**
`set_player.build_chapters` admission path. This requires the original
session plus studio/transition source bindings and verifies the actual
PCM16 WAV bytes against its private receipt. It refuses a missing,
symlinked or overwritten dashboard path or writing into Git. The HTML
is exclusively written with file permissions `0600`.

For an earlier portable delivery, the optional arguments
`--compressed PATH --compressed-receipt PATH` admit only an actual
same-directory local MP3 or FLAC whose compressed output SHA and source
WAV SHA match its own official private delivery receipt. You may also
provide `--compressed-player PATH` or `--runbook PATH` if those
private same-directory companions exist.

## Limits

This is the navigation interface for an **already truly rendered** event.
It is not a live audio mixer, musical-quality or human-preference study,
copyright licensing proof, or guarantee of dependable audio hardware.
M1 stays OPEN pending separate real-music and blind-listener evidence.
If this optional landing page fails, the Event Publisher preserves the
original WAV and reports the dashboard error without discarding the
working audio package.
