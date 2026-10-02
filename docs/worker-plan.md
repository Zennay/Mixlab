# Worker continuation plan

Status: executable work-package definitions, not claims that these tasks have been inserted into the live queue. The integration owner should map each ID into zCloud's VPS SQLite queue. Notion is documentation and evidence only. Read the repository's current files before extending them; the scopes below define future ownership, not proof that every named module already exists.

## Operating contract

One worker owns each active task and file scope. Claim a task through the existing zCloud lease mechanism; use the actual queue API/schema after inspecting it, never invent a SQL mutation. Use an isolated branch/worktree. Shared schema, README, dependency files and CI are owned by the integration owner unless explicitly handed over. Parallel work is allowed only for disjoint scopes after dependencies are satisfied. Keep leases alive through existing orchestration, and release with evidence or an honest partial state. Commit and test execution use the established repository and VPS runner routes.

Company OS owns scope and milestone decisions. Product/DJ Systems and DSP/MIR roles make musical and implementation decisions. Data/Governance owns provenance. QA/Evaluation owns blind review. Auditor OS checks claims against immutable evidence; it does not accept a worker's self-reported green status as independent proof.

## Work packages

| ID / role | Scope owned | Dependencies | Acceptance criteria |
| --- | --- | --- | --- |
| ML-01 · Platform/zSSH | `.github/workflows/`, `ops/`, `docs/infra-evidence.md` | Foundation commit | Dispatch baseline checks on the intended runner; record run ID, SHA, final conclusion, peak RSS and duration; execute one synthetic render; no real-audio uploads; prove CI serialization and document pending-run reconciliation. Proposed resource budget becomes measured or remains explicitly unverified. |
| ML-02 · Data/Governance | `mixlab/ingest.py`, `schemas/library.schema.json`, `tests/test_ingest.py`, `docs/dataset-manifest.md` | Stable core schema contract | Validate local permitted source manifest, unique IDs, supported audio formats, duration/segment bounds and provenance. Reject absent/unknown permission declaration. Keep media outside checkout. Define a private 20–50-track manifest and dev/evaluation split; if tracks are unavailable, finish validators and leave dataset gate open. Coordinate package-path adjustment with integration owner. |
| ML-03 · DSP/MIR | `mixlab/analysis/`, `tests/test_analysis.py`, `docs/adr/analysis-provider.md` | ML-02 | Define replaceable beat/downbeat/phrase/key interfaces with confidence and manual-vs-measured provenance. Evaluate dependency candidates in an ADR before installs. Provide reference annotations and measured error outputs if an approved provider is available. Stubs/manual metadata do not close analysis acceptance or M1. |
| ML-04 · Audio DSP | `mixlab/dsp/`, `tests/test_dsp.py`, `docs/adr/renderer-quality.md` | Baseline renderer and ML-01 measurements | Harden supported renderer behavior for stereo, segment edges, gain and delay tails. Test invalid input rejection and deterministic PCM hashes. Document unsupported tempo/key transformations and absence of stems. Include real private listening checks before making sound-quality claims. Any core renderer edits require an explicit scope transfer from integration owner. |
| ML-05 · QA/Evaluation + DJ | `mixlab/evaluation/`, `tests/test_evaluation.py`, `docs/benchmark-report.md` | ML-02, baseline review-pack contract; analysis deliverables for full M1 | Freeze 5–10 evaluation pairs/recipes and review protocol before ratings. Validate stable randomization, key separation, no duplicated votes and tie handling. Gather at least three listeners; report raw counts, per-pair outcomes and loudness confounds. Publish only non-sensitive aggregate results. No listeners/data means benchmark tooling may finish, benchmark proof remains open. |
| ML-06 · Auditor/Company OS | `docs/milestone-audit.md`, Notion handoff mirror | ML-01–ML-05 evidence as available | Independently inspect commit/run/artifact linkage, test conclusions, dataset permission declarations and blind preference computation. State each original M0/M1 requirement as evidenced, partial or missing. Complete M0 only with reproducible renderer evidence; do not close M1 without original analysis/stem deliverables and real-audio human proof, or an explicitly approved roadmap revision. |

Scope names may be adjusted once to fit the initial package layout before tasks are claimed. Do not create a second competing package tree simply because this plan uses a different path. ML-03 and ML-04 can run in parallel only after shared interfaces are frozen. ML-05 tooling can begin while audio work proceeds; final review must use pinned candidates. ML-06 may audit partial progress without marking incomplete gates done.

## Required evidence per task

Record task ID, owner, scope, branch/commit, files changed, acceptance criteria met/open, workflow run ID and final conclusion if executed, relevant artifact hashes, and next dependency. A missing run ID or unfinished listener benchmark must be visible. `DONE` applies to an evidenced task, not automatically to a milestone. `CONTINUE` requires a material change such as committed implementation, a real execution, or a concrete durable task dispatch; reading and planning alone do not qualify.

## Short continuation prompt

> Werk verder aan MixLab. Lees de actuele fase en handoff in Notion en controleer de repo. Claim de eerstvolgende vrije taak in de zCloud SQLite-queue en werk die concreet uit binnen je eigen bestandsscope. Gebruik de VPS-runner voor tests/renders; leg commit, run-ID en bewijs vast. Muziek blijft privé. Sluit M1 pas na echte audio en blinde menselijke voorkeurstests.

The infrastructure/worker contract carries detailed rules so the repeated prompt can remain short. Preserve project claims and non-overlapping file scopes in orchestration rather than sending long repeated instructions to workers.
