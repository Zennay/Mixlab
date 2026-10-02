"""Bounded synthetic proof runner. Run only on the designated VPS Actions lane."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time


def main():
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    os.nice(10)
    started = time.monotonic()
    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=False)
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    (destination / "tests.log").write_text(result.stdout)
    print(result.stdout)
    if result.returncode:
        raise SystemExit(result.returncode)
    with tempfile.TemporaryDirectory(prefix="mixlab-proof-") as temporary:
        manifest = Path(temporary) / "library/library.json"
        pack = Path(temporary) / "pack"
        for args in (("fixture", manifest.parent), ("validate", manifest),
                     ("benchmark", manifest, pack, "--seed", "42")):
            subprocess.run([sys.executable, "-m", "mixlab", *map(str, args)], check=True, timeout=180)
        receipt = json.loads((pack / "receipt.json").read_text())
        wavs = sorted((pack / "review").glob("*.wav"))
        assert receipt["render_count"] == 4 and receipt["trial_count"] == 3 and len(wavs) == 6
        receipt.update({"tested_commit": os.environ.get("MIXLAB_SHA", "unknown"),
                        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local-unbound"),
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "children_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                        "test_result": "success", "evidence_scope": "synthetic-foundation-only",
                        "audio_sha256": [hashlib.sha256(p.read_bytes()).hexdigest() for p in wavs]})
        # Publish only sanitized metadata. No source paths, media or private answer keys.
        (destination / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
