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
(|sample| >=1024); at least 2048 informative samples and 32 distinct values
are required on *both* sides. It warns when >=99.5% of candidate informative
samples are multiples of 256 or 64 while <10% of baseline informative samples
are multiples of the same step. Both thresholds are heuristics designed to
recognize conspicuous resolution collapse without misclassifying already
coarse baselines, silence or constant tone. One degraded stereo channel can
raise a warning even if the other stays unchanged. Lack of enough data
returns `null`, **not** a clean bill of health.

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
