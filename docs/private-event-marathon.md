# Private Event Marathon — join finished DJ events into one continuous WAV

MixLab can now assemble **2–8 already rendered, private, rights-approved sets** into a single continuous event master. Unlike creating new pair transitions, this tool **does not** try to beatmatch, pitch-shift, crossfade or recompute any DJ technique. It copies the original PCM16 stereo frames at exact boundaries, preserving the finished MixLab transitions inside each approved set.

## Create a private continuous event

Start with distinct, existing event folders that were originally made by `mixlab.event_publish` and still contain both `studio-session/` and `final-set.wav`:

~~~bash
python3 -m mixlab.event_marathon \
  /private/mixlab-marathon \
  /private/event-friday/studio-session /private/event-friday/final-set.wav \
  /private/event-saturday/studio-session /private/event-saturday/final-set.wav
~~~

The command prints the selected event names, their actual receipt-verified durations and rendered chapter counts. It requires the operator to type **`yes`** to explicitly approve the new private compilation. The destination must be **new**, separate from the original events, outside Git and symlinked paths.

After successful publication:

~~~text
/private/mixlab-marathon/
  marathon.wav                       # real joined PCM16 stereo master
  marathon.receipt.private.json      # exact output WAV hash and input-set SHA/positions
  index.html                         # private offline playback and event navigation
~~~

The offline page lets you play the whole actual WAV, jump between sets, skip to the next event, seek, download the WAV and export a standard cue sheet of the original event boundaries. It does not embed, upload or duplicate the original source songs. The output WAV itself **contains copyrighted rendered material** from the approved private sets and must remain private unless separately licensed for the intended use.

## Optional: render real crossfades between finished events

The default Marathon is still **sample-exact hard joins**, preserving
every frame. To create an *independent, new audio version* with actual
gain-crossfaded transitions between previously approved full sets:

~~~bash
python3 -m mixlab.marathon_blend \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon-soft \
  --fade-seconds 8 --start 20:30 --bundle
~~~

The new command requires the SHA-verified **original** hard-join Marathon
receipt, checks its entire PCM16 master, then asks for a fresh human
`yes`. Choose exactly 2, 4, 8 or 16 seconds of overlap. Every original
event must be longer than twice that length. No render ever overwrites the
existing master, source tracks or original Studio sessions.

### Visual offline Join Studio (no terminal duration list)

For a private original Marathon, the Event Publisher's Marathon route now
automatically creates `marathon.join-studio.private.html` alongside its
receipt-verified `marathon.wav`. The offline Marathon player links to it
with **Arrange transitions**. To create a separate editor manually:

~~~bash
python3 -m mixlab.marathon_join_studio \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon/new-join-studio.private.html
~~~

Open the HTML in a local browser. Choose 2, 4, 8 or 16 seconds **independently
for every event handoff**. The page shows the actual receipt-bound event
labels, original WAV boundary clocks and the proposed shorter running
time. **Listen to approximation** uses temporary local browser streams and
a manually controlled complementary-gain blend. Browser audio is best-effort
and is not the canonical MixLab PCM renderer or reliable evidence of quality.

Choose **Export private render plan** to download a small JSON file (no
music/audio included) with the original WAV's SHA-256, exact original PCM
frame count, sample rate, all original event SHA-256s and the selected
durations. Move it to any trusted private local path and render the
**real** PCM16 WAV with:

~~~bash
python3 -m mixlab.marathon_blend \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon-custom \
  --join-plan /private/mixlab-marathon-joins.private.json \
  --bundle
~~~

The renderer rehashes the original WAV, compares all bound fields and
refuses a stale or unrelated plan before creating any output. A fresh
typed **yes** remains mandatory; a browser export cannot grant source
rights or authorize production on its own. The private Marathon USB ZIP
carries the offline editor when present, and the existing restore command
retains its adjacent original WAV so the editor remains usable on a
trusted second computer.

### Choose a different fade for each transition

For an original Marathon of **four complete sets**, there are three joins.
Give the exact durations in the intended order:

~~~bash
python3 -m mixlab.marathon_blend \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon-custom \
  --join-fades 16,4,8 --bundle
