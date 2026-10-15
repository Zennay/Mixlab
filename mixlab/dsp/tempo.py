"""Explicit optional pitch-preserving tempo preparation using installed FFmpeg.

No installation, network input, implicit fallback or playback-rate substitution.
Private source/result files remain local to the caller.
"""
from array import array
from dataclasses import asdict, replace
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

from ..ingest import MAX_FRAMES, digest, inspect_wav, number
from ..models import Recipe
from . import render


def capabilities():
    executable = shutil.which("ffmpeg")
    if not executable:
        return {"available": False, "reason": "ffmpeg_not_installed"}
    try:
        version = subprocess.run([executable, "-version"], capture_output=True, text=True,
                                 timeout=10, check=True).stdout.splitlines()[0]
        filters = subprocess.run([executable, "-hide_banner", "-filters"], capture_output=True,
                                 text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        raise ValueError("Cannot inspect installed FFmpeg") from exc
    available = any(" rubberband " in line for line in filters.splitlines())
    return {"available": available, "reason": None if available else "rubberband_filter_missing",
            "executable": executable, "version": version}


def tempo_ratio(source_bpm, target_bpm):
    number(source_bpm, "source bpm", 30, 300)
    number(target_bpm, "target bpm", 30, 300)
    ratio = target_bpm / source_bpm
    if not .90 <= ratio <= 1.10:
        raise ValueError("Tempo ratio must stay within 0.90..1.10; use a different transition")
    return ratio


def prepare(source_path, output_path, *, source_bpm, target_bpm):
    ratio = tempo_ratio(source_bpm, target_bpm)
    source, output = Path(source_path).resolve(), Path(output_path)
    if output.resolve() == source or (output.exists() and output.samefile(source)):
        raise ValueError("Output must not overwrite source")
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    info = inspect_wav(source)
    expected = round(info["frame_count"] / ratio)
    if not 2 <= expected <= MAX_FRAMES:
        raise ValueError("Tempo preparation exceeds output frame budget")
    backend = capabilities()
    if not backend["available"]:
        raise ValueError("Pitch-preserving backend unavailable: " + backend["reason"])
    before = digest(source)
    rate, channels = info["sample_rate"], info["channels"]
    # Explicit locked parameters, no caller-supplied filter expression.
    filter_graph = (f"rubberband=tempo={ratio:.12g}:pitch=1:transients=crisp:"
                    "detector=compound:phase=laminar:window=standard:"
                    "smoothing=off:channels=together")
    with tempfile.TemporaryDirectory(prefix=".mixlab-tempo-", dir=output.parent) as temporary:
        root = Path(temporary)
        floating, candidate = root/"render.f32", root/"candidate.wav"
        command = [backend["executable"], "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-n", "-threads", "1", "-filter_threads", "1", "-protocol_whitelist", "file,pipe",
                   "-f", "wav", "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
                   "-af", filter_graph, "-ar", str(rate), "-ac", str(channels),
                   "-c:a", "pcm_f32le", "-f", "f32le", str(floating)]
        try:
            subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=120, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Pitch-preserving backend failed or timed out") from exc
        size = floating.stat().st_size
        if size % (4*channels):
            raise ValueError("Backend produced a partial audio frame")
        frames = size // (4*channels)
        if not 2 <= frames <= MAX_FRAMES or abs(frames-expected) > max(2, round(.05*rate)):
            raise ValueError("Backend output duration outside 50 ms tolerance")
        peak = 0.
        with floating.open("rb") as stream, wave.open(str(candidate),"wb") as target:
            target.setparams((channels,2,rate,frames,"NONE","not compressed"))
            while raw := stream.read(4096*channels*4):
                values = array("f")
                values.frombytes(raw)
                if sys.byteorder != "little": values.byteswap()
                packed = array("h")
                for value in values:
                    if not math.isfinite(value) or not -1 <= value <= 32767/32768:
                        raise ValueError("Tempo processing would clip PCM16; reduce source gain first")
                    peak = max(peak,abs(value))
                    packed.append(round(value*32768))
                if sys.byteorder != "little": packed.byteswap()
                target.writeframesraw(packed.tobytes())
        if digest(source) != before:
            raise ValueError("Source changed during tempo preparation")
        inspect_wav(candidate)
        os.link(candidate, output)
    return {"schema_version":1,"backend":"ffmpeg-rubberband","backend_version":backend["version"],
            "source_sha256":before,"output_sha256":digest(output),
            "source_bpm":source_bpm,"target_bpm":target_bpm,"tempo_ratio":ratio,"pitch_scale":1.,
            "filter":filter_graph,"sample_rate":rate,"channels":channels,
            "expected_frames":expected,"actual_frames":frames,"peak_before_pcm":peak,
            "duration_error_seconds":(frames-expected)/rate,
            "timing_contract":"source cue seconds divided by tempo ratio; inspect transients",
            "musical_quality":"requires real-audio listening"}


def render_pair(a_path, b_path, output_path, recipe, *, a_bpm, b_bpm):
    if not isinstance(recipe,Recipe): raise TypeError("recipe must be a Recipe")
    if recipe.a_bpm is not None or recipe.b_bpm is not None:
        raise ValueError("Declare original tempos only in a_bpm/b_bpm arguments")
    ar, br = tempo_ratio(a_bpm,recipe.bpm), tempo_ratio(b_bpm,recipe.bpm)
    output = Path(output_path)
    originals = (Path(a_path).resolve(),Path(b_path).resolve())
    if output.resolve() in originals or (output.exists() and any(output.samefile(p) for p in originals)):
        raise ValueError("Output must not overwrite an original source")
    if output.exists() or output.is_symlink(): raise ValueError("Output already exists")
    # Validate both formats and original segment ranges before expensive DSP.
    infos=[inspect_wav(p) for p in originals]
    if (infos[0]["sample_rate"],infos[0]["channels"]) != (infos[1]["sample_rate"],infos[1]["channels"]):
        raise ValueError("Source formats must match")
    for info,start,bpm in zip(infos,(recipe.a_start,recipe.b_start),(a_bpm,b_bpm)):
        if start+recipe.beats*60/bpm > info["duration_seconds"]:
            raise ValueError("Original source is too short for requested beats")
    hashes=[digest(p) for p in originals]
    with tempfile.TemporaryDirectory(prefix=".mixlab-pair-",dir=output.parent) as temporary:
        root=Path(temporary)
        prepared, transforms=[],[]
        for label,path,bpm in zip(("a","b"),originals,(a_bpm,b_bpm)):
            if bpm == recipe.bpm:
                prepared.append(path)
                transforms.append({"backend":"identity","source_sha256":digest(path),"tempo_ratio":1.,"pitch_scale":1.})
            else:
                destination=root/(label+".wav")
                transforms.append(prepare(path,destination,source_bpm=bpm,target_bpm=recipe.bpm))
                prepared.append(destination)
        aligned=replace(recipe,a_start=recipe.a_start/ar,b_start=recipe.b_start/br)
        staged=root/"mix.wav"
        result=render(*prepared,staged,aligned)
        if [digest(p) for p in originals] != hashes:
            raise ValueError("Original source changed during pair render")
        # Do not retain temporary source paths in durable recipe metadata.
        result["sources"]=[{"path":str(p),"sha256":h} for p,h in zip(originals,hashes)]
        result["output_path"]=str(output)
        result["original_recipe"]=asdict(recipe)
        result["tempo_transforms"]=transforms
        result["alignment_source"]="manual_cues_scaled_after_explicit_timestretch"
        result["tempo_source"]="manual_declared_original_tempos"
        result["engine_version"]="0.3.0-explicit-tempo"
        os.link(staged,output)
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description="Explicit pitch-preserving tempo-matched transition")
    parser.add_argument("a"); parser.add_argument("b"); parser.add_argument("output")
    parser.add_argument("--a-bpm",type=float,required=True)
    parser.add_argument("--b-bpm",type=float,required=True)
    parser.add_argument("--target-bpm",type=float,required=True)
    parser.add_argument("--a-start",type=float,default=0.)
    parser.add_argument("--b-start",type=float,default=0.)
    parser.add_argument("--beats",type=int,default=8)
    parser.add_argument("--family",choices=("baseline","bass_swap","echo_exit","hard_cut"),default="bass_swap")
    parser.add_argument("--gain-db",type=float,default=-6.)
    args=parser.parse_args()
    try:
        recipe=Recipe(bpm=args.target_bpm,beats=args.beats,family=args.family,
                      a_start=args.a_start,b_start=args.b_start,gain_db=args.gain_db)
        result=render_pair(args.a,args.b,args.output,recipe,a_bpm=args.a_bpm,b_bpm=args.b_bpm)
    except (OSError,ValueError,TypeError) as exc:
        parser.exit(2,f"MixLab tempo: {exc}\n")
    # CLI stdout can be saved as private evidence; hide local paths by default.
    result.pop("sources",None); result.pop("output_path",None)
    print(json.dumps(result,sort_keys=True,allow_nan=False,indent=2))

if __name__ == "__main__":
    main()
