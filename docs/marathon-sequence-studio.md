# Marathon Sequence Studio — private browser arrangement to real WAV

Build one uninterrupted, *real* MixLab audio master from **two to eight already finished**, manually approved Event Publisher sets. Unlike a command-line-only arrangement, the order and optional exclusions are chosen in an offline browser. This does **not** analyze tempo, beats, key, stems or musical quality.

## 1. Prepare an offline editor from original private sets

```bash
python3 -m mixlab.marathon_sequence prepare \
  /private/arrangement/mixlab-sequence.private.html \
  /private/set-a/session /private/set-a/final-set.wav \
  /private/set-b/session /private/set-b/final-set.wav \
  /private/set-c/session /private/set-c/final-set.wav
```

Provide 2–8 **alternating original Studio session and completed WAV** pairs. Exact directory names depend on your existing Event Publisher output. MixLab checks the existing complete-set receipts and actual source WAVs before writing the private HTML. The page lists only local folder labels, exact output SHA-256 identifiers, duration and sample rate; the audio and private absolute paths are not embedded.

Open `mixlab-sequence.private.html` locally. Use **↑/↓** to reorder completed events, untick any event you don't want, and choose the **output transition style**: default hard joins, or a separately rendered audio crossfade at each incoming event (2, 4, 8 or 16 seconds; an individual choice for each join). Choose **Export exact-source render plan**. The browser downloads `mixlab-marathon-sequence.private.json`; no media or metadata is sent to a server. You must keep **2–8 selected** events and stay within the existing **768 MiB uncompressed master** limit. You can start with a larger inventory and exclude events to fit the budget.

## 2. Approve and render a new actual Marathon

```bash
python3 -m mixlab.marathon_sequence render \
  /private/arrangement/mixlab-marathon-sequence.private.json \
  /private/marathon-new \
  /private/set-a/session /private/set-a/final-set.wav \
  /private/set-b/session /private/set-b/final-set.wav \
  /private/set-c/session /private/set-c/final-set.wav \
  --start 21:00 --bundle
```

**Pass every original SESSION/WAV pair in the same *original input order* as the prepare command.** The downloaded JSON contains the chosen indices, not private file paths. The CLI recomputes source master hashes, validates all original files/receipts, confirms an unchanged rate/frame inventory, rejects duplicate/invalid positions, checks the selected PCM budget and shows the final order. The canonical existing Marathon compiler still demands the operator's explicit typed **yes** and creates a **new** private folder.

### Manual crossfade export: two explicit approvals, two independently valid WAVs

For a plan whose browser transition style is **Separate manually blended WAV**, add a second **new** folder via `--blend-output`:

```bash
python3 -m mixlab.marathon_sequence render \
  /private/arrangement/mixlab-marathon-sequence.private.json \
  /private/marathon-original \
  /private/set-a/session /private/set-a/final-set.wav \
  /private/set-b/session /private/set-b/final-set.wav \
  /private/set-c/session /private/set-c/final-set.wav \
  --blend-output /private/marathon-with-fades --bundle
```

The command first validates the exact original plan, checks every selected event is long enough to accommodate both incoming/outgoing fades, and asks for **yes** before creating the **sample-preserving original WAV**. It then invokes MixLab's existing `marathon_blend` renderer with the *individually selected* 2/4/8/16-second fades. It presents those choices and demands **another explicit yes** before writing the **second actual PCM16 WAV** in its separate folder. Optional `--bundle` and `--delivery` apply to the final blended result; the original master stays available in any case.

If optional blending fails or its second approval is withheld, the original completed WAV is retained and the command reports a separate `blended_warning`, never claiming a final blended WAV was produced. No alternate DSP algorithm or automatic beatmatching is introduced; fades remain manual. The editor itself provides decisions, **not a deceptive audio preview**.

After approval, the result contains `marathon.wav` (the actual consecutive PCM16 master), receipt, offline chapter/Stage player, optional showbook and optionally a private USB ZIP. The original source sets remain untouched. Add `--delivery mp3` or `--delivery flac` only when compatible FFmpeg/FFprobe are installed locally. An unavailable optional mobile encoding does not remove the real WAV.

An alternative separate editing route is the existing [Marathon Join Studio](marathon-stage.md), which can edit and render crossfades on an already completed original Marathon.

## Important limits

- Original, receipt-verified user-permitted local sources only. No catalog scraping, copyrighted uploads, external music rights inference, cloud sync or permission bypass.
- No self-trained models, audio embeddings, hidden tempo stretch or invisible DJ decisions.
- Human browser arrangement is an *unsigned* JSON plan whose cryptographic hashes only bind it to original source assets; they do **not** authenticate an external author.
- Offline HTML and real complete WAV remain private. The audio quality of reordering and hard boundaries must be auditioned by the operator before any venue performance. M1 Transition Lab's real-music blind human preference gate stays open.
