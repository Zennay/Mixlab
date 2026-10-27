"""Read-only SHA-bound PCM16 duration preview for a manual complete DJ set.

Original-source headers and hashes are checked; no full audio is decoded and
no permissions, musical accuracy or listening quality are inferred.
"""
from pathlib import Path
from .media_import import OUTPUT_RATE, _regular_source, _canonical_pcm16_wav
from .set_export import MAX_SET_BYTES


def inspect_playlist(manifest_path, catalog, route, transitions):
    source = Path(manifest_path).absolute().parent.resolve(strict=True)
    tracks = {t['id']: t for t in catalog}
    if len(tracks) != len(catalog) or len(route) != len(catalog):
        raise ValueError('Invalid source catalog for complete WAV preview')
    frames = {}
    for ident in route:
        entry = tracks[ident]
        if not isinstance(entry.get('path'), str) or not entry['path'].lower().endswith('.wav'):
            raise ValueError('WAV duration preview accepts only original PCM16 WAVs; omit --verify-wavs for other formats')
        wav = _regular_source(source, entry['path'])
        info = _canonical_pcm16_wav(wav, entry.get('sha256'))
        if info is None:
            raise ValueError('A source is not SHA-verified 44.1 kHz PCM16 mono/stereo WAV')
        # A short file that lies about its WAV frame count cannot supply the
        # nominal data payload even if a reader accepts its header.
        if wav.stat().st_size < 44 + info['frames'] * info['channels'] * 2:
            raise ValueError('Declared PCM WAV frames exceed source bytes')
        frames[ident] = info['frames']
    before = 0
    total = 0
    for item in transitions:
        length = round(item['beats'] * 60 / item['bpm'] * OUTPUT_RATE)
        a = round(item['outgoing_cue_seconds'] * OUTPUT_RATE)
        b = round(item['incoming_cue_seconds'] * OUTPUT_RATE)
        if (length < 2 or a < before or a + length > frames[item['from_track']]
                or b + length > frames[item['to_track']]):
            raise ValueError('A manual transition extends outside the original PCM WAV or overlaps a previous transition')
        total += a - before + length
        before = b + length
    tail = frames[route[-1]] - before
    if tail < 0:
        raise ValueError('Last song ends before the final transition')
    total += tail
    expected_bytes = 44 + total * 4  # Import normalizes PCM16 mono/stereo to stereo.
    if total < 2 or expected_bytes > MAX_SET_BYTES:
        raise ValueError('Complete PCM preview exceeds the existing 512 MiB renderer budget')
    return dict(complete_mix_duration=round(total / OUTPUT_RATE, 6),
                exact_expected_pcm_frames=total,
                expected_stereo_pcm_wav_bytes=expected_bytes,
                source_wav_hashes_and_headers_verified=True,
                source_audio_validated=False,
                preview_audio_scope='source SHA and PCM16 header verified; no full decode',
                audio_rendered=False)
