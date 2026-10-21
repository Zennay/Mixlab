"""Private, re-openable cue-review session manifest admission.

The session is a small *local* list of relative PCM16/receipt pairs, never an
import from URLs or a permission grant. Its paths and contents are not copied
into HTML; no files or media are modified by reading it.
"""
from __future__ import annotations

from pathlib import Path

from ..evaluation.json_admission import load_bounded_json

MAX_SESSION_PAIRS = 8
MAX_RELATIVE_PATH = 240


def _local_relative(root: Path, raw: str) -> str:
    """Only canonical relative paths within the manifest's local directory."""
    if (not isinstance(raw, str) or not 1 <= len(raw) <= MAX_RELATIVE_PATH
            or "\\" in raw or ":" in raw or any(ord(ch) < 32 for ch in raw)):
        raise ValueError("Invalid private session path")
    parts = raw.split("/")
    if (any(part in ("", ".", "..") for part in parts) or
            raw.startswith("/") or any(len(part) > 100 for part in parts)):
        raise ValueError("Private session paths must be local and canonical")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Private session path cannot contain symlinks")
    return str(current)


def load_session(path):
    """Resolve an exact private manifest into eight or fewer source/receipt pairs."""
    manifest = load_bounded_json(path)
    if (not isinstance(manifest, dict) or set(manifest) !=
            {"schema_version", "kind", "pairs"} or
            type(manifest["schema_version"]) is not int or
            manifest["schema_version"] != 1 or
            manifest["kind"] != "private_cue_review_session"):
        raise ValueError("Invalid private cue session schema")
    entries = manifest["pairs"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_SESSION_PAIRS:
        raise ValueError("Private session must contain one to eight pairs")
    root = Path(path).absolute().parent
    pairs = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"wav", "receipt"}:
            raise ValueError("Invalid private session pair")
        wav = _local_relative(root, item["wav"])
        receipt = _local_relative(root, item["receipt"])
        if wav == receipt or wav in seen or receipt in seen:
            raise ValueError("Private session source or receipt repeated")
        seen.update((wav, receipt))
        pairs.append((wav, receipt))
    return pairs
