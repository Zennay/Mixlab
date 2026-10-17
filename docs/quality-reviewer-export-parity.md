# ML-07 — reviewer export / rating-ingest parity gate

The official MixLab review generator currently outputs a reviewer input with required and maxlength=40, but no browser pattern. The Python aggregator requires an ASCII-only 1–40 character pseudonym with first character alphanumeric and subsequent alphanumeric, underscore or hyphen. A browser accepts e.g. "listener 01" or "équipe" but the aggregator refuses them. This can invalidate completed blind-review responses.

## Independent QA addition

Command: python -m mixlab.quality.reviewer_export_parity /private/pack/review/index.html

The validator is bounded (1 MiB), nofollow, read-only and path-redacted. It never returns audio, raw HTML, reviewer identities, source names, hashes or trial IDs.

- Exit 0: static field contract matches browser-safe HTML5 reviewer pattern, required input and maxlength=40, with no obvious native-validation bypass.
- Exit 3: HOLD, including current official generated HTML because its reviewer input is too permissive.
- Exit 2: invalid arguments or unreadable/unsafe input, with redacted diagnostics.

The HTML pattern is [A-Za-z0-9][A-Za-z0-9_\-]{0,39}; the escaped hyphen matters for modern browser UnicodeSets v-mode regex. This is only a STATIC field check. It does not execute JavaScript or prove browser validation, screen-reader accessibility, identity independence, rights, audio or actual preference. It does NOT replace inspect_review_pack(require_generated_html=True, require_receipt=True) or the composed PR #84 gate.

## Integration ownership and repair

The shared mixlab.cli.write_review() and mixlab.evaluation.aggregate() belong to other scopes. This PR intentionally does not edit them.

After lease/scope coordination, the integration owner should: (1) add the browser-safe pattern and understandable reviewer guidance to the canonical generated form, without silently rewriting IDs; (2) coordinate the official HTML exact-byte check and PR #84 template allowlist; (3) run real headless browser valid/invalid inputs and download assertions; and (4) round-trip a valid synthetic ratings export through the real aggregate() at the exact SHA.

The dedicated hosted CI uses only synthetic text and Python 3.13/3.14 with an explicit memory cap. No private audio, VPS worker, queue, service, deployment or shared module is touched. This gate cannot close M1: 20–50 rights-safe tracks, measured beat/key, a frozen 5–10 pair study and at least three independent listeners remain necessary.
