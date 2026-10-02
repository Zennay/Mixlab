# Foundation execution evidence

## Initial proof — 2 October 2026

- Tested commit: `f089e0ddfc22347b7ccb08f88c5dfa6ec12663cf`.
- [VPS workflow run 36994858704](https://github.com/Zennay/zCloud/actions/runs/36994858704): **success**.
- Runner: `zcloud-vps-1`, host: `vps-bb300bba`.
- 17 unittest cases passed in 7.403 seconds.
- Synthetic end-to-end proof: 4 renders, 3 blinded comparisons, 6 neutral-named WAVs.
- Total proof duration: 11.949 seconds; maximum child-process RSS: 62,876 KiB.
- One-CPU affinity and lowered priority were applied by `ops/prove.py`.
- [Sanitized artifact 11220969408](https://github.com/Zennay/zCloud/actions/runs/36994858704/artifacts/11220969408), ZIP SHA-256 `4d14b51389131e8439f7941f4da16c650b296fc8cbb90840c8d82a7ff91bc752`.
- The same successful run received SQLite confirmation for queue ID `zssh-mixlab-foundation-integration-20261002`, project `zssh`, status `queued`. This is a registration/integration handoff, not proof of deployment or an active MixLab worker.

Evidence scope is synthetic foundation engineering only. This does not prove maximum-size memory use, real-music quality, completed MIR/stem analysis, listener preference, deployed zCloud project registration, or M1 completion. Artifact retention is 14 days; immutable commit/run references and this sanitized record preserve the key evidence.

Follow-up changes bind ratings to pack IDs and reject malformed recipe values earlier. Those changes require a separately pinned execution before being described as tested.
