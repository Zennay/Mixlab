# Human Transition Revision Studio · source-bound offline DJ workflow

The earlier private MixLab tools can already create four real PCM16 transition families, capture one human choice per track pair, assemble 2–8 chapters into one offline reel, render the complete WAV, and collect timestamped rehearsal feedback. This companion gives the DJ a **real iteration loop**, without automatically evaluating the music or overwriting any prior result.

## Step 1 — Listen to alternatives from the original recordings

You need the **original** reel and the original galleries used to produce every chapter, in the same order:

```sh
python3 -m mixlab.private_rehearsal_revision prepare \
  ./private-rehearsal-01 ./rehearsal-revision-studio-01 \
  --gallery ./original-pair-01-gallery \
  --gallery ./original-pair-02-gallery \
  --gallery ./original-pair-03-gallery
```

Open `rehearsal-revision-studio-01/index.html` directly in your browser. For each chapter, you get the **four actual audio alternatives** (baseline, bass swap, echo exit and hard cut). The original human-selected family is preselected. Listen to each; select either the current family or a deliberate replacement, add an optional human cue note, then click **Download my source-bound revision plan**. The resulting private file is `mixlab-human-revision.json`.

The prepare command rejects mismatched gallery order, duplicate galleries, source-hash discrepancies, missing or changed WAVs, noncanonical families and excessive total audio (>128 MiB). Media stays locally in the new owner-private folder. No absolute source file paths are embedded into the exported studio or plan.

## Step 2 — Apply the human decisions to a new playable reel

```sh
python3 -m mixlab.private_rehearsal_revision apply \
  ./rehearsal-revision-studio-01 ./mixlab-human-revision.json \
  ./private-rehearsal-02
```

This creates a **new complete rehearsal reel** with `index.html`, `receipt.json`, and the *actually selected* WAV clips. It uses the existing MixLab `private_transition_reel` browser player, so you can immediately listen, reorder, print and export another original-source-bound running order. You can also continue with `private_rehearsal_mixdown` and `private_rehearsal_player` for a full-length WAV and timestamp notebook.

The revision JSON must match both the current studio receipt's SHA-256 and the exact original reel receipt hash. Every chapter must be selected exactly once, in its original numbered position, with one of the four original families and a bounded human note. Selected candidate WAV bytes are SHA-256 verified again before publishing. The new reel carries the original gallery receipt fingerprint and an **authentic SHA-256 of the downloaded revision-plan file** for every human selection; `human_choice_source: revision-plan` distinguishes this from the earlier per-gallery standalone choice documents. It does not fabricate an independent per-chapter human-study receipt.

## Privacy, resources and integrity

- All sources are local, original and user-supplied. No API, hosted service, model download, stem extraction, beat estimation, resampling or cloud upload is involved.
- At most eight chapters and **128 MiB of total original PCM16** candidates are copied, using the existing bounded, regular-file, no-follow, SHA-verified read path.
- All output folders must be brand new (mode 0700), every media and receipt file is private (0600), original source files are untouched, and publication refuses collisions and cleans up partial copies.
- Original ML-04 DSP engineering, ML-05 research gates and rights requirements remain separate. The operator's selections are **human-directed rehearsal choices**, not blinded listening evidence, validated licensing, professional mastering or automated musical-quality scores.
- These features modify no zCloud runtime, SQLite queue, claims, self-hosted runner, system services or production deployment. No QA or regression suite is added or manually executed.

This is a product delivery for the still-open [ML-04 issue](https://github.com/Zennay/Mixlab/issues/4); do not close that issue until the original quality, resource, permissions and human-listening requirements are met.
