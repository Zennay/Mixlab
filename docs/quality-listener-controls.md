# ML-07 — Offline blind listening control preflight

This strictly **read-only** static HTML preflight complements MixLab's existing
PCM checks and frozen-study binding. It does **not** certify preference,
accessibility in a real browser, JavaScript safety, legal source rights,
appropriate loudness or musical quality.

## Why this matters

A fully valid WAV comparison can still produce invalid blinded ratings if
one playback control is disabled/hidden, labels are switched, a preference
select is optional, or a trial silently omits "Tie" / "Both unusable".
This independent gate catches those ordinary markup regressions before
a human review pack is issued.

Run on the **private local** generated review page:

```sh
python3 -m mixlab.quality.listener_controls /private/pack/review/index.html
```

Success exits 0 with a bounded, anonymous JSON summary of trial count,
two labelled playback controls per trial, mandatory rating controls and
the reviewer input / status announcer. The checker never reads private WAVs,
renders or answer keys, nor emits pack ID, audio names, absolute paths,
reviewer codes or content. Malformed / missing / moved / linked / too-large
files fail closed with exit 3 and a generic diagnostic. Invalid CLI arguments
exit 2 without echoing their raw values.

## Explicit checks

- Generated offline form includes a valid opaque 64-char pack ID,
  one required *labelled* reviewer code and a working submit control.
- Trial IDs are contiguous `trial-001..`, 1–60; each fieldset contains
  exactly two labelled A/B audio players, `controls`, `preload="none"`
  and neutral expected local sources.
- One labelled `required` select per pair binds to the corresponding trial,
  with the five unaltered options: choose-placeholder, A, B, Tie,
  Both unusable.
- Hidden/inert/disabled, `aria-hidden=true`, negative tab order and
  duplicate attributes are refused in the reviewer UI.
- The ratings status announcer is present. No private metadata is returned.
- Ancestor and final path symlinks, FIFOs/nonregular files, oversized input,
  decode failures and local source replacement/mutation during the scan
  cause refusal. HTML is limited to 1 MiB.

The preflight deliberately checks the **current official generated markup
contract**. It is not a permissive general-purpose custom page checker.
A future UX change must update the checker and review the semantic
accessibility and listener implications together.

## Mandatory separate gates

Also run
`python3 -m mixlab.quality.pack /private/pack/review --require-generated-html --require-receipt --fail-on-warnings`
and the frozen-study check for actual controlled experiments. The pack
check validates real WAV inventory/bytes and exact official generated HTML.
The static preflight here does **not** inspect the waveform, JavaScript
behaviour, browser focus/keyboard/screen-reader interactions, or alternative
media. An independent browser/DJ review and at least three blinded listeners
are still necessary for M1 milestone claims.

Automated regressions use only synthetic HTML generated via
`mixlab.cli.write_review` and never require copyrighted audio or a VPS render.
