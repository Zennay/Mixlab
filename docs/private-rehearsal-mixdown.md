# Private source-bound rehearsal mixdown · ML-04 companion

This follows the existing [rehearsal reel](private-transition-reel.md), which assembles 2–8 human-selected MixLab transition clips and exports the DJ's manually reordered running-order JSON.

**Create an actual offline PCM16 preview WAV** (with an explicit 350ms silence gap between chosen clips):

```sh
python3 -m mixlab.private_rehearsal_mixdown ./private-rehearsal-01 \
  ./private-preview.wav --order ./mixlab-private-running-order.json --gap-ms 350
```

Omit `--order` to retain the receipt's original chapter order. `--gap-ms` accepts integers 0–1000; zero means a hard join, **not** a beatmatched or click-free DJ transition. Two new owner-private files are published exclusively: `private-preview.wav` and `private-preview.rehearsal.json`. Pre-existing files are never overwritten.

## Real user experience

The offline reel's responsive browser now has a **Reopen a private order** input. Manually select a previously exported `mixlab-private-running-order.json`; the page restores that exact ordering only when its SHA-256 receipt fingerprint matches the current original reel, and the JSON contains a complete nonduplicated permutation of all original chapter numbers. Invalid or foreign files do not change the visible order. The browser uses no cloud/network requests, automatic file storage, cookies or rights checks.

The command then reopens the original reel receipt and, when present, its exported human running order. It validates original-vs-export identity, all canonical chapter audio filenames and full distinct chapter coverage. It re-copies every originally chosen WAV through the integrated single-FD no-follow stable-source check and SHA-256 hash comparison; it never trusts a JSON-supplied media path. All source clips must be uncompressed PCM16 at a **matching** sample rate (8–96 kHz) and mono/stereo channel count; incompatible clips require deliberately rendering compatible galleries first. The audio renderer streams at most 4,096 frames at once, rejects short/truncated PCM payloads and bounds the complete output to 128 MiB. It inserts actual PCM16 zero samples, never normalizes, clips, resamples or changes the source's chosen frames.

The sidecar records exact SHA-256 of the output, original reel receipt, optional human order JSON, every original gallery and choice proof, human chapter notes, sample format, duration and explicit silence gap. It states `seamless_dj_mix: false`, `loudness_normalized: false`, `rights_verified: false` and `blind_preference_verified: false`. This is a **private rehearsal preview**, not a public music stream, continuous beatmatched set, research finding or permissions proof.

No runtime/worker/queue/VPS/deploy mutations, paid services, automated releases or QA suites are part of this feature. Source integration and original security/human authorization gates remain independent.
