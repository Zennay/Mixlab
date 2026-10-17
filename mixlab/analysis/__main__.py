import argparse
import json
from . import EnergyOnsetProvider, analyze_cached
from .key import ChromaKeyProvider
PROVIDERS = {"energy-onset": EnergyOnsetProvider, "chroma-key": ChromaKeyProvider}
parser = argparse.ArgumentParser(description="Propose a regular beatgrid or global key from a bounded private PCM16 clip")
parser.add_argument("wav")
parser.add_argument("--cache", required=True)
parser.add_argument("--provider", choices=sorted(PROVIDERS), default="energy-onset")
args = parser.parse_args()
try:
    result = analyze_cached(args.wav, args.cache, PROVIDERS[args.provider]())
except (OSError, ValueError, TypeError) as exc:
    parser.exit(2, f"MixLab analysis: {exc}\n")
print(json.dumps(result, allow_nan=False, sort_keys=True))
