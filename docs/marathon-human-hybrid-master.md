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
- `master-picks.stage.html` — a mobile/desktop **offline live cue navigator** that plays only the real finished `marathon.wav`, shows the currently playing event, the next event, countdown to its actual receipt-bound join, each real hard/fade decision and the private note. Jump to 8 seconds before a join, previous/next join, ±15 seconds, and fullscreen stage mode. No server, microphone, telemetry or localStorage.


You can open `master-picks.stage.html` directly with `marathon.wav`
alongside it, on an offline laptop or tablet; use `master-picks.private.html`
for paper. A separate rebuild is also possible after moving the verified
hybrid and operator choices:

```bash
python3 -m mixlab.marathon_hybrid_stage   /private/new-hybrid-event/marathon.wav   /private/new-hybrid-event/master-picks.private.json   /private/new-hybrid-event/master-picks.stage.html
```

The stage generator rechecks the **actual complete rendered WAV SHA-256**,
its valid Marathon receipt and every note/decision/timestamp relationship.
The browser does not itself hash the WAV and must not be used as a professional
timing or live-output guarantee; its countdown is guidance derived from the
verified rendered timeline. This extra page is not part of the regular music
ZIP and must be handed off privately.

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


## 5. Transfer private stage notes to a second already-authorised offline master

The full audio ZIP intentionally **does not** carry your private operator notes.
If you want a second offline device to show the identical human-selected
cue sheet, use a **separate, explicitly consented, small notes-only ZIP**.

After creating an actual hybrid master with a complete
`master-picks.private.json`, optionally add `--operator-notes-usb` to the
hybrid render command. **After the real WAV and operator cues exist**, MixLab
asks for another typed `yes` to release the human private notes. This creates
`master-operator-notes.private.zip` beside the actual finished hybrid master;
the ZIP contains *no* `marathon.wav`, music excerpts, source media paths,
download URLs or whole-show audio. If only the optional notes transfer fails,
the approved hybrid WAV and local notes remain intact.

You can also package an already completed set independently:

```bash
python3 -m mixlab.marathon_operator_transfer pack \
  /private/hybrid-event/marathon.wav \
  /private/hybrid-event/master-operator-notes.private.zip
```

On a second machine, first transfer or restore the **real original hybrid
Marathon WAV** by its existing approved, private source path, with its
`marathon.receipt.private.json` intact. Do **not** assume that a cue-only ZIP
provides or licenses music. For an existing verified hybrid master with no
operator files:

```bash
python3 -m mixlab.marathon_operator_transfer restore \
  /private/usb/master-operator-notes.private.zip \
  /private/restored-hybrid-event/marathon.wav
```

Restore refuses mismatched full-master SHA, altered source-provenance SHA,
missing/inconsistent join labels or fade selections, symlinked ancestors,
unexpected ZIP members, compressed/oversized/archive-traversal entries and
any pre-existing decision/stage/print file. After typed `yes`, it restores
the **private notes** and regenerates printable
`master-picks.private.html` and live offline `master-picks.stage.html`
against the actual recovered local WAV and verified receipt, not by trusting
copied HTML. A failure rolls back only newly created notes/pages, **never the
approved audio**. This small ZIP is **unsigned**: SHA proves self-consistency
with the local WAV but not the sender's identity, music rights or DJ preference.


## 6. Record and print manual offline playback-rehearsal cues

Open the existing `master-picks.stage.html` beside the actual approved
`marathon.wav`. While **rehearsing the local player**, use **Mark heard
NOW** beside any join; it captures the WAV player's current playback position
and shows its signed delta to that exact receipt-verified boundary. Marks
can be replaced or cleared; they are held only in this open tab and never
sent to a service. Once at least one join is marked, use **Export private
playback journal** to download
`mixlab-hybrid-playback-journal.private.json`, with every real source
boundary, manual local playback marker, notes and finished WAV SHA-256.

The user can independently create a fresh private printable report beside
the original, already verified finished hybrid WAV:

