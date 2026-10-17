"""CLI: python -m mixlab.quality baseline.wav candidate1.wav [candidate2.wav]."""

import argparse
import json
from . import compare_wavs


class _PrivateArgumentParser(argparse.ArgumentParser):
    """Never include caller-supplied paths or values in parser diagnostics.

    argparse's default errors quote unknown positional arguments and invalid
    option values verbatim. CLI arguments often contain private track names,
    so a CI preflight must redact errors *before* WAV validation runs.
    """

    def error(self, message):
        self.exit(2, "quality preflight: invalid command-line arguments (details withheld)\n")


def main():
    parser = _PrivateArgumentParser(description="Offline technical preflight; NOT a musical-quality ranking")
    parser.add_argument("baseline", help="Local PCM16 WAV baseline")
    parser.add_argument("candidates", nargs="+", help="Local PCM16 WAV candidate(s)")
    parser.add_argument("--window-ms", type=int, default=100)
    parser.add_argument("--loudness-tolerance-db", type=float, default=1.5)
    parser.add_argument(
        "--fail-on-warnings", action="store_true",
        help="Exit 2 on any baseline/candidate warning (optional technical CI gate, not a music score)",
    )
    args = parser.parse_args()
    try:
        report = compare_wavs(args.baseline, args.candidates,
                              window_ms=args.window_ms,
                              loudness_tolerance_db=args.loudness_tolerance_db)
    except (OSError, ValueError):
        # Exception messages (and Python tracebacks) may expose private WAV
        # paths. Never echo exception text to shared CI or shell logs.
        parser.exit(3, "quality preflight: invalid or unreadable WAV input (details withheld)\n")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    if args.fail_on_warnings and (
        report["baseline_warnings"] or any(row["warnings"] for row in report["candidates"])
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
