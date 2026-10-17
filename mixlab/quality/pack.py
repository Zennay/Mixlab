"""Blind A/B review-pack quality preflight; never read the private answer key.

Inspect only neutral trial-###-{A,B}.wav pairs. All audio remains local.
Metrics are technical diagnostics, not proof of musical preference.
"""

from __future__ import annotations

from array import array
import argparse
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import wave

from . import MAX_SOURCE_BYTES, compare_wavs

_TRIAL_WAV = re.compile(r"^(trial-([0-9]{3}))-([AB])\.wav$")
MAX_TRIALS = 60
MAX_REVIEW_HTML_BYTES = 1024 * 1024
MAX_PUBLIC_RECEIPT_BYTES = 8192
# The shipped receipt contains only public binding/audit metadata.
# Unknown keys can accidentally serialize source paths or hidden answers.
_PUBLIC_RECEIPT_KEYS = frozenset({
    "schema_version", "pack_id", "trial_count", "render_count",
    "status", "manifest_sha256",
})
# Worst-case per-file limits alone permit 120 separate 32MiB inputs.
# Cap the whole pack *before* any PCM scans so a large private benchmark
# cannot monopolize a constrained shared worker.
MAX_REVIEW_PACK_BYTES = 512 * 1024 * 1024
MAX_REVIEW_PACK_FRAMES = 100_000_000
# Review pages are often passed to listeners as static files. Static
# resource references other than the expected A/B audio can phone home,
# reveal the listener identity or compromise offline study conditions.
_EMBED_ELEMENTS = frozenset({
    "iframe", "frame", "frameset", "object", "embed", "link", "base",
    "img", "picture", "source", "track", "video", "svg", "math",
})
_RESOURCE_ATTRIBUTES = frozenset({
    "href", "srcset", "action", "formaction", "poster", "background",
    "cite", "manifest", "xlink:href", "data",
})
# Playback manipulation in a custom listener page can bias A/B responses
# even when both audio src paths are local and correctly labelled.
_AUDIO_PLAYBACK_BIAS_ATTRIBUTES = frozenset({
    "autoplay", "muted", "loop",
})
_HIDDEN_LISTENER_ATTRIBUTES = frozenset({"hidden", "inert"})


