# Finalize a human original-vs-revised take (private, source-bound)

After preparing the [original vs revised rehearsal comparison](private-original-vs-revised.md), listening to both real PCM16 clips for each same-source track pair and downloading your explicit `mixlab-human-take-comparison.json`, turn the **decided** chapters into a new playable private MixLab reel:

```sh
python3 -m mixlab.private_rehearsal_finalize \
  ./private-original-vs-revised \
  ./mixlab-human-take-comparison.json \
  ./private-final-human-reel-01
```

This is an **operator-directed product handoff**, not a guess at which transition sounds best. The human decision must contain every chapter exactly once in original order, choose **original** or **revised** for each and match the exact SHA-256 of (a) the current two-take comparison receipt, (b) the original reel receipt, and (c) the revised reel receipt. If *any* chapter says `undecided`, contains missing or duplicated evidence, or belongs to another source, the command refuses to make a final reel. There is no "automatically pick revised" or "default original" policy.

For each chosen chapter, the command reopens the known fixed-source `NN-original.wav` or `NN-revised.wav` from the private comparison studio, recopies the actual bounded PCM16 bytes through the existing stable no-follow, SHA-256-verifying reader, and writes a **new, original-compatible private rehearsal reel**. This contains `index.html`, `receipt.json` and one genuine WAV per chapter; it works with the existing portable reel player, manually exported running orders, multi-chapter mixdown and full-WAV private chapter player.

The final receipt preserves which actual take won, the exact original track-pair gallery digest, the **real SHA-256 of your downloaded human comparison file**, the comparison receipt's SHA, your written comparison reason and the chosen candidate's earlier cue note. It includes `human_choice_source: explicit-visible-comparison`, `status: human-selected-not-blind-study`, and `rights_status: unverified`. This prevents an ordinary human rehearsal decision from being represented as new research, independent blind-preference evidence or source distribution rights.

No original WAV, gallery, comparison or prior reel is overwritten. The output must be a new owner-only directory and its WAV/JSON/HTML files remain private, with at most 8 PCM16 chapters and 128 MiB total local audio. No network call, original DSP changes, stem analysis, AI inference, worker/queue/runner mutation or VPS deployment occurs.

A final file means **a final chosen rehearsal draft**, not an externally authorized release or confirmation of real-world DJ quality. The independent ML-04/ML-05 rights, resource and human research gates stay open.
