# MixLab Set Composer — offline, private multi-track mixes

MixLab already renders four real PCM16 transition styles for each manually
approved pair and has a continuous WAV exporter. Set Composer connects them
with an **offline browser workflow**, without asking the user to transcribe
pair IDs and transition families into a long shell command.

## Create a private session and open the composer

1. Keep source music and its manifest **outside Git**. Only use locally
   possessed/appropriately licensed audio; a rights declaration alone does not
   prove the applicable rights.
2. Create a complete Studio session with every intended pair and manually
   verified matching BPM/cues (not `--pair` unless using one pair):

       python3 -m mixlab.session /private/music/project.json /private/session-01

3. Create the browser editor from the existing Studio receipts:

       python3 -m mixlab.set_composer create /private/session-01

4. Open `/private/session-01/set-composer/index.html` in a local browser.
   Play each transition via the browser audio controls, then build a set by
   clicking **Voeg overgang toe**. A next pair is selectable only if its outgoing
   track is the previous pair's incoming track. Select baseline, bass_swap,
   echo_exit or hard_cut separately for each step.
5. Click **Download keuzeplan**. The resulting
   `mixlab-set-plan.private.json` is a local, session-bound plan, not audio.
   You can load it again with **Heropen eerder keuzeplan** on the same page.

## Turn the choices into one continuous mix

    python3 -m mixlab.set_composer render \
      /private/session-01 \
      /private/mixlab-set-plan.private.json \
      /private/final-set-01.wav

### WAV + Event Player + portable MP3 in dezelfde opdracht

Je kunt de volledige WAV en een draagbare versie in één commando laten
maken (als lokaal FFmpeg en FFprobe geïnstalleerd zijn):

~~~bash
python3 -m mixlab.set_composer render \
  /private/session-01 \
  /private/mixlab-set-plan.private.json \
  /private/final-set-01.wav \
  --portable-mp3 /private/final-set-01-portable.mp3
~~~

Na het renderen publiceert MixLab de complete originele WAV, de offline
[Full Set Player](private-full-set-player.md) met eventmodus en,
optioneel, een lossy 192 kbit/s MP3 met CUE/M3U8 en privé hash-receipt
(zie [Portable DJ Set](private-portable-dj-set.md)). De MP3-export
hercontroleert de oorspronkelijke WAV en sessiehashes. Als FFmpeg
ontbreekt of MP3-encodering mislukt, blijft de geslaagde WAV staan en
meldt de CLI **`portable_warning`**; een mislukte bijlage vernietigt
niet de originele mix. Er worden geen oude bestanden overschreven.

The composer additionally publishes `<output>.wav.player.html` next to the
finished audio: a local continuous player with clickable song/transition
chapters, JSON chapter export and a compatible `.cue` download. The original
WAV survives even if the optional HTML publication fails. See
[Full Set Player](private-full-set-player.md).

The output is one full-length local PCM16-WAV plus its private SHA-256 receipt
(`final-set-01.wav.receipt.private.json`). The standard exporter uses the
original normalized solo passages between selected transitions; it does not
rerender or apply gain twice to transition WAVs. The original music is never
uploaded. Existing output WAVs are never overwritten.

The browser includes only track and pair IDs, manually declared BPM/beat counts,
relative transition-WAV links and session SHA-256 bindings, **not source file
paths or real music contents**. It makes no network requests and uses no CDN.

## Fail-closed session binding and limits

- Every Studio transition WAV used by the composer must exist inside the private
  Studio and match its SHA in the original Studio receipt.
- The Studio and session receipts must bind to the current excerpt manifest.
- Downloaded plans contain only schema/kind, original session/studio receipt
  SHA-256 digests and ordered `{pair, family}` selections. A changed or foreign
  session, duplicate pair, missing family, invalid ID or disconnected route
  is rejected on render. A saved plan is a selection, **not trusted render
  authorization**: the final exporter rechecks the original media hashes,
  exact cues, timing, WAV format and per-render hashes.
- At most ten distinct transitions. Existing exporter bounds still apply:
  maximum 512 MiB output; PCM16; limited tracks and verified manual cues;
  transition excerpts cannot exceed the canonical renderer's frame budget.
- Composer creates its own new `set-composer/` directory inside the private
  session and refuses to overwrite an existing one. Keep downloaded plan files
  outside the immutable session folder.
- A failed export does not invalidate the underlying Studio; correct the plan
  and choose another new output name.

## What this does **not** prove

The composer is a labelled **creative DJ audition**; it is not a blinded study.
Beat, bar, phrase, key and right-to-remix facts are not inferred. Current Studio
requires manually verified matching BPM and cues, and there is no pitch-preserving
tempo adaptation in the shipped renderer. Human musical preference, rights-safe
real source recordings, automatic MIR/stems and M1 acceptance remain open.

For the existing CLI-only route see [continuous set export](continuous-set-export.md).
