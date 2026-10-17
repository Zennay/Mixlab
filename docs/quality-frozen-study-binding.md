# ML-07 frozen-study / listener-pack binding preflight

This isolated, standard-library QA gate checks **private pinned metadata consistency** before a frozen study reaches listeners. It adds no new audio renderer, blinding algorithm, network access or main quality parser edits.

## Scope

1. The operator provides an **expected study ID previously saved outside the pack**; the frozen study JSON must hash canonically to exactly this ID.
2. The public receipt and private evidence must carry that same ID. Forging both copies no longer passes this optional QA check, even though the legacy pack_id remains unchanged.
3. The existing private verify_pack validates every real PCM16 review WAV checksum against the frozen render records and answer key.
4. Every frozen study pair maps to exactly one A/B trial and two recorded render families (baseline plus one preselected candidate); source hashes, source BPM and recipe family must agree with the preregistered rows, and no extra or duplicated pair may appear.
5. A valid frozen *protocol* also requires a strict integer `max_track_uses` (1–4), an actual track-use count within that limit, balanced candidate-family assignment (max difference 1 across bass_swap/echo_exit/hard_cut), one stable source hash per track ID and no source SHA reused under a different track ID. These gates execute before private PCM scanning and reject even self-consistently rehashed, otherwise plausible malformed studies.
6. The result includes only anonymous counts and explicit false claims for rights validation, original audio authentication, human preferences and milestone success.


Usage (private environment; supply the ID from your separately retained preregistration):

    python3 -m mixlab.quality.study_binding /private/study/study.json /private/packs/frozen-pilot --expected-study-id <64-lowercase-hex-id>

Success is descriptive only. Invalid or missing inputs exit 2 with a path-redacted error.

## Limitations and other ownership

**This is not a cryptographic attestation of source audio.** The original pack_id does not bind study selection, claimed original source hashes or recipe metadata. An adversary can forge self-reported provenance and recompute unsigned values; the separate pinned study commitment and independent source/rights validation remain necessary. Never use the untrusted pack's own study ID as your expected independent anchor.

The existing JSON and PCM admissions are bounded but do not guarantee immutable hostile storage or defeat all TOCTOU/ancestor symlink attacks. This preflight is not a substitute for the separately owned public review gate inspect_review_pack(require_receipt=True, require_generated_html=True). At the time of implementation ML-05 draft PR #71 writes a public study_id that the current ML-07 receipt allowlist rejects; coordinate the owner-only compatibility fix before distributing any review pack. This tool deliberately does not bypass that check.

All unit tests are synthetic 5-pair PCM16; there is no private/music upload, no real A/B preference evidence, and no verified licensing. M1 remains open pending original tracks/analysis, actual pre-frozen study with 3+ independent human reviewers, perceptual loudness control and integration review.

Refs: MixLab issues #5/#7, frozen-study PR #71, previous provenance fix #78 and canonical Notion handoff.
