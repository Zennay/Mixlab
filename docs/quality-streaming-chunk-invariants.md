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
- Repeat impulse detection at 8, 16, 48 and 96 kHz (mono/stereo)\n  to protect sample-addressed scanning independently of sample rate.\n- Place a 480-frame all-channel zero gap at multiple 4096-boundary offsets;
  verify a >=60 ms *interior* PCM dropout is flagged, but not misidentified
  as a >=200 ms coarse-window gap.
- Place the same dropout in the left channel while the right remains clearly
  audible; assert channel-only dropout without falsely flagging the stereo
  signal itself as missing.
- Compare identical PCM in two different valid RIFF containers (with/without
  JUNK) and verify private PCM digests, window samples and public metrics
  are identical. Private digests are **not printed**.
- Verify a public blind-review WAV with extra RIFF JUNK metadata is refused\n  even when the internal diagnostic reader can decode that PCM unchanged.\n- Check A/B candidate warnings retain an isolated impulse; verify JSON does
  not contain fixture locations or source bytes.
- Refuse a declared PCM16 WAV whose actual data is truncated.

Source generation is fully procedural. There is no downloaded or user-owned
music, reviewer account, model or external audio package. 10,003 frames at
8 kHz are deliberately long enough to cross several 4096-frame reads while
staying well under the existing 2 million-frame and 32 MiB limits.

## Reproduction and acceptance

```bash
python -m unittest discover -s tests -p 'test_quality_streaming_chunk_invariants.py' -v
```

The companion GitHub-hosted workflow runs both Python 3.13 and 3.14 at
the **exact PR head SHA**, enforces 192 MiB virtual address space, checks the
canonical quality suite and CLI privacy suite, and records peak RSS via
/usr/bin/time. A green result means a bounded synthetic scanner contract
is protected, **not** that private WAVs were played or M1 passed.

## Integration / ownership

Adds only one new test file, this page and a dedicated workflow. It makes
no edits to existing scanner/renderer/evaluator, active ML-05 and ML-07 PR
paths, zCloud queue, Notion release flags, source music or live VPS resources.
Keep this PR draft until exact-head CI, an independent owner review and
coordination establish a safe merge. No milestone conclusion is inferred.
