# MixLab ML-07 — CPU-first audio preflight

## Purpose
This is a **technical smoke/level-confound screen**, not a musical score,
automatic DJ, beat/key detector, signal repair tool, or substitute for a
blinded A/B human preference test. The listener decides whether a transition
is good; this tool catches incomparable / suspicious renders before a test.

## Mid-clip single-channel dropout guard

The bounded per-frame scanner now detects a **recovered 50ms or longer**
near-zero gap in *one* stereo channel while the opposite channel remains
prominent during at least 25% of those frames. It reports only
`longest_interior_stereo_channel_quiet_gap_ms` and
`short_interior_stereo_channel_dropout_risk`; the shared baseline/
candidate warning is `short_interior_stereo_channel_dropout_inspect`.
The test spans 4096-frame reads without storing the waveform. The existing
>=20%-of-RMS-windows partial-channel-loss check can miss a 50–90ms gap
that sits inside an otherwise audible 100ms window.

This is intentionally conservative: it excludes opening/trailing
silence, permanently silent channels, whole-mix breaks and mono audio.
An intentional brief stereo pan can trigger the inspect flag; background
noise above 64 PCM16 units can conceal genuine dropout. The check
neither repairs audio nor infers a beat, music preference, origin or
listener assignment. Raw sample positions, paths and private audio
are never emitted.

## Run locally (Python 3.10+, standard library only)

Use the existing renderer / benchmark to produce two or more short, private
PCM16 WAV renders. Preserve the neutral A/B and private answer-key boundary.

    python3 -m mixlab.quality /private/baseline.wav /private/candidate.wav
    python3 -m mixlab.quality /private/baseline.wav /private/a.wav /private/b.wav --window-ms 100 --loudness-tolerance-db 1.5
    python3 -m mixlab.quality /private/baseline.wav /private/candidate.wav --fail-on-warnings

The command reads the WAVs and prints JSON to stdout. It **does not change audio**
or automatically select a winning transition. Redirect locally to a
restricted destination if retention is needed. It emits opaque candidate IDs
rather than source paths, samples, source hashes or private recording metadata.
Without `--fail-on-warnings`, a well-formed report exits 0 even if it warns.
The opt-in flag returns 0 for a clean report and 2 for any candidate **or
baseline** warning, but always prints the full anonymized JSON to stdout
before exiting. Treat this as an optional technical CI gate: musical hard
cuts, phase effects and intentional silence may need human override, and
a clean report never proves a musically good transition.
Unreadable, missing, corrupt and mismatched WAV inputs now fail with exit code
**3** and one sanitized stderr diagnostic; no absolute paths, exception
messages, or traceback are logged. No JSON is produced for an invalid pack,
which must not be mistaken for a successful comparison. Exit code **2**
continues to mean only the *opt-in* technical warning gate. Keep source
media private regardless of sanitized CLI output.

## Complete blind A/B review-pack preflight

The existing benchmark produces neutral `review/trial-###-A.wav` and
`review/trial-###-B.wav` files. Inspect the **review directory only**;
do not supply the private answer-key folder or any recording/source library.

    python3 -m mixlab.quality.pack /private/pack/review
    python3 -m mixlab.quality.pack /private/pack/review --fail-on-warnings
    python3 -m mixlab.quality.pack /private/pack/review --require-generated-html --fail-on-warnings
    python3 -m mixlab.quality.pack /private/pack/review --require-generated-html --require-receipt --fail-on-warnings

The pack inspector rejects empty, incomplete, improperly named, linked or
excessive (more than 60) trial WAV inventories. A valid pack must also have
**contiguous trial IDs starting at `trial-001`** with both A and B for each;
a partial copied pack that skips `trial-002`, for example, fails before audio
is scanned even if the remaining files are individually valid. Before reading PCM samples it
also enforces a **512 MiB total WAV size** and **100 million aggregate declared
frames** across the entire review pack, in addition to existing per-WAV
32 MiB / 2 million frame caps. It checks all filenames, regular-file sizes
and WAV headers before running potentially costly sample-domain diagnostics;
truncated/malformed PCM is still rejected by the streaming reader. These
resource budgets protect a CPU-only shared worker and fail with sanitized
exit 3 instead of starting an unbounded multipack analysis. A larger study
should be split into independently reviewed, frozen packs rather than
silently increasing production limits.

