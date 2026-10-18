# Marathon Master Review: real original vs. blended WAV → private chosen delivery

A complete local DJ production now has a human decision step **after** the two real outputs have been rendered. This tool compares the actual separately rendered original and crossfaded MixLab Marathon PCM16 masters and exports an unsigned, private SHA-bound choice. It does **not** run a blind preference study, rate music automatically, infer rights or record audio.

## 1. Generate a private listening board

Only original **receipt-verified** completed Marathon files, with their own immutable `marathon.receipt.private.json` companion files:

```bash
python3 -m mixlab.marathon_master_review prepare \
  /private/marathon-original/marathon.wav \
  /private/marathon-with-fades/marathon.wav \
  /private/review/mixlab-master-review.private.html
```

The implementation checks both WAV bytes and their actual PCM16 WAV/receipts, verifies one exact original-to-blend provenance relation (`source_marathon_sha256`), identical source-event hashes, section lengths/labels and matching sample rate. It refuses arbitrary or unrelated files. The result is chmod `0600` offline HTML. It includes only expected WAV hashes, sizes, durations, chapter names and precise original/blended boundary times; **no raw audio or private directory paths**.

Open the generated page locally, then use the two file pickers to attach the *original local WAVs* by hand. Each file has the same basename (`marathon.wav`), so choose carefully from the two named source directories above. Browser checks byte length/filename/decoded duration only; it does **not** cryptographically validate files. The CLI already validated complete audio and receipts when generating the page.

The page provides:
- Actual local original and blended PCM WAV playback in two separate, mutually pausing players.
- A one-click **Play original near join** and **Play blend near join** button for every event boundary, each navigating to the right boundary in **that** version's actual timeline (crossfades shorten the rendered PCM). Browser seeking is approximate, unlike the deterministic private WAV receipt.
- Private handwritten per-join notes and an optional overall rationale.
- A radio choice of **Original hard joins** or **Real manual crossfades**, and **Export binding master choice** → `mixlab-marathon-master-choice.private.json` (no embedded music).

Nothing uploads, persists in localStorage, or makes a public release. Browser-held source blob URLs are revoked when the page closes.

## 2. Package only the version you selected

```bash
python3 -m mixlab.marathon_master_review publish \
  /private/review/mixlab-marathon-master-choice.private.json \
  /private/marathon-original/marathon.wav \
  /private/marathon-with-fades/marathon.wav \
  --delivery mp3 --bundle
```

The `publish` CLI revalidates the *two* originals and their full PCM16 SHA-256 receipts, the explicit decision JSON, all event source identities and the original-to-blend binding; it prints the actual selected SHA and asks for **typed `yes`**. After reconfirming the exact source hashes, it delegates to existing official MixLab `marathon_delivery` and `marathon_bundle` functions. Output stays inside the **selected WAV's own private folder**: `marathon.mp3` or `marathon.flac` plus receipts/offline player, and/or a new `marathon.selected.private.zip`. The other original WAV and its event package are not modified.

Select `--delivery flac` instead of `--delivery mp3` for optional lossless local encoding, or `--bundle` alone to retain the original WAV format in portable ZIP. At least one output flag is required. These optional outputs need enough local space and installed codecs (for MP3/FLAC). An unavailable codec/ZIP is recorded as a warning; the existing real WAVs remain unchanged. Previously created output files are never overwritten.

## Important gates

- Use only privately allowed music and actual completed MixLab Event Publisher/Marathon masters. The receipt hashes verify internal consistency, **not a recording's licensing or authentic authorship**.
- The browser is a non-blind human review of two *already separately rendered* WAVs, **not** an independent A/B listening experiment. M1's research milestone remains open until authorized real tracks and human blind ratings exist.
- Nothing here changes or claims work in ML-02 ingest, ML-03 MIR, ML-04 DSP, ML-05 blind study or ML-07 QA. No testsuites are included or run.
- The exported JSON is an operator's unsigned local decision; it must never be treated as cryptographically authenticated permission to distribute music publicly.
