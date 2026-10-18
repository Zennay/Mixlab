# Real Marathon Join Reels — listen to actual approved crossfades offline

MixLab can turn two **already completed, receipt-verified** private Marathon masters (one sample-exact original and its separate, human-approved real PCM16 crossfade derivative) into a standalone local listening folder. This is not a blind research benchmark: the operator knows which is which.

## Make a compact set of real audio snippets

```bash
python3 -m mixlab.marathon_join_reels \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  /private/handoff-listening
```

The output destination is a **new** directory in an existing non-Git, non-symlink private location. The CLI first checks both actual source WAV hashes/receipts, the blend's exact original SHA provenance and same source-event identities. It prints the source fingerprints, privacy warning and asks for **typed `yes`** before copying audio.

Inside `/private/handoff-listening/`:
- `join-01-original.wav` and `join-01-blend.wav` (then join 02, etc.) are **genuine excerpts** from the already rendered stereo PCM16 WAVs. No synthesis, in-browser fade, resampling, tempo warping or additional mixing is done.
- The copy includes up to **8 seconds before the actual original/blended entry boundary** and **the selected real fade length plus 8 seconds after**; very short sections and playlist edges are clamped to source-frame bounds. Each version is sliced from its own receipt-derived true timeline.
- The folder includes its own `index.html` offline player: direct A/B buttons per original/blended handoff, keyboard **1/2** to switch between real audio clips, left/right to navigate, space to pause, and an optional private personal DJ note export. Rehearsal notes are saved only when explicitly downloaded; not uploaded or stored persistently.
- `join-reels.receipt.private.json` records exact source SHA-256s, each excerpt's actual frame start/count, playable WAV SHA-256, original/blended boundary time and manual fade duration. Clip count is 2 per boundary (maximum 14).
- Excerpts are size-bounded to **192 MiB total uncompressed PCM**, generated in small frame buffers, and files are private (mode 0600). If production fails, the new unfinished folder is removed; original masters are preserved.

Open the generated `index.html` locally while keeping all `join-XX-*.wav` files beside it. If your browser cannot play local WAV because of its security settings or codec support, use a local music app instead.

### What this means for mastering

Unlike the existing Sequence Studio two-deck approximation, Join Reels play the **actual final PCM16** chosen by the MixLab renderer. This allows rapid operator audition of the audible transition moments without reloading entire 768 MiB masters.

The clips are **not** a substitute for hearing the full chosen WAV. Their receipt demonstrates only internal consistency, not external media authenticity, permission to share the recordings or musical superiority. M1's independently frozen, rights-safe blind preference study remains open; user-entered operator notes here must not be treated as that experiment's ratings.

For a real choice after listening, use [Marathon Master Review](marathon-master-review.md) to bind original/blended SHA fingerprints and publish just the selected private master.
