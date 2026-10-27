import argparse
import json
from . import EnergyOnsetProvider, analyze_cached
parser = argparse.ArgumentParser(description="Propose a regular beatgrid from a bounded private PCM16 clip")
parser.add_argument("wav")
parser.add_argument("--cache", required=True)
args = parser.parse_args()
try:
    result = analyze_cached(args.wav, args.cache, EnergyOnsetProvider())
except (OSError, ValueError, TypeError) as exc:
    parser.exit(2, f"MixLab analysis: {exc}\n")
print(json.dumps(result, allow_nan=False, sort_keys=True))
