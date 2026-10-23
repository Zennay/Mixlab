# Original vs revised private rehearsal · human take comparison

This companion makes the [MixLab Human Transition Revision Studio](private-human-revision-studio.md) useful across actual iterations: after the human DJ has explicitly selected new variants and generated a **new reel**, compare the previous and new real audio rather than inferring that a revision must have improved it.

```sh
python3 -m mixlab.private_rehearsal_compare \
  ./private-rehearsal-01 ./private-rehearsal-02 \
  ./private-original-vs-revised
```

Open `private-original-vs-revised/index.html` in your browser. Each chapter shows two real, playable PCM16 alternatives, with their original/revised family names and **authentic previous and new human cue notes**. Only one player runs at a time. For each chapter, explicitly choose **Original works better**, **Revision works better**, or **Needs another rehearsal**, with optional new written comments. Download `mixlab-human-take-comparison.json` locally; it binds the human decision to the exact SHA-256 of the comparison receipt **and both complete original reel receipts**. Nothing is uploaded, auto-applied or silently stored.

The comparison command admits the two original-compatible private reel receipts through the existing bounded JSON reader. It requires 2–8 chapters in the same order and the same precise original gallery SHA-256 for every track pair; a different track or chapter count is rejected rather than portrayed as an A/B result. It copies both chosen actual WAVs from the original and revised reels using the existing SHA-256-checking, bounded, no-follow, stable-source PCM16 file reader. The new studio never overwrites originals, publishes only to a new owner-private folder (0700, individual files 0600), and caps all compared audio at 128 MiB. No new DSP computations, replacement licences or playlist accesses are performed.

**Important:** This screen deliberately shows which transition is the original and which is the revision. It is a transparent *human rehearsal preference*, not a formal blinded study, musical-quality benchmark, or scientific significance result. Rights remain unverified, no automatic scoring or model-based preference selection happens, and the original ML-04 DSP/ML-05 research claims remain open. The downloaded decision is a private working artifact, not a deployment or permission grant.

Follow-up to build a final merged choice from these human comparisons must treat every `Needs another rehearsal` chapter as unresolved, never silently promote a winner.
