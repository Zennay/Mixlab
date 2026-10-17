"""Blind A/B review-pack quality preflight; never read the private answer key.

Inspect only neutral trial-###-{A,B}.wav pairs. All audio remains local.
Metrics are technical diagnostics, not proof of musical preference.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import wave

from . import compare_wavs

_TRIAL_WAV = re.compile(r"^(trial-([0-9]{3}))-([AB])\.wav$")
MAX_TRIALS = 60
MAX_REVIEW_HTML_BYTES = 1024 * 1024


class _ReviewPageLinks(HTMLParser):
    """Extract audio references without executing or exposing HTML content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current_trial = None
        self.trials = []
        self.audio_links = []
        self.invalid_nesting = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "fieldset":
            if self.current_trial is not None:
                self.invalid_nesting = True
            self.current_trial = attributes.get("data-trial")
            self.trials.append(self.current_trial)
        elif tag == "audio":
            self.audio_links.append((self.current_trial, attributes.get("src")))

    def handle_endtag(self, tag):
        if tag == "fieldset":
            self.current_trial = None


def _verify_public_review_page(directory: Path, groups: dict[str, dict[str, Path]]) -> bool:
    """Check generated review UI audio links against exactly the local trial WAVs.

    A missing index is allowed for audio-only QA. When it exists, all
    fieldsets/audio references must match the canonical blinding contract.
    """
    index = directory / "index.html"
    if not index.exists():
        return False
    if index.stat().st_size > MAX_REVIEW_HTML_BYTES:
        raise ValueError("Review page exceeds safe size")
    checker = _ReviewPageLinks()
    checker.feed(index.read_text(encoding="utf-8"))
    checker.close()
    expected_trials = sorted(groups)
    expected_links = [(trial, f"{trial}-{label}.wav")
                      for trial in expected_trials for label in ("A", "B")]
    if (checker.invalid_nesting or checker.trials != expected_trials
            or checker.audio_links != expected_links):
        raise ValueError("Review page audio links do not match the trial WAV inventory")
    return True


def _private_audio_fingerprint(path: Path, expected_metrics: dict) -> bytes:
    """Identify repeated *playback PCM* without exporting an audio fingerprint.

    Source format is included so the same sample bytes played at a different
    rate or channel layout do not create a false match. The streaming scanner
    already validated format and byte/frame limits before this private pass.
    """
    digest = hashlib.sha256()
    try:
        with wave.open(str(path), "rb") as source:
            channels, sample_width, rate, frames, compression, _ = source.getparams()
            if (channels != expected_metrics["channels"] or sample_width != 2
                    or rate != expected_metrics["sample_rate"]
                    or frames != expected_metrics["frames"] or compression != "NONE"):
                raise ValueError("Review audio changed during quality preflight")
            for number in (channels, rate, frames):
                digest.update(number.to_bytes(4, "little"))
            remaining = frames
            while remaining:
                count = min(4096, remaining)
                raw = source.readframes(count)
                if len(raw) != count * channels * sample_width:
                    raise ValueError("Review audio truncated during quality preflight")
                digest.update(raw)
                remaining -= count
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid review WAV") from exc
    return digest.digest()


