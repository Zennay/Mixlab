# ML-07 exact PCM reuse / stale stereo quality preflight

This **optional** offline signal-integrity check for A/B candidate WAVs is invoked via `python3 -m mixlab.quality.reuse BASELINE.wav CANDIDATE.wav [CANDIDATE2.wav ...] [--fail-on-warnings]` from a MixLab checkout. It is a **pre-merge draft**; no production CLI or renderer was modified.

It flags candidate audio where nearly every *audible* PCM frame is byte-for-byte identical (`>=98%`), where one stereo channel stays unchanged while the other meaningfully changes (`>=95%` unchanged vs `<=80%`), or where stereo L/R samples exchange in `>=75%` of audible frames. Shared silence does not count as copy evidence: below 1,000 active frames or 5% active coverage, similarity metrics are `null` with an inspect warning. Active frame threshold is 1,024 in any channel of either source. Comparison uses integer little-endian PCM16 equality; reported fractions are rounded to four decimals.

**Interpretation:** exact matching is not perceptual similarity, timing/tempo evidence, musical quality or human preference. A valid creative transition can include large spans of unchanged context. Every warning is an *inspect* hint, not a release gate or a proven defect. This supplements existing waveform, timing, loudness and spectral diagnostics, replacing none of them.

**Security/resource boundary:** max 32 MiB / 2M frames per source, 8M total logical baseline+candidate frames, maximum 8 candidates, 8–96 kHz uncompressed mono/stereo PCM16 only; two streams in 4,096-frame blocks from regular WAVs through `O_NONBLOCK|O_NOFOLLOW` file descriptors. Reject FIFOs, symlinks, changed metadata/inodes, truncated PCM and unmatched audio dimensions. The baseline is read once per candidate: total CPU read effort may be twice the logical aggregate limit. No output audio, network, model downloads, audio uploads or external dependencies.

CLI stdout contains anonymized `candidate-XX` IDs, aggregate fractions and generic warnings only; no file paths, filenames, PCM, hashes, sample positions or track identifiers. Error messages redact user-controlled input. Exit codes: 0 success, 2 warnings with `--fail-on-warnings` or bad args, 3 input rejection. Channel-specific aggregate fractions may be sensitive for proprietary music: keep reports local unless authorized.

All tests use synthetic PCM only. Passing CI proves technical source behavior, **not** canonical VPS renderer proof, permitted real-music quality, blind listening preference, or authority to release zCloud PWQ-320 / close M1.
