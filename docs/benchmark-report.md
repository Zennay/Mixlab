# Blind evaluation tooling

After listeners download their existing review-page JSON, run:

`python3 -m mixlab.evaluation /private/pack /private/ratings/listener-*.json`

Aggregation verifies the pack identity against the private answer key and render hashes, re-hashes all listening files, requires complete coverage, rejects repeated reviewers (case-insensitive), duplicate/foreign trials and foreign pack IDs. Ties and both-unusable votes have explicit counts and are excluded from decisive preference denominators. Counts are grouped by pair **and candidate family**, avoiding misleading pooling across alternatives. RMS confounds are rescanned from the bound audio.

The existing four-family pack is exploratory: comparing three candidates per pair is not the frozen one-candidate pilot in architecture.md. No output automatically passes M1, and synthetic votes remain software tests. Before a pilot: select one candidate per pair without seeing evaluation responses, use real partitioned permitted audio, resolve loudness confounds, collect at least three distinct real listeners, record audible defects and perform independent review. The CLI cannot verify that three pseudonyms are three people.

Do not publish source audio, private answer keys, raw reviewer identities or source paths. Share only the neutral review directory with authorized listeners. No listener data has been collected in this implementation.
