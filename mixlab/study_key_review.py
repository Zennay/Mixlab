"""Private human key confirmation before freezing MixLab's blind M1 study.

A key estimate is a heuristic, not a human-verified annotation. This tool
creates an initially unapproved review sheet and publishes a NEW candidate
file only when every evaluation-split proposal is explicitly reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .evaluation.json_admission import load_bounded_json
from .evaluation.study import KEYS, _tracks, write_exclusive
from .study_alignment import _private_output


def _canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(',', ':')).encode()


def _load_candidates(path):
    data = load_bounded_json(path)
    tracks = _tracks(data)
    if not any(row['split'] == 'evaluation' for row in tracks.values()):
        raise ValueError('Candidate file has no evaluation split')
    return data, hashlib.sha256(_canonical(data)).hexdigest()


def _review_items(data):
    return [dict(id=t['id'], source_sha256=t['sha256'],
                 proposed_key=t['key'], proposed_source=t['key_source'],
                 decision='pending', confirmed_key=None, human_checked=False)
            for t in data['tracks']
            if t['split'] == 'evaluation' and t['key_source'] != 'manual']


def prepare(candidates_path, review_path):
    data, sha = _load_candidates(candidates_path)
    review = dict(schema_version=1, original_candidates_sha256=sha,
                  kind='mixlab-human-key-review-v1', keys=_review_items(data))
    write_exclusive(_private_output(review_path), review)
    return len(review['keys'])


def apply(candidates_path, review_path, approved_path):
    """Publish human-confirmed candidate keys, never rewrite a frozen study."""
    original, original_sha = _load_candidates(candidates_path)
    output = _private_output(approved_path)
    review = load_bounded_json(review_path)
    required = {'schema_version', 'original_candidates_sha256', 'kind', 'keys'}
    if (not isinstance(review, dict) or set(review) != required or
            type(review['schema_version']) is not int or
            review['schema_version'] != 1 or
            review['kind'] != 'mixlab-human-key-review-v1' or
            review['original_candidates_sha256'] != original_sha or
            not isinstance(review['keys'], list)):
        raise ValueError('Review is not bound to the original candidate file')
    expected = _review_items(original)
    if len(review['keys']) != len(expected):
        raise ValueError('Incomplete or excess key reviews')
    decisions = {}
    fixed = ('id', 'source_sha256', 'proposed_key', 'proposed_source')
    for source, item in zip(expected, review['keys']):
        if (not isinstance(item, dict) or set(item) != set(source) or
                any(item[field] != source[field] for field in fixed) or
                item['human_checked'] is not True):
            raise ValueError('Key or source changed; every key requires manual review')
        action, key = item['decision'], item['confirmed_key']
        if action == 'accept' and source['proposed_source'] == 'measured-heuristic' and key == source['proposed_key']:
            pass
        elif action == 'override' and type(key) is str and key in KEYS:
            pass
        elif action == 'unavailable' and key is None:
            pass
        else:
            raise ValueError('Review requires an explicit valid key decision')
        decisions[source['id']] = (key, 'unavailable' if key is None else 'manual')
    final = dict(original)
    final['tracks'] = []
    for source in original['tracks']:
        row = dict(source)
        if source['id'] in decisions:
            row['key'], row['key_source'] = decisions[source['id']]
        final['tracks'].append(row)
    _tracks(final)  # same immutable track ids, source hashes, BPM, split, rights
    if hashlib.sha256(_canonical(load_bounded_json(candidates_path))).hexdigest() != original_sha:
        raise ValueError('Original candidates changed while reviewing keys')
    write_exclusive(output, final)
    return len(decisions)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Confirm or reject key proposals before freezing a private study')
    sub = parser.add_subparsers(dest='command', required=True)
    for action in ('prepare', 'apply'):
        child = sub.add_parser(action)
        child.add_argument('candidates')
        child.add_argument('key_review')
        if action == 'apply':
            child.add_argument('approved_candidates')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            n = prepare(args.candidates, args.key_review)
            status = 'review-required-before-study-freeze'
        else:
            n = apply(args.candidates, args.key_review, args.approved_candidates)
            status = 'manual-key-reviewed-candidates-not-study-frozen'
    except (OSError, TypeError, ValueError, KeyError, OverflowError):
        parser.exit(2, 'MixLab key review: invalid, changed or unconfirmed private input\n')
    print(json.dumps({'status': status, 'reviewed_keys': n}, sort_keys=True))


if __name__ == '__main__':
    main()
