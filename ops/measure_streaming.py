"""Synthetic maximum-excerpt proof, isolated child RSS; no audio is exported."""
from array import array
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import wave
from mixlab.dsp import render
from mixlab.models import Recipe

def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mixlab-stream-budget-") as temporary:
        root=Path(temporary)
        rate=48000
        block=array("h", (v for i in range(4096) for v in (6000 if i%100<50 else -6000,0)))
        if sys.byteorder != "little": block.byteswap()
        for name in ("a.wav","b.wav"):
            with wave.open(str(root/name),"wb") as out:
                out.setparams((2,2,rate,rate*32,"NONE","not compressed"))
                left=rate*32
                while left:
                    count=min(4096,left)
                    out.writeframesraw(block[:count*2].tobytes())
                    left-=count
        result=render(root/"a.wav",root/"b.wav",root/"mix.wav",
                      Recipe(family="echo_exit",beats=64,bpm=120))
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if result["frames"] != 1536000 or result["post_pcm_metrics"]["clipping_samples"]:
            raise SystemExit("Streaming proof output failed")
        if rss > 128*1024:
            raise SystemExit("Streaming child exceeds 128 MiB RSS gate")
        print(json.dumps({"scope":"synthetic-32s-48khz-stereo-streaming",
                          "frames":result["frames"],"output_sha256":result["output_sha256"],
                          "peak_rss_kib":rss,"duration_seconds":round(time.monotonic()-started,3),
                          "post_pcm_clipping_samples":result["post_pcm_metrics"]["clipping_samples"]}))

if __name__ == "__main__":
    main()
