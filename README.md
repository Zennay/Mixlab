# MixLab · Transition Lab

An offline AI-DJ research project: understand track segments, discover surprising combinations, render real transitions and eventually build full sets around context and an energy journey.

**Current phase: M1 — Transition Lab (OPEN).** MixLab now has a private real-music import route, a visual two-deck cue editor, a local transition Studio, a two-song full-length WAV exporter, a manual multi-song party-mix exporter, and a one-command playable synthetic DJ demo. These are creative product features, not proof of superior musical quality. Equal-BPM/manual-cue constraints remain. Automatic downbeat/phrase/key analysis, actual source separation, approved real-track listening evidence and blinded preference comparisons have **not** passed M1 gates.

- [Notion project](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
- [Current handoff](https://app.notion.com/p/3e79e19ac95581f4bf15c26a833da642)
- [Architecture and evaluation](docs/architecture.md)
- [Infrastructure plan](docs/infrastructure.md)
- [Worker tasks and ownership](docs/worker-plan.md)

## Probeer MixLab direct — geen muziekbestanden nodig

Er is nu een **volledig lokale, luisterbare DJ-productdemo**. Deze maakt twee
originele synthetische 120-BPM-nummers, genereert vier echte
overgangsvarianten en een complete twee-track-mix, plus een visuele
cue-editor. Er worden geen beschermde muziektracks, modellen of
externe diensten gedownload; voor deze WAV-demo is geen FFmpeg nodig.

~~~bash
python3 -m mixlab.demo /private/mixlab-demo-01
~~~

Open vervolgens **/private/mixlab-demo-01/index.html** in je browser.
Gebruik een nieuwe directory buiten je Git-checkout. De
synthetische productdemo is géén bewijs voor echte muziekkwaliteit of een
geblindeerde gebruikersstudie. Zie [de demo-handleiding](docs/offline-dj-demo.md).

### Eigen muziek: van nummers naar echte DJ-overgang

MixLab kan privé en lokaal eigen toegestane MP3/FLAC/M4A/WAV verwerken,
cues visueel laten goedkeuren en een volledige mix exporteren.
Gecomprimeerde audio vereist bestaande FFmpeg/FFprobe; 44,1 kHz PCM16-WAV
werkt ook direct met de Python-standaardbibliotheek.

~~~bash
python3 -m mixlab.project_wizard /private/music /private/music/sources.json
python3 -m mixlab.interactive_session start /private/music/sources.json /private/mixlab-project-01
~~~

Open **/private/mixlab-project-01/sources/cue-editor.html**, beluister de
nummers, selecteer handmatig de A/B-startmomenten en download de keuze-JSON.
Rond vervolgens af en maak optioneel direct één volledig tweetrack-WAV:

~~~bash
python3 -m mixlab.interactive_session finish /private/mixlab-project-01 /private/mixlab-cue-selections.json \\
  --pair pair-001 --full-song --full-song-family bass_swap
~~~

Open **/private/mixlab-project-01/studio/index.html** voor de korte
transities of **/private/mixlab-project-01/full-song/index.html** voor de
volledige mix. Zie [interactieve workflow](docs/interactive-private-studio.md),
[complete mix](docs/full-song-mix-export.md) en
[volledige sets met meerdere tracks](docs/continuous-set-export.md).

**Privacy / grens:** bronmuziek blijft buiten Git en wordt niet geüpload.
Een rechtenverklaring is geen juridisch bewijs. Automatische BPM-
matching, echt key/phrase/downbeat-begrip en human-preference bewijs
zijn niet afgerond; experimenteer alleen met bronnen die je mag gebruiken.

## Implemented

- Canonical Track, Segment, Recipe and TransitionCandidate records.
- Validated, checksum-bound local audio manifests with explicit permission declarations.
- Deterministic PCM16 mono/stereo renderer: equal-power baseline, bass swap, echo exit and hard cut.
- Peak, RMS, clipping, DC offset and sample-jump diagnostics; identical render length and common gain across recipes.
- Original synthetic fixtures for reproducible infrastructure tests.
- Neutral A/B audio filenames, a local listening page, separate answer key and downloadable ratings.
- Strict streaming ingest with recording/PCM split-leakage checks and a JSON Schema.
- Replaceable analysis provider, measured regular-tempo proposals, manual cue/key annotations, content-addressed private feature cache and beat-error evaluation.
- Streaming transition renderer with exclusive complete-file publication, clipping rejection and post-PCM metrics.
- Checksum-bound rating aggregation with duplicate/coverage validation and explicit volume confounds.
- No runtime dependencies beyond Python 3.10+ standard library.

## Reproduce on the VPS runner

Shell/build/test/render execution goes through the existing GitHub self-hosted runner on `vps-bb300bba`. Do not provision another server or install models for this slice.

```bash
python3 -m unittest discover -s tests -v
python3 -m mixlab fixture /tmp/mixlab-example-library
python3 -m mixlab validate /tmp/mixlab-example-library/library.json
python3 -m mixlab benchmark /tmp/mixlab-example-library/library.json /tmp/mixlab-example-pack --seed 42
```

Use fresh output directories; existing packs are never overwritten. Open `review/index.html` locally. Only the `review/` directory goes to listeners; `private/` contains identity mappings, recipes, source paths and metrics. Omit `--seed` for real listening pilots. The synthetic fixture is **not** a music benchmark.

The canonical M1 benchmark still consumes short uncompressed PCM16 WAV excerpts with identical source channel count/sample rate (8–96 kHz), manual equal BPM, and max 32 MiB / 2 million frames per excerpt. **Separate new product modules do accept bounded full-length WAV and optionally FFmpeg-decoded MP3/FLAC/M4A**, and can export private continuous mixes. Tempo stretching and automatic musical alignment remain separate, unfinished work. The benchmark renderer now processes bounded blocks and a compact delay ring; the original array renderer remains as a regression reference. The exact-source VPS run must establish measured memory and timing.

The current pilot uses common gain, not matched perceived loudness; this is a known listening confound to fix before a milestone-quality benchmark. Objective diagnostics are not a musical preference score. Do not tune on a frozen evaluation set.

## Local library manifest

The fixture command writes a complete example. Replace sources only with explicitly permitted local excerpts and recompute their SHA-256 values. Each track requires `id`, relative `path`, `sha256`, `bpm`, `rights` and nonempty `provenance`. Supported manifest permissions: `synthetic`, `licensed`, `user-permitted`, `public-domain`. A permission declaration is provenance metadata, not verification of legal ownership. `pairs` declares distinct `a`/`b` IDs, BPM, integer beat count and start offsets in seconds.

Keep source media, derived stems, private renders, manifests with personal paths and credentials outside this public repository. Only synthetic CI fixtures and sanitized aggregate evidence may be uploaded by the foundation workflow.

## Direct een complete lokale WAV-set maken

De nieuwe private `party_mix` route voert bestaande stappen achter elkaar
uit: rechten- en SHA-gebonden lokale muziekinvoer → handmatige cue-Studio →
zelfgekozen overgangen → één doorlopende PCM16-WAV.

```bash
python3 -m mixlab.party_mix /private/music/project.json /private/new-studio /private/full-set.wav \
  --transition pair-001:bass_swap --transition pair-002:echo_exit
```

De volgorde van de paren is expliciet en moet één doorlopende route vormen;
er wordt geen maat, BPM of muziekrecht automatisch geraden. Bekijk
[de complete set-handleiding](docs/continuous-set-export.md) en
[de één-commando route](docs/one-command-studio.md) voor grenzen,
herstel na fouten en de niet-bewezen muzikale kwaliteit.

## Engine tools

```bash
python3 -m mixlab.ingest /private/library/library.json
python3 -m mixlab.analysis /private/library/clip.wav --cache /private/features
python3 -m mixlab.evaluation /private/pack /private/ratings/listener-*.json
```

The analyzer proposes a constant beatgrid from regular percussive excerpts and abstains on insufficient evidence. It does not identify musical phrases, vocals or key automatically, and never silently overwrites manual rendering metadata. ManualProvider accepts verified downbeats/phrases/key; these stay labelled manual. See [analysis decisions](docs/adr/analysis-provider.md), [renderer decisions](docs/adr/renderer-quality.md), [manifest contract](docs/dataset-manifest.md) and [evaluation rules](docs/benchmark-report.md).

## Continue

> Werk verder aan MixLab. Kijk in Notion naar de huidige fase en wat er nog moet gebeuren, claim een vrije taak en werk die uit.

Detailed coordination belongs in [AGENTS.md](AGENTS.md) and the worker plan. GitHub holds code and task specifications; the zCloud VPS SQLite queue holds live claims and scheduling. Notion is the product/decision/handoff mirror. Do not infer a live queue entry from an issue or a plan file.
