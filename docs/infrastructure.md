# MixLab infrastructure plan

Status: proposed deployment and resource envelope, not an installed service or measured budget. Initial execution is an offline batch process on the existing `vps-bb300bba` GitHub self-hosted runner. No new public endpoint, database server, GPU service or perpetual worker is required for M0.

## Execution envelope

| Item | Initial policy |
| --- | --- |
| Compute | One MixLab render/test job at a time; proposed 1 CPU budget |
| Memory | Proposed 512 MiB soft operating target; measure peak RSS before accepting |
| Scheduling | Existing higher-priority workloads retain their allocation; yield or defer MixLab when capacity is unavailable |
| Runtime | Standard-library baseline; explicit supported Python version in CI |
| Network | No audio downloads, API calls or model installation during baseline tests |
| CI | GitHub Actions on self-hosted labels `self-hosted`, `zcloud`, `vps`, subject to runner label verification |
| Concurrency | One repository-wide execution group with `cancel-in-progress: false`; do not cancel active work |
| Output | Private WAV/JSON locally; GitHub receives code/test results and synthetic-only evidence |

GitHub concurrency prevents simultaneous execution in its group, but pending runs may be superseded. It is not the durable job queue. zCloud SQLite remains authoritative: a worker must reconcile a queued run's final state and retry an unexecuted task without claiming completion. Never infer success from dispatch acceptance.

A 512 MiB target is unproven for Python audio arrays and copies. Use short bounded segments first; measure peak RSS and elapsed time with realistic stereo inputs. If a job exceeds the target, reduce chunk sizes or record a justified budget change before expanding the workload. CPU affinity is not a utilization quota. Apply a tested cgroup/systemd limit only after the runner's permissions and host service setup are verified; never edit global runner limits blindly.

## Proposed private filesystem

These paths are a deployment proposal, not confirmation that directories exist:

| Path | Contents |
| --- | --- |
| `/opt/mixlab` | Versioned working checkout |
| `/var/lib/mixlab/source_media` | User-provided/permitted originals |
| `/var/lib/mixlab/metadata` | Provenance, manifests, source hashes |
| `/var/lib/mixlab/derived_features` | Analysis outputs keyed by input and analyzer versions |
| `/var/lib/mixlab/renders` | Private evaluation WAVs and render manifests |
| `/var/lib/mixlab/reviews` | Frozen listener packs, separate keys and ratings |

Use restrictive directory permissions for source, renders and reviews; log opaque track IDs rather than absolute private paths. Repository ignore rules are a convenience, not the only privacy control: CI uploads must allowlist synthetic outputs or non-sensitive metrics, and must not glob whole data directories. Keep source music outside the checkout so cleanup and branch changes cannot remove it.

## Runner job contract

Each execution request contains task ID, pinned commit/ref, named allowlisted operation, input manifest ID, output location and resource expectation. Validate any operator-supplied path; do not interpolate arbitrary user strings into shell commands. A successful job records task ID, commit, workflow run ID, exit status, durations, test counts and artifact hashes. Failures record a concise classified reason and bounded retries. Never include credentials or source audio in logs.

Dispatch acceptance means queued, not running or done. Completion requires the final GitHub run conclusion plus task-specific acceptance evidence. If the runner is unavailable, leave the request actionable in SQLite and continue independent code/document work. Notion mirrors outcomes; it does not acquire execution leases.

## Safe provisioning sequence

1. Verify runner availability/labels, checkout target and writable private data location through an existing authorized workflow.
2. Run code checks and the synthetic fixture in the single execution group; preserve run ID and output hashes.
3. Measure elapsed time and peak RSS for supported short mono/stereo inputs; confirm the envelope is realistic.
4. Add private directories and local data configuration only through an explicitly scoped zSSH task. No public ingress is needed.
5. Load permitted real tracks locally and run the frozen benchmark; listener access remains private.
6. Add repeatable jobs only when the manual recipe is sound. Use idempotent outputs keyed by input/recipe hashes and a lock per output ID.

No automatic ML, FFmpeg, source-separation or feature-library installation is part of this baseline. Future dependencies need an ADR covering license, CPU/RAM/disk cost, offline behavior, deterministic behavior and a measurable quality hypothesis. Service hosting, public sharing and catalog licensing are later decisions.

## Retention and recovery

Retain manifests, recipes, hashes and frozen review results; reproduce derived files where feasible. The first cleanup implementation must default to dry-run and operate only within a dedicated generated-output directory, never source media. Define a storage quota and retention period after measuring actual fixture/benchmark size. Back up metadata and ratings before cleanup; do not assume source-music backup or redistribution rights.
