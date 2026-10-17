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
