# MixLab Visual Cue Editor — offline waveforms, preview and manual editing

MixLab has an offline visual cue-selection workflow for M1 Transition Lab. You can see each real track's waveform energy, click a transition start, listen to that exact-length passage, nudge cues by a beat or a bar, and export a new manifest without overwriting your originals.

The editor is a local HTML file, with no HTTP server, account, CDN, cloud storage, audio upload or extra frontend dependencies.

## From MP3/FLAC to visually selected real transitions

Create your private source manifest using the existing project wizard, then normalize local permitted music to PCM16 WAV using the installed FFmpeg:

~~~bash
python3 -m mixlab.project_wizard /private/music /private/music/sources.json
python3 -m mixlab.media_import /private/music/sources.json /private/imported-music
~~~

Generate an editor **beside** the converted library manifest so the browser can open relative local WAV paths:

~~~bash
python3 -m mixlab.cue_editor prepare /private/imported-music/source_manifest.json /private/imported-music/cue-editor.html
~~~

Open /private/imported-music/cue-editor.html locally with Firefox or Chromium.

### What you can do

- The offline browser editor uses **Dutch labels** and shows the recognisable private source **filename without its extension** alongside each original technical track ID. You select pairs by song name, not by having to decode opaque `track-001` identifiers; labels are not authenticated metadata or rights proofs. Manual unsaved cue changes show a clear reminder to download the private JSON.
- View both A and B audio-energy waveforms, independently edit their start times with a slider or click on the waveform, and see precise timestamps.
- Preview only the currently selected transition-length excerpt on each deck. A second preview stops the first.
- Nudge by one beat or four beats. Optionally snap to a **manually declared** first-downbeat and BPM grid (no automatic beat inference).
- Switch between all registered pairs while keeping edits in memory.
- Download a small cue-selection JSON containing only pair IDs, cue seconds and source manifest SHA256. It does not contain audio data or full source paths.
- If a later outgoing cue starts **before** the preceding incoming transition has finished on the same song, the editor immediately explains which pair is conflicting and disables the download button. Move that cue later until it fits. Cue boundaries are checked using the original SHA-verified audio sample rate, not guessed musical phrase lengths. This does not automatically choose better cues.

### Save your chosen cues without overwriting anything

Move the downloaded selection JSON to your private library or reference its Downloads path. Apply it against the original manifest, writing a NEW name:

~~~bash
python3 -m mixlab.cue_editor apply /private/imported-music/source_manifest.json /private/mixlab-cue-selections.json /private/imported-music/approved-cues.json
~~~

Apply revalidates the registered WAV source hashes and formats, requires exact source manifest SHA, checks that each declared pair appears exactly once, and rejects cues that exceed a source file's frame budget. It also checks that connected transitions are in the right order and that each new outgoing cue starts **on or after the previous incoming transition ends**. Invalid selections fail before a new manifest is written; the originals and the user's downloaded JSON are preserved. It never rewrites the original manifest or media, nor changes an existing frozen evaluation pack.

Now compile the approved excerpts and render the actual transition candidates:

~~~bash
python3 -m mixlab.cueprep /private/imported-music/approved-cues.json /private/approved-excerpts
python3 -m mixlab.studio render /private/approved-excerpts/library.json /private/approved-transition-studio
~~~

Open /private/approved-transition-studio/index.html to hear the baseline, bass swap, echo exit and hard cut candidates and export a chosen WAV.

## Boundaries and trust

- Preparation requires an existing full-length PCM16 WAV private source manifest, 2–20 tracks and 1–10 pairs. Use media_import before this command for MP3/FLAC/M4A.
- All source tracks require manually verified BPM, declared rights/provenance and pinned SHA256. Existing matching tempo, channel/sample-rate, 15-minute/256 MiB full-track and 2M-frame/32MiB excerpt limits remain.
- Waveform energy is computed from bounded private local PCM sampling at ~4k frames/sec and 250ms hops, not musical phrase detection or loudness-calibrated mastering. Generated local HTML is bounded to 2 MiB.
- The GUI browser may restrict local-file media playback depending on profile security. There is no automatic public server or relaxed browser security setting.
- Keep output HTML, original audio, manifests and cue files outside Git. Browser script references only private *relative* WAV filenames, not original absolute source paths; no audio bytes are embedded in HTML.
- This is **unblinded creative manual editing**. It cannot establish musical-quality superiority, listener preference, or verified automatic analysis. Never tune an already frozen evaluation split.

The tool is completely additive and does not modify active owner files in DSP, MIR, CLI, benchmark or ML-07 quality scopes.