def inspect_review_pack(
    review_directory: str | Path, *, window_ms: int = 100,
    loudness_tolerance_db: float = 1.5,
) -> dict:
    """Screen an immutable local review directory without looking up answers.

    Fail closed on malformed, incomplete, aliased or excessive WAV inventories.
    Do not return filenames, paths, source hashes or PCM window envelopes.
    """
    directory = Path(review_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Review input must be a real directory, not a symlink")
    groups: dict[str, dict[str, Path]] = {}
    for entry in directory.iterdir():
        # The review directory may be served to a listener. Reject leaked
        # answer keys, manifests, downloads or other unexpected assets, even
        # when they are not audio. Only the generated index is public.
        if entry.name == "index.html":
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("Review index must be a regular file")
            continue
        if entry.suffix.lower() != ".wav":
            raise ValueError("Review directory contains an unexpected public asset")
        match = _TRIAL_WAV.fullmatch(entry.name)
        if match is None or int(match.group(2)) == 0:
            raise ValueError("Review directory contains an unexpected WAV filename")
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("Review WAV must be a regular file, not a symlink")
        trial_id, _, label = match.groups()
        labels = groups.setdefault(trial_id, {})
        if label in labels:
            raise ValueError("Review directory contains a duplicate trial label")
        labels[label] = entry
        if len(groups) > MAX_TRIALS:
            raise ValueError("Review directory exceeds the trial limit")
    if not groups:
        raise ValueError("Review directory contains no trial WAV pairs")
    if any(set(labels) != {"A", "B"} for labels in groups.values()):
        raise ValueError("Review directory contains an incomplete trial WAV pair")
    page_links_verified = _verify_public_review_page(directory, groups)

    trials = []
    warning_trial_count = 0
    cross_trial_repeated_variant_count = 0
    seen_audio: dict[bytes, str] = {}
    for trial_id, labels in sorted(groups.items()):
        result = compare_wavs(
            labels["A"], [labels["B"]], window_ms=window_ms,
            loudness_tolerance_db=loudness_tolerance_db,
        )
        candidate = result["candidates"][0]
        warnings = {
            "A": result["baseline_warnings"],
            "B": candidate["warnings"],
        }
        # A/B designation has no relationship to baseline/candidate assignment:
        # packaging randomization stays blinded and no private key is opened.
        if candidate["duplicate_pcm_of"] == "baseline":
            warnings["B"] = [
                "identical_pcm_between_A_and_B" if w == "identical_pcm_to_baseline_inspect_for_noop" else w
                for w in warnings["B"]
            ]
        # Repeating an identical reference across independently randomized
        # trials can reveal its identity through recognition. This is an
        # inspect-for-blinding warning, not a claim that the answers leaked.
        # A/B-neutral references are safe; fingerprints never leave memory.
        earlier_audio = {}
        for label in ("A", "B"):
            digest = _private_audio_fingerprint(labels[label], (
                result["baseline"] if label == "A" else candidate["metrics"]
            ))
            previous = seen_audio.get(digest)
            if previous is not None:
                # Duplicate A/B within the same trial is already reported by
                # compare_wavs; only repetition in *different* trials counts.
                if not previous.startswith(trial_id + "/"):
                    warnings[label].append("repeated_pcm_across_trials_inspect_blinding")
                    earlier_audio[label] = previous
                    cross_trial_repeated_variant_count += 1
            else:
                seen_audio[digest] = f"{trial_id}/{label}"
        flagged = bool(warnings["A"] or warnings["B"])
        warning_trial_count += flagged
        trials.append({
            "trial_id": trial_id,
            "A": {"metrics": result["baseline"], "warnings": warnings["A"]},
            "B": {"metrics": candidate["metrics"], "warnings": warnings["B"]},
            "B_minus_A_rms_db": candidate["rms_delta_db_vs_baseline"],
            "short_window_level_mismatch_fraction": candidate["short_window_level_mismatch_fraction"],
            "short_window_level_mismatch_risk": candidate["short_window_level_mismatch_risk"],
            "identical_pcm": candidate["duplicate_pcm_of"] == "baseline",
            "cross_trial_repeated_pcm_of": earlier_audio,
            "technical_warnings_present": flagged,
        })
    return {
        "schema_version": 1,
        "purpose": "blind_review_technical_preflight_not_musical_quality",
        "analysis_method": "streaming_pcm16_rms_not_lufs",
        "trial_count": len(trials),
        "warning_trial_count": warning_trial_count,
        "cross_trial_repeated_variant_count": cross_trial_repeated_variant_count,
        "human_preference_test_required": True,
        "answer_key_opened": False,
        "review_page_audio_links_verified": page_links_verified,
        "contains_source_paths_hashes_or_audio": False,
        "trials": trials,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect neutral A/B review WAVs without opening a private answer key"
    )
    parser.add_argument("review_directory", help="Directory containing trial-###-[AB].wav")
    parser.add_argument("--window-ms", type=int, default=100)
    parser.add_argument("--loudness-tolerance-db", type=float, default=1.5)
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_review_pack(
            args.review_directory, window_ms=args.window_ms,
            loudness_tolerance_db=args.loudness_tolerance_db,
        )
    except (OSError, ValueError):
        parser.exit(3, "review quality preflight: invalid or unreadable pack (details withheld)\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 2 if args.fail_on_warnings and result["warning_trial_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
