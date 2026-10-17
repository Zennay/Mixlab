# MixLab Transition Studio — local creative audition

This adds a usable **offline DJ audition workflow** on top of the existing
private MixLab renderer. Instead of distributing a blinded academic benchmark
pack to hear your own transitions, you can generate a local, beautifully laid
out listening page showing the real rendering techniques by name, play every
candidate and save your favorite WAV.

Studio deliberately displays styles and cannot be used to claim unbiased
listener preference. Frozen A/B research must continue using the separate
`benchmark` / `mixlab.evaluation` workflow.

## Start with your existing private manifest

For longer tracks, first use the new
[manual full-track cue compiler](full-track-cue-preparation.md) to generate
short bounded WAVs and a compatible `library.json`.

```bash
python3 -m mixlab.studio render /private/mixlab-cue-pack/library.json /private/transition-studio
```

Open `/private/transition-studio/index.html` locally in your browser. Each
track pair shows the already-supported equal-power baseline, bass swap,
echo exit and hard cut with labelled audio controls. Click **Save this WAV**
to save an individual result through the browser. No backend, cloud storage,
JavaScript library, CDN, account or network is involved.

Render a single pair when the library is large or disk resources are tight:

```bash
python3 -m mixlab.studio render /private/mixlab-cue-pack/library.json /private/one-pair-studio --pair pair-001
```

Export an exact checksum-pinned candidate using Python if you want an
immutable selected-output artifact:

```bash
python3 -m mixlab.studio export /private/transition-studio pair-001 bass_swap /private/selected-bass-swap.wav
```

- The studio runs the **canonical `validate_library`** (rights declaration,
  source SHA and constraints) before rendering any pairs. Existing DSP
  `Recipe` and `render` implementations generate the WAVs; no new audio
  algorithms are claimed.
- All render styles for a pair have the same manually supplied BPM, cue and
  beat duration. Equal sample rates/channel counts, equal tempos and excerpt
  budgets still apply. The studio is deliberately a bounded sequential CPU
  renderer (no concurrent workers or model/GPU downloads).
- The new destination must not exist. The total planned output audio is
  limited to 512 MiB. Use `--pair` to keep sessions small. New session folders
  are created mode 0700. Destinations inside Git repositories or the input
  music library directory are rejected.
- `studio-receipt.private.json` binds every candidate to its generated WAV
  SHA256, sample format and basic PCM metrics. It contains **no source paths,
  song titles or audio bytes**. The local HTML only refers to local relative
  rendered paths and pair identifiers.
- Export reopens the private session receipt, verifies its recorded content
  digest and the chosen audio's SHA256, then copies the chosen WAV to a new
  filename without overwriting an existing file. It rejects Git checkout
  destinations and accidental exports inside the immutable session folder.
- If any candidate render fails, the newly created incomplete session is
  removed; the original library and its source music are never changed.

**Limitations:** This is not full-set rendering, time stretching, automatic
pair discovery, harmonic compatibility assessment or blind A/B analysis.
Auditioning a chosen pair proves that an algorithm produced PCM — not that
the music sounds better than baseline. Human ratings and real DJ review
remain separate M1 gates.

## Workflow with real music

1. Keep permitted music and local manifests private and outside the repository.
2. Declare manual BPM, exact cue positions and source provenance. Use the cue
   compiler to create bounded manifest excerpts from full-length WAV songs.
3. Open this Studio to audition all current transition styles and select a
   favorite for a real creative mix. Run a separate blinded, frozen study
   when evidence is needed for a scientific quality claim.

This is an additive M1 product entry point, with no changes to existing
renderer, CLI, study/QA modules, shared contracts, workflows or other PR
file scopes. No source audio is ever uploaded by Studio.
