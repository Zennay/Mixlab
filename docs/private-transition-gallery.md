# Private four-family transition gallery (ML-04 product companion)

The standalone command `mixlab.private_transition_gallery` creates one **local, offline listening gallery** from two manually aligned, legally permitted PCM16 WAVs. It reuses the existing bounded `mixlab.dsp.render` implementation without changing the claimed ML-04 DSP engine, shared CLI, blind-study owner scopes or live workers.

## One-command use

```sh
python3 -m mixlab.private_transition_gallery ./my-permitted-a.wav ./my-permitted-b.wav ./private-gallery-01 \
  --bpm 120 --beats 8 --a-start 16 --b-start 32 --gain-db -6 --reduce-common-gain
```

Open `private-gallery-01/index.html` locally in a browser. It contains four independently playable, identically timed WAV variations: baseline, bass swap, echo exit and hard cut. Starting another player pauses the previous player. Nothing is uploaded, streamed externally, auto-played, or handed to workers. The DJ can also choose a preferred family, type a maximum-240-character private cue note and download `mixlab-dj-choice.json` without any server request; the choice is bound to the SHA-256 of the original `receipt.json`, not represented as blinded research evidence. On reopening the gallery, use **Reopen a saved choice** to load that previous JSON manually: only this exact gallery's receipt fingerprint, known family and bounded note are accepted. Invalid files leave the current form untouched. Neither the preference nor the uploaded-file content is sent over the network or silently persisted.

All four variants share the **same** human-specified BPM, cue points and gain. The optional `--reduce-common-gain` retries the *whole* family at -3 dB increments only when the native renderer rejects PCM16 clipping. It stops at -60 dB. The final receipt records both requested and chosen gain; no family is independently boosted, peak-limited or normalized. Without the option, a clipped variant fails the entire gallery (the renderer's current default policy). An invalid source, changed original WAV, missing PCM frames or unsupported manual recipe also fails the entire gallery rather than silently skipping a variant.

## Deliverables

The destination must be a **new directory** under an existing parent and contains only:

- `index.html` — responsive, offline audio comparison; no remote resources.
- `baseline.wav`, `bass_swap.wav`, `echo_exit.wav`, `hard_cut.wav` — actual PCM16 renders using `mixlab.dsp.render`.
- `mixlab-dj-choice.json` — optionally downloaded by the DJ from the browser, with preferred family, short note and hash of the precise gallery receipt; not saved automatically in the gallery.\n- `receipt.json` — full source SHA-256 identifiers, per-output SHA-256, shared gain, manual BPM/cues, post-quantization peak/RMS and explicit `rendered-not-listener-validated` status.

All intermediates are placed in a private same-filesystem scratch directory first; the output folder is exclusively created and only populated after all four variants and the private receipt are ready. Errors clean the staged files, and previously existing destinations are never replaced. Inputs remain untouched. Keep `receipt.json` private: the source hashes can identify your own audio files across recordings. No absolute file path, credential or private user comment is embedded into the exported gallery files.

## Boundaries and follow-up

This is a usable manual DJ comparison, not a claim of perceptual advantage. It does **not** estimate beat grids, downbeats, stems, licences or musical fit. RMS/peak are engineering measures, not LUFS; the different musical families are **not** psychoacoustically loudness matched. The original ML-04 DSP quality/benchmarks and ML-05 independent real-track blind human study remain separately gated. Only use sources you are entitled to process. No QA or regression suite accompanies this product addition, and no automated VPS/queue/claim/runtime changes are involved.
