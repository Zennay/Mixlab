# Blind evaluation tooling

After listeners download their existing review-page JSON, run:

`python3 -m mixlab.evaluation /private/pack /private/ratings/listener-*.json`

Aggregation verifies the pack identity against the private answer key and render hashes, re-hashes all listening files, requires complete coverage, rejects repeated reviewers (case-insensitive), duplicate/foreign trials and foreign pack IDs. Ties and both-unusable votes have explicit counts and are excluded from decisive preference denominators. Counts are grouped by pair **and candidate family**, avoiding misleading pooling across alternatives. RMS confounds are rescanned from the bound audio.

The existing four-family pack is exploratory: comparing three candidates per pair is not the frozen one-candidate pilot in architecture.md. No output automatically passes M1, and synthetic votes remain software tests. Before a pilot: select one candidate per pair without seeing evaluation responses, use real partitioned permitted audio, resolve loudness confounds, collect at least three distinct real listeners, record audible defects and perform independent review. The CLI cannot verify that three pseudonyms are three people.

Do not publish source audio, private answer keys, raw reviewer identities or source paths. Share only the neutral review directory with authorized listeners. No listener data has been collected in this implementation.

## Freezing the pilot study (before any ratings)

`python3 -m mixlab.evaluation.study freeze /private/study/candidates.json /private/study/study.json --pairs 8` selects 5–10 pairs from tracks declared `"split": "evaluation"` only. Candidate schema v1: `{"schema_version": 1, "tracks": [{"id", "sha256", "bpm", "key", "key_source", "split", "rights"}]}`. `key_source` is `manual`, `measured-heuristic` or `unavailable` (then `key` is null); a recording hash may appear only once. Selection is seeded hash order (the seed is drawn and recorded when omitted), stratified half harmonically compatible (Camelot distance ≤ 1) and half contrasting/unknown. That keeps the study representative rather than flattering. Each track is used at most twice by default. Pairs need equal BPM unless `--tempo-tolerance-percent` is set, and those pairs are labelled `renderable_without_stretch: false`, because the current renderer does not time-stretch. Each pair gets exactly one preselected candidate family, balanced across `bass_swap`, `echo_exit` and `hard_cut`, for comparison with the equal-power baseline. The study manifest records the candidate-file hash, a hash of the development track IDs and a `study_id` over all content. It is written exclusively (never overwritten). `verify` recomputes the identity and re-checks reuse and family balance.

The frozen study is a selection, not a result. Rendering and pack generation from it, loudness matching, and at least three real listeners remain required before any preference claim. Measured-heuristic keys must be confirmed by a human before the study is used.
