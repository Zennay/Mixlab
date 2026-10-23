# ML-07 · all-four-gates integration QA on one frozen study

This is a **test-only integration check** for the four independent opt-in
quality diagnostics already merged in PR #88 (pre-rating side allocation),
#90 (whole frozen pair omission), #91 (whole reviewer omission), and #92
(post-rating A/B button response). No production implementation, quality
thresholds, worker schedules, renderer, evaluator or licensing data changes.

The gates all rely on one genuine 5-pair/10-WAV original *procedural*
PCM fixture with a checksum-bound frozen private answer key, receipt,
external SHA-256 study ID and synthetic reviewer ballots. This suite
independently invokes each public QA function with the very same frozen
study and PCM, rather than substituting a mocked acceptance function.

### What the regression establishes

- **Unanimous candidate votes:** all four modules accept the same
  unchanged PCM-bound synthetic pack, produce only anonymous reports
  and always deny M1 approval. Five candidate-favored pairs give a
  *conditional* fair-sign reference of 1/32, degrading to 1/16 upon
  deleting a whole pair, while reviewer jackknife is stable.
- **All A-button votes:** 3 valid synthetic reviewer files always
  select A; the post-rating position diagnostic emits its expected
  methodological warning. This is not a fraud finding.
- **One influential reviewer:** 8/15 candidate votes become 3/10
  after deleting one complete rater, so reviewer influence correctly
  requires review without contradicting source/PCM verification.
- **Corrupt PCM:** physically mutating a sample of the frozen WAV
  makes *all four* independent gates refuse the pack.
- **Wrong externally pinned study:** the three study-binding gates
  reject an incorrect expected SHA-256 ID; the post-rating button
  gate is deliberately different and validates against the pack ID
  through the official aggregator, not an external study ID.
- **Immutability and privacy:** all four complete successfully
  without rewriting the frozen answer key, receipt or evidence;
  public reports contain no path, reviewer pseudonym, private
  answer, output hash or trial identifier, and always report
  `milestone_pass: false`.

The workflow covers Python 3.13/3.14 at exact triggering SHA with
a 192MiB virtual-memory cap. It runs the original standalone
component suites **as well as** the combined end-to-end test, so
otherwise individually green changes are less likely to silently
break another quality gate.

These are procedural computer-generated recordings and scripted votes.
No real human audition, authenticity of individual listeners,
permissions for 20–50 real songs, measurable DJ quality uplift or
statistical inference is established. This remains **M1 OPEN**.

The workflow is safe on GitHub-hosted runners; it never requires
production VPS SSH, zCloud queues, or any permission expansion.
