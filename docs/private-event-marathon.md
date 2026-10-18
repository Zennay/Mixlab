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
