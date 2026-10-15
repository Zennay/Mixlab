# Private library contract

Run `python3 -m mixlab.ingest /private/library/library.json`.
The existing schema_version=1 fixture remains accepted. Ingest streams PCM16 instead of allocating millions of Python tuples. Limits are 50 tracks, 10 pairs, 32 MiB and 2,000,000 frames per source, 1 MiB per manifest.

Each track requires id, relative path, lowercase SHA-256, manual bpm, rights and provenance. Absolute paths, parent traversal, escaping symlinks, truncated WAVs, nonfinite numbers and duplicate JSON keys fail. Each pair requires id, a, b, bpm, with optional beats (8), a_start (0), b_start (0). Equal source tempo and PCM format are still required.

For frozen studies add partition (development/evaluation) to **every** track and recording_id identifying the underlying recording across encodings/edits. Cross-partition pairs, identical decoded PCM and reused recording IDs across partitions fail. PCM hashes do not recognize remasters or transcoding; recording_id and a human provenance audit remain necessary. Freeze the manifest checksum before listening. Legacy unpartitioned manifests remain development-only.

No real-music dataset is bundled. A 20–50 track licensed/local library and human listening remain open gates. Validation checks a permission declaration; it cannot establish legal ownership.
