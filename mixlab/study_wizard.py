"""Guided private M1 study from a permitted library to real blind A/B WAVs.

Explicit human decisions, no source uploads, model downloads or rights inference.
All review forms remain private; real listener evidence is NOT collected here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from .evaluation.candidates import build_candidates
from .evaluation.study import freeze, write_exclusive
from .evaluation.study_pack import build as build_pack, verify_study_pack
from .evaluation import verify_pack
from .study_alignment import prepare as prepare_cues, apply as approve_cues
from .study_key_review import prepare as prepare_keys, apply as approve_keys
from .evaluation.study import KEYS


def _private_dir(value):
    folder = Path(value).absolute()
    if folder.exists() or folder.is_symlink():
        raise ValueError('Study output folder already exists')
    for part in (folder.parent, *folder.parent.parents):
        if part.is_symlink() or (part / '.git').exists():
            raise ValueError('Private output may not be inside Git or a symbolic link')
    if not folder.parent.is_dir():
        raise ValueError('Private destination parent missing')
    folder.mkdir(mode=0o700)
    return folder


def _new_json(path, document):
    write_exclusive(path, document)


MAX_INPUT_ATTEMPTS = 3


def _answer(ask, message, allowed, *, retry=False):
    """Retry non-approval choices; consent/rights confirmation is one-shot."""
    attempts = MAX_INPUT_ATTEMPTS if retry else 1
    for attempt in range(attempts):
        prompt = message if attempt == 0 else 'Invalid choice; try again: ' + message
        value = ask(prompt).strip()
        if value in allowed:
            return value
    raise ValueError('Unrecognized decision; no music or approvals were inferred')


def _number(ask, label, lower, upper, integer=False):
    """Give operators limited chances to correct cues, not approvals."""
    import math
    for attempt in range(MAX_INPUT_ATTEMPTS):
        prompt = label if attempt == 0 else 'Invalid cue value; try again: ' + label
        raw = ask(prompt).strip()
        try:
            value = int(raw) if integer else float(raw)
        except (ValueError, OverflowError):
            continue
        if (math.isfinite(value) and lower <= value <= upper and
                (not integer or str(value) == raw)):
            return value
    raise ValueError('Cue value is invalid after three attempts')


def _key_review(ask, draft, destination):
    document = json.loads(draft.read_text())
    for number, row in enumerate(document['keys'], 1):
        index = f'{number}/{len(document["keys"])}'
        can_accept = row['proposed_source'] == 'measured-heuristic' and row['proposed_key'] is not None
        options = {'a', 'o', 'u'} if can_accept else {'o', 'u'}
        choices = '[a]ccept measured, [o]verride, [u]nknown' if can_accept else '[o]verride, [u]nknown'
        action = _answer(ask, f"Source {index} · {row['id']} · proposed key {row['proposed_key'] or 'unknown'} ({row['proposed_source']}); {choices}: ", options, retry=True)
        if action == 'a':
            if row['proposed_source'] != 'measured-heuristic' or row['proposed_key'] is None:
                raise ValueError('No measured key to accept; choose override or unknown')
            row['decision'] = 'accept'
            row['confirmed_key'] = row['proposed_key']
        elif action == 'o':
            key = _answer(ask, f"Enter independently checked major/minor key for {row['id']} (e.g. C major): ", KEYS, retry=True)
            row['decision'] = 'override'
            row['confirmed_key'] = key
        else:
            row['decision'] = 'unavailable'
            row['confirmed_key'] = None
        if _answer(ask, f"Have you personally checked this decision for {row['id']}? Type CONFIRM: ", {'CONFIRM'}) != 'CONFIRM':
            raise ValueError('Musical key decision was not checked')
        row['human_checked'] = True
    _new_json(destination, document)
    return len(document['keys'])


def _cue_review(ask, draft, destination):
    document = json.loads(draft.read_text())
    for number, row in enumerate(document['pairs'], 1):
        name, a, b = row['pair_id'], row['a'], row['b']
        step = f'{number}/{len(document["pairs"])} · {name}'
        row['beats'] = _number(ask, f'{step}: checked beat count for {a} to {b}: ', 1, 64, integer=True)
        row['a_start'] = _number(ask, f'{step}: outgoing {a} cue in seconds: ', 0, 250)
        row['b_start'] = _number(ask, f'{step}: incoming {b} cue in seconds: ', 0, 250)
        _answer(ask, f'{step}: enter CUES-VERIFIED after personally checking both cues: ', {'CUES-VERIFIED'})
        _answer(ask, f'{step}: enter PRIVATE-ONLY to declare authorization for private processing: ', {'PRIVATE-ONLY'})
        row['human_cues_confirmed'] = True
        row['permission_for_private_render_confirmed'] = True
    _new_json(destination, document)
    return len(document['pairs'])


def run(manifest_path, split_path, private_destination, *, pairs=5, seed=0,
        manual_keys=None, measure_keys=False, ask=input):
    """Prepare and render an isolated M1 pack after each explicit review step."""
    source = Path(manifest_path).absolute()
    if source.suffix.lower() != '.json':
        raise ValueError('Expected a private JSON library manifest')
    # Check the actual manifest, source hashes, rights declarations and split
    # before allocating a workspace or asking for any human decisions.
    candidates = build_candidates(source, split_path, manual_keys, measure_keys)
    if type(pairs) is not int or not 5 <= pairs <= 10 or type(seed) is not int or not 0 <= seed < 2 ** 63:
        raise ValueError('Invalid frozen study size or preregistered seed')
    root = _private_dir(private_destination)
    raw, pending = root / 'unreviewed.json', root / 'keys-pending.json'
    reviewed, approved = root / 'keys-reviewed.json', root / 'approved.json'
    frozen, cue_pending = root / 'frozen.json', root / 'cues-pending.json'
    cue_reviewed, pack = root / 'cues-reviewed.json', root / 'blind-pack'
    _new_json(raw, candidates)
    prepare_keys(raw, pending)
    nkeys = _key_review(ask, pending, reviewed)
    approve_keys(raw, reviewed, approved)
    study = freeze(approved, pairs, seed)
    _new_json(frozen, study)
    prepare_cues(source, frozen, cue_pending)
    ncues = _cue_review(ask, cue_pending, cue_reviewed)
    # A study id identifies the immutable selection, not a single operator
    # session. Two separate attempts with the same seed/study must never
    # collide or overwrite one another's independently confirmed cue sheets.
    session_id = hashlib.sha256(os.fsencode(root)).hexdigest()[:16]
    new_manifest = source.with_name(source.stem + '.m1-' + study['study_id'][:12]
                                    + '-' + session_id + '.json')
    approve_cues(source, frozen, cue_reviewed, new_manifest)
    # Freeze the candidate STUDY with the preregistered seed, but randomize
    # baseline-as-A independently for each listener pack using system entropy.
    # Otherwise a published study seed predicts the supposedly blind A/B key.
    build_pack(new_manifest, frozen, pack, seed=None)
    receipt, evidence, trials = verify_pack(pack)
    if verify_study_pack(pack, frozen) != study['study_id']:
        raise ValueError('Private render does not match the frozen study')
    if len(trials) != pairs or len(evidence['renders']) != 2 * pairs:
        raise ValueError('Incomplete blind audio pack')
    return dict(status='private-pack-ready-not-listener-validated', key_reviews=nkeys,
                cue_approvals=ncues, frozen_pairs=len(trials),
                rendered_wavs=len(evidence['renders']), study_id=study['study_id'],
                pack_id=receipt['pack_id'])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Guided private M1: confirm keys and cues, then render frozen blind A/B audio')
    parser.add_argument('library', help='existing local rights-declared WAV library')
    parser.add_argument('split', help='previously declared development/evaluation split')
    parser.add_argument('destination', help='new private workspace outside the repo')
    parser.add_argument('--manual-keys', help='optional human-verified source keys')
    parser.add_argument('--measure-keys', action='store_true', help='optional offline heuristic key estimates')
    parser.add_argument('--pairs', type=int, choices=tuple(range(5, 11)), default=5)
    parser.add_argument('--seed', type=int, default=0, help='recorded selection seed, fixed before listening')
    args = parser.parse_args(argv)
    try:
        result = run(args.library, args.split, args.destination, pairs=args.pairs,
                     seed=args.seed, manual_keys=args.manual_keys,
                     measure_keys=args.measure_keys)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, EOFError, KeyboardInterrupt):
        parser.exit(2, 'MixLab private pilot: incomplete or unconfirmed input; no completed review pack was published\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
