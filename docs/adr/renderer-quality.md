# ADR: bounded streaming renderer

`mixlab.dsp.render` preserves the four established transition formulas and explicit endpoints, with interleaved int16 blocks and a compact float64 delay ring. Memory scales with block size and delay, not source duration. All input bounds still apply. This permits the maximum supported excerpt without millions of Python tuples.

The reference engine remains available for byte-exact regression. The benchmark CLI uses the streaming implementation after integration. Changing block size must not change PCM output. Meter both pre-quantization and actual quantized PCM, channel by channel.

Clipping policy: fail before publication and request lower **common** gain across a comparison. Never silently clamp, normalize each candidate differently or confuse RMS with LUFS. A private temporary file is published exclusively after the complete render and source-hash recheck; failed runs clean it up. Existing candidates and source files cannot be replaced.

The echo remains an in-window effect with a taper and no extra tail; extending a tail would change the same-duration benchmark. Hard cut remains intentionally discontinuous and must be assessed as such. Bass swap is first-order low/high splitting, not stem separation. Equal BPM and manually verified offsets remain required; no hidden resampling or tempo conversion. Human sound-quality evidence is still needed.
