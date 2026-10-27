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
- **Zoom each deck independently to 1×, 4× or 16× around its currently selected cue** using the new offline waveform controls. The selected viewport shows its original WAV start/end times; clicking its waveform maps the position back to the correct **absolute original-track timestamp**, preserving optional human BPM-grid snapping, 0.10s fine nudges and undo. Selecting a zoom level alone never changes a cue, manifest, source or editor history. Zoom is purely a waveform-navigation tool, not an automated beat/phrase detector. The entire original WAV remains private.
- Preview only the currently selected transition-length excerpt on each deck. A second preview stops the first.
- Nudge by one beat or four beats. Optionally snap to a **manually declared** first-downbeat and BPM grid (no automatic beat inference).
- Switch between all registered pairs while keeping edits in memory.
- **Undo / redo your actual manual cue changes** with the visible Dutch **Ongedaan maken** and **Opnieuw** buttons (last 40 edits kept in this open page). Undo also selects the pair whose cue was changed, so the waveform, cue timestamp and predicted complete-set timeline return to the previous values. A new edit clears the redo chain. **Herstel dit paar** resets only the selected A/B pair to its originally saved cue positions; that reset can itself be undone. **Herstel alle cues** resets **every changed pair at once** to the source-manifest positions after explicit user confirmation. This is **one single Undo step**: if you clicked it accidentally you can bring back all experiments with **Ongedaan maken**, or reset them again with **Opnieuw**. Canceling the confirmation leaves the timeline and inputs untouched. The source WAVs, original manifest, and previous downloads are never overwritten. Buttons are disabled when there is nothing to reverse. This is in-memory-only: download the revised cue JSON to keep your chosen edits, and apply it to a NEW manifest. No original WAVs or existing source metadata are overwritten.
- **See the complete set timeline update while moving cues**: the editor now reconstructs the planned solo and A→B transition chapters in actual source-PCM frame order. It displays the estimated total set length, how many pair cues have changed, and the difference from the untouched original manifest. Every chapter shows its proposed start/end time; choose **Wijzig deze overgang** to jump back to that pair without losing unsaved edits. Impossible overlapping/out-of-order cues clear the proposed timeline rather than showing fictitious song times. Empty zero-frame solos do not appear. This is based on SHA-pinned original PCM16 source counts and declared BPM/cue positions, not decoded mixed audio or an independently performed listening test.
- Download a small cue-selection JSON containing only pair IDs, cue seconds and source manifest SHA256. It does not contain audio data or full source paths.
- **Reload saved manual cues without rerendering anything:** after reopening this same private editor, choose your earlier `mixlab-cue-selections.json` under **Eerder gedownloade cuekeuzes** and click **Laad opgeslagen cues**. Every chosen A/B cue is restored together and the planned complete-set timeline immediately updates. The entire import is **one Undo step**, so **Ongedaan maken / Opnieuw** switches between before and after the import. The file must be at most 64 KiB and refer to the **exact unchanged original source manifest SHA**; all registered pair IDs must appear once, and each cue must fit the actual SHA-pinned source PCM length and continuous set with no overlapping A/B transitions. Invalid, foreign or malformed files change **none** of the current cues. If the editor has unsaved changes, it asks confirmation before replacing them, allowing you to download your current work first. Everything happens in local browser memory; no automatic saving, network upload or rehash of changed audio. Apply later rechecks source WAV hashes when writing a NEW manifest.
- If a later outgoing cue starts **before** the preceding incoming transition has finished on the same song, the editor immediately identifies the first offending pair, disables downloading and reveals **Ga naar probleemovergang**. Select it to open that actual Deck A waveform (keyboard focus included), with the **earliest sample-frame-safe manual outgoing cue** shown next to it. The DJ chooses and listens to the cue; MixLab never shifts it automatically. If no later cue fits the original track, the guidance says to revise the preceding Deck B cue or source plan rather than suggesting an impossible value. Undo/Redo immediately recheck the route and show/hide the navigation. Disconnected original source track order also points to its offending pair but requires a new corrected manifest. The full WAV, originals and rights records are unaffected. This is a manual repair aid, not music-quality proof.

### Save your chosen cues without overwriting anything

Move the downloaded selection JSON to your private library or reference its Downloads path. Apply it against the original manifest, writing a NEW name:

~~~bash
python3 -m mixlab.cue_editor apply /private/imported-music/source_manifest.json /private/mixlab-cue-selections.json /private/imported-music/approved-cues.json --plan-html --plan-verify-wavs
~~~

With `--plan-html --plan-verify-wavs`, the same command also writes a NEW offline private HTML visual set plan beside the music folder, never a Studio or WAV. The preview shows the verified exact expected full-set duration and track/transition timeline; the original manifest is unchanged. Its path is returned as `private_plan_html`. The path is automatically derived from the new manifest filename (`approved-cues-planned-set.wav.preview.html` in this example), and a preexisting plan is never overwritten. Omit these optional flags for the original apply-only behavior. If optional page generation fails after a new manifest was safely created, the CLI returns nonzero and tells you that the new manifest was preserved. A private plan is not proof of rights or musical quality.

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
