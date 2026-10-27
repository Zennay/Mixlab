# Human key review before a frozen MixLab M1 study

A measured key is a **proposal**, not a human-confirmed annotation. The new offline `mixlab.study_key_review` command adds an explicit source-SHA-bound handoff between candidate import and irreversible pilot freezing. It never invents keys, reads listener ratings, verifies copyright permissions or uploads audio. The generated documents remain private and must stay outside Git.

## Workflow

1. Generate candidates from the verified private library using `python3 -m mixlab.evaluation.candidates /private/library/library.json /private/split.json /private/candidates.json --measure-keys`. All key estimates are labelled `measured-heuristic` and abstentions `unavailable`; already supplied `manual` keys are untouched.
2. Run `python3 -m mixlab.study_key_review prepare /private/candidates.json /private/key-review.json`. Every evaluation-split track without a manual key appears with its original source SHA-256, original estimate/source and `decision: "pending"`, `confirmed_key: null`, `human_checked: false`. Development-only tracks are not brought into this preregistration review.
3. **A person with authorization to handle the private recording must inspect the audio** and edit each review row: set `human_checked: true` and choose exactly one decision:
   - `"accept"`: set `confirmed_key` to the existing measured proposal exactly (permitted only if the estimate exists and was actually reviewed).
   - `"override"`: set `confirmed_key` to the independently confirmed key, e.g. `"D minor"`. All 12 chromatic major/minor names are supported.
   - `"unavailable"`: leave `confirmed_key: null` when the key cannot be verified or the estimate is rejected. This track remains in the unknown harmonic stratum rather than being given invented certainty.
4. Run `python3 -m mixlab.study_key_review apply /private/candidates.json /private/key-review.json /private/approved-candidates.json`. Every source identity, SHA, proposed key, source file hash and split is bound and checked; any pending decision, edited proposal, stale source or unapproved track **fails without publishing**. The new candidate file labels only human-approved keys as `manual`; it preserves all rights declarations and development/evaluation partitions. The previous candidate file is never overwritten.
5. Freeze **only the new approved file**: `python3 -m mixlab.evaluation.study freeze /private/approved-candidates.json /private/frozen-study.json --pairs 5`. Then use `python3 -m mixlab.study_alignment prepare|apply` for separate, human-confirmed source rights/cues before rendering with `mixlab.evaluation.study_pack`.

The worksheet records a person's declaration; software cannot independently prove the annotation or that a real reviewer was involved. Original M1 requirements for real permitted recordings, genuine cue approval, independent musical accuracy evidence, stems and at least three real blind listeners **remain open**. No user music, worksheets, hashes, raw ratings or audio should appear in public repositories or CI artifacts.
