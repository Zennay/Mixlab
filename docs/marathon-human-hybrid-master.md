# Human-selected hybrid Marathon: one real master from per-join A/B decisions

The private **Real Join Reels** player can now export one operator choice at every boundary: keep the original sample-exact hard join, or use the already approved 2/4/8/16-second real PCM16 crossfade. This creates a **new, genuinely rendered hybrid event master** rather than choosing the same original/blended version for an entire event.

These are **unblinded personal DJ decisions**, not quality-study ratings, music permission, model inference or automated harmonic compatibility.

## 1. Produce and audition real paired excerpts

Create your original and separately consented blended full Marathon WAVs via [Marathon Sequence Studio](marathon-sequence-studio.md). Then create/restore [Real Join Reels](marathon-real-join-reels.md), or pass `--reels-output NEW_FOLDER` during Sequence render. Open the reel folder's `index.html` locally.

Listen to both **actual recorded** WAV clips for each boundary. The original clip comes from the verified original master; the blend clip from the same approved separate blended master. Choose **Keep exact original hard join** or **Use actual approved crossfade** for every row. Optional note text stays in your open browser tab until explicitly exported.

Click **Export join-by-join master choices**. This downloads `mixlab-marathon-join-master-picks.private.json` without music bytes or source paths. All boundaries must have an explicit choice. The file includes the exact original and blended master SHA-256s and the labels and pre-approved fade for each chosen boundary. Never publish the private decisions to GitHub.

## 2. Produce a new real full-length hybrid master

On an authorised offline system with both of the **original complete** WAV masters and the choice JSON:

```bash
python3 -m mixlab.marathon_reel_decisions \
  /private/choices/mixlab-marathon-join-master-picks.private.json \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  /private/new-hybrid-event
```

The CLI verifies both existing full WAVs and their private receipts, their exact parent-child master relationship, sequence identity, join labels, fade lengths, number/order of choices, and the browser-exported SHA-256 fingerprints. It refuses missing/incomplete/foreign choices, symlinked plan paths and existing output directories.

The per-boundary renderer uses `0` seconds for a **sample-exact hard join** and the approved `2/4/8/16` seconds for a **real complementary-gain crossfade**. It streams through the existing bounded PCM16 stereo renderer with no tempo change, model, cloud upload, source rewrite or hidden audio data. It displays the precise choices and asks for a new typed **`yes`**. The original and compared blended WAVs are retained.

The resulting new folder contains:
- `marathon.wav` — the actual combined stereo PCM16 master.
- `marathon.receipt.private.json` — full hybrid master SHA-256, source original SHA-256 and exact `0/2/4/8/16`-second decisions for every join.
- `index.html` and, when possible, the original existing printed show runbook.
- `master-picks.private.json` — the explicit operator decisions, private notes and SHA-256 of the **actual newly rendered** hybrid.
- `master-picks.private.html` — printable private cue sheet tying each hard join/crossfade and human note to the exact completed hybrid WAV.

The decision/print artifacts are optional operator handoff extras: if their local publication fails after the actual approved WAV renders, MixLab retains the real master and reports a warning. If every join was marked **original**, simply use the already approved original WAV; there is no reason to create a misleading redundant derivative, so the hybrid command rejects that case.

## 3. Optional private portable export

```bash
python3 -m mixlab.marathon_reel_decisions \
  /private/choices/mixlab-marathon-join-master-picks.private.json \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  /private/new-hybrid-event --bundle --delivery mp3
```

The existing local MP3/FLAC delivery and SHA-manifest full-master ZIP paths are opt-in; they retain the existing audio permissions and privacy checks. **The private cue notes are deliberately NOT silently placed in the portable bundle**. Use the separate private cue HTML for trusted offline human handoff.

## 4. One-command original-vs-hybrid real WAV listening reels (optional)

Add `--reels-output /private/new-hybrid-listening --reels-usb` to the hybrid
render command to create **two actual short PCM16 WAV excerpts for each
join**: frames from the original hard master vs frames from the new, uniquely
chosen hybrid master. These are not browser-produced simulations.

After the hybrid WAV has been explicitly approved and rendered, creating
the short reels requests **another typed `yes`**; the ZIP then uses the
existing flat private SHA-manifest transfer route. If clips or ZIP creation
fail, the full real hybrid WAV remains intact. Because 0-second hard joins
are allowed, a few original-vs-hybrid pairs may sound **identical by design**;
this is an operator comparison, not a blinded quality study. No original
full masters or private operator notes are silently included in the short
clip ZIP.

The hybrid can be opened in the ordinary private Marathon player/showbook and, if the local music permissions allow, re-excerpted as genuine WAV handoffs for further listening. A receipt verifies **internal file consistency**, not that a third party is the legitimate copyright holder or that a hybrid is musically better. Independently consented, frozen blind listening evidence and verified audio-usage rights remain open M1 requirements.
