# ML-07: private PCM16 low-bit precision-loss screen

This isolated quality-validation proposal spots a specific A/B confound: a
candidate may keep the same duration, peak, RMS, and channel layout while
discarding PCM16's lower bits. It does not infer music quality, missing
frequency content, SNR in dB, dithering, perceptual preference or effective
audio bit depth. It cannot detect deliberately dithered degradation.

Run locally on **rights-permitted, private** equal-length PCM16 files:

```sh
python3 -m mixlab.quality.precision /private/baseline.wav /private/candidate.wav
```

The read-only comparison accepts at most two uncompressed PCM16 mono/stereo
8–96 kHz WAVs, each <=32 MiB and <=2,000,000 frames. Files are opened with
no-follow/nonblocking flags, checked for regular-file type, and streamed in
4096-frame chunks. A size/inode/time metadata snapshot is checked afterward.
No audio, PCM fingerprints, file paths or segment positions are returned.

For each channel separately, the detector counts **informative** PCM samples
(|sample| >=1024). Globally at least 2048 informative samples and 32 distinct
values are required on *both* sides. Its **fixed-size residue histograms**
detect any quantizer phase (sample mod 256, 128, 64, 32 or 16), not just multiples of the
step: the candidate must concentrate >=99.5% of informative samples on one
residue; the baseline must have <10% even in its **most frequent** residue.
This also avoids false alarms when both sources are coarse but quantized with
different offsets.

To catch a damaged part hidden by the undamaged rest, the same check runs
across **8 fixed, corresponding time regions** per channel, each requiring
>=512 informative samples and >=16 distinct values on both sides. At least
**two** regions showing precision loss are necessary for a persistent regional
warning; a single isolated region gives `null` rather than a false all-clear.
The public report never includes those window positions or signal statistics.
A globally decisive warning also takes precedence over unavailable regional
data. A clean (false) flag requires informative, negative global and regional
evidence on *all* channels. Silence or insufficient data returns `null`,
**not** a clean bill of health.


Quantizer steps 16–256 correspond to discarding roughly 4–8 low PCM16 bits
(about 12–8 retained bits). Smaller steps, including an 8-sample grid, are
intentionally outside this conservative screen; neither a clean result nor
a warning determines perceptual audibility. The added step-16/32 checks
retain the same sample/region budgets and remain phase-independent.

The thresholds are heuristics designed to recognize conspicuous PCM
resolution collapse without misclassifying already coarse baselines,
silence or constant tones. One degraded stereo channel can raise a warning
even if the other remains unchanged. This does not detect quantization
followed by dither, noise shaping or other processing that obscures the grid.

Stable public JSON has only `schema_version`, `status`,
`candidate_precision_loss_inspect` (true/false/null), and an anonymous warning
token. Private file IO or format failures use generic error text and exit 3;
the CLI never prints source paths. The check reads neither private answer keys
nor permitted source media beyond the specified local PCM files.

**Limits and gates:** low-bit quantization may be an intentional production
effect. A warning requests human inspection; it is not a release gate or
a musical score. Clean results cannot exclude noise-shaped quantization,
band-limiting, codec artifacts or other audible defects. Do not treat
synthetic CI as evidence of real-music M1 preference. Existing original M1
gates still require lawful tracks, downbeat/phrase/key/stem proof, and a
pre-registered A/B study with independent listeners. The feature is isolated
from concurrent quality, DSP and evaluation owners and is not integrated into
the shared CLI/pack code until an integration owner accepts it.


## CI resource proof and adversarial regressions

The PR-only GitHub-hosted workflow checks exact immutable source SHA,
compiles source/tests, runs synthetic maximum-size 2,000,000-frame stereo
fixtures, and measures peak RSS with `/usr/bin/time -v`. It fails if the
entire synthetic precision test process exceeds **192 MiB peak RSS**; this is
a conservative CI admission bound, **not** a guaranteed bound on all operating
systems or evidence that the VPS has sufficient free RAM. Existing ML-07
quality/companion/privacy suites run separately.

Adversarial tests also exercise signed PCM, shifted 16/32/64/128/256-step quantization,
different quantizer offsets in noncontiguous regions, partial one-channel
loss, unknown/short regions, chunk-size invariance, read-only file hashes,
nonregular sources, and redacted CLI errors. Healthy and suspicious verdicts
are **synthetic signal-invariant assertions**, not listening preferences.
