# Portable Complete Show — optional MP3/FLAC and private USB bundle

This follows [Complete Show Master](private-complete-show-master.md). It
does **not** render any new original music or close M1 listening/rights
gates. It packages or transcodes only one separately approved, already
finished and SHA-verified `show.wav` in its private output folder.

## Optional portable MP3 or FLAC

Install FFmpeg and FFprobe locally if they are not already present:

```bash
python3 -m mixlab.show_delivery encode \
  /private/new-real-show/show.wav --format mp3 --bitrate-kbps 192
```

Or, instead:

```bash
python3 -m mixlab.show_delivery encode \
  /private/new-real-show/show.wav --format flac
```

The tool rechecks the **entire** PCM16 output SHA-256, receipt, exact section
frames, sample rate/channels and the private rights posture, then asks for a
new typed **`yes`** before using the installed local FFmpeg encoder.
Only bounded local encoding is permitted; audio cannot be uploaded. The
already finished original WAV is re-hashed after encoding before the new
output is published. New optional files, each restricted to private local
access, are `show.mp3` or `show.flac`,
`show.mp3.receipt.private.json` / corresponding FLAC receipt, and a
corresponding offline player HTML. The encoded audio hash is recorded
separately from the unchanged original WAV hash; MP3 playback may have
encoder delay, so its chapter positions are only approximate.

Encoding is **not** a music redistribution license. Real originals and
their source permissions remain separately necessary.

## Create one bounded, deliberately consented private ZIP

The standard package is intentionally only the real completed show WAV,
its **sanitized** source-bound receipt, a newly generated sanitized local
offline player and a SHA-256 inventory:

```bash
python3 -m mixlab.show_delivery pack \
  /private/new-real-show/show.wav
```

If an MP3 or FLAC was separately encoded and receipt-verified already,
include **exactly one** such derivative:

```bash
python3 -m mixlab.show_delivery pack \
  /private/new-real-show/show.wav --include-encoded
```

Both modes require a new typed **`yes`**. The ZIP is a private local
`show.private.zip`, never an automatic upload. It is streamed with bounded
ZIP64 stored entries, using source mutation and full-WAV SHA checks.

**Privacy: the original local Show Master receipt and stage HTML contain
human operator notes, and may expose event-specific set-folder labels.**
The exporter therefore does **not** put those original files into the
music ZIP. Instead it regenerates their sanitized equivalents from the
verified WAV receipt: notes are empty, labels are generic *Set 1, Set 2...*,
and the private start clock is redacted. The same sanitization is applied to
the optional portable HTML player. The original private notes and schedule
remain unchanged on the original local computer.

The ZIP inventory intentionally excludes source-track files, original
Studio sessions, human-notes JSON and any credentials. It is **unsigned**:
SHA-256 verifies internal file consistency, not who sent it or whether the
recipient holds the rights to the music.

Keep this ZIP only on authorized private devices with a suitable player.
If a compressed format is not installed or optional encoding fails, the
canonical, independently approved `show.wav` is still available.

## Restore an approved private Show ZIP to a second offline device

After moving the original `show.private.zip` to another authorized offline
computer, choose an entirely **new** private destination directory outside
music sources, symlinks and any Git checkout:

```bash
python3 -m mixlab.show_restore \
  /private/usb/show.private.zip \
  /private/restored-complete-show
```

The restore command admits only the exact official flat WAV/source-receipt/
offline-player/SHA-manifest inventory and, optionally, one previously
approved local MP3 or FLAC with its corresponding receipt/player. It rejects
path traversal, duplicate entries, symlinks, directories, compressed entries,
extra operator files, oversized individual files, mismatched SHA-256s and
source mutation while streaming. A typed **`yes`** is needed before any
files are written into the new private 0700 folder. Original ZIP and sources
are never modified, and an incomplete restore removes only the new files.

**Executable HTML from the ZIP is not implicitly trusted.** Once the entire
restored `show.wav` is re-hashed and validated against its official frame
receipt, MixLab reconstructs the canonical sanitized receipt/player from the
installed application templates and compares them byte-for-byte against
what arrived. For the optional encoded audio it also verifies its actual
SHA-bound receipt and canonical HTML player. Any edited, non-sanitized or
unexpected browser code is refused before reporting a successful restore.

The restored folder contains the actual complete WAV, a safe offline
`index.html`, the redacted source receipt and archive manifest, and any
separately selected portable encoded format. Full WAV hash proves internal
consistency only: **the archive is unsigned and does not certify who sent it
or whether the recipient has legal music-use rights.**