~~~

This renders a 16-second first blend, a quick 4-second second blend and an
8-second final blend. Each choice must be **2, 4, 8 or 16 seconds**.
The number of entries must equal the number of actual joins; `--join-fades`
and `--fade-seconds` cannot be combined. Every source set must be longer
than its preceding plus following overlap, otherwise MixLab refuses it
without creating a new audio file.

The renderer prints every named source event pair and its chosen duration
**before** asking for explicit `yes`. Actual output chapters, per-event
start offsets, full-WAV SHA, optional show runbook and local player include
the new frame-accurate transition arrangement. A receipt always records
the full per-join durations and original Marathon SHA so no user or downstream
tool can mistake this for a hard-cut master or a globally uniform fade.
This works with the existing private ZIP exporter and offline restore.

MixLab actually reads the **end of one event and the start of the next**
from the original completed WAV and streams one complementary-gain PCM16
crossfade per boundary. All untouched passage frames are copied unmodified.
The result is a NEW `marathon.wav` and original-source-bound
`marathon.receipt.private.json`, with exact **shorter** sample frame count,
new event entry offsets, own offline player and optional operator runbook
and private USB ZIP. The Event Vault, Marathon showbook, USB exporter and
Event Restore understand this distinct rendered-join receipt.

This is a manually configured stereo fade, **not beat detection,
harmonic matching, pitch preservation, actual cue intelligence or evidence
that the result sounds good**. Both originals and the edited version remain
private; use the offline player to hear every boundary, especially
music with dense vocals, percussion or radically different BPMs. The
crossfade uses non-amplifying complementary linear gains (unlike claims
of an equal-power or mastering-quality algorithm). No source rights can
be inferred from an output SHA.

## Operator runbook for the entire Marathon

The normal Marathon command now also creates
`marathon.runbook.private.html` when the completed WAV's original joined
receipt can be verified. Give an optional planned local start time:

~~~bash
python3 -m mixlab.event_marathon \
  /private/mixlab-marathon \
  /private/event-friday/studio-session /private/event-friday/final-set.wav \
  /private/event-saturday/studio-session /private/event-saturday/final-set.wav \
  --start 20:30 --bundle
~~~

The runbook has **actual frame-derived event offsets**, projected wall-clock
start/end times, a manual readiness checklist, per-event handoff notes,
print/PDF styling and a private CSV cue-sheet export. This is a schedule
for human operation, not live hardware or performance certification.

You can create a **new** runbook later from an existing completed Marathon:

~~~bash
python3 -m mixlab.marathon_showbook \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon/another-marathon.runbook.private.html \
  --start 20:30
~~~

The private offline Marathon player links to the default runbook when
available. The portable Marathon ZIP includes that default page if it
exists and is regular and bounded; private Event Restore also restores it
and reports the path. Optional showbook/ZIP publication failure never
deletes a successfully published continuous WAV.

## Mobile audio: private MP3 / FLAC without rebuilding your mix

The finished Marathon can now optionally be encoded into a **real MP3 or
FLAC file** using MixLab's **existing** installed local FFmpeg/FFprobe
backend. The original WAV's full SHA, frame count and joined-event
receipt are checked before encoding. Nothing is uploaded or re-mixed.

For the original hard-join `event_marathon` or the later editable
`marathon_blend`, add `--delivery mp3` (or `--delivery flac`).
The MP3 bitrate defaults to 192 kbps; use `--bitrate-kbps 256` or
320, 128, etc., if desired. Example for an approved original Marathon:

~~~bash
python3 -m mixlab.event_marathon \
  /private/mixlab-marathon \
  /private/event-1/studio-session /private/event-1/final-set.wav \
  /private/event-2/studio-session /private/event-2/final-set.wav \
  --delivery mp3 --bitrate-kbps 256 --bundle
~~~

To create a NEW portable copy later from the same original full WAV:

~~~bash
python3 -m mixlab.marathon_delivery \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon/marathon.mp3 \
  --bitrate-kbps 256
~~~

