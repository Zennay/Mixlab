"""A playable, rights-safe MixLab DJ demo generated entirely on the user's machine.

Creates three original procedural PCM16 songs (no samples, recording downloads
or third-party models), renders the established real MixLab transitions and a
continuous three-song mix, and exposes local browser pages to hear/edit them.

This is a creative product demonstration, NOT a blind listening study,
research preference claim, or substitute for real rights-cleared music.
"""
from __future__ import annotations

import argparse
from array import array
import html
import json
import math
import os
from pathlib import Path
import shutil
import sys
import wave

from .cueprep import _digest
from .cue_editor import prepare as prepare_visual_editor
from .full_mix import full_mix
from .session import make_session
from .set_composer import create_composer
from .set_export import export_set
from .set_player import publish_player


SAMPLE_RATE = 44100
BPM = 120
CHANNELS = 2
SONG_SECONDS = 24
BLOCK_FRAMES = 2048

# Original synthetic progressions: roots chosen for beat-synchronous musical
# variation, not recordings or samples of copyrighted songs.
ROOTS = (
    (110.000, 87.307, 130.813, 97.999),
    (130.813, 97.999, 110.000, 87.307),
    (97.999, 110.000, 87.307, 130.813),
)


def _song(path, roots, variant):
    """Deterministically synthesize an original drum/bass/pad stereo piece."""
    rate = SAMPLE_RATE
    frames = SONG_SECONDS * rate
    state = (0x117D36 + variant * 0x4871) & 0x7fffffff
    with path.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        with wave.open(output, "wb") as writer:
            writer.setparams((CHANNELS, 2, rate, frames, "NONE", "not compressed"))
            for start in range(0, frames, BLOCK_FRAMES):
                result = array("h")
                for i in range(start, min(start + BLOCK_FRAMES, frames)):
                    now = i / rate
                    # At 120 BPM: two beats per second, four beats/bar.
                    beat = now * (BPM / 60)
                    beat_index = int(beat)
                    beat_time = (beat - beat_index) * .5
                    bar_index = beat_index // 4
                    root = roots[(bar_index // 2) % len(roots)]
                    # Quiet chord/pad plus filtered-ish bass in both channels.
                    pad = (math.sin(2 * math.pi * (root * 2) * now) * .088 +
                           math.sin(2 * math.pi * (root * 2 * 1.25) * now) * .07 +
                           math.sin(2 * math.pi * (root * 2 * 1.5) * now) * .06)
                    pulse = .65 + .35 * math.sin(math.pi * min(1., beat_time/.5))
                    bass = (math.sin(2 * math.pi * root * now) * .13 *
                            math.exp(-2.6 * beat_time))
                    kick = (math.sin(2 * math.pi *
                            (60 * beat_time + 25 * (1-math.exp(-18*beat_time))/18)) *
                            .27 * math.exp(-18 * beat_time)
                            if beat_index % 2 == 0 else 0.)
                    # Local deterministic noise for a restrained snare + hat.
                    state = (1103515245 * state + 12345) & 0x7fffffff
                    noise = state / 0x3fffffff - 1.
                    snare = (.13 * noise * math.exp(-25 * beat_time)
                             if beat_index % 4 in (1, 3) else 0.)
                    halfbeat_time = (now % .25)
                    hat = .034 * noise * math.exp(-65 * halfbeat_time)
                    warm = (pad * pulse + bass + kick + snare + hat)
                    # Stereo arrangement depends on the original generated song.
                    stereo_offset = math.sin(2*math.pi*(root*1.001)*now) * .016
                    left = warm + stereo_offset
                    right = warm - stereo_offset
                    for value in (left, right):
                        if not -1. <= value <= 32767/32768:
                            raise ValueError("Synthetic demo unexpectedly exceeds PCM16")
                        result.append(round(value * 32768))
                if sys.byteorder != "little":
                    result.byteswap()
                writer.writeframesraw(result.tobytes())


def _demo_landing(root):
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>MixLab / Private DJ Demo</title><style>
:root{font:16px system-ui;background:#0a0c12;color:#f5f2ff;color-scheme:dark}
main{max-width:920px;margin:auto;padding:6vh 24px}h1{font-size:clamp(3.5rem,10vw,7rem);
letter-spacing:-.08em;line-height:1}small{color:#c6aaff;letter-spacing:.16em}
p{color:#bac4d8;line-height:1.65}.grid{display:grid;grid-template-columns:
repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:30px 0}
a{display:block;background:#212437;border:1px solid #59506b;border-radius:16px;
padding:24px;color:#eee6ff;text-decoration:none;font-weight:700}
a:hover,a:focus{border-color:#c9aaf9;outline-offset:4px}span{display:block;
font-size:.84rem;font-weight:400;color:#bac4d8;margin-top:12px}
</style><main><small>OFFLINE / RIGHTS-SAFE DJ DEMO</small>
<h1>Make music<br>flow.</h1><p>Three original, locally synthesized songs. Eight real
MixLab transition auditions across two pairs. A complete three-song playthrough. No external music,
rights uncertainty, online connection, FFmpeg installation, downloads,
or AI model. All audio stays on your machine.</p><div class="grid">
<a href="audition/studio/index.html">Hear 4 transition styles
<span>Baseline, bass swap, echo exit and hard cut.</span></a>
<a href="three-song-set.wav.player.html">Play the complete three-song set
<span>Track A → bass swap → Track B → echo exit → Track C, with clickable chapters.</span></a>
<a href="audition/set-composer/index.html">Build your own three-song route
<span>Audition both pairs, choose transition families and export a local choice plan.</span></a>
<a href="full-song/index.html">Play the classic two-song comparison
<span>Track A → real DSP transition → remaining track B.</span></a>
<a href="audition/sources/cue-editor.html">Open visual cue editor
<span>Listen, click waveforms and move manually predeclared beat cues.</span></a>
</div><p>These musical loops are synthetic creative demos, not real-artist tracks.
No blind listener experiment was conducted and no claim of transition
superiority follows from the demo. For your own music, use the private
source wizard and interactive session.</p></main></html>'''
    target = root / "index.html"
    target.write_text(page, encoding="utf-8")
    target.chmod(0o600)


def create_demo(destination):
    """Create a real local, private, playable end-user demo in one call."""
    root = Path(destination).absolute()
    if root.exists() or root.is_symlink() or not root.parent.is_dir():
        raise ValueError("Demo must use a new directory inside an existing parent")
    for parent in (root, *root.parents):
        if (parent / ".git").exists():
            raise ValueError("Do not generate private audio inside a Git checkout")
    root.mkdir(mode=0o700)
    try:
        input_dir = root / "sources"
        input_dir.mkdir(mode=0o700)
        source_tracks = []
        for number, roots in enumerate(ROOTS):
            tid = f"demo-song-{number+1:02d}"
            name = tid + ".wav"
            audio = input_dir / name
            _song(audio, roots, number)
            source_tracks.append({
                "id": tid, "path": name, "sha256": _digest(audio),
                "bpm": BPM, "rights": "synthetic",
                "provenance": "Original beat-grid-aligned procedural MixLab audio, generated locally",
                "first_downbeat_seconds": 0, "recording_id": tid,
                "partition": "development"
            })
        declared = {
            "schema_version": 1, "purpose": "development-pilot",
            "tracks": source_tracks,
            "pairs": [{
                "id": "demo-pair-001", "a": source_tracks[0]["id"],
                "b": source_tracks[1]["id"], "bpm": BPM, "beats": 16,
                "a_start_seconds": 16.0, "b_start_seconds": 0.0
            }, {
                "id": "demo-pair-002", "a": source_tracks[1]["id"],
                "b": source_tracks[2]["id"], "bpm": BPM, "beats": 16,
                "a_start_seconds": 16.0, "b_start_seconds": 0.0
            }]
        }
        spec = input_dir / "demo-source-spec.json"
        with spec.open("xb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write((json.dumps(declared, sort_keys=True,
                                     indent=2, allow_nan=False)+"\n").encode("utf-8"))
        # Reuse real already-merged product paths, including FFmpeg-free WAV import.
        make_session(spec, root / "audition")
        normalized = root / "audition" / "sources" / "source_manifest.json"
        prepare_visual_editor(normalized, root / "audition" / "sources" / "cue-editor.html")
        full_mix(normalized, root / "full-song",
                 pair_id="demo-pair-001", family="bass_swap", gain_db=-9.)
        # Real product composition and export paths, using original local audio.
        create_composer(root / "audition")
        finished_set = export_set(root / "audition", root / "three-song-set.wav",
                                  ["demo-pair-001:bass_swap", "demo-pair-002:echo_exit"])
        publish_player(root / "audition", finished_set)
        _demo_landing(root)
        return root / "index.html"
    except BaseException:
        # Fresh-only destination: no original music or existing work removed.
        shutil.rmtree(root)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create a complete local DJ demo with original procedural music")
    parser.add_argument("private_output", help="New folder outside Git/source checkout")
    args = parser.parse_args()
    try:
        page = create_demo(args.private_output)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, "MixLab demo: " + str(exc) + "\n")
    print(json.dumps({"ready": True, "open_locally": str(page),
                      "original_synthetic_audio": True,
                      "real_music_quality_study": False,
                      "audio_uploaded": False}))


if __name__ == "__main__":
    main()
