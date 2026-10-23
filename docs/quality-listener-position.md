# ML-07 · private post-rating A/B position consistency

**Scope:** an optional, offline *methodology* preflight run only after the
listening responses are locked. This is not a DJ score, psychological
assessment, fraud determination, approval to publish any recordings, or a
substitute for independent reviewers. M1 remains open.

The pre-rating frozen-study A/B side balance gate is in draft PR #88; this
module checks a **different** problem: response-side patterns in submitted
review JSON. A respondent can systematically prefer whichever audio button
is shown at A, irrespective of track identity. The official aggregation may
still count such votes as admissible: a valid reviewer file is not proof of
a thoughtfully listened rating.

## Actual guarantees and boundaries

- Uses the existing actual `mixlab.evaluation.aggregate()` to validate
  authenticated pack ID, WAV checksums, complete/unique trials, reviewer
  pseudonym grammar and duplicate-reviewer rejection.
- Refuses nonregular rating files, symlinked final **or ancestor** rating
  components, files over 64 KiB, content/name identity drift, and changed
  review files during real aggregation. Maximum 16 ratings files.
- Emits **no** private file path, answer key, pack hash, reviewer codes,
  per-trial choices, original audio or filenames. Output contains only
  reviewer count, trial count, number of decisive answers, and anonymous
  boolean-or-null methodological flags.
- Flags at least 80% aggregate A-or-B selection over at least 12 decisive
  votes from at least 3 reviewers; marks `null` if insufficient.
- Independently flags a reviewer with at least five decisive selections,
  of which >=80% use the same button; the public report includes only a
  boolean, no reviewer identity.
- The arbitrary 80% threshold is a **conservative review heuristic**,
  not a p-value, listener identity proof or assertion of cheating. Real
  preference can be strong and can correlate with randomized positions.
  False positives and negatives are expected. Always preserve the
  separately frozen A/B study design and evaluate real music blinded.

CLI:

```sh
python -m mixlab.quality.listener_position PRIVATE_PACK/ PRIVATE_RATING1.json PRIVATE_RATING2.json PRIVATE_RATING3.json
```

Exit 0: enough responses and no observed 80%-side pattern.
Exit 3: potential side-response pattern; seek methodological review.
Exit 4: insufficient evidence for a verdict.
Exit 2: inconsistent/unreadable/changed private material, with path-free
diagnostics. Every result has `milestone_pass: false`.

## Deterministic synthetic evidence

`tests/test_quality_listener_position.py` creates 5-trial PCM16 WAVs,
real checksum-bound private pack metadata and 3 distinct *synthetic*
complete reviewer JSON files using existing merged MixLab fixtures.
It calls the **actual production aggregator**, not a mocked acceptance
grammar. The suite covers a fully balanced side mix, 15/15 A selections,
mixed aggregate totals hiding individual always-one-side responders,
ties/unusable/low-evidence abstentions, invalid reviewer and pack IDs,
duplicate JSON keys, changing files during genuine aggregation, symlink
ancestor/final rejection and CLI exit codes/privacy.

No human actually reviewed audio, and synthetic votes do not establish
musical preference. Uploaded music, output recordings, real reviewer
identifiers, VPS work, queue changes and deployment are not part of this
scope. Python 3.13/3.14 GitHub-hosted workflow runs immutable trigger-SHA
source under a 192MiB virtual-memory cap.

## Ownership handoff

The QA integrator must only adopt this after the existing ML-05/ML-07
pack, browser/reviewer parity, and frozen-study position/rights gates
are coordinated. It is an optional explanatory diagnostic, not an
automatic disqualification of an individual. Don't use technical flags
as a proxy for source rights, human evaluation or M1 release approval.