The encoder creates `marathon.mp3` or `marathon.flac`, a separate
`.receipt.private.json` bound to the actual source-WAV SHA and the
actual encoded-output SHA, and an offline portable-audio player with
original set boundaries. **Compressed seeking and cue positions are
approximate** because codecs can add encoder delay. The source PCM16
master is the exact reference and is never overwritten.

If `--bundle` is also selected, the existing USB ZIP exporter will
include one verified portable codec, its receipt and offline player if
the whole private package fits its original 896 MiB total limit.
You cannot silently pack both MP3 and FLAC in the same ZIP. The existing
Event Restore recognizes a correctly bound portable companion in that
trusted private ZIP. Mobile encoding is optional: an FFmpeg error does
not delete the already completed real WAV.

**Rights boundary:** MP3/FLAC are new private copies of potentially
copyrighted music, not a license or authorization to distribute.
Audio never leaves your private machine or trusted removable storage.

## Optional portable private USB ZIP

Add `--bundle` to the same `python3 -m mixlab.event_marathon` invocation.
After the real continuous PCM16 WAV, receipt and offline player are produced,
MixLab optionally creates `marathon.private.zip` beside the master. The
original audio is never deleted if packaging cannot complete.

You can also package an existing completed Marathon later without re-rendering:

~~~bash
python3 -m mixlab.marathon_bundle \
  /private/mixlab-marathon/marathon.wav \
  /private/mixlab-marathon/another-new-marathon.private.zip
~~~

The bounded, Zip64, `ZIP_STORED` archive includes **only** the actual
`marathon.wav`, its exact original SHA-256 receipt, private `index.html`
and an internal file/hash inventory. Original music, underlying full event
sources, rights manifests, local absolute paths and Studio state are absent.
The exporter checks the original Marathon's entire WAV hash and frame/section
receipt before packaging.

On a second trusted offline machine, use the **existing Event Restore**
command (now also supports Marathon ZIPs):

~~~bash
python3 -m mixlab.event_restore \
  /media/usb/marathon.private.zip \
  /home/dj/restored-marathon
~~~

This creates a **new** private directory and streams SHA checks against all
package members. The extractor independently checks the original Marathon
receipt, joined-frame sequence and PCM16 WAV header before final publication.
Open the extracted `index.html` to play and navigate between sets, or
include the restored folder in the [private Event Vault](private-event-vault.md).

**Trust boundary:** the internal ZIP SHA manifest is not cryptographically
signed. Someone could modify and rehash a forged file set. Transfer only
a private archive you made or received from a trusted source; don't launch
untrusted embedded HTML. The actual joined WAV may still contain copyrighted
recordings and cannot be distributed without applicable permissions.

## Audio boundaries

Only original event masters whose **entire source/render/WAV receipts** are verified by the existing canonical `build_chapters` reader are admitted. An unsigned USB package alone does not provide the original private Studio receipt chain, so restored packages **are intentionally not accepted** as Marathon sources.

All source masters must have matching sample rates, two channels, PCM16 little-endian WAV and the same concrete raw format. For a different rate, the tool refuses to run rather than invent an automatic tempo or format conversion. Output is one WAV with a hard **768 MiB** PCM payload budget (2–8 original sets); streaming chunks are at most 16,384 stereo frames. Each opened source is checked for file identity and change timestamps before and after copying. Output never modifies any original event or changes canonical DSP.

The exact event starts, original full-set SHA-256s, sample frame counts, joined WAV SHA-256 and playback duration are saved to the private receipt. The browser player displays the real set boundaries; no alignment-quality, sound-quality, live-playback hardware reliability or listening preference is inferred.

## Operating cautions

This creates a *gapless* sequence, **not a musically mixed transition across the event boundary**. Plan your preceding set endings and following set openings appropriately and preview the join in your own local player. The standalone WAV and private receipt can be copied to a trusted offline system, but are not part of the ordinary event bundle format: do not pass them to `mixlab.event_bundle` as if they were a Playlist Studio event.

If the output is too large, split the programme into smaller event blocks. Do not upload private original music or compiled mixes to public music services without all necessary rights.

**M1 is still open.** This feature extends private DJ production workflow but does not close the automatic analysis/tempo/separation or real independent listener requirements.
