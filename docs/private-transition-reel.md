# Private multi-gallery DJ rehearsal reel · ML-04 companion

A DJ may audition four MixLab transition families for several manually prepared track pairs, download a **human-selected** choice per gallery, and now assemble **2–8 original selections into a single private rehearsal workspace**.

```sh
python3 -m mixlab.private_transition_reel ./private-rehearsal-01 \
  --pair ./pair-01-gallery ./pair-01/mixlab-dj-choice.json \
  --pair ./pair-02-gallery ./pair-02/mixlab-dj-choice.json \
  --pair ./pair-03-gallery ./pair-03/mixlab-dj-choice.json
```

Open `private-rehearsal-01/index.html` locally. Each chapter is an actual chosen PCM16 transition from the **original private gallery**, with the DJ's human cue note and ordinary audio controls. Use **Play from start** for sequential listening (not a continuous beatmatched DJ mix); Stop to reset, ↑/↓ to reorder the local rehearsal running order and **Print cue sheet** for an annotated reference. **Export private running order** downloads `mixlab-private-running-order.json` bound to the new reel receipt. Browser changes are intentionally ephemeral unless exported.

### Product source authority and confidentiality

The builder reopens each original receipt and browser-downloaded DJ choice with the already-integrated bounded, duplicate-key-denying, read-only JSON admission. The choice must name one canonical family and include the original receipt's exact SHA-256; no user-supplied file path in JSON is followed. Every WAV is copied from the original gallery's known fixed family filename using the same already-integrated single-descriptor, no-follow SHA-256 verification, regular-file size cap, and stable inode metadata checks as `private_transition_selection`. Each original gallery is accepted only once per reel, to prevent accidental duplicate chapters. The total copied PCM16 budget is 128 MiB, at most eight choices. No full audio is held in memory.

The command never changes the source gallery, chosen WAV, original DJ choices, cue metadata or zCloud state. It stages output in a private temporary directory; a destination must not exist, and its contents are exclusively published to an owner-only new directory. Each local chapter file is mode 0600. `receipt.json` stores bounded family, original receipt digest, selected WAV digest, human-selected note and human-choice digest, but **no local source paths, account information, credentials, or audio rights claims**. `index.html` is responsive, uses no external libraries or network requests, and prints a clean non-interactive cue sheet.

The new running-order JSON is **only an operator arrangement**, not a mutation of the original source-bound receipt or blinded evaluation. This workflow intentionally makes no claim of DJ suitability, time stretching, source separation, music rights, streaming/sync or offline-proof of a human blind preference. Its source is on GitHub; no production/VPS workers, data rights, blind-study gates, protected claims, or quality-validation code are changed.
