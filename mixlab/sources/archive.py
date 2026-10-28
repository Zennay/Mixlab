"""Fetch Creative Commons dance tracks from the Internet Archive netlabel collection.

Only licenses that allow adapted material to be shared are admitted (BY,
BY-SA, BY-NC, BY-NC-SA); ND and sampling licenses are rejected because a
rendered transition is an adaptation. One track per release and per creator
keeps the set diverse. Each download is checked against the archive's SHA-1,
then ffmpeg decodes one excerpt to PCM16 WAV. The license declaration is
taken from the item's metadata as published; it is provenance, not a legal
verification of the uploader's rights.

python3 -m mixlab.sources.archive /private/library --tracks 40
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.parse

SEARCH = "https://archive.org/advancedsearch.php"
METADATA = "https://archive.org/metadata/"
DOWNLOAD = "https://archive.org/download/"
QUERY = ('collection:netlabels AND subject:(house OR techno OR "tech house" OR "deep house" '
         'OR "minimal techno" OR disco) AND licenseurl:*creativecommons*')
LICENSE = re.compile(r"creativecommons\.org/licenses/(by|by-sa|by-nc|by-nc-sa)/(\d\.\d)", re.I)
EXCLUDE_SUBJECTS = re.compile(r"\b(mix|mixed|dj ?set|live set|podcast|ambient|noise|breakcore)\b", re.I)
MAX_DOWNLOAD = 40 * 1024 * 1024
MIN_SECONDS, MAX_SECONDS = 150, 720
EXCERPT_SECONDS = 45
RATE = 44100


def _curl_json(url, attempts=3):
    for attempt in range(attempts):
        result = subprocess.run(["curl", "-sS", "--fail", "--max-time", "60", url],
                                capture_output=True)
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except ValueError:
                pass
        time.sleep(2 * (attempt + 1))
    raise ValueError("Archive request failed")


def license_of(url):
    match = LICENSE.search(url or "")
    return (match.group(1).lower(), match.group(2)) if match else None


def search(pages=10, rows=100, query=QUERY, sort="identifier asc"):
    items = []
    for page in range(1, pages + 1):
        params = urllib.parse.urlencode([("q", query), ("fl[]", "identifier"), ("fl[]", "creator"),
                                         ("fl[]", "licenseurl"), ("fl[]", "subject"), ("fl[]", "title"),
                                         ("sort[]", sort), ("rows", rows), ("page", page),
                                         ("output", "json")])
        docs = _curl_json(f"{SEARCH}?{params}")["response"]["docs"]
        items.extend(docs)
        if len(docs) < rows:
            break
    return items


def admissible(item):
    subjects = item.get("subject") or []
    subjects = " ".join(subjects if isinstance(subjects, list) else [subjects])
    return (license_of(item.get("licenseurl")) is not None and item.get("creator")
            and not EXCLUDE_SUBJECTS.search(subjects + " " + str(item.get("title", ""))))


def pick_track(identifier):
    """First original MP3 of plausible single-track length, with its published SHA-1."""
    meta = _curl_json(METADATA + identifier)
    for f in sorted(meta.get("files", []), key=lambda f: f.get("name", "")):
        name = f.get("name", "")
        try:
            length, size = float(f.get("length", 0)), int(f.get("size", 0))
        except (TypeError, ValueError):
            continue
        if (name.lower().endswith(".mp3") and f.get("source") == "original" and "/" not in name
                and MIN_SECONDS <= length <= MAX_SECONDS and 0 < size <= MAX_DOWNLOAD and f.get("sha1")):
            return meta["metadata"], name, length, f["sha1"]
    return None


def download(identifier, name, sha1, target):
    url = DOWNLOAD + identifier + "/" + urllib.parse.quote(name)
    result = subprocess.run(["curl", "-sS", "--fail", "-L", "--max-time", "300",
                             "--max-filesize", str(MAX_DOWNLOAD), "-o", str(target), url],
                            capture_output=True)
    if result.returncode != 0:
        raise ValueError("Download failed")
    digest = hashlib.sha1(target.read_bytes()).hexdigest()
    if digest != sha1:
        target.unlink(missing_ok=True)
        raise ValueError("Downloaded file does not match the archive SHA-1")
    return url


def excerpt(source, target, start, seconds=EXCERPT_SECONDS):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{start:.3f}", "-t", str(seconds),
                    "-i", str(source), "-map_metadata", "-1", "-ac", "2", "-ar", str(RATE),
                    "-c:a", "pcm_s16le", "-f", "wav", str(target)], check=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(destination, tracks=40, pages=10, query=QUERY, sort="identifier asc"):
    """Add up to `tracks` new tracks; an existing library is extended, never rewritten."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "originals").mkdir(exist_ok=True)
    (root / "excerpts").mkdir(exist_ok=True)
    index_path = root / "sources.json"
    records = json.loads(index_path.read_text())["tracks"] if index_path.exists() else []
    known = {r["item_url"].rsplit("/", 1)[-1] for r in records}
    creators = {str(r["creator"]).strip().lower() for r in records}
    added = 0
    for item in search(pages, query=query, sort=sort):
        if added >= tracks:
            break
        creator = str(item["creator"]).strip().lower() if admissible(item) else None
        if not creator or creator in creators or item["identifier"] in known:
            continue
        try:
            picked = pick_track(item["identifier"])
            if picked is None:
                continue
            metadata, name, length, sha1 = picked
            index = len(records) + 1
            original = root / "originals" / f"ia-{index:03d}.mp3"
            url = download(item["identifier"], name, sha1, original)
            wav = root / "excerpts" / f"ia-{index:03d}.wav"
            # Skip intros: start a third into the track, inside the main groove.
            start = round(min(length / 3, length - EXCERPT_SECONDS - 5), 3)
            excerpt(original, wav, start)
        except (ValueError, subprocess.CalledProcessError, KeyError):
            continue
        kind, version = license_of(item["licenseurl"])
        creators.add(creator)
        added += 1
        records.append({
            "id": f"ia-{index:03d}", "excerpt": f"excerpts/{wav.name}", "excerpt_sha256": sha256(wav),
            "excerpt_start_seconds": start, "excerpt_seconds": EXCERPT_SECONDS,
            "identifier": item["identifier"], "source_url": url, "item_url": f"https://archive.org/details/{item['identifier']}",
            "source_sha1": sha1, "source_seconds": length, "file": name,
            "title": metadata.get("title"), "creator": item["creator"],
            "license": f"CC {kind.upper()} {version}", "license_url": item["licenseurl"],
        })
    temporary = index_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema_version": 1, "source": "archive.org netlabels",
                                     "tracks": records}, indent=2, sort_keys=True))
    os.replace(temporary, index_path)
    credits = [f"- {r['creator']}: \"{r['title']}\" ({r['file']}), {r['license']} {r['license_url']}, "
               f"{r['item_url']}" for r in records]
    (root / "CREDITS.md").write_text("# Credits\n\nExcerpts used for private MixLab listening tests.\n\n"
                                     + "\n".join(credits) + "\n")
    return records


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Fetch CC-licensed dance tracks from archive.org")
    parser.add_argument("destination", help="private directory outside the repository")
    parser.add_argument("--tracks", type=int, default=40)
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--query", default=QUERY, help="archive.org advanced-search query")
    parser.add_argument("--sort", default="identifier asc", help='e.g. "downloads desc"')
    args = parser.parse_args(argv)
    if Path(args.destination).resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.exit(2, "MixLab sources: keep media outside the repository checkout\n")
    records = fetch(args.destination, args.tracks, args.pages, args.query, args.sort)
    print(json.dumps({"tracks": len(records)}))


if __name__ == "__main__":
    main()
