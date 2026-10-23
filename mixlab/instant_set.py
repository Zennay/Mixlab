"""One-command, rights-bound continuous WAV export from a prepared DJ Studio.

Select an explicit default transition family with optional per-pair choices
and compile the entire registered ordered playlist, including chapter player.
Uses the canonical export_set receipts, not an alternate DSP/audio pipeline.
"""
from __future__ import annotations

import argparse
import json
import wave
import subprocess

from .cueprep import _read_spec
from .set_composer import _session_catalog
from .set_export import export_set
from .set_player import publish_player
from .studio import FAMILY_NAMES


def _choose_transitions(session, family, overrides):
    root, catalog = _session_catalog(session)
    if family not in FAMILY_NAMES:
        raise ValueError("Choose an existing M1 transition family")
    if not isinstance(overrides, (tuple, list)) or len(overrides) > 10:
        raise ValueError("At most ten explicit pair-specific choices are allowed")
    source = _read_spec(root / "sources" / "source_manifest.json")
    registered = source.get("pairs")
    if not isinstance(registered, list) or not 1 <= len(registered) <= 10:
        raise ValueError("A full DJ set requires 1..10 registered transition pairs")
    available = {p["id"]: p for p in catalog["pairs"]}
    # Do not silently produce a short mix if a Studio was rendered for
    # only one of several registered pairs.
    if len(registered) != len(available):
        raise ValueError("Session does not contain real rendered auditions for every registered pair")
    choices = {}
    for value in overrides:
        if not isinstance(value, str) or value.count(":") != 1:
            raise ValueError("Use --style PAIR_ID:FAMILY")
        pair, requested = value.split(":", 1)
        if pair not in available or requested not in FAMILY_NAMES or pair in choices:
            raise ValueError("Unknown, duplicate or unsupported pair-specific family")
        choices[pair] = requested
    if choices.keys() - set(available):
        raise ValueError("Unknown transition pair in overrides")
    result, visited = [], set()
    last_incoming = None
    for pair in registered:
        if not isinstance(pair, dict):
            raise ValueError("Corrupt source transition list")
        pid, a, b = pair.get("id"), pair.get("a"), pair.get("b")
        if pid not in available or a != available[pid]["a"] or b != available[pid]["b"]:
            raise ValueError("Registered transition does not match the rendered Studio")
        if last_incoming is not None and a != last_incoming:
            raise ValueError(
                "Registered pairs do not follow a continuous route. "
                "Use the interactive Set Composer to choose a connected path.")
        if a in visited or a == b or b in visited:
            raise ValueError("Full automatic playlist export cannot revisit already played tracks")
        selected = choices.get(pid, family)
        if selected not in available[pid]["families"]:
            raise ValueError("Requested family has no real rendered audio for transition " + str(pid))
        result.append(str(pid) + ":" + selected)
        visited.add(a)
        last_incoming = b
    if last_incoming in visited:
        raise ValueError("Full playlist ends in an already visited song")
    return root, result


def render_instant_set(session, new_wav, *, family="bass_swap", styles=(),
                       delivery=None, bitrate_kbps=192):
    """Render a complete user-selected family pattern from official audio."""
    root, selected = _choose_transitions(session, family, styles)
    wav = export_set(root, new_wav, selected)
    response = {"continuous_set": str(wav),
                "receipt": str(wav) + ".receipt.private.json",
                "track_count": len(selected) + 1,
                "transitions": selected, "offline_player": None,
                "private": True, "automatic_track_discovery": False,
                "human_preference_proven": False}
    # Publication of the real full-set WAV is durable; a browser failure
    # must not remove it or disguise that it was successfully exported.
    try:
        response["offline_player"] = str(publish_player(root, wav))
    except (OSError, ValueError, KeyError, TypeError, wave.Error) as exc:
        response["player_warning"] = "Completed WAV exists; optional HTML player unavailable: " + str(exc)
    if delivery is not None:
        try:
            from .delivery import export_delivery
            response["compressed_delivery"] = export_delivery(
                root, wav, delivery, bitrate_kbps=bitrate_kbps)
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            response["delivery_warning"] = (
                "Completed PCM16 WAV exists; optional MP3/FLAC delivery unavailable: " + str(exc))
    return response


def main():
    parser = argparse.ArgumentParser(
        description="Export all registered private playlist songs as one continuous rendered WAV")
    parser.add_argument("session", help="Existing complete private M1 Studio session")
    parser.add_argument("new_wav", help="New output WAV outside source session/Git")
    parser.add_argument("--family", choices=tuple(FAMILY_NAMES), default="bass_swap",
                        help="Explicit transition family for all pairs unless overridden")
    parser.add_argument("--style", action="append", default=[], metavar="PAIR:FAMILY",
                        help="Override the transition family for one registered pair; repeatable")
    parser.add_argument("--delivery", help="Optional NEW local .mp3 or .flac with bound private receipt")
    parser.add_argument("--bitrate-kbps", type=int, choices=(128, 192, 256, 320),
                        default=192, help="MP3 encoding bitrate; FLAC is lossless")
    args = parser.parse_args()
    try:
        result = render_instant_set(args.session, args.new_wav,
                                    family=args.family, styles=args.style,
                                    delivery=args.delivery, bitrate_kbps=args.bitrate_kbps)
    except (ValueError, KeyError, TypeError, OSError, wave.Error) as exc:
        parser.exit(2, "MixLab Instant Set: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
