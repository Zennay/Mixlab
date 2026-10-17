# ML-07 — streaming PCM16 read-boundary invariants

## Purpose and boundary

This independent, add-only quality-validation regression proves that the
canonical 4096-frame streaming reader does not lose synthetic clicks or
short audio/channel dropouts when a PCM event crosses a read boundary.
It additionally compares the real scanner's *private* decoded-PCM SHA and
public metrics for a canonical WAV versus the **same audio** with a harmless
RIFF JUNK chunk. This is a software invariant, not a claim of audio quality.

**Stage:** M1 Transition Lab remains OPEN. The active source-of-truth issues
are [ML-07](https://github.com/Zennay/Mixlab/issues/7) and
[ML-05](https://github.com/Zennay/Mixlab/issues/5).
Blind preference and lawful real-media access are still missing.

## Deterministic synthetic cases

- Position one isolated 10,000-count sample at frames 4094, 4095, 4096 and
  4097, in both mono and stereo, verifying the native click counter, frames
  and position-invariant peak/adjacent-step/near-clipping metrics.
- Repeat impulse detection at 8, 16, 48 and 96 kHz (mono/stereo)
  to protect sample-addressed scanning independently of sample rate.
- Place a 480-frame all-channel zero gap at multiple 4096-boundary offsets;
  verify a >=60 ms *interior* PCM dropout is flagged, but not misidentified
  as a >=200 ms coarse-window gap.
- Place the same dropout in the left channel while the right remains clearly
  audible; assert channel-only dropout without falsely flagging the stereo
  signal itself as missing.
- Compare identical PCM in two different valid RIFF containers (with/without
  JUNK) and verify private PCM digests, window samples and public metrics
  are identical. Private digests are **not printed**.
- Check **exact 50ms fenceposts**: 49.875/50ms at 8 kHz, 44.1kHz
  fractional-time frame counts, and 96kHz, for full PCM and one-channel
  dropout straddling a 4096-frame block boundary. A single sample below the
  threshold must not be promoted to a HOLD.
- Check a continuous 220Hz procedural tone in mono and stereo has no
  *false* boundary clicks/dropouts, phase cancellation or A/B warnings.
- Verify 60ms silence only at the beginning or end of a clip does **not**
  masquerade as an interior dropout (both whole PCM and one-channel stereo).
- Verify full-scale negative signed PCM16 (−32768) at a 4096-frame
  boundary cannot wrap into a false polarity-inverted fingerprint; the
  diagnostic reader still reports its clipping/headroom risk.
- Verify a public blind-review WAV with extra RIFF JUNK metadata is refused
  even when the internal diagnostic reader can decode that PCM unchanged.
  A patched comparator would raise if ever invoked: the guard must refuse
  extra public RIFF chunks during header admission, before a PCM scan.
- Prove public WAV admission rejects **LIST, bext, iXML and JUNK**
  chunks *before or after* audio, including valid private diagnostic
  WAVs, and refuses unaccounted trailer bytes. The comparator is mocked
  to fail if invoked before container admission finishes.
- Check simultaneous **multi-candidate** stereo L/R swaps, signed polarity
  inversion and PCM-identical audio with changed RIFF container at frame
  4095 or 4096. The comparator must preserve reuse warnings without
  revealing original paths or private decoded fingerprints.
- Check truncation after 1, 4095, 4096, 4097 and 10,002 declared source
  frames, for both mono and stereo. An incomplete read must fail closed.
- Run a **reproducible seeded metamorphic sweep** across 20 interior
  offsets (including both 4096-frame read seams) with 399/400 frame
  quiet runs. 50ms at 8 kHz must trigger; one less frame must not.
- Preserve the independent **1.5dB global RMS confound gate** under
  mono/stereo and non-audio RIFF metadata: +1.40dB passes the comparison
  tolerance, +1.58dB fails closed without revealing private paths.
- Exercise **actual** PCM16 source capacity without a mocked frame limit:
  a streamed 2,000,000-frame 96kHz stereo WAV with a 50ms interior gap
  crossing the 4096-frame reader boundary must scan within the CI 192 MiB
  cap; a real 2,000,001-frame WAV must reject on admission.
- Verify very short valid mono/stereo 1, 2, 159, 160 and 4095–4097-frame
  WAVs at 8/96kHz and 20/1000ms window sizes have the mathematically
  correct ceil(window count), no false interior loss and strict finite JSON.
- Check A/B candidate warnings retain an isolated impulse; verify JSON does
  not contain fixture locations or source bytes.
- Refuse a declared PCM16 WAV whose actual data is truncated.

Source generation is fully procedural. There is no downloaded or user-owned
music, reviewer account, model or external audio package. Most fixtures use
10,003 frames at 8 kHz; the dedicated actual-capacity fixture streams 2M
frames at 96kHz without constructing the full audio in Python memory. The
2M+1 negative control rejects the actual above-limit source before scanning.

## Independent PCM numerical reference oracle (new large QA work package)

The dedicated `tests/test_quality_pcm_reference_oracle.py` is an
**independent brute-force decoder oracle**, not a collection of golden output
snapshots or a call back into the product's metric helpers. It derives sample
peak/RMS/DC, per-channel RMS, clipped fractions, sample-to-sample jumps,
short-impulse and plateau counts, prominent onsets, PCM fingerprints, exact
20–1000ms RMS window averages, and true interior 50ms gaps directly from
synthesized signed-16-bit frame tuples. It compares those numbers to the
canonical 4096-frame streaming scanner with no knowledge of read chunks.

- **120 fixed-seed differential cases** include five original wave families:
  broadband signed extrema, sparse click/dropouts, bounded periodic
  non-DC signals, sustained high flat tops and genuine quiet PCM; across
  1/2 channels, 8/44.1/96kHz, tiny/4096-/8192-frame edges and four
  analysis-window sizes.
- **64 cross-chunk dropout oracle cases** use full-channel silent runs one
  frame below/exactly at 50ms for all 8/16/44.1/96kHz mono/stereo formats
  and 4095/4096/4097/8191-frame start positions. The independent oracle
  computes first/last quiet-frame intervals, not product detector flags.
- A separate **mutation sensitivity control** deliberately falsifies five
  expected measurements (click count, peak, RMS, adjacent jump, plateau
  count) and proves the oracle comparison rejects the substitutions.
- Private PCM SHA-256, independently encoded signed inversion and stereo
  swap fingerprints are checked without serializing hashes, samples,
  source filenames, private IDs or listener data into any public report.
- No hypothesis library, corpus access, licensed recordings, external
  dependency, production daemon or heavy model is used. The new file is
  add-only; existing rendering/analysis/other-worker modules remain untouched.

A green oracle means the **arithmetic/streaming implementations agree with
an independently constructed deterministic reference**, not that audio sounds
better, sources have been licensed, or human blind preference has passed.

## Reproduction and acceptance

```bash
python -m unittest discover -s tests -p 'test_quality_streaming_chunk_invariants.py' -v
python -m unittest discover -s tests -p 'test_quality_pcm_reference_oracle.py' -v
```

The companion GitHub-hosted workflow runs both Python 3.13 and 3.14 at
the **exact PR head SHA**, enforces 192 MiB virtual address space, checks the
canonical quality suite, CLI privacy suite and the synthetic frozen-five-pair
four-gate M1 integration suite, and records peak RSS via
/usr/bin/time. A green result means a bounded synthetic scanner contract
is protected, **not** that private WAVs were played or M1 passed.

## Integration / ownership

Adds only two new test files, this page and a dedicated workflow. It makes
no edits to existing scanner/renderer/evaluator, active ML-05 and ML-07 PR
paths, zCloud queue, Notion release flags, source music or live VPS resources.
Keep this PR draft until exact-head CI, an independent owner review and
coordination establish a safe merge. No milestone conclusion is inferred.
