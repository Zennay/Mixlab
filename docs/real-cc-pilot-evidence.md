# Real-music pilot evidence — 27 October 2026

The first run of MixLab's analysis and blind-study tooling on **real, openly licensed dance music**, not synthetic fixtures. No audio, private paths or listener data are stored in this repository; only aggregate numbers follow.

## Library
- `python3 -m mixlab.sources.archive /private/library` fetched **100 tracks from 100 different artists** from Internet Archive netlabel releases.
  - The first 40 come from house/techno/disco subjects, sorted by identifier; the next 60 from house, tech house, deep house, progressive house and nu disco, sorted by downloads.
  - Only CC BY, BY-SA, BY-NC and BY-NC-SA licenses were admitted. ND and sampling licenses are rejected, because a transition is an adaptation.
  - Every download is checked against the archive SHA-1, and a 45 s PCM16 excerpt is cut starting one third into the track.
- License declarations are the uploaders' metadata (provenance), not a legal verification.
- ccMixter was evaluated first (it has artist-declared BPM), but it refuses scripted downloads (HTTP 403). That restriction was respected, not bypassed.

## Beat analysis on real audio (M1 question: "is beat analysis stable enough?")

| Provider | Answered on first 40 excerpts | Notes |
| --- | --- | --- |
| `energy-onset-v2` (existing) | **2 / 40** | Abstains on full mixes: hats, bass and pads swamp its single broadband envelope. |
| `kick-grid-v1` (new, `mixlab/analysis/kick.py`) | **26 / 40** | Low-band kick onsets, autocorrelation within 100–140 BPM, least-squares grid fit; abstains on irregular or sparse kicks. |

**Stability:** a second 45 s excerpt was taken from each track at 55 % of its length. On the 22 tracks where both excerpts produced a grid, the two tempos agree within **0.2 % in 22 / 22 cases**, mostly within 0.02 %. Estimates cluster on round production tempos (e.g. 123.006, 130.003, 133.000, 128.003). The fit residual for answered excerpts was 1.7–14.8 ms.

There is no human-verified reference: these are self-consistency results, **not accuracy against annotations**. Downbeats (`accent-phase-v1`) abstained on most real excerpts, so most pairs are aligned on beats, not bars.

## Pilot pack (`python3 -m mixlab.evaluation.pilot /private/library /private/pilot`)
1. Out of 100 tracks:
   - 39 had their tempo abstained;
   - 7 failed the post-conform re-measurement (±0.5 %);
   - 4 were dropped by the 50-track manifest cap.
2. The remaining **50 tracks** were conformed to an even-BPM grid with pitch-preserving ffmpeg `atempo`; the largest stretch was **0.82 %**. Tempo groups: 120 (12), 122 (7), 124 (5), 126 (13), 128 (4), 130 (3), 134 (2), 136 (3), 100 (1).
3. A seeded split put 39 tracks in evaluation and 11 in development. Keys were measured (`chroma-kk-v1`), and many abstained.
4. A frozen study of **8 pairs** (`study_id aa7f2d3a…`) was rendered as baseline versus one preselected family per pair: hard_cut ×3, echo_exit ×3, bass_swap ×2.
5. Gates:
   - `verify_study_pack`: OK;
   - ML-07 `verify_study_pack_binding`: OK;
   - ML-07 `inspect_review_pack(require_receipt=True)`: OK. Six of the eight trials carry technical "inspect for clicks/pops" warnings, spread across baseline and candidates; real transients and excerpt edges trigger them. `hard_cut` additionally shows level and gap warnings, which are inherent to a cut.

## What remains open
- **Human ratings:** the blind pack has been handed to the project owner. At least three distinct listeners are needed before any preference claim, and `milestone_pass` stays false until then.
- Loudness is still common gain, not LUFS-matched.
- Tempo, alignment and keys are machine proposals; no human verified them.
- The kick grid needs evaluation against human beat annotations (`python3 -m mixlab.analysis.benchmark`) before it is called accurate.