The inspector also takes a **best-effort metadata snapshot** of the local
review WAVs, verified `index.html` (if present), and the public receipt (if
`--require-receipt` is used). After all audio checks it compares device,
inode, size, nanosecond modification time and change time, rejecting files
that were replaced or edited while the report was being computed. This
prevents accepting internally inconsistent results during ordinary
concurrent edits; it is *not* a cryptographic signature, immunity to
malicious timestamp manipulation, or proof that files remain unchanged
after preflight. Freeze and independently retain the original pack for
a real listener study.
Invalid packs error out with a
path-free diagnostic (exit **3**). A and B are deliberately neutral: the
tool never determines which is the baseline or accesses `private/answer-key.json`.
Anonymized JSON contains the trial IDs, two sets of technical metrics,
a B-vs-A RMS comparison, local-level mismatch and duplicate-PCM flags.
It **does not** export paths, sample arrays, PCM fingerprints, envelope windows
or the private answer key. The review directory is treated as publishable:
only neutral A/B WAVs and the generated regular `index.html` are allowed.
Unexpected files (especially `answer-key.json` / evidence / unapproved
downloads), symlinks and nested directories cause a sanitized failure,
rather than risking accidental publication of private trial assignments.
The inspector does not read or copy hidden source/answer content.
When the review directory includes `index.html`, the parser checks the
actual audio player links and enclosing trial fieldsets against all local
A/B WAVs in the canonical order. Missing, duplicated, swapped or remote audio
sources and unmatched trial IDs fail closed with a sanitized error (exit 3).
The review page is capped at 1 MiB; its text is never returned in JSON.
Audio-only review folders without an index can still be checked, but
`review_page_audio_links_verified` is then `false`, not a quality guarantee.
Review HTML parsing also rejects **duplicate attribute names**, including
case-insensitive repeated `src`, `data-trial` and `data-pack-id` on a
single element. Browsers generally use the first duplicate while Python's
`dict(attrs)` kept the last; a remote audio `src` followed by a local
`src` could previously make the static check report safe links while the
browser tried the remote source. Rejection is fail-closed even if the duplicate
values agree. CLI errors remain path- and payload-free. The strict official
HTML regeneration check is still recommended before any private listener pack.

The default static page preflight now also rejects playback-altering HTML
`autoplay`, `muted` and `loop` on audio players and `hidden` / `inert`
on any listener-page element. Otherwise a modified listening form could
show identical, valid A/B audio paths while playing an option silently,
starting it unexpectedly, repeating it or hiding the choice. Ordinary
`controls` and `preload="none"` remain accepted, including the official
offline generator. This catches common accidental A/B presentation
biases but is **not** an arbitrary inline-JavaScript/CSS inspection or
proof of equivalent listening conditions. Use `--require-generated-html`
for frozen official studies and an independent human review.

The static review-page check rejects external resource tags such as
`iframe`, `img`, `link` and `script src`, remote navigation/form
attributes, event-handler attributes and CSS `@import` / `url(...)`.
An inadvertently modified listener page must not fetch third-party
resources during offline review. This guards common static exfiltration
paths but **does not prove arbitrary inline JavaScript safe**; the exact
generated listener script still requires code review/CSP before public
distribution. For a frozen **official MixLab-generated** study, use the
opt-in `--require-generated-html` mode: the inspector rebuilds the
current official `write_review` HTML in a private temporary directory
from the **public** pack ID and neutral trial IDs, and requires exact
HTML equality. This detects modified inline scripts, text or CSS that
static audio-link screening alone could miss. No audio or answer key is
read during template reconstruction. Custom pages or missing `index.html`
fail closed with status 3 in this strict-template mode. A report records
`official_generated_html_verified` only if requested and confirmed;
the default remains `false` to avoid implying a performed check.
Matching the official template does **not** prove its JavaScript safe,
replace human JS/CSP security review, establish listening preference or
authorize publication of third-party music.

