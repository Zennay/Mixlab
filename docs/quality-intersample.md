# ML-07 — intersample peak screening for private offline A/B

This is a **read-only, CPU-only, synthetic-test-backed technical diagnostic**. It does **not** judge mixes, listening preference, perceived loudness or compliance with ITU-R BS.1770. There is no external dependency, background worker, audio upload, stem model or new VPS service.

## Why it exists

A PCM16 peak meter checks only stored discrete samples. A signal with two adjacent samples below 0 dBFS may overshoot between samples during DAC/playback reconstruction. This standalone command offers a **4×, eight-tap Blackman-windowed sinc estimate** as one additional risk screen. It is a finite approximation, not a calibrated true-peak meter. Warnings need corroboration on a reference meter and/or human audition; absence of a warning is not proof of clipping-free playback.

## Run locally (files never leave the machine)

```bash
python3 -m mixlab.quality.intersample PRIVATE_BASELINE.wav PRIVATE_CANDIDATE.wav
python3 -m mixlab.quality.intersample PRIVATE_BASELINE.wav PRIVATE_CANDIDATE.wav --fail-on-risk
```

Outputs only anonymous JSON: `baseline`, `candidate-1`, sample rate, channels, frame count, sampled peak in dBFS, interpolated peak **estimate** in dBFS, number of estimated fractional over occurrences, and a separate `high_frequency_near_ceiling_ambiguity_risk` / `technical_review_required` flag. No track IDs, filenames, source paths, raw frames, hashes or listening verdicts. `--fail-on-risk` returns exit 2 if **either** baseline or any candidate has an estimated fractional over, unresolved near-ceiling sign-reversal ambiguity, or fewer than eight frames (the screen cannot run). A warning is not proof of actual clipping. Invalid arguments exit 2; unreadable/malformed sources exit 3 with pathless diagnostics. `--help` is non-mutating.

## Resource and input contract

* PCM16 uncompressed mono/stereo WAV, 8–96 kHz, one baseline plus 1–3 candidates.
* Strictly equal channel count, sample rate and frame count are required **before reading PCM**, and the same inode cannot appear twice in the group.
* Per-source file bound 32 MiB and 2,000,000 frames; aggregate group bound 8,000,000 frames; at most 4 file descriptors, <=4096 input frames per read and eight-frame interpolation ring. Processing is linear in frames and deliberately CPU-intensive; schedule under normal offline admission only.
* Physical regular-file checks, final-component symlink refusal, full declared-frame reads, post-read descriptor identity/mtime/ctime/size checks; source bytes are never modified. These checks are not a hostile-filesystem security sandbox or full RIFF canonicalization. For stronger source/header guarantees use the separately scoped ML-07 single-FD/neutral-container preflight.
* With fewer than eight frames, `screen_evaluable=false`. The first/last three/four samples do not have enough two-sided context for interpolation; a clean result cannot certify those boundaries.
* The short filter can **miss** actual between-sample peaks in near-Nyquist bandlimited sine waves. A conservative, channel-local guard treats a fast sign reversal with one sample >=95% FS and the other >=55% FS as an **uncertain near-ceiling case** rather than as `intersample_over_risk=true`. This signal heuristic is not spectral classification; it may warn for legitimate percussive content and it cannot catch all underestimates. It counts only events, never positions or PCM values. `technical_review_required` combines estimated overs, this ambiguity warning and insufficient (<8) frames. This allows a fail-closed CI risk gate without inventing false 'measured overs'.
* The filter's frequency response is not equivalent to a formally calibrated true-peak meter. The number of estimated overs is a proxy count of fractional phases/channels, **not a count of independent audible clips**. Do not label the estimate 'dBTP' or use it to rank A/B candidates.

## Evidence and isolation

Synthetic regressions validate DC-preserving FIR weights, normal mono/stereo, an in-range PCM peak pair with a positive fractional overshoot, matching and nonmatching A/B duration, symlink/hardlink safeguards, truncated data, path redaction, and CLI exit codes. CI checks the exact PR head and measures elapsed CPU/RSS using `/usr/bin/time -v` on GitHub-hosted infrastructure. This proposal modifies only `mixlab/quality/intersample.py`, `tests/test_quality_intersample.py`, `tests/test_quality_intersample_stress.py`, this document and its own workflow. No changes to ML-02/03/04/05/06, another ML-07 PR, shared renderer/CLI, live SQLite queue or production VPS. Keep draft pending independent review, integration ownership and musical evidence. The original M1 gates (permitted music, measured analysis/stems, preregistered blind A/B with >=3 listeners) remain open.

## Full-capacity synthetic resource regression

A separate Linux CI-only stress test (`tests/test_quality_intersample_stress.py`) creates two entirely synthetic 2,000,000-frame, 48 kHz stereo PCM16 WAVs in a disposable directory, compares the complete A/B pair without source mutation, and **fails** if process peak RSS reaches 192 MiB. The dedicated workflow runs this test and the 19 focused synthetic checks separately, then re-runs seven baseline CLI privacy tests; it measures actual wall-time and peak RSS using GNU `time -v`. On an isolated non-VPS local container, the 2M-frame test passed with 18.02 seconds processing and 96,524 KiB peak RSS, **not** a production VPS or musical source. Hosted exact-head evidence for the earlier 13-test version is at [run #39019907226](https://github.com/Zennay/Mixlab/actions/runs/39019907226): 13/13 focus + 1/1 stress (31.820s, 19,608 KiB RSS) + 7/7 existing CLI/privacy on hosted Python, and 13+7 replay on hosted Python 3.14.8; [canonical ML-07 #39019907212](https://github.com/Zennay/Mixlab/actions/runs/39019907212) also passed. These runs **predate the near-Nyquist ambiguity change**; validate the new exact head separately before accepting it.

## Differential synthetic false-negative regression (near Nyquist)

A full-scale-related 0.4 cycles/sample sinusoid with **analytic amplitude 34,200 / 32,768 = 1.0437 FS** can be sampled at phase zero to all legal PCM16 values (peak **32,526**, less than the clip ceiling). With the short FIR, reconstructed 4× samples remain at or below the stored peak, so an interpolated-only screen reports **no over** even though the analytic sine's between-sample peak exceeds full-scale. The test explicitly reproduces this miss; it then requires `high_frequency_near_ceiling_ambiguity_risk=true` and CLI `--fail-on-risk` exit 2. Control cases at low amplitude, low frequency, and stereo single-channel exercise specificity. A short (<8-frame) untestable file likewise fails closed with `technical_review_required=true`. The heuristic only reduces known false-negative risk; its thresholds are conservative and not calibrated as an ITU true-peak detector.
