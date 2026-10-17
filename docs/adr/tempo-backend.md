# ADR: explicit pitch-preserving tempo backend

Use an **already installed** FFmpeg build with its Rubber Band filter. No installer, network source, model or implicit atempo fallback is added. [FFmpeg documents](https://ffmpeg.org/ffmpeg-filters.html#rubberband) separate tempo and pitch factors and a build-time librubberband requirement. The adapter fixes pitch=1, stereo channel coupling and explicit transient settings. [Rubber Band](https://breakfastquay.com/rubberband/) remains a replaceable backend; review its licensing and the FFmpeg build before distributing binaries. This change invokes the user's existing local binary and does not bundle it.

Tempo conversion is explicit and constrained to a 0.90–1.10 ratio per source. Inputs remain private bounded PCM16 excerpts. Original manual cue seconds are divided by the ratio; the adapter records transform versions, settings, input/output hashes, actual duration and timing limitations. Pitch-preserving processing can still create transient/vocal artifacts; it is not a human-quality guarantee or automatic phrase alignment.

The backend writes private float32 first. MixLab checks finite values, output frame/duration bounds and pre-quantization clipping before PCM16 conversion and exclusive publication. Timeout is 120 seconds, decoder/filter threads are 1, input protocol is local file/pipe only, and the process does not emit private paths to logs. Missing backend fails clearly; equal-tempo pairs use the existing renderer without it.

```bash
python3 -m mixlab.dsp.tempo a.wav b.wav mix.wav --a-bpm 120 --b-bpm 124 --target-bpm 122 --beats 8 --family bass_swap
```

The existing benchmark manifest still deliberately requires equal BPM; transformed comparisons need a separately frozen benchmark. This opt-in CLI does not silently change existing recipes. CI requires the real installed backend for pitch, stereo isolation, pulse timing, duration and actual mismatched-tempo pair tests; optional installations elsewhere may skip those tests explicitly.
