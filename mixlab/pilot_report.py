"""Local, private, descriptive blind results dashboard. Never declares M1 passed."""
from __future__ import annotations
import argparse
import html
import json
import os
from pathlib import Path
from .evaluation import aggregate


def h(v):
    return html.escape(str(v), quote=True)


def render(report):
    if report.get('milestone_pass') is not False or report.get('status') != 'descriptive-only-requires-independent-human-review':
        raise ValueError('Not an independently verified pilot')
    counts, rows = report['counts'], report['per_pair_family']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError('Invalid pair results')
    labels = ('candidate', 'baseline', 'ties', 'both_unusable')
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in labels):
        raise ValueError('Invalid aggregated counts')
    n = counts['candidate'] + counts['baseline']
    if n != report['non_tied_preferences']:
        raise ValueError('Wrong decisive vote denominator')
    table = []
    for row in rows:
        if not isinstance(row, dict) or any(type(row.get(k)) is not int or row[k] < 0 for k in labels):
            raise ValueError('Invalid pair vote counts')
        decisive = row['candidate'] + row['baseline']
        pct = 100*row['candidate']/decisive if decisive else 0
        label = f"{row['candidate']} / {decisive}" if decisive else 'No decisive votes'
        meter = f'<div class="meter" aria-label="Candidate share {pct:.1f} percent"><span style="width:{pct:.1f}%"></span></div>'
        table.append('<tr><th scope="row">'+h(row['pair'])+'</th><td>'+h(row['candidate_family'])+
                     '</td><td>'+h(label)+meter+'</td><td>'+h(row['ties'])+'</td><td>'+h(row['both_unusable'])+'</td></tr>')
    confounds = report['audio_confounds']
    if not isinstance(confounds, list) or len(confounds) > 30:
        raise ValueError('Invalid audio diagnostics')
    warnings=[]
    for issue in confounds:
        if not isinstance(issue, dict) or not isinstance(issue.get('warnings'), list):
            raise ValueError('Invalid diagnostic row')
        warnings.append('<li>'+h(issue['trial'])+': '+h(', '.join(map(str, issue['warnings']))[:200])+'</li>')
    pcm = '<ul>'+''.join(warnings)+'</ul>' if warnings else '<p>No reported PCM confounds; musical quality remains unverified.</p>'
    percent = f"{100*counts['candidate']/n:.1f}%" if n else 'No decisive votes'
    cards = (('Reviewer codes', report['reviewers']), ('Pairs', report['trials']),
             ('Candidate decisive share', percent), ('Ties', counts['ties']))
    summary = ''.join('<div><strong>'+h(v)+'</strong><small>'+h(k)+'</small></div>' for k,v in cards)
    status = ('Fewer than three reviewer codes.' if report['reviewers'] < 3 else
              'Pseudonyms cannot establish three distinct real listeners.')
    body = ('<header><small>MIXLAB · PRIVATE OPERATOR</small><h1>Blind listening results</h1>'
            '<p>Descriptive preferences. Not a release approval or proof of musical quality.</p></header>'
            '<section><div class="stats">'+summary+'</div><p>'+h(status)+
            ' Candidate: '+h(counts['candidate'])+'; baseline: '+h(counts['baseline'])+
            '; ties: '+h(counts['ties'])+'; unusable: '+h(counts['both_unusable'])+'.</p></section>'
            '<section><h2>Per transition</h2><div class="scroll"><table><thead><tr><th>Pair</th>'
            '<th>Family</th><th>Decisive votes</th><th>Ties</th><th>Unusable</th></tr></thead><tbody>'+
            ''.join(table)+'</tbody></table></div></section>'
            '<section><h2>Audio diagnostics</h2>'+pcm+'</section><section><h2>What is not proved</h2>'
            '<p>Real reviewer identities, recording rights, timing, key accuracy, listening quality or '
            'independent audit. Keep this operator-only report away from blinded listeners.</p></section>'
            '<footer>M1 OPEN · Pack ID: <code>'+h(report['pack_id'])+'</code></footer>')
    style = (':root{color-scheme:dark}body{background:#111823;color:#f1f5fc;font:16px system-ui;margin:0}'
             'main{max-width:980px;margin:auto;padding:40px 20px}h1{font-size:clamp(26px,5vw,44px)}'
             'small,p{color:#bfcbdd}p{line-height:1.6}section{margin-top:32px}'
             '.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}'
             '.stats>div{border:1px solid #42516c;padding:20px;border-radius:16px}'
             '.stats strong{display:block;font-size:29px}.stats small{display:block}.scroll{overflow-x:auto}'
             'table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #394762}'
             '.meter{height:6px;background:#344258;border-radius:7px;overflow:hidden;margin-top:8px}'
             '.meter span{height:100%;display:block;background:#aabaff}'
             'footer{margin-top:40px;border-top:1px solid #40506a;padding-top:24px}code{overflow-wrap:anywhere}')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &apos;none&apos;; style-src &apos;unsafe-inline&apos;; base-uri &apos;none&apos;">'
            '<title>MixLab private listening results</title><style>'+style+'</style></head><body><main>'+body+'</main></body></html>')


def publish(pack, rating_files, destination):
    """Verify original PCM/ballots first, then exclusively publish private HTML."""
    output = Path(destination).absolute()
    if output.suffix.lower() != '.html' or output.exists() or output.is_symlink():
        raise ValueError('Choose a new private HTML file')
    if not output.parent.is_dir() or any(
            p.is_symlink() or (p / '.git').exists()
            for p in (output.parent, *output.parent.parents)):
        raise ValueError('Do not write inside Git or a symlinked directory')
    result = aggregate(pack, rating_files)
    page = render(result)
    flags = os.O_WRONLY | os.O_EXCL | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(output, flags, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(page)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return dict(status='private-descriptive-only-not-a-milestone-pass',
                reviewers=result['reviewers'], pairs=result['trials'],
                audio_confounds=len(result['audio_confounds']), pack_id=result['pack_id'])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline private visual overview of verified blind ratings')
    parser.add_argument('private_pack')
    parser.add_argument('new_html_report')
    parser.add_argument('rating_files', nargs='+')
    args = parser.parse_args(argv)
    try:
        result = publish(args.private_pack, args.rating_files, args.new_html_report)
    except (ValueError, TypeError, OSError, KeyError, OverflowError):
        parser.exit(2, 'MixLab report: invalid, changed or unavailable private input\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
