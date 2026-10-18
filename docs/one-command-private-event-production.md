# MixLab Private Event Publisher — approved event to complete local package

**One approved private event → real complete WAV, optional MP3/FLAC, local
chaptered player and printable show runbook.** This is an end-to-end creative
product workflow, not a new renderer, model, automatic license check or
independent claim of better DJ quality.

## Before the command

Have a private folder of your own permitted songs **outside Git**, and
create a SHA-pinned [Energy Journey / Event Brief](offline-event-brief-studio.md)
plan plus a [rights and actual cue approval file](offline-playlist-approval.md).
The browser pages remain local. You must manually confirm the BPM, A/B cue
positions, source rights and permission basis; the browser's two-deck
prelisten is not a substitute for the canonical rendered DSP.

Assume:

- `/private/music`: original permitted local music files;
- `/private/music/event-plan.private.json`: original, unmodified plan;
- `/private/music/mixlab-event-approved.private.json`: manually
  approved rights/cues/optional pair-specific render styles, bound to the
  **exact SHA-256 bytes** of that original plan;
- `/private/mixlab-party-01`: a **NEW**, non-existing private output
  folder outside music and Git. Create its parent first if necessary.

## One command produces the whole event

~~~bash
python3 -m mixlab.event_publish \
  /private/music \
  /private/music/event-plan.private.json \
  /private/music/mixlab-event-approved.private.json \
  /private/mixlab-party-01 \
  --delivery mp3 --bitrate-kbps 192 --start 19:30
~~~

The Publisher:

1. Admits only an existing, bounded private approved JSON and its matching
   original plan; recomputes/checks the selected source-file SHA hashes
   **before** creating the output directory.
2. Reads the approved number of transition beats directly from the
   explicitly approved file, so it cannot accidentally render a different
   length from the browser form.
3. Creates a new output folder with permissions `0700`; constructs a
   new exclusive, mode-`0600` source manifest **next to the music**
   named `mixlab-mixlab-party-01.sources.private.json`. This is
   necessary for the canonical relative source path rules.
4. Shows the same full local route and still requires the final
   human **Accept this exact suggested order? Type yes** response.
   Without this input no new approved source manifest is written.
5. Runs the **existing canonical** MixLab Playlist Studio, private audio
   import, SHA/recovery receipts and transition renders, and compiles
   `/private/mixlab-party-01/final-set.wav` from those exact inputs.
   Pair-specific styles already selected in the approval form are used;
   `--family bass_swap` only supplies the default where no pair-specific
   option was selected.
6. Publishes the existing offline chaptered WAV player, plus an optional
   compressed `final-set.mp3` or `final-set.flac` using **already
   locally installed FFmpeg/FFprobe**, not a cloud encoder.
7. From the actual, canonical WAV receipt, creates a **private printable
   show runbook** with chapter times and optional human-selected
   local start time (`--start HH:MM`). The paper/CSV cue sheet is
   complementary to the audio player, not a live audio mixer.

Example private package:

~~~text
/private/music/mixlab-mixlab-party-01.sources.private.json
/private/mixlab-party-01/
    studio-session/                            # original source/Studio/receipt data
    final-set.wav                              # real canonical mixed PCM16
    final-set.wav.receipt.private.json         # exact WAV / source binding
    final-set.wav.player.html                  # offline chapter/event player
    final-set.mp3                              # optional; requires FFmpeg
    final-set.runbook.private.html             # private operator timeline
~~~

A published `final-set.wav` is never deleted just because optional
MP3/FLAC delivery or a show runbook failed. Such errors are returned
explicitly in `warnings`. Conversely, if no actual full-set WAV was
published, this wrapper reports a failure even if the initial private
Studio exists; it never reports a complete event based only on HTML or
generated manifests.

## Permissions and recovery

- All input files, outputs and source media stay on your **local
  computer/private server**. No uploads, model downloads, service
  exposure, Spotify access or independent licensing inference.
- Choose a **different new event-folder name** for each run. Existing
  JSON, WAV, HTML and receipts are never overwritten. The output folder
  must be outside Git and must not be a symlink or below the music folder.
- A failure after the source manifest was written may leave a completed
  Studio and/or real master WAV. Do not delete or overwrite these;
  use the exact manifests and the existing Playlist Studio `--resume`
  path for intentional recovery. Optional failures do not destroy master
  audio, and arbitrary reruns do not silently overwrite previous results.
- Import and render time/PCM resource bounds remain enforced by the
  canonical code. Different-tempo pairs remain unsupported in this
  immediate route; any separate opt-in backend requires its own
  authorization and evaluation.
- **M1 is still open.** This packaging feature does not assert verified
  musical preference, DSP superiority, explicit legal music rights,
  professional live-playback reliability, source separation or
  automatic BPM/downbeat/key/phrase detection.
