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

## Full M1 software-path validation without real music

The hosted browser job additionally runs **the existing MixLab production
software path on original rights-safe procedural fixtures**. It creates a
16 kHz stereo two-track library with `mixlab.cli.fixture`, builds a
seeded **three-trial, four-family** frozen blind pack with
`mixlab.cli.benchmark`, and validates it using the canonical:
`check_review_controls`, `inspect_review_pack(require_generated_html=True,
require_receipt=True)`, and `verify_pack` APIs. Every neutral A/B renderer
WAV is loaded in a real hosted Chromium page copied to a disposable browser
directory, preserving the original frozen pack. Browser-created, explicitly
**synthetic** ratings A/Tie/Both-unusable are passed to the *existing*
`mixlab.evaluation.aggregate` (one machine-generated test identity) to
verify the end-to-end contract and the invariant `milestone_pass=False`.

A second complete benchmark render from the same private synthetic manifest
and fixed test seed must produce the **same frozen pack identity and trial
assignments**. This is a reproducibility test, not an invitation to fix a seed
for actual blinded listening. Production pilots must omit `--seed`, freeze
their permitted 5–10 independent preselected pairs, match loudness, and obtain
three independent human responses. These CI tests do not evaluate taste,
quality superiority, source ownership, real audio device output or accessible
screen-reader behaviour. All files are temporary GitHub-hosted fixtures;
the production VPS and private audio library remain untouched.

## Browser playback initiation vs full PCM decode (strict evidence boundary)

A first headless Chromium regression asked for a physical-like
`HTMLMediaElement.ended` event after synthetic playback. [The exploratory
hosted run #39043402427](https://github.com/Zennay/Mixlab/actions/runs/39043402427)
correctly **failed**: the audio element's `play()` promise resolved, but
Chrome's accelerated `--virtual-time-budget` did not provide an `ended`
event that can establish actual wall-clock playback or audio output. This
is not evidence of an application fault, nor proof of audible sound.

The gate now keeps two distinct assertions:

- Browser `HTMLMediaElement.play()` **accepts initiation** of an existing
  local synthetic WAV, rather than pretending time-accelerated headless
  playback proves the entire clip was heard.
- A separate browser `OfflineAudioContext.decodeAudioData` reads **all
  PCM16 bytes** of a generated 8 kHz stereo, 0.4-second WAV, verifies the
  3,200-frame decoded `AudioBuffer`, sample rate, channel count, duration,
  nonzero content and opposite-channel sample relation. A corrupt,
  non-WAV byte array must reject. No output device, external network or
  user music is needed.

The browser media metadata checks still prove all ten local neutral WAV
references resolve (and fail for removed/corrupted files); the actual
renderer-to-evaluation smoke independently verifies checksum-bound renders
and browser-created **synthetic** JSON ratings. **No automated CI output
certifies real audible listening, assistive technology accessibility,
legal rights, human preference, or M1 milestone completion.**

## Single-command frozen pilot technical admission

Instead of individually running disconnected checks before a pilot, the QA
branch exposes:

```sh
python3 -m mixlab.quality.pilot_preflight /private/frozen-pack \
  --study /private/frozen-study.json \
  --expected-study-id THE_64_HEX_SHA256_PINNED_OUTSIDE_THE_PACK
```

**Do not copy the study ID out of editable pack metadata.** It must be
independently recorded *before* a real listening session. All three inputs
are private and never printed in reports/errors. The gate composes:

1. The official generated review form (required controls, labels, frozen
   JavaScript and stylesheet, no mutable extra scripts).
2. The strict private PCM review-pack scanner, with official HTML identity,
   public receipt binding and A/B WAV integrity.
3. The frozen 5–10 pair preregistration identity and private study/render
   metadata consistency, checked against the independently supplied ID.

Exit code **0** means **technical_gate=pass** only when *all* constituent
checks are consistent and **no PCM warning or cross-trial duplication**
was found. Exit **2** means `technical_gate=hold`: the structure and pinned
metadata are consistent, but technical audio or blinding warnings need
review. Exit **3** means invalid/unbound source or malformed options, with
a single sanitized private-path-free diagnostic and no JSON output.

JSON output contains **only** anonymous aggregate counts and booleans.
It never publishes pack IDs, source hashes, trial-level private statistics,
filenames, reviewer codes, answer assignments, or audio.

Even a technical PASS always declares:
`actual_source_rights_independently_authenticated=false`,
`actual_source_audio_authenticated=false`,
`independent_listeners_verified=false`,
`human_preference_proven=false`, `release_authorized=false`,
`milestone_pass=false`.

This gate therefore cannot autonomously move MixLab out of M1. Source
licenses, a real browser/assistive-tech review, independent 3+ listeners,
and actual DJ preference remain **external approval gates**. The pilot
tool is deliberately not imported into the shared renderer/CLI or ML-05
owner files, to avoid parallel ownership conflicts.

The hosted CI additionally exercises the gate against a real five-pair
procedural frozen-study fixture already covered by the independent
study-binding contract, including corrupt PCM, modified HTML, forged
study IDs, sanitized CLI arguments, and simulated clean vs warning
technical summaries. No real music, permission claims, or rating data
is collected.
