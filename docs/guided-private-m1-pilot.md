# Guided, private M1 blind-pilot wizard

MixLab can now go from an existing **locally permitted PCM16 WAV library** and a separately preregistered development/evaluation split to a genuine five-to-ten-pair review audio pack in **one guided terminal interaction**. This is the offline human-in-the-loop M1 **product workflow**, not an automatic music licence, DJ judgment, perceptual benchmark result, audio-analysis validation or real listener evidence. Nothing is uploaded.

## Run

Use an unused private directory outside your Git checkout. Keep original audio and all intermediate private metadata out of Git, logs and public artifacts:

~~~bash
python3 -m mixlab.study_wizard \
  /private/music/library.json \
  /private/study/split.json \
  /private/new-m1-pilot --pairs 5 --seed 2
~~~

- The library's original local PCM16 WAVs must have valid hashes, BPM and source permission declarations; the split file must allocate every source to exactly one of `development` or `evaluation`, before preferences are collected. The renderer still requires equal tempo; no time-stretching or source separation is inferred.
- Optionally add `--manual-keys /private/study/keys.json` for independently annotated musical keys, or `--measure-keys` for the existing bounded local chroma heuristic, whose proposals **must be reviewed**. No model installation is performed. Sources with existing manually supplied keys are not silently re-reviewed. Evaluation tracks without manually verified keys prompt for `a` (accept a real measured proposal), `o` (manual override, e.g. `D minor`), or `u` (unknown). Each requires a separate typed `CONFIRM`. Unknown keys remain unknown; no guess is fabricated.
- For **each** preselected pair in its exact frozen outgoing/incoming order, listen to the original audio yourself, enter the independently verified number of transition beats and both cue start times in seconds, type `CUES-VERIFIED`, and explicitly declare permitted private source rendering by typing `PRIVATE-ONLY`. This text records your declaration: software cannot prove the actual permission or correctness. Do not type the confirmation if you do not have rights or are unsure of the cues.
- A new directory with mode `0700` contains the unreviewed and reviewed key forms, the SHA-bound approved candidates, the already frozen selection, and separate pending/confirmed cue forms. The new validated source library manifest is published as a distinct `.m1-<study-id>-<private-workspace-id>.json` next to the original source manifest so relative WAV paths remain correct. The workspace-bound suffix prevents an earlier attempt with the same study seed from blocking a second private session, while still refusing to overwrite a source manifest. Existing source audio/manifests/studies are **not overwritten**.
- Only after checking the real WAV bounds, exact hashes, source declarations and cue approvals can the renderer publish the private `blind-pack/` directory. The wizard then verifies all render hashes, matched-loudness A/B PCM and binding against the pre-registered study. It reports the verified `study_id`, `pack_id`, pack counts and status `private-pack-ready-not-listener-validated` but makes no preference or M1 success claim. A second session with the same frozen `study_id` is **not independent evidence**; it may have a different audio `pack_id` when cues differ, and reviewer responses must never be pooled across distinct pack identities.

Input library and split validation occurs before allocating a new private workspace, so missing or inconsistent source metadata does not create a stray directory. If a person cancels or any later step fails, the private work directory may retain **incomplete** forms, but it must not be treated as a shareable listening pack; finish only with an entirely **new** destination. Do not forward anything from `blind-pack/private/` (including the answer key). Existing blind listening review pages/ratings and aggregation remain the next **separate** step: at least three distinct real reviewers, permission/provenance checks, independent audit, and musical quality evidence are still required. In synthetic demos, scripted prompts are **not real human review or legal rights evidence**.

For the underlying individually controllable tools, see [candidate ingestion](benchmark-report.md), [key review](frozen-study-key-review.md) and [cue approval](frozen-study-human-alignment.md).
