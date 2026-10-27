"""Offline handoff: frozen pairs -> explicitly approved private cue manifest.

Never infer rights, cue locations or listening quality. No audio is uploaded.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from .evaluation.json_admission import load_bounded_json
from .evaluation.study import verify_study, write_exclusive
from .ingest import _read_bounded_manifest, validate_library


def _private_output(value):
    path = Path(value).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError('Destination exists; never overwrite')
    if any((p / '.git').exists() for p in (path.parent, *path.parent.parents)):
        raise ValueError('Private source metadata cannot be written inside Git')
    return path


def _input(manifest_path, study_path):
    source = Path(manifest_path).absolute()
    study = verify_study(study_path)
    manifest, tracks = validate_library(source)
    for row in study['pairs']:
        a, b = tracks.get(row['a']), tracks.get(row['b'])
        if (a is None or b is None or
                (a['sha256'], b['sha256']) != (row['a_sha256'], row['b_sha256']) or
                a['bpm'] != row['a_bpm'] or b['bpm'] != row['b_bpm'] or
                row['renderable_without_stretch'] is not True):
            raise ValueError('Study sources, tempo or hashes do not match the library')
    sha = hashlib.sha256(_read_bounded_manifest(source).encode()).hexdigest()
    return source, sha, manifest, study


def _rows(study):
    return [dict(pair_id=p['pair_id'], a=p['a'], b=p['b'],
                 a_sha256=p['a_sha256'], b_sha256=p['b_sha256'],
                 beats=None, a_start=None, b_start=None,
                 human_cues_confirmed=False,
                 permission_for_private_render_confirmed=False)
            for p in study['pairs']]


def prepare(manifest_path, study_path, worksheet_path):
    """Write a private worksheet with ALL approvals unset; never render."""
    _, sha, _, study = _input(manifest_path, study_path)
    output = _private_output(worksheet_path)
    write_exclusive(output, dict(schema_version=1, study_id=study['study_id'],
                                 source_manifest_sha256=sha, pairs=_rows(study)))
    return len(study['pairs'])


def apply(manifest_path, study_path, worksheet_path, output_path):
    """Publish a new manifest only when every source/cue has human confirmation."""
    source, sha, manifest, study = _input(manifest_path, study_path)
    output = _private_output(output_path)
    if output.parent != source.parent or output.suffix.lower() != '.json':
        raise ValueError('New library manifest must be a sibling .json file')
    sheet = load_bounded_json(worksheet_path)
    if (not isinstance(sheet, dict) or set(sheet) != {
            'schema_version', 'study_id', 'source_manifest_sha256', 'pairs'} or
            type(sheet['schema_version']) is not int or sheet['schema_version'] != 1 or
            sheet['study_id'] != study['study_id'] or
            sheet['source_manifest_sha256'] != sha or
            not isinstance(sheet['pairs'], list) or
            len(sheet['pairs']) != len(study['pairs'])):
        raise ValueError('Worksheet not bound to the source and frozen study')
    pairs = []
    for index, (expected, row) in enumerate(zip(_rows(study), sheet['pairs'])):
        if (not isinstance(row, dict) or set(row) != set(expected) or
                any(row[k] != expected[k] for k in (
                    'pair_id', 'a', 'b', 'a_sha256', 'b_sha256')) or
                row['human_cues_confirmed'] is not True or
                row['permission_for_private_render_confirmed'] is not True):
            raise ValueError('Human cue and private source approval required per pair')
        beats = row['beats']
        if type(beats) is not int or not 1 <= beats <= 64:
            raise ValueError('Confirmed beat count must be 1..64')
        offsets = []
        for field in ('a_start', 'b_start'):
            val = row[field]
            if type(val) not in (int, float) or not math.isfinite(val) or not 0 <= val <= 250:
                raise ValueError('Confirmed cue starts must be finite seconds')
            offsets.append(val)
        pairs.append(dict(id=expected['pair_id'], a=expected['a'], b=expected['b'],
                          bpm=study['pairs'][index]['a_bpm'], beats=beats,
                          a_start=offsets[0], b_start=offsets[1]))
    updated = dict(manifest)
    updated['pairs'] = pairs
    fd, temp = tempfile.mkstemp(prefix='.mixlab-alignment-', suffix='.json', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(updated, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        validate_library(temp)
        if hashlib.sha256(_read_bounded_manifest(source).encode()).hexdigest() != sha:
            raise ValueError('Source manifest changed before publication')
        os.link(temp, output)  # atomic, exclusive publication
    finally:
        Path(temp).unlink(missing_ok=True)
    return len(pairs)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private frozen-study human cue handoff; never infer cues or rights')
    sub = parser.add_subparsers(dest='command', required=True)
    for action in ('prepare', 'apply'):
        child = sub.add_parser(action)
        child.add_argument('source_manifest')
        child.add_argument('frozen_study')
        child.add_argument('worksheet')
        if action == 'apply':
            child.add_argument('new_manifest')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            count = prepare(args.source_manifest, args.frozen_study, args.worksheet)
            status = 'await-human-cues-and-permission'
        else:
            count = apply(args.source_manifest, args.frozen_study, args.worksheet, args.new_manifest)
            status = 'private-manifest-confirmed-not-listener-validated'
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        parser.exit(2, 'MixLab alignment: invalid, changed or unapproved private input\n')
    print(json.dumps({'status': status, 'pairs': count}))


if __name__ == '__main__':
    main()