A public receipt used for this opt-in check must not acquire hidden trial
assignments, music source paths or arbitrary extra fields. Its accepted keys
are exactly `schema_version`, `pack_id`, `trial_count`, and optional
`render_count`, `status`, `manifest_sha256`. The optional fields, if
provided, must have their documented bounded types: positive bounded
integer render count, literal `rendered-not-listener-validated` status
and 64-character lowercase hexadecimal manifest fingerprint. Duplicate
JSON object keys are rejected instead of allowing parser-last-value
ambiguity. Unknown fields (including even innocently added metadata) must
be explicitly reviewed and kept out of a listener-visible receipt; preserve
the existing private `evidence.json` and `answer-key.json` separately.
This check is performed only with `--require-receipt` and does not prove
the receipt is authentic, signed or safe to redistribute with licensed music.

For an actual frozen listening pack, also set `--require-receipt`. This
opt-in reads **only** the bounded regular `receipt.json` sibling of the
public `review/` directory (maximum 8 KiB); it checks schema v1, the
receipt trial count against A/B pairs, and its 64-hex `pack_id` against
the listener form's public `data-pack-id`. The report sets
`public_receipt_pack_id_verified=true` only when this check succeeds.
It never reads `private/answer-key.json`, and rejects symlinked, missing,
malformed or mismatched receipts with a sanitized exit **3**. This prevents
accidentally collecting ratings under the wrong pack ID, **not** malicious
joint replacement of both receipt and page: the receipt is not
cryptographically signed. Preserve the original frozen pack and obtain
independent evidence review before a human benchmark.

The pack preflight snapshots the complete public review directory inventory
(filename plus device/inode/size/mtime/ctime) and the directory identity
**before** WAV header inspection, public receipt parsing or listener-page
validation. Immediately before success it checks the complete inventory
again, plus the directory identity and optional sibling receipt. A private
answer key, extra WAV or other file inserted while PCM is streaming, or
a page/receipt edited during initial validation, now fails closed even if
all expected audio files still match. This is a best-effort filesystem
race detector, **not** a cryptographic seal, atomic transaction, guarantee
against transient add-and-remove races, or proof of safe public release.
Keep a frozen immutable pack and perform an independent rights review.

Public blind-review WAVs are now subject to a **neutral RIFF container**
preflight before PCM scanning: a canonical RIFF/WAVE file must contain
exactly one 16-byte `fmt ` chunk followed by one `data` chunk, with a
consistent declared RIFF/file length and no extra bytes. Additional
`LIST`/`INFO`/`bext`/`JUNK` chunks, duplicate chunks, extended headers
and trailing payloads are refused, even if Python's WAV reader can play the
PCM normally. Such chunks can include source, title, artist or review
assignment metadata that unblinds an otherwise neutral `trial-###-A/B.wav`
filename. This protection applies only to *published neutral review WAVs*,
not private source ingest. The header check reads a bounded number of bytes
and skips PCM payload without decoding it; the existing streaming scanner
still verifies PCM16 format and exact samples. Some legitimate third-party
WAV exporters attach metadata or extended format headers: export a clean
neutral PCM16 **review copy** after respecting source rights, rather than
loosening the blind pack rule. This cannot certify that the audible material
itself does not reveal identity, or replace the human protocol audit.

The review preflight additionally fingerprints each playback waveform
*privately*, including sample rate/channel layout, and reports a neutral
`repeated_pcm_across_trials_inspect_blinding` **trial-level** warning
when an exact PCM recording is reused in a **different** randomized A/B
trial. Critically, the report does **not** reveal which A/B slot repeated
or link to an earlier slot: that would itself give away the hidden reference
in a reviewer-visible QA report. Private digests, source paths and audio
never leave memory. This is a potential **recognition and unblinding
risk**, not evidence that a listener actually identified
the baseline. Deliberate repeated-reference designs may require an
explicit independent protocol review, but must not silently pass a strict
blind-review gate. The official synthetic `fixture -> benchmark` pack
reuses the same baseline among its three family comparisons and should
trigger the warning. Review-pack checks do not automatically relabel,
rewrite or randomize the experiment.

