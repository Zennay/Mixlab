# MixLab Energy Journey — private local playlist planning

MixLab M1 currently requires a **human-confirmed, same-BPM playlist**, explicit source rights and real transition cues. The Energy Journey Planner removes the repetitive work of deciding track order *after* you've annotated your permitted music. It does **not** infer BPM, mood, key, phrase, downbeats, track compatibility or preference from audio. It does not replace the original M1 listener gate.

## Workflow: subjective energy → editable order → genuine full-set WAV

Use a local folder **outside Git** containing 2–20 supported private music files (WAV; existing FFmpeg/FFprobe is required by Studio for compressed imports). Paths below are examples; use new output files for every run.

**1. Make private human annotations.**

~~~bash
python3 -m mixlab.journey notes /private/music /private/music/energy-notes.private.json
~~~

Select song numbers; manually enter the actual BPM (30–300), subjective energy (1–10), and optional lowercase comma-separated genre/mood tags for each. Each selected recording gets a content SHA-256 in the private notes file. Reading files for hashes is local; it does not decode, upload or alter them. The notes JSON is newly created with mode 0600 and can be edited only as private source data.

**2. Suggest a journey** from those exact checked notes:

~~~bash
python3 -m mixlab.journey plan \
  /private/music \
  /private/music/energy-notes.private.json \
  /private/music/build-plan.private.json \
  --tracks 5 --shape late-peak --prefer-tag house
~~~

Shapes: `build` (gentle to energetic), `release` (high-energy to calm), `peak` (mid-set climax), `late-peak` (build to a late climax then ease). Optionally restrict to one human-confirmed BPM with `--tempo 120`.

The planner groups songs by **exact human-confirmed BPM**; it **never auto-stretches audio**, merges incompatible tempos or invents tags. It uses bounded beam search (192 candidates per step, at most 20 annotated songs, at most 11 selections), minimizing squared target-energy mismatch and abrupt jumps with a small optional tag preference. This is a deterministic heuristic for **creative suggestions**, not a measured transition-quality or listener-preference model. The planner refuses insufficient same-tempo candidates. Proposed filenames, hashes, tags and order stay private.

**3. Review and rearrange in an offline browser**, if desired:

~~~bash
python3 -m mixlab.journey_board \
  /private/music \
  /private/music/build-plan.private.json \
  /private/music/journey-board.private.html
~~~

Open `/private/music/journey-board.private.html` locally (no network, no player/audio loads). The solid energy line shows the selected tracks; the dashed line shows the chosen target curve. The up/down buttons change order without touching existing files. **Export my ordered set** downloads a *new* `mixlab-journey-curated.private.json`. Move it into the same music folder before proceeding. This downloaded file remains an **unapproved proposal**.

**4. Approve the idea and render an actual private full set**:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-approved-playlist.private.json \
  /private/my-mixlab-session \
  --journey-plan /private/music/mixlab-journey-curated.private.json \
  --beats 16 --full-set-wav /private/my-event-mix.wav \
  --family bass_swap \
  --delivery /private/my-event-mix.mp3 --bitrate-kbps 192
~~~

You may use `build-plan.private.json` directly without rearranging. The Studio reopens and rehashes **every chosen local recording**, verifies matching declared BPM and the planner schema, displays the energy route, and asks **Accept this exact suggested order? Type yes**. If rejected, it creates **no source manifest**. Even after approving, Studio separately asks for verified downbeat if available, **source rights + provenance** for every track, and exact outgoing/incoming A/B start seconds for every transition. The existing canonical renderer and hash/rights gates continue unchanged.

For staged operation, add `--manifest-only`; later render the exact immutable approved playlist with `--resume` (without `--journey-plan`). Optional MP3/FLAC is decoded/encoded only through already-installed local FFmpeg, and optional delivery failure leaves the master WAV and Studio.

## Boundaries and safeguards

- All notes, plans and offline HTML must be **new files directly inside the private music folder**. Existing paths, symlinks, Git checkouts, oversized planning JSON and source mutations are refused. Private outputs use mode 0600; files never go into repository commits or online study artifacts.
- Plans are bound to SHA-256 recordings and checked *again* immediately before Studio's manual cue stage. If a source changed, regenerate notes and create a new plan. A filename is not a substitute for source-rights proof.
- You may edit source JSON locally or adjust the browser order, but any resulting energy shape is a **human proposal**. Neither a numerical objective cost nor a pleasing SVG curve establishes professional DJ quality.
- Not supported: different-tempo pairs, automatic BPM/downbeat/phrase/key inference, stems, lyrics or set-level human preference claims. Those remain separate M1/M2+ milestones. No production deployment, VPS renderer or hosted media service is part of this feature.

## Files/entry points

- `mixlab/journey.py`: private human notes, same-BPM bounded planner, checksum-bound proposal loading.
- `mixlab/journey_board.py`: static offline plan editor and private JSON export.
- `mixlab/playlist_studio.py --journey-plan`: explicit user acceptance and authoritative existing Studio rendering.