class _ReviewPageLinks(HTMLParser):
    """Extract audio references without executing or exposing HTML content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current_trial = None
        self.trials = []
        self.audio_links = []
        self.pack_ids = []
        self.invalid_nesting = False
        self.unsafe_external_resource = False
        self._within_style = False

    def handle_starttag(self, tag, attrs):
        # HTMLParser preserves duplicate names in attrs, but dict() keeps
        # only the LAST value while browsers normally honor the FIRST.
        # Reject any ambiguity before trusting src/data-trial/pack-id.
        attributes = dict(attrs)
        if len(attributes) != len(attrs):
            self.unsafe_external_resource = True
        # HTMLParser lowercases element/attribute names. Do not whitelist
        # unknown resource-bearing tags or event-handler attributes.
        if (tag in _EMBED_ELEMENTS
                or any(k.startswith("on") or k in _RESOURCE_ATTRIBUTES
                       or k == "style" or k in _HIDDEN_LISTENER_ATTRIBUTES
                       for k in attributes)
                or (tag == "audio" and any(
                    k in _AUDIO_PLAYBACK_BIAS_ATTRIBUTES for k in attributes
                ))
                or (tag == "script" and (attributes or "src" in attributes))
                or (tag == "meta" and (attributes.get("http-equiv") or "").lower() == "refresh")
                or (tag != "audio" and "src" in attributes)):
            self.unsafe_external_resource = True
        if tag == "style":
            self._within_style = True
        if tag == "form":
            self.pack_ids.append(attributes.get("data-pack-id"))
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
        if tag == "style":
            self._within_style = False

    def handle_comment(self, data):
        # Public comments are not visible to listeners, but are readable in
        # source and can accidentally disclose the A/B answer key or tracks.
        # A frozen official listening form has no HTML comments.
        self.unsafe_external_resource = True

    def handle_pi(self, data):
        # Refuse browser-dependent/bogus processing instructions in a
        # purportedly neutral offline review page.
        self.unsafe_external_resource = True

    def handle_decl(self, decl):
        # The official template uses <!doctype html>; unexpected public
        # document declarations offer another opaque disclosure channel.
        if decl.strip().lower() != "doctype html":
            self.unsafe_external_resource = True

    def unknown_decl(self, data):
        # HTMLParser exposes CDATA and other marked sections here. Do not
        # silently treat their embedded text as an audited listener UI.
        self.unsafe_external_resource = True

    def handle_data(self, data):
        # External style sheets can also be introduced without a <link>.
        # This static check is not a substitute for a full JS/CSP audit.
        if self._within_style and ("@import" in data.lower() or "url(" in data.lower()):
            self.unsafe_external_resource = True


def _unique_public_json_object(pairs: list[tuple[str, object]]) -> dict:
    """Do not interpret a receipt whose duplicated JSON keys are ambiguous."""
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError("Public pack receipt contains duplicate JSON keys")
        parsed[key] = value
    return parsed


def _read_public_receipt_id(directory: Path, trial_count: int) -> str:
    """Read only the canonical sibling receipt, never the private answer key.

    This checks internal pack identity/coherence, not an authenticated
    signature or the correctness of the private trial answer key.
    """
    path = directory.parent / "receipt.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Official public pack receipt missing or linked")
    if path.stat().st_size > MAX_PUBLIC_RECEIPT_BYTES:
        raise ValueError("Official public pack receipt exceeds the size limit")
    try:
        receipt = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_public_json_object,
        )
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid official public pack receipt") from exc
    if not isinstance(receipt, dict):
        raise ValueError("Invalid official public pack receipt")
    if not receipt.keys() <= _PUBLIC_RECEIPT_KEYS:
        raise ValueError("Public pack receipt contains unexpected public fields")
    if ("render_count" in receipt
            and (type(receipt["render_count"]) is not int
                 or not 1 <= receipt["render_count"] <= 4 * MAX_TRIALS)):
        raise ValueError("Public pack receipt has invalid render count")
    if ("status" in receipt
            and receipt["status"] != "rendered-not-listener-validated"):
        raise ValueError("Public pack receipt has unexpected validation status")
    if ("manifest_sha256" in receipt
            and (not isinstance(receipt["manifest_sha256"], str)
                 or re.fullmatch(r"[0-9a-f]{64}", receipt["manifest_sha256"]) is None)):
        raise ValueError("Public pack receipt has invalid manifest fingerprint")
    pack_id = receipt.get("pack_id")
    if (receipt.get("schema_version") != 1
            or type(receipt.get("trial_count")) is not int
            or receipt["trial_count"] != trial_count
            or not isinstance(pack_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", pack_id) is None):
        raise ValueError("Public pack receipt does not match review trial inventory")
    return pack_id


def _verify_public_review_page(
    directory: Path, groups: dict[str, dict[str, Path]], *,
    require_generated_html: bool = False, expected_pack_id: str | None = None,
) -> bool:
    """Check generated review UI audio links against exactly the local trial WAVs.

    A missing index is allowed for audio-only QA. When it exists, all
    fieldsets/audio references must match the canonical blinding contract.
    """
    index = directory / "index.html"
    if not index.exists():
        return False
    if index.stat().st_size > MAX_REVIEW_HTML_BYTES:
        raise ValueError("Review page exceeds safe size")
    page_html = index.read_text(encoding="utf-8")
    checker = _ReviewPageLinks()
    checker.feed(page_html)
    checker.close()
    expected_trials = sorted(groups)
    expected_links = [(trial, f"{trial}-{label}.wav")
                      for trial in expected_trials for label in ("A", "B")]
    if (checker.unsafe_external_resource or checker.invalid_nesting
            or checker.trials != expected_trials
            or checker.audio_links != expected_links):
        raise ValueError("Review page audio links do not match the trial WAV inventory")
    if expected_pack_id is not None and checker.pack_ids != [expected_pack_id]:
        raise ValueError("Listener pack ID differs from the public benchmark receipt")
    if require_generated_html:
        # A static HTML resource check does not detect malicious inline JS.
        # Build the exact canonical offline template using only its *public*
        # pack_id and neutral trial IDs, then compare the entire HTML text.
        # No answer key, private recordings or source paths are opened.
        if (len(checker.pack_ids) != 1 or not isinstance(checker.pack_ids[0], str)
                or re.fullmatch(r"[0-9a-f]{64}", checker.pack_ids[0]) is None):
            raise ValueError("Review page lacks a canonical public pack identifier")
        from ..cli import write_review

        with tempfile.TemporaryDirectory(prefix="mixlab-quality-public-page-") as temp:
            reference = Path(temp) / "index.html"
            write_review(reference, expected_trials, checker.pack_ids[0])
            if reference.read_text(encoding="utf-8") != page_html:
                raise ValueError("Review page differs from the official offline generator")
    return True


def _verify_neutral_public_wav(path: Path) -> None:
    """Reject non-audio RIFF chunks and trailing payloads in public A/B WAVs.

    A normal PCM16 playback WAV needs only a standard fmt header and data.
    LIST/INFO, bext, JUNK and similar metadata can reveal hidden study
    labels/source identities to a reviewer inspecting public downloads.
    This reads chunk headers only; PCM remains in the bounded audio scanner.
    """
    size = path.stat().st_size
    if size < 44:
        # Preserve the established corrupt-header diagnostic for truncated
        # input, while enforcing a stricter *valid* public WAV container.
        raise ValueError("Invalid review WAV header")
    if size > MAX_SOURCE_BYTES:
        raise ValueError("Review public WAV exceeds canonical container bounds")
    with path.open("rb") as source:
        riff = source.read(12)
        if (len(riff) != 12 or riff[:4] != b"RIFF" or riff[8:] != b"WAVE"
                or int.from_bytes(riff[4:8], "little") + 8 != size):
            raise ValueError("Review public WAV has invalid RIFF bounds")
        block_align = None
        for expected in (b"fmt ", b"data"):
            chunk = source.read(8)
            if len(chunk) != 8 or chunk[:4] != expected:
                raise ValueError("Review public WAV contains unexpected RIFF chunks")
            length = int.from_bytes(chunk[4:8], "little")
            if ((expected == b"fmt " and length != 16)
                    or length > size - source.tell()):
                raise ValueError("Review public WAV has invalid PCM chunk bounds")
            if expected == b"fmt ":
                # wave.open() accepts inconsistent byte_rate/block_align.
                # Such headers can conceal metadata or play differently on
                # other clients despite valid-looking sample diagnostics.
                fmt = source.read(16)
                if len(fmt) != 16:
                    raise ValueError("Review public WAV has invalid PCM chunk bounds")
                encoding = int.from_bytes(fmt[0:2], "little")
                channels = int.from_bytes(fmt[2:4], "little")
                rate = int.from_bytes(fmt[4:8], "little")
                byte_rate = int.from_bytes(fmt[8:12], "little")
                block_align = int.from_bytes(fmt[12:14], "little")
                bits_per_sample = int.from_bytes(fmt[14:16], "little")
                if (encoding != 1 or channels not in (1, 2)
                        or not 8000 <= rate <= 96000
                        or bits_per_sample != 16
                        or block_align != 2 * channels
                        or byte_rate != rate * block_align):
                    raise ValueError("Review public WAV has inconsistent PCM format metadata")
            else:
                if length % block_align:
                    raise ValueError("Review public WAV has incomplete PCM frames")
                source.seek(length, 1)
        if source.tell() != size:
            raise ValueError("Review public WAV contains extra payload or metadata")


def _private_audio_fingerprint(path: Path, expected_metrics: dict) -> tuple[bytes, bytes | None]:
    """Identify repeated exact or channel-swapped playback PCM privately.

    Source format is included so the same sample bytes played at a different
    rate or channel layout do not create a false match. The streaming scanner
    already validated format and byte/frame limits before this private pass.
    """
    digest = hashlib.sha256()
    swapped_digest = hashlib.sha256() if expected_metrics["channels"] == 2 else None
    try:
        with wave.open(str(path), "rb") as source:
            channels, sample_width, rate, frames, compression, _ = source.getparams()
            if (channels != expected_metrics["channels"] or sample_width != 2
                    or rate != expected_metrics["sample_rate"]
                    or frames != expected_metrics["frames"] or compression != "NONE"):
                raise ValueError("Review audio changed during quality preflight")
            for number in (channels, rate, frames):
                format_bytes = number.to_bytes(4, "little")
                digest.update(format_bytes)
                if swapped_digest is not None:
                    swapped_digest.update(format_bytes)
            remaining = frames
            while remaining:
                count = min(4096, remaining)
                raw = source.readframes(count)
                if len(raw) != count * channels * sample_width:
                    raise ValueError("Review audio truncated during quality preflight")
                digest.update(raw)
                if swapped_digest is not None:
                    samples = array("h")
                    samples.frombytes(raw)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    reversed_stereo = array("h", samples)
                    reversed_stereo[::2] = samples[1::2]
                    reversed_stereo[1::2] = samples[::2]
                    if sys.byteorder != "little":
                        reversed_stereo.byteswap()
                    swapped_digest.update(reversed_stereo.tobytes())
                remaining -= count
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid review WAV") from exc
    return digest.digest(), swapped_digest.digest() if swapped_digest is not None else None


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Best-effort, non-cryptographic file identity across a scan.

    lstat (rather than stat) detects substitution with symlinks. Deliberate
    same-metadata tampering is outside this cooperative offline check.
    """
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inspect_review_pack(
    review_directory: str | Path, *, window_ms: int = 100,
    loudness_tolerance_db: float = 1.5, require_generated_html: bool = False,
    require_receipt: bool = False,
) -> dict:
    """Screen an immutable local review directory without looking up answers.

    Fail closed on malformed, incomplete, aliased or excessive WAV inventories.
    Do not return filenames, paths, source hashes or PCM window envelopes.
    """
    if not isinstance(require_generated_html, bool):
        raise ValueError("require_generated_html must be boolean")
    if not isinstance(require_receipt, bool):
        raise ValueError("require_receipt must be boolean")
    directory = Path(review_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Review input must be a real directory, not a symlink")
    groups: dict[str, dict[str, Path]] = {}
    total_wav_bytes = 0
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
        total_wav_bytes += entry.stat().st_size
        if total_wav_bytes > MAX_REVIEW_PACK_BYTES:
            raise ValueError("Review WAV inventory exceeds total byte budget")
        trial_id, _, label = match.groups()
        labels = groups.setdefault(trial_id, {})
        if label in labels:
            raise ValueError("Review directory contains a duplicate trial label")
        labels[label] = entry
        if len(groups) > MAX_TRIALS:
            raise ValueError("Review directory exceeds the trial limit")
    if not groups:
        raise ValueError("Review directory contains no trial WAV pairs")
    # The canonical benchmark and rating aggregation use trial-001, -002,
    # ... with no gaps. A partially copied pack can otherwise look complete
    # if its public receipt trial count has also been modified.
    expected_trial_ids = [f"trial-{index:03d}" for index in range(1, len(groups) + 1)]
    if sorted(groups) != expected_trial_ids:
        raise ValueError("Review trial identifiers are not a contiguous sequence")
    if any(set(labels) != {"A", "B"} for labels in groups.values()):
        raise ValueError("Review directory contains an incomplete trial WAV pair")
    # Freeze the public file inventory *before* reading headers, the page or
    # the public receipt. A listener pack must not gain private files during
    # the scan, even if all previously present audio remains byte-identical.
    # This is a cooperative best-effort snapshot, not an atomic filesystem
    # transaction or a cryptographic signature.
    before_inventory = {entry.name: _file_identity(entry) for entry in directory.iterdir()}
    before_directory = _file_identity(directory)
    receipt_path = directory.parent / "receipt.json" if require_receipt else None
    if receipt_path is not None and (receipt_path.is_symlink() or not receipt_path.is_file()):
        raise ValueError("Official public pack receipt missing or linked")
    before_receipt = _file_identity(receipt_path) if receipt_path is not None else None

    # Headers are cheap to read. Bound the total *declared* frame workload
    # before expensive sample-level diagnostics. scan_wav still independently
    # verifies every declared frame and rejects truncated input.
    total_frames = 0
    try:
        for labels in groups.values():
            for path in labels.values():
                _verify_neutral_public_wav(path)
                with wave.open(str(path), "rb") as src:
                    total_frames += src.getnframes()
                if total_frames > MAX_REVIEW_PACK_FRAMES:
                    raise ValueError("Review WAV inventory exceeds total frame budget")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid review WAV header") from exc
    expected_pack_id = _read_public_receipt_id(directory, len(groups)) if require_receipt else None
    page_links_verified = _verify_public_review_page(
        directory, groups, require_generated_html=require_generated_html,
        expected_pack_id=expected_pack_id,
    )
    if (require_generated_html or require_receipt) and not page_links_verified:
        raise ValueError("Official listener page missing from review pack")
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
        repeated_from_other_trial = False
        for label in ("A", "B"):
            digest, swapped_digest = _private_audio_fingerprint(labels[label], (
                result["baseline"] if label == "A" else candidate["metrics"]
            ))
            previous = seen_audio.get(digest)
            # A reversed L/R reference is recognizably reused audio too.
            # The private format-bound swapped fingerprint never leaves QA.
            # Exact equality takes precedence for dual-mono files.
            if previous is None and swapped_digest is not None:
                previous = seen_audio.get(swapped_digest)
            if previous is not None:
                # Duplicate A/B within the same trial is already reported by
                # compare_wavs; only repetition in *different* trials counts.
                if not previous.startswith(trial_id + "/"):
                    # Never expose *which side* repeats: a QA report could
                    # otherwise defeat the very A/B blinding it audits.
                    repeated_from_other_trial = True
                    cross_trial_repeated_variant_count += 1
            else:
                seen_audio[digest] = f"{trial_id}/{label}"
        trial_warnings = (["repeated_pcm_across_trials_inspect_blinding"]
                          if repeated_from_other_trial else [])
        flagged = bool(warnings["A"] or warnings["B"] or trial_warnings)
        warning_trial_count += flagged
        trials.append({
            "trial_id": trial_id,
            "A": {"metrics": result["baseline"], "warnings": warnings["A"]},
            "B": {"metrics": candidate["metrics"], "warnings": warnings["B"]},
            "B_minus_A_rms_db": candidate["rms_delta_db_vs_baseline"],
            "short_window_level_mismatch_fraction": candidate["short_window_level_mismatch_fraction"],
            "short_window_level_mismatch_risk": candidate["short_window_level_mismatch_risk"],
            "identical_pcm": candidate["duplicate_pcm_of"] == "baseline",
            "trial_warnings": trial_warnings,
            "technical_warnings_present": flagged,
        })
    # Comparing every filename AND identity catches an answer key, extra WAV,
    # or other unexpected listener-visible asset inserted mid-scan. Snapshot
    # the directory itself too so rename/replace operations cannot silently
    # exchange the reviewed pack. Receipt checks are opt-in as before.
    after_inventory = {entry.name: _file_identity(entry) for entry in directory.iterdir()}
    if (after_inventory != before_inventory
            or _file_identity(directory) != before_directory
            or (receipt_path is not None and _file_identity(receipt_path) != before_receipt)):
        raise ValueError("Review pack files changed during quality preflight")
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
        "official_generated_html_verified": require_generated_html,
        "public_receipt_pack_id_verified": require_receipt,
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
    parser.add_argument(
        "--require-generated-html", action="store_true",
        help="Reject any modified listener page, including changed inline scripts",
    )
    parser.add_argument(
        "--require-receipt", action="store_true",
        help="Bind the review form pack ID and trial count to the sibling receipt.json",
    )
    args = parser.parse_args()
    try:
        result = inspect_review_pack(
            args.review_directory, window_ms=args.window_ms,
            loudness_tolerance_db=args.loudness_tolerance_db,
            require_generated_html=args.require_generated_html,
            require_receipt=args.require_receipt,
        )
    except (OSError, ValueError):
        parser.exit(3, "review quality preflight: invalid or unreadable pack (details withheld)\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 2 if args.fail_on_warnings and result["warning_trial_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
