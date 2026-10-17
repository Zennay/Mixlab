# ML-07 frozen-study / listener-pack binding preflight

This isolated, standard-library QA gate checks **private pinned metadata consistency** before a frozen study reaches listeners. It adds no new audio renderer, blinding algorithm, network access or main quality parser edits.

## Scope

1. The operator provides an **expected study ID previously saved outside the pack**; the frozen study JSON must hash canonically to exactly this ID.
2. **Only private evidence** must carry that same ID. The canonical v1 public receipt MUST OMIT `study_id` and all other private study provenance, matching the strict public quality allowlist. Forging a private `study_id` is detected against the external pinned commitment despite the legacy `pack_id` remaining unchanged.
3. The existing private verify_pack validates every real PCM16 review WAV checksum against the frozen render records and answer key.
4. Every frozen study pair maps to exactly one A/B trial and two recorded render families (baseline plus one preselected candidate); source hashes, source BPM and recipe family must agree with the preregistered rows, and no extra or duplicated pair may appear.
5. A valid frozen *protocol* also requires a strict integer `max_track_uses` (1–4), an actual track-use count within that limit, balanced candidate-family assignment (max difference 1 across bass_swap/echo_exit/hard_cut), one stable source hash per track ID and no source SHA reused under a different track ID. These gates execute before private PCM scanning and reject even self-consistently rehashed, otherwise plausible malformed studies.
   Existing renderer compatibility is also required: every pair's `renderable_without_stretch` must be the actual JSON boolean `true` and the declared source tempos must match exactly. The current M1 renderer cannot time-stretch a mismatched pair. The *actual recorded render recipe* must independently declare the identical effective `bpm` (strict finite number), `beats` must be a true JSON integer from 1 to 64 with rendered duration no greater than 120 seconds, `a_start` and `b_start` must be finite nonnegative numbers, and `gain_db` must be a finite numeric attenuation in [-60, 0] dB; merely agreeing about two `a_bpm`/`b_bpm` source claims is insufficient. These checks also reject forged recipe metadata outside the old `pack_id` hash. **A/B comparison fairness additionally requires the baseline and the selected candidate of each frozen pair to share identical BPM, beats, source start offsets, gain and declared source tempos.** If any one side claims different timing, duration, alignment or gain, the pair is rejected before PCM admission, even when both recipes are individually legal and the old pack ID still verifies. Self-consistently rehashed unsupported pair metadata is rejected before private WAV reads.
6. The result includes only anonymous counts and explicit false claims for rights validation, original audio authentication, human preferences and milestone success.


Usage (private environment; supply the ID from your separately retained preregistration):

    python3 -m mixlab.quality.study_binding /private/study/study.json /private/packs/frozen-pilot --expected-study-id <64-lowercase-hex-id>

Success is descriptive only. Invalid or missing inputs exit 2 with a path-redacted error.

## Limitations and other ownership

**This is not a cryptographic attestation of source audio.** The original pack_id does not bind study selection, claimed original source hashes or recipe metadata. An adversary can forge self-reported provenance and recompute unsigned values; the separate pinned study commitment and independent source/rights validation remain necessary. Never use the untrusted pack's own study ID as your expected independent anchor.

The independent frozen-study and all claimed per-render metadata contracts (chosen family, ordered source SHA, global/source BPM and beats) are now rejected **before any private PCM scan**. The existing bounded `verify_pack` then validates the actual WAV bytes against their declared digests, and the returned render metadata must still equal the pre-scanned snapshot. This avoids unnecessary CPU/disk reads for clearly invalid private packs and rejects persistent metadata drift between the two reads. It is not an atomic filesystem transaction.

The existing JSON and PCM admissions are bounded but do not guarantee immutable hostile storage or defeat all TOCTOU/ancestor symlink attacks. This preflight is not a substitute for the separately owned public review gate inspect_review_pack(require_receipt=True, require_generated_html=True). The current [ML-05 frozen study PR #71](https://github.com/Zennay/Mixlab/pull/71) uses a v1 public receipt **without** `study_id` and keeps the frozen study commitment in private evidence only. Previously, #71 emitted a public study ID and failed the strict review allowlist; this issue was reproduced and later fixed by the #71 owner. The private QA gate now rejects an injected public `study_id`, while demanding the independently pinned ID in private evidence. Both the true private pack and `inspect_review_pack(require_receipt=True, require_generated_html=True)` are checked together in hosted CI against upstream #71 commit `d6d573d234739a706d035dd0b8c704d2ea0c1958`. If #71 changes, update the pinned upstream commit and rerun the compatibility gate before merging; do not silently accept an unreviewed new source.

All unit tests are synthetic 5-pair PCM16; there is no private/music upload, no real A/B preference evidence, and no verified licensing. M1 remains open pending original tracks/analysis, actual pre-frozen study with 3+ independent human reviewers, perceptual loudness control and integration review.

Refs: MixLab issues #5/#7, frozen-study PR #71, previous provenance fix #78 and canonical Notion handoff.