By default it exits **0** with JSON regardless of nonfatal warnings.
With `--fail-on-warnings`, it exits **2** when any review pair raises a
technical warning (including identical A/B PCM) but still prints the JSON.
Good technical preflight is not evidence of listener preference or of a
musically superior transition, and intentional DJ effects may be flagged.
Synthetic regressions render actual DSP transition families and also run
MixLab's **official** `fixture -> benchmark -> review` workflow before feeding
the resulting public review directory into this quality gate. That verifies
the deployed pack filename/layout contract; it is still not real-audio or
human preference evidence.

## Contract and interpretations
- Bounded per input: at most 32 MiB and 2,000,000 PCM16 frames; supported
  sample rate 8–96 kHz, one or two channels; reads at most 4096 frames per
  chunk. Reuses existing bounded WAV constraints, no numpy/torch or GPU.
- An in-memory SHA-256 fingerprint of **PCM frames only** detects candidates
  that are acoustically identical to the baseline or to an earlier candidate,
  including WAV files with different container metadata. The report contains
  only neutral references (`duplicate_pcm_of`: `baseline` or
  `candidate-XX`) and inspection warnings, **never** the digest, source
  filenames or audio. Duplicate detection is not an automatic DJ quality
  score; it prevents meaningless blind comparisons. Strict mode treats these
  warnings like other technical preflight warnings.
- Exact same rate, channels and frame count are required for candidates.
  Mismatches fail closed instead of silently time-stretching or resampling.
- RMS and peak are basic sample-domain dBFS, **not** integrated loudness (LUFS).
  An RMS delta above 1.5 dB is a *possible level confound*, not a proof
  of audible bias and not a suggested gain change. Check a real loudness
  standard before frozen tests; do not simply boost into clipping.
- Equal whole-file RMS does not guarantee fair short-term balance. The
  bounded scanner privately compares time-aligned RMS windows against the
  baseline and warns when >=25% of non-silent windows differ by >=9 dB or
  one side is silent. Output exposes only a fraction and technical flag,
  **not** the underlying private waveform/envelope. This is not
  BS.1770/LUFS, does not normalize audio, and may flag intentional dramatic
  transitions. The LUFS matching work remains separately owned.
- Leading and trailing below -55 dBFS RMS windows are also measured as
  window-resolution milliseconds. For two audible A/B variants with identical
  frame count, a difference of >=200 ms at **either** end emits
  `ab_edge_silence_alignment_confound_inspect` and
  `edge_silence_mismatch_risk=true`. Such asymmetry can cue a listener to
  which variant is playing even if the file duration matches. Entirely silent
  files use the existing silence warning, not an inferred timing verdict.
  Intentional DJ dramatic pauses can be valid; this is only a technical
  *inspect* signal, not proof of poor mix quality or a preference winner.
  Window size (20–1000 ms) limits time resolution; preserve the original
  audio and ask the independent reviewer before a frozen blind benchmark.
- Consecutive below -55 dBFS RMS windows are tracked in streaming mode.
  A gap >=200 ms **between** audible sections raises
  `interior_silent_gap_inspect_for_dropouts`, even when fewer than half of
  the windows are silent. Leading/trailing silence, an entirely silent file
  and sub-200 ms interior gaps do not raise this specific warning. Durations
  are window-resolution estimates; intentional dramatic silence remains a
  creative choice for human review, not a quality failure verdict.
- The baseline receives `baseline_warnings` using the same artifact checks
  applied to candidates. An apparently clean candidate cannot hide a
  clipped, silent, phase-cancelling or interrupted baseline.
  Both sides flag a likely lost stereo channel when its whole-file RMS is
  below -55 dBFS while the other exceeds -35 dBFS; deliberate hard panning
  is not automatically rejected. `channel_rms_dbfs` is diagnostic only.
- Stereo channel checks also examine each non-silent RMS window. A channel
  below -55 dBFS while the other exceeds -35 dBFS in >=20% of eligible
  windows (at least two of three or more) warns about partial channel loss
  even if both *whole-file* channels have healthy RMS. Single brief pans and
  silent sections are excluded; results show only a window fraction/flag,
  never the private per-window channel levels. Musical hard panning may be
  intentional and must be judged by a listener.