```bash
python3 -m mixlab.marathon_stage_journal \
  /private/hybrid-event/marathon.wav \
  /private/rehearsal/mixlab-hybrid-playback-journal.private.json \
  /private/hybrid-event/master-playback-journal.private.html
```

The renderer rechecks the entire real WAV SHA and receipt, validates each
boundary's actual frame position, join mode, private label, bounded human
note and optional playback marker, and refuses foreign/malformed log
entries. It writes only a new private HTML; media is never modified or
uploaded. The report can be printed for your own rehearsal review.

**Important:** The marker means where the user manually clicked in a local
WAV player, possibly after seeking or pausing. It does **not** measure when
a performer played something at a physical event, how a room reacted, mix
quality, rights provenance, or a scientific preference outcome. Private
logs are never automatically inserted into regular portable music ZIPs.

## 7. Reopen, revise and re-render a completed real hybrid set

A DJ can now **revise previously approved join choices without starting over**.
The source is not a browser-generated approximation: the new
`mixlab.marathon_revision_desk` first verifies the previous completed hybrid
WAV and receipt, original master, compared previously approved real blended
master, every source hash, its human choice log, and exact per-join fade values.

Choose a **new local HTML file** in an existing trusted private folder:

```bash
python3 -m mixlab.marathon_revision_desk \
  /private/current-hybrid/marathon.wav \
  /private/original/marathon.wav \
  /private/approved-blend/marathon.wav \
  /private/work/mixlab-revise-handoffs.html
```

Open the HTML without a server. Each real boundary remembers its previously
approved hard-cut/crossfade decision and note. Change one or more joins,
reset to the previous choices, set all to original, or choose all previously
rendered fades. The UI calculates the **new estimated PCM frame count and
duration difference** for the exact selected already-rendered fade lengths.
There is no audio embedded, no network, no hidden model or real-time mix claim.
The existing original/approved-blend sources stay untouched.

Only a plan with an actual transition change can be exported. If every join
becomes original, use the **already approved original** WAV; the application
does not create a redundant hybrid copy. The exported
`mixlab-hybrid-revision.private.json` includes the *previous* fully
verified hybrid master SHA-256 as `parent_hybrid_sha256`. Its output is
never silently treated as valid for a different previous master.

To actually render the revised version:

```bash
python3 -m mixlab.marathon_reel_decisions \
  /private/work/mixlab-hybrid-revision.private.json \
  /private/original/marathon.wav \
  /private/approved-blend/marathon.wav \
  /private/new-revised-hybrid \
  --previous-hybrid /private/current-hybrid/marathon.wav
```

The renderer independently rechecks the previous full WAV hash, its existing
private human decision log and its exact original/blend ancestry, and refuses
no-op revisions, missing/mismatched parent SHA, wrong fade provenance or
changed source media. It still asks for human typed `yes` before actual
PCM16 rendering. A **new separate, source-verified WAV** is created and the
private decision log retains `parent_hybrid_sha256` for traceability;
existing original, blended and parent hybrid masters are never overwritten.
Print stage/notes and optional approved ZIP workflows remain available. This
is manual local DJ curation, **not** proof of music rights or blinded
independent sound quality.

## 8. Audition only the REAL WAV joins changed by your revision

After the new revised hybrid was actually consented and rendered, MixLab can
compare **true PCM16 frames** from the previous hybrid and its exact
descendant. Both complete source WAV SHA-256 receipts and private per-join
decisions must match, including the new receipt's
`parent_hybrid_sha256`. Unrelated/foreign mixes are refused.

To build one new private review folder:

```bash
python3 -m mixlab.marathon_revision_reels \
  /private/current-hybrid/marathon.wav \
  /private/new-revised-hybrid/marathon.wav \
  /private/revision-review
```

