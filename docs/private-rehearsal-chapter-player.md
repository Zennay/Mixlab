# Private full-rehearsal chapter player · ML-04 companion

Turn the [source-bound rehearsal PCM16 preview](private-rehearsal-mixdown.md) into an **offline chapter player for the entire compiled WAV**, using the exact original mixdown receipt rather than regenerating cues or performing any music analysis.

```sh
python3 -m mixlab.private_rehearsal_player \
  ./private-preview.wav ./private-rehearsal-player-01
```

This reads the accompanying `private-preview.rehearsal.json`, checks its human-only/rights-unverified schema, original source hashes, every chapter frame count and exact cumulative cue boundaries. It copies the WAV through an owner-private bounded single-descriptor file read, verifies the full SHA-256 against its existing receipt, and verifies the PCM16 WAV header and complete frame payload before creating a **new** local folder.

Open `private-rehearsal-player-01/index.html` directly in a browser to:

- Play the entire source-bound WAV with one ordinary HTML audio player.
- Jump to each actual source chapter marker (derived from the original selected WAV frame counts and intentional gap duration).
- Navigate to previous or next chapter without opening or recreating original files.
- Read and print the originally human-authored cue notes.
- Add your own local rehearsal observations per chapter and explicitly download `mixlab-private-rehearsal-debrief.json`. This human-only debrief is bound to the exact original mixdown receipt hash and actual WAV SHA-256.

The offline workspace contains `rehearsal.wav`, `original-receipt.json`, and `index.html`, all with owner-private permissions. It is created under a new mode-0700 directory via staging and exclusive same-filesystem hardlinks. **No existing filename or source is replaced.** No linked file, oversized (>128 MiB) source, changed SHA-256, short frame payload, impossible chapter timestamps or unrecognized receipt is silently accepted. The browser has no external assets, uploads, accounts, autoplay or automatic note persistence.

A chapter player is a **human-oriented rehearsal tool**. It does not detect beats, synchronize tempo, make seamless transitions, improve loudness, check distribution rights, infer DJ quality or create independent blind human research evidence. It never changes the portfolio queue, worker ownership or production services. No standalone QA, regressions or tests were authored or manually run.