- On stereo inputs, phase correlation and mono-fold-down loss (positive dB)
  are measured from streaming PCM samples. Each non-silent RMS window with
  >=9 dB mono-fold-down loss raises a technical warning, including brief
  anti-phase passages hidden by otherwise healthy overall RMS. Fully silent
  windows are excluded. The rule is a screening heuristic, **not** a measured
  listener preference, true-peak measure, phase correction or guaranteed
  mono-compatibility score. Complete cancellation reports a null global loss
  with a true risk flag; mono files also use null where not applicable.
- Repeated high-amplitude PCM plateaus can indicate **earlier clipping
  followed by gain reduction** even when no current sample reaches -0.001 dBFS.
  The streaming scanner counts runs of >=4 *exactly equal* consecutive samples
  at >=72% full scale, including across 4096-frame chunk boundaries, on both
  baseline and candidates. It is an **inspect-for-prior-limiting heuristic**,
  not proof of clipped audio: deliberately flattened bass, square waves or
  creative effects can legitimately trigger it. No automatic audio repair.
- Separately from jumps *between* PCM samples, the first and last sample
  of each playback excerpt can cause a click when playback enters/exits from
  zero. The bounded scanner privately examines only those two stereo/mono
  frames and warns `playback_boundary_step_inspect_for_clicks` when any
  channel reaches >=25% of full scale at either file boundary. The report
  carries aggregate `playback_start_peak` / `playback_end_peak` and
  `playback_boundary_pop_risk`, not raw sample values, paths or music.
  This is a potential step at an isolated playback boundary, **not** a
  measured audible click: a beat cut, joined continuous audio or intentional
  DJ effect can be valid. No fading or repair is applied automatically.
- Unexpected adjacent-sample jumps >=50% full scale are counted, including
  across the internal 4096-frame read boundary, and receive a technical pop
  warning. DC offset exceeding 3% full scale on any channel receives an
  inspect-for-headroom warning. Both diagnostics apply equally to baseline and
  candidates; intentional hard cuts, asymmetrical signals and drums may
  produce legitimate results, so they never auto-reject music.
- A sample near digital full-scale is flagged for inspection, not labeled
  proven clipped; intentional silence and percussive jumps can be musical.
  No psychoacoustic, phase, low-end-masking, key, phrase or crowd-response
  judgment is inferred.
- Every result retains "requires_human_review" and
  "human_preference_test_required". There is deliberately **no quality
  winner, model score or automatically fabricated DJ preference**.