The command lists both full-WAV hashes, shows the number of changed
boundaries, and requires another typed `yes`. It copies **only changed
joins**: one short previous PCM16 excerpt and one short genuinely revised
PCM16 excerpt, taken from each respective finished WAV's own frame offsets.
Clips contain up to 8 seconds before the real boundary, its manually
selected actual fade duration (which can be 0 for a hard cut), and 8 seconds
after. Source frame count/rate, clip SHA-256 and revision ancestor hashes
are recorded in `revision-clips.receipt.private.json`; all copied audio is
streamed in bounded chunks (maximum 192 MiB). The originals are never
re-rendered, resampled, modified, or uploaded.

Open the new folder's local `index.html` beside its short WAVs to hear
previous vs revised per changed boundary; keyboard 1/2 switches real versions
and arrow keys navigate. This is **unblinded operator audition**, not a
formal A/B preference experiment, and the source and clip SHA receipts prove
only internal consistency, not rights, identity or musical quality.

Instead, add `--revision-reels-output /private/revision-review` when
running `mixlab.marathon_reel_decisions ... --previous-hybrid ...`. The
same separately approved real full hybrid WAV is rendered first; the clip
step then requests an **additional typed `yes`**. If it fails, only
the optional new listening folder is rolled back. The full prior and newly
approved revised WAV masters remain available.

## 9. Browse real WAV revisions and release one selected master

Use the following with 2–8 **ordered consecutive** finished private hybrid WAVs:

```bash
python3 -m mixlab.marathon_revision_history prepare \
  /private/work/mixlab-revision-history.html \
  /private/hybrid-v1/marathon.wav /private/hybrid-v2/marathon.wav
```

The CLI verifies each full PCM16 WAV SHA-256, official receipt, source identity,
original approved blend relationship, private operator decisions, and every
successive `parent_hybrid_sha256`. Foreign/out-of-order versions are rejected.
The local offline HTML shows original durations, real changed transition counts
and SHA fingerprints. You can manually attach each local WAV to listen, but
the browser checks only basename, size and decoded duration, **not SHA**;
the CLI always independently hashes original audio before any publication.
Export a selected-version JSON without source paths or audio bytes.

```bash
python3 -m mixlab.marathon_revision_history publish \
  /private/work/mixlab-selected-hybrid-lineage.private.json \
  /private/hybrid-v1/marathon.wav /private/hybrid-v2/marathon.wav \
  --bundle --delivery mp3
```

`publish` re-verifies all ordered WAVs and the exact selection, requests
explicit typed `yes` and invokes only the existing official private WAV USB
and installed FFmpeg routes. The selected already finished WAV is **never
modified**, other versions cannot be silently chosen, and private DJ notes
are not automatically included. Optional output failures keep original WAVs.
Music rights, external sender authenticity and independent blinded listening
preference are still **not** proven by internal source hashes.

## 10. Audition genuine original/blend WAV excerpts while revising

The revision desk can also play the original **actual** PCM16 A/B snippets
before you edit your previous decisions, without repeatedly loading huge
WAVs. First generate or restore the official [Real Join Reels](marathon-real-join-reels.md)
for the same original and approved blended source masters. Then place a
**new** revision HTML beside the already verified short WAV files:

```bash
python3 -m mixlab.marathon_revision_desk \
  /private/hybrid-current/marathon.wav \
  /private/original/marathon.wav \
  /private/approved-blend/marathon.wav \
  /private/handoff-reels/mixlab-revision.html \
  --reels-folder /private/handoff-reels
```

The CLI re-verifies the entire original/blended/hybrid full WAVs, current
choice history, the exact official Real Join Reels receipt, each tiny stereo
PCM16 WAV header and content SHA-256, source SHA match, sample rate,
transition labels, selected fade lengths and join cardinality. It refuses
unrelated, changed or symlinked reel sources. The editor now shows **Hear
actual hard join / Hear actual rendered crossfade** for each row; both are
existing, already copied short WAVs, **never browser-created audio or new
models**. Browser playback may be restricted locally and does not itself
re-hash the WAV, but the CLI rechecks the physical sources before publishing.
The editor remains offline with no media embedded, storage or upload.
Re-exported revisions still require a separate typed approval and preserve
the older finished WAV and its real SHA/receipt.
