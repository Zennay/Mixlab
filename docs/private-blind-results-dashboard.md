# Private offline results dashboard for a frozen M1 listening study

The existing `mixlab.evaluation` command verifies the original, locally held PCM16 A/B files, their immutable pack ID and the downloaded ratings for every frozen trial. `mixlab.pilot_report` adds a **read-only, private, accessible HTML operator view** of precisely that preexisting aggregate. It does not replace the statistical protocol or human audit, and it never claims an M1 pass.

## Create after authorized reviewers have completed their listening

Keep the complete private pack and all reviewer rating files with the study operator. Never copy the private `answer-key.json` or this operator-only report to blinded listeners.

~~~bash
python3 -m mixlab.pilot_report \
  /private/m1/blind-pack \
  /private/m1/first-private-results.html \
  /private/ratings/response-01.json \
  /private/ratings/response-02.json \
  /private/ratings/response-03.json
~~~

The report includes the cryptographically bound `pack_id`, number of distinct **reviewer pseudonyms**, comparison count, baseline/candidate/tie/both-unusable totals, decisive candidate preference percentage, per-pair family results and automated PCM/loudness warnings. Invalid, duplicate, incomplete, wrong-pack or tampered ratings are rejected by the existing verified aggregation before publication. No reviewer pseudonyms, raw ballots, input filenames, local music paths, WAV bytes, answer-key objects, browser scripts, external URLs or analytics are copied to the HTML. All untrusted labels are HTML-escaped. The file is created exclusively (`0600`) outside Git; existing output files cannot be overwritten and nothing is sent over a network.

The HTML is responsive for small screens, uses a real table with row labels and textual counts alongside visual bars, and requires no external assets. It retains all key limitations even when the candidate preference share appears high. A reviewer code cannot prove a distinct person; the current source-rights declarations and musical correctness still need independent verification. A synthetic demonstration or three generated ratings files must **never** be reported as three human listeners or successful musical research. Full M1 acceptance additionally requires permitted real recordings, musical analysis/stems as scoped, genuine blind listeners, real defect notes and Auditor OS signoff.

For raw verified aggregates use `python3 -m mixlab.evaluation PRIVATE_PACK RATING_1.json ...`; for the end-to-end audio preparation, use `python3 -m mixlab.study_wizard` and [the private guided pilot workflow](guided-private-m1-pilot.md).