- Treat synthetic tests as engineering proof only. A natural-music benchmark,
  blind listener data and independent review remain [ML-05](https://github.com/Zennay/Mixlab/issues/5)
  / [ML-06](https://github.com/Zennay/Mixlab/issues/6) acceptance gates.

## Reproduce the tests

    python3 -m unittest -v tests.test_quality
    python3 -m unittest discover -s tests -v

No music sources, copyrighted stems or real render recordings are checked into
this repository or uploaded to GitHub Actions. The module is isolated from
shared ML-02 ingest, ML-03 analysis, ML-04 renderer and ML-05 A/B code.

## CPU-first milestone linkage
- [Notion execution plan](https://app.notion.com/p/3f89e19ac95581299d47f11dffb12266)
- [MixLab HQ](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
- [Existing roadmap](https://app.notion.com/p/3e79e19ac9558150a32cf32a96fb1f64)
- [ML-07 issue](https://github.com/Zennay/Mixlab/issues/7)

ML-07 is an independent preflight slice. It does not complete M1. Later,
after the approved private library and matched-loudness method exist, the
integration owner may explicitly wire this into evaluation preflight. Until
then it remains an optional read-only CLI; no zCloud worker launch or
production deployment is implied by merging the code.


### Isolated sample transients below the severe splice threshold

The bounded PCM16 scan also reports `isolated_sample_impulse_count` and
`isolated_sample_impulse_risk` for a one-frame impulse on an individual mono
or stereo channel. An interior sample at **>=8192 absolute PCM16 amplitude**
surrounded by two neighboring samples each **<=2048** (same channel) produces
`isolated_sample_impulse_inspect_for_clicks`. The three-frame test carries
over the 4096-frame streaming-read boundary. This closes a narrow false
negative in the older `severe_adjacent_jump_count` rule: a 9000-sample
isolated click has jumps of just ~27% full-scale, below its 50% threshold.
Applies equally to baseline and candidate. There is **no attempt to repair
or suppress audio** and the JSON publishes only counts/booleans, not sample
coordinates or raw audio. Highly percussive or deliberately synthesized
single-frame sounds may be legitimate: warnings require human listening and
are never interpreted as musical preference, clipping proof or an overall
quality score.


### Canonical PCM16 header consistency for published review audio

Beyond forbidding extra RIFF metadata, each neutral `trial-###-A/B.wav`
must have internally consistent **little-endian PCM16** `fmt ` fields:
format code 1 (not floating-point), 1–2 channels, sample rate 8–96 kHz,
16 bits per sample, `block_align = channels × 2`, and
`byte_rate = sample_rate × block_align`. The `data` chunk must
contain a whole number of interleaved frames (`size % block_align == 0`).
Python's `wave.open` can ignore an inconsistent byte-rate or block-align
value and silently truncate a partial stereo frame; other players need
not interpret those bytes identically. Rejecting such public containers
before sample-level quality analysis prevents avoidable playback
differences and hidden non-audio bytes inside a partial final frame.

This strictness applies only to neutral *public review copies*. The
private ingest/render contracts and original rights/permission
requirements are unchanged. A validated header is not an authenticated
asset signature or evidence of musical preference.


### Short quiet-PCM dropouts hidden inside RMS windows

The existing 100-ms RMS-window detector can miss a 50–90-ms audible
interruption: the active part of its window keeps RMS above the silence
threshold. A separate constant-memory, per-frame check detects *interior*
runs of **at least 50ms** during which **all channels** stay within
±64 PCM16 units of zero. The output includes only
`longest_interior_quiet_pcm_gap_ms` and
`short_interior_pcm_dropout_risk`; `short_interior_pcm_dropout_inspect`
is a technical warning for both baseline and candidate. The run state
persists across 4096-frame reads and is independent of the user's
RMS `--window-ms`. Only audible→quiet→audible runs qualify:
initial silence, final fade to near silence, fully silent files and
one-channel-only creative panning are not classified as dropouts.

This is a conservative *near-digital silence* heuristic, not a general
quiet-passage detector: background noise can mask an interruption,
and intentional dramatic breaks may trigger it. No sample timeline,
source path or PCM buffer appears in the JSON; no audio is repaired.
Human listening remains required for genuine transition quality.


### Audible-onset alignment between A/B choices

Two equally long, similarly loud excerpts can begin at noticeably
different times without triggering the original >=200ms **RMS-window
edge-silence** warning. The per-frame scanner now records
`prominent_audio_onset_ms`, the position of the *first* mono or stereo
frame whose absolute PCM16 sample reaches **5% full-scale** (1638 units).
When both versions have such an event, a difference of **>=75ms**
produces `prominent_onset_mismatch_ms`,
`prominent_onset_mismatch_risk` and
`ab_prominent_audio_onset_mismatch_inspect`. It is independent of the
chosen 20–1000ms RMS window and does not record audio, private paths
or an onset waveform. Entirely silent/below-threshold clips report a
null onset and rely on existing silence warnings instead.

This flag is for reviewer inspection of **possible listening-time
confounds**; it is not beat detection, downbeat/phrase synchronization,
DJ phrase compatibility or a quality winner. A deliberate anticipation,
pickup or soft fade may have different first-prominent-sample times
without being defective. Listening with permitted music remains essential.


### Stereo channel-swap identity in blind A/B comparisons

An exact left/right channel reversal produces different **interleaved PCM**
bytes, so ordinary duplicate-content checks miss it even though no
different music or transition was rendered. The bounded streaming scanner
now computes a **second, private stereo-swap fingerprint** from only one
4096-frame read chunk at a time. If a candidate is byte-for-byte equal
to the baseline (or an earlier candidate) **after exchanging its L/R
samples**, it emits
`stereo_channel_swapped_pcm_inspect_for_reused_audio` and
`stereo_swapped_pcm_of` with only a neutral baseline/candidate ID.
Mono inputs and exact duplicate stereo/dual-mono inputs retain their
existing classifications. Hashes, content samples, source paths and
A/B answer assignments are not exported.

A reversed stereo field can itself be an intended creative decision:
this is a **review-for-independent-transition** warning, not proof of
plagiarism, a listening preference or an overall DJ quality score.
The extra scan uses bounded RAM, no model, no audio edits and no
private-data uploads.


### Exact polarity inversion as a blind A/B near-duplicate

The bounded PCM16 pass also computes a *private* sign-inverted PCM
fingerprint. A candidate whose **every mono or stereo sample is the
exact negative** of a baseline or previous candidate receives
`polarity_inverted_pcm_inspect_for_reused_audio` and a neutral
`polarity_inverted_pcm_of` reference. Exact unchanged PCM still takes
precedence, including silence and dual-mono. For any input containing
the un-negatable signed PCM16 sample `-32768`, inverted identity is
reported as unavailable rather than silently wrapping/clipping the
sample and claiming exact equivalence. The scanner works in bounded
4096-frame chunks, without emitting raw PCM, sample coordinates,
private hashes, source paths or listener answer keys.

Whole-wave polarity inversion can be an intentional processing choice
and may matter when blended with other signals. This is only a
technical **reused-audio inspection warning**, not proof of musical
equivalence, perceptual quality, ownership or a listening preference.


### Late-onset left/right channel imbalance

For stereo PCM16 only, the first sample of each channel reaching **5%
full scale** is measured during the existing bounded read. If **both**
channels become prominent but their first onsets differ by **>=100ms**,
the report exposes `stereo_channel_onset_gap_ms` and
`stereo_channel_onset_skew_risk` and warns
`stereo_channel_onset_skew_inspect` on either baseline or candidate.
This can catch a short missing-channel opening (<20% of audible RMS
windows) that the sustained partial-channel-loss checker deliberately
ignores. Mono, fully silent and indefinitely silent single-channel
inputs report a null gap instead of inventing an onset time; the
existing missing-channel warning continues to cover such cases.

The 100ms threshold is a **human-inspection heuristic**, not a beatgrid
measurement, downbeat synchronization, technical proof of an error or
musical taste. An intentional stereo entrance or creative asymmetric
fade may trigger it. The report never contains individual sample
positions, signal waveforms, private source paths or listening answers.


### Across-trial stereo swaps are also repeated blind references

The neutral listener pack validator compares *all* public A/B PCM variants
across distinct trials to find a repeated baseline that reviewers can learn
to recognise. This check now also treats an **exact left/right stereo
channel swap** in a later trial as repeated playback material. Its private
streaming fingerprints include sample rate, channel count and frame count;
changing playback speed does not produce a false match. Ordinary mono files
have no stereo-swap fingerprint. Reuse of A and B within the same trial
remains covered by the separate within-trial comparison.

The report adds only the existing aggregate
`cross_trial_repeated_variant_count` and the neutral trial-level warning
`repeated_pcm_across_trials_inspect_blinding`. It intentionally does **not**
disclose which trial, A/B side, baseline role or earlier reference matched,
nor any fingerprints or source paths. In strict mode this warning continues
to block promotion until the blind study design is independently checked.

A creative channel swap can be intentional, but repeatedly exposing an
identifiable audio excerpt across trials may compromise the listener's
blind assignment. This check supplies technical synthetic evidence only,
not real-listener validation.


### Public listening pages must not hide answer keys in opaque markup

The default static public-review HTML parser now rejects **all HTML
comments**, processing instructions, CDATA/unknown marked declarations,
and noncanonical document declarations. These constructs can carry hidden
A/B assignments, source track names, external document-system identifiers
or other unreviewed metadata while the page still contains the right
`trial-###-A/B.wav` links. The only accepted declaration is the normal
`<!doctype html>` (case insensitive); the official MixLab generated
listening form remains compatible and contains no such comments.

Rejected payload text is never quoted back by the sanitized CLI.
This is a **fail-closed public artifact hygiene check**, not a claim that
the rest of an arbitrary listener page's text, CSS or inline JavaScript
is safe. Frozen studies should also require the exact official generated
HTML, public receipt binding, source-rights audit, and human browser
review before collecting preferences.
