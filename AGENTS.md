# MixLab worker contract

Read canonical Notion HQ/handoff linked in README, open issues/PRs and current GitHub main before selecting a task. Continue the M0/M1 Transition Lab critical path. Rendered audio and human evidence determine progression.

- GitHub: Zennay/Mixlab. Notion documents decisions. zCloud VPS SQLite is the live queue and claim source.
- Acquire and renew the existing zCloud project/task lease before shared-project writes once registered. On scope conflict choose another ready, disjoint task. Never steal or silently override an active claim.
- Use isolated branches and exact file scopes in docs/worker-plan.md. A single integration owner controls shared models, CLI, README and workflows. Contract edits require scope transfer; no parallel edits to the same files.
- Start with one MixLab write worker and one bounded render/test process. Do not change portfolio worker counts or other projects' CPU allocations.
- All shell, tests, builds and renders run through the self-hosted VPS runner vps-bb300bba. No direct SSH dependency. Record workflow_run_id, tested commit, conclusion and sanitized artifact hashes.
- No paid services, GPU jobs, model downloads, public music/lyrics uploads or externally exposed service in M0. Keep private media outside the checkout and evidence upload paths.
- Never label manual BPM/downbeat input as an analysis model, synthetic smoke evidence as listener proof, or a code commit as a completed M1 milestone.
- Preserve immutable benchmark manifests and private answer keys; prevent track leakage between tuning and final evaluation.
- A blocked data/listener step does not stop independent tooling work. Commit a coherent slice, verify it at the available level, update handoff with exact evidence and release its lease.

OS responsibilities: Genesis owns architecture/infra boundaries; Company owns scope and current bottleneck; Senior Team owns implementation; a separate Auditor checks evidence before milestone closure.
