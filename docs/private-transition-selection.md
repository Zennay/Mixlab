# Private transition choice → playable WAV (ML-04 product handoff)

After creating an offline [four-family gallery](private-transition-gallery.md), a human DJ can select an actual variant in `index.html`, add a short private cue note, and download `mixlab-dj-choice.json`.

Export exactly that selected, hash-verified PCM16 WAV without running another render:

```sh
python3 -m mixlab.private_transition_selection \
  ./private-gallery-01 ./mixlab-dj-choice.json ./my-chosen-transition.wav
```

The command creates **two new files** next to one another: `my-chosen-transition.wav` (byte-for-byte unchanged from the rendered selected family) and `my-chosen-transition.choice.json` (private source evidence). Neither filename may exist already. It never overwrites an original WAV, modifies a gallery, updates a central playlist, syncs to a cloud, or triggers a zCloud worker.

## Product integrity

- The DJ choice must be the actual browser-exported v1 schema with a human-selected family. It contains the SHA-256 digest of **the complete original gallery receipt**. A choice exported from another gallery is rejected, even if both galleries have the same candidate names.
- The gallery receipt must contain the four canonical families, their exact local relative `.wav` filenames, all four 64-character SHA-256s, its original `rendered-not-listener-validated` status and explicit unverified rights. Arbitrary file paths from JSON are never used as source paths.
- The chosen WAV is copied from a single regular, no-follow descriptor with an enforced 32 MiB input cap, stable file metadata and SHA-256 equality with the original receipt. A changed, linked or replaced source file is rejected.
- Private JSON source files are bounded to 64 KiB with duplicate-key and nonfinite-value rejection; no raw audio is loaded into memory. A private scratch directory stages the selected WAV and choice receipt; exclusive same-filesystem hardlinks publish both only when ready, rolling back the WAV on a sidecar conflict.
- The handoff sidecar retains exact receipt/choice SHA-256s, selected WAV SHA-256, human cue note and the original common-gain reference. It explicitly says `rights_status: unverified`, `human_blind_preference_verified: false`. Do not treat it as permission to share, stream, publish or claim an actual listener preference study.

The entire flow is user-triggered, CPU/local and source-only. There are no uploads, third-party APIs, automated rights checks, machine-made preference claims, blind human-study evidence or VPS/queue/worker mutations. It adds no QA suite; normal repository merge/security rules remain intact.
