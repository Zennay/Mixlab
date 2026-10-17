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
  CSS-hidden controls and additional script/style tags fail closed. The trusted
  stylesheet must appear before the form and the trusted script after the
  form's submit control and closing tag: content-equal but browser-breaking
  script relocation is invalid.
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

## Hosted real-browser smoke (synthetic)

`tests/test_quality_listener_browser.py` provides a complementary browser
execution check. On a GitHub-hosted Ubuntu runner with preinstalled Chromium
or Google Chrome, it opens a **generated local, original five-trial HTML page**
and uses isolated in-page test instrumentation to exercise the real DOM:

- A required but blank rating must block `form.requestSubmit()`.
- With all five ratings selected, `A`, `B`, `Tie`, `Both unusable`, and
  `A` must serialize to the correct trial IDs and frozen synthetic pack ID.
- The generated script must export the correct `schema_version` and anonymous
  reviewer code, update its status announcement and expose ten A/B controls.
- The synthetic harness intercepts download clicks and Blob generation;
  it does not upload audio, create real reviewer ratings or open network
  endpoints. Browser execution uses a bounded 35-second process and a
  disposable isolated profile, *only* on hosted CI, not the swap-constrained VPS.

The JavaScript instrumentation is added **only to a temporary synthetic
fixture**; it is never part of the review UI and never weakens the static
generated-asset equality gate. This proves basic runtime browser form/export
behavior in one headless engine. It is **not** independent human usability,
a multi-browser/screen-reader/keyboard audit, listener preference evidence or
a release authorization. Run a separate manual, rights-safe listener study
before any M1 preference claims.

## Forced answers and offline submission safeguards
The exact official reviewer `input`, submit `button` and each rating
`option` have a strict attribute contract. Even apparently harmless extra
attributes are refused until reviewed: `readonly`, preset reviewer `value`,
restrictive `pattern`, preselected A/B options, misleading `label`,
`formnovalidate` (which would bypass mandatory choices) and button
`formaction` (which could redirect the offline response) are not permitted.
The select's empty placeholder is the only option allowed an explicit
`value=""`; all four substantive options must be unselected without any
extra attributes. Generated official markup remains the positive fixture.

## Real offline PCM16 source binding (hosted browser only)

The independent browser smoke now also creates **ten deterministic private
PCM16 WAV files** (five neutral trials × A/B; mono A and stereo B, 8 kHz,
0.4 seconds). It opens the official local review page using `file:` in actual
headless Chromium and explicitly loads every HTML audio source despite the
intended `preload="none"` behaviour of real listening sessions.

An asynchronous result is published only after all ten audio elements report
valid finite duration, a local `file:` source and a non-error metadata-ready
state. A separate fresh Chrome profile is used after deleting one WAV, and
again after replacing it with malformed RIFF bytes: these **negative controls
must fail**. This distinguishes working local audio source references from
merely having ten superficially valid `<audio controls>` elements.

Important evidence limit: `loadedmetadata` establishes media recognition
and declared duration, **not** that every PCM frame was decoded, sound was
played to real output hardware, signal continuity was perfect or a human
could hear a good transition. The existing bounded PCM scanner and human
listening study remain mandatory. Fixtures are generated in a disposable
temporary folder and are never committed or uploaded as media.
