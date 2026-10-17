# ML-07 — Single-channel stereo polarity reuse screening (draft)

## Evidence gap

The ML-07 streaming PCM16 comparator previously caught exact PCM reuse, whole-file
polarity inversion and swapped stereo channels, but a candidate that inverted
**only left or only right** was treated as distinct PCM. A review pack can
therefore repeat the same recording with a channel-polarity edit while giving
the appearance of an independently generated transition.

The new independent check computes two private SHA-256 fingerprints for each
stereo candidate: the original PCM with exactly one channel negated. These are
compared with the baseline and previously accepted neutral candidate digests.
A match is reported as a **review warning only**:

- `single_stereo_channel_polarity_flip_inspect_for_reused_audio` in warnings.
- `single_channel_polarity_inverted_pcm_of` references `baseline` or an
  opaque `candidate-NN`. No left/right assignment, PCM bytes, source filenames
  or digest values are emitted to JSON.
- Exact duplicates retain their prior primary duplicate warning; mono audio
  does not create stereo fingerprints.

Only 4096 decoded frames are kept per read, plus bounded temporary interleaved
arrays and digests. PCM16 `-32768` is not representably negatable: the
corresponding transformed digest becomes unavailable instead of clipping
or pretending to be an exact match. Inverting the *other* channel is still
valid. The 32-MiB / 2-million-frame source restrictions are unchanged.

A single-channel polarity change can audibly affect stereo imaging or mono
fold-down; this check must **not** label the audio identical perceptually,
pick a winner, edit WAVs, or imply that the transition is good. Independent
DJ/technical review remains necessary.

## Bounded synthetic evidence

The isolated `tests/test_stereo_polarity.py` suite covers both inversion
directions, 4096-frame block boundaries, candidate-to-candidate reuse,
nonmatching samples, exact-duplicate precedence, saturation at PCM16
minimum, path/digest non-disclosure in JSON and CLI, read-only files,
and unchanged mono diagnostics. It requires Python standard library only.
Run from the root of the exact source checkout:

```sh
python3 -m unittest discover -s tests -p 'test_stereo_polarity.py' -v
python3 -m unittest discover -s tests -p 'test_quality.py' -v
```

The already-merged companion-suite check from PR #54 invokes
`python3 -m unittest discover -s tests -p 'test_[!q]*.py' -v`
within the quality suite; this pattern **includes** the new
`test_stereo_polarity.py` module. The PR branch now contains a merge of that
change, so an ML-07 quality Actions result for the **exact integrated PR
head** exercises both the quality suite and this six-case regression.
A green run for the older pre-merge head is *not* sufficient. Verify exact
checkout SHA, the companion suite test count, and the hosted run conclusion
before removing the draft gate. A later squash-merged main still requires
independent exact-main proof.

This is **synthetic DSP/quality QA only**. No private music, human preference
ratings, sample-rate pitch proof or authorization for publication is claimed.
M1 remains open, including real rights-safe A/B listening and independent
audit. No VPS workload has been added while memory/swap pressure is high.

## Private WAV format integrity (additional ML-07 improvement)

The direct `scan_wav` / `compare_wavs` quality commands previously relied
only on Python `wave.open` to interpret the PCM16 header. That reader may
tolerate a bogus `byte_rate`/`block_align`, a partial stereo data frame, or
a malformed RIFF chunk extent. A preflight could have reported legitimate
technical metrics for a recording whose playback interpretation differs in
another audio client.

The new `mixlab/quality/riff.py` checks the private WAVE container **before
PCM decoding**: RIFF/WAVE identity and declared bounds; sane unique `fmt`;
PCM16 mono/stereo and 8–96 kHz; arithmetic consistency for bit depth,
channel block alignment and byte rate; valid optional `fmt` extension size;
and integral PCM frames within the declared RIFF boundary. Only chunk headers
and 16–18 bytes of format metadata are read. Parsing is capped at **4096**
RIFF chunks per input to reject pathological metadata-heavy files before
full PCM decoding. Unknown private metadata chunks
are skipped using RIFF padding rules, never copied to the report. Private
trailing data outside the declared RIFF is deliberately still tolerated for
the existing metadata-insensitive PCM fingerprint contract. This is **not**
a general-purpose WAV verifier, authoring tool, nor permission to ship that
metadata inside public listener packs: `quality.pack` continues to enforce
the stricter canonical metadata-free public-WAV contract.

`tests/test_private_riff.py` adds deterministic positive and adversarial
cases for valid mono/stereo, private metadata before/after PCM, forged
byte rate, block alignment, bit depth, partial-frame truncation, invalid
RIFF extents, duplicate/misordered `fmt`/`data` chunks, legitimate optional
`fmt` extension and corrupt extension size, and sanitized strict/default
CLI failures without source paths. The existing public pack and blind-rating
code are untouched.

Exact-head quality Actions proof must include both
`test_stereo_polarity.py` and `test_private_riff.py` via the companion
suite. Do not promote the draft PR on a CI run for an earlier SHA.

## Signed stereo channel swaps — further ML-07 blinding protection

A stereo variant can reuse exact PCM under a *combination* of channel
swapping and channel polarity inversion. Earlier ML-07 heuristics detected
plain L/R swap, full polarity inversion and individual L/R polarity inversion
separately, but not the three composite cases `(-R,L)`, `(R,-L)` and
`(-R,-L)`. A supposedly independent listening option may therefore be
nothing more than a signed swap of an earlier recording.

The streaming scan now derives three additional **private** bounded digests
per stereo PCM16 read, with the same sample-rate/frame/channel checks and
the same strict `-32768` cannot-be-negated rule. The public neutral diagnostic
is `signed_stereo_swap_pcm_inspect_for_reused_audio` and
`signed_stereo_swap_pcm_of` references only `baseline` or the prior
anonymous `candidate-NN`. Exact duplicate-PCM diagnostics remain separate;
no samples, fingerprints, source files, trial answer keys, left/right mapping,
or audio are included in output.

Six new deterministic tests in `tests/test_signed_stereo_swap.py` cover
all three transformations (crossing 4096-frame boundaries), previous-candidate
reuse, single-sample mismatch, the PCM16 `-32768` edge and legal opposite
channel case, exact duplicate/mono non-regression, and CLI privacy with
read-only input verification.

These are *exact transformed-PCM equality* warnings for possible A/B
recognition confounds, not proof of perceptual identity or bad mixing;
intentional phase and stereo manipulations may sound different.
M1 still needs rights-approved real audio and blind listener evidence.
