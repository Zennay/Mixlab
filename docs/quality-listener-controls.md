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
- Hidden/inert/disabled, `aria-hidden=true`, arbitrary tab reordering,
  inline styles/event handlers and duplicate attributes are refused. Browser-
  inert or reinterpreted contexts such as `template`, `noscript`, `textarea`,
  `xmp` and `plaintext` are rejected rather than trusted as usable DOM.
- Form actions, unexpected fieldset/form metadata and remote script sources
  are not accepted; the actual official JavaScript still needs independent
  inspection or strict generated-template comparison.
- The ratings status announcer and the exact labelled button text are present;
  each fieldset has one correct, visible `legend` matching its trial ID.
- The embedded script and stylesheet must each occur **exactly once** and
  match the trusted `mixlab.cli.write_review` generator byte-for-byte.
  The comparison reconstructs a throwaway one-trial public template using
  a constant fake pack ID; it never reads any actual private WAV, answer key,
  source path or reviewer entry. Script injection, modified rating selection,
  CSS-hidden controls and additional script/style tags fail closed.
- HTML comments (which could disclose the private A/B assignment),
  processing instructions and altered/multiple doctype declarations are
  refused. No private metadata is returned.
- Ancestor and final path symlinks, FIFOs/nonregular files, oversized input,
  decode failures and local source replacement/mutation during the scan
  cause refusal. HTML is limited to 1 MiB.

The preflight deliberately checks the **current official generated markup
contract**. It is not a permissive general-purpose custom page checker.
A future UX change must update the checker and review the semantic
accessibility and listener implications together. This includes legitimate
changes to the official JavaScript or stylesheet: they are frozen deliberately
until a focused human review can establish whether the change affects
blindness, answer integrity, browser navigation or keyboard behavior.

## Mandatory separate gates

Also run
`python3 -m mixlab.quality.pack /private/pack/review --require-generated-html --require-receipt --fail-on-warnings`
and the frozen-study check for actual controlled experiments. The pack
check validates real WAV inventory/bytes and exact official generated HTML.
The static preflight here compares trusted JavaScript/CSS **text** for
unexpected modifications but does **not execute** JavaScript or inspect the
waveform, browser focus/keyboard/screen-reader interactions, or alternative
media. The official generator itself is not treated as audited or immutable:
a malicious change to both generator and checker can evade the equality gate. An independent browser/DJ review and at least three blinded listeners
are still necessary for M1 milestone claims.

Automated regressions use only synthetic HTML generated via
`mixlab.cli.write_review` and never require copyrighted audio or a VPS render.
