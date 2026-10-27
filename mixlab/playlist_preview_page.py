"""Static, private DJ-plan overview. No audio, script, source paths or network."""
from __future__ import annotations
from html import escape
import os
from pathlib import Path


def h(value):
    return escape(str(value), quote=True)


def clock(seconds):
    tenths = max(0, round(seconds * 10))
    whole, fraction = divmod(tenths, 10)
    return f'{whole//60:02}:{whole%60:02}' + (f',{fraction}' if fraction else '')


def local_song_title(source_path):
    """Human-readable basename only; never render original directories."""
    if not isinstance(source_path, str):
        raise ValueError('Invalid music filename in private manifest')
    name = Path(source_path).stem.strip()
    # User-controlled private filenames can be unusually long or contain
    # control characters. Bound the *display*, not the source manifest.
    label = ' '.join(name.split())[:96]
    return label or 'Naamloos nummer'


def render(plan, display_names=None):
    route, pairs = plan['track_order'], plan['transitions']
    if not isinstance(route, list) or not isinstance(pairs, list) or not 2 <= len(route) <= 11 or len(pairs) != len(route)-1:
        raise ValueError('Invalid manual plan')
    if display_names is not None and (not isinstance(display_names, dict) or
            any(not isinstance(display_names.get(i), str) for i in route)):
        raise ValueError('Missing display name for an original song')
    verified = plan.get('source_wav_hashes_and_headers_verified') is True
    duration = plan.get('complete_mix_duration')
    cards = [('Nummers', len(route)), ('Overgangen', len(pairs)),
             ('Overgangstijd', clock(plan['total_transition_seconds'])),
             ('Geplande mixtijd', clock(duration) if verified and isinstance(duration,(int,float)) else 'Nog onbekend')]
    stats = ''.join('<div><b>'+h(v)+'</b><span>'+h(k)+'</span></div>' for k,v in cards)
    style_names = {'baseline':'Basisovergang','bass_swap':'Basswissel',
                   'echo_exit':'Echo-uitloop','hard_cut':'Directe overgang'}
    items = []
    for i, ident in enumerate(route):
        transition = ''
        if i < len(pairs):
            pair = pairs[i]
            style = style_names.get(pair['family'],pair['family'])
            transition = ('<div class="join" aria-label="Overgang naar het volgende nummer">'
                          '<span class="arrow" aria-hidden="true">↓</span><div><b>'+h(style)+'</b>'
                          '<p>'+h(pair['beats'])+' beats · '+h(pair['bpm'])+' BPM · '+
                          h(pair['duration_seconds'])+' sec.</p><p>Uitgaand '+
                          h(pair['outgoing_cue_seconds'])+' sec. · inkomend '+
                          h(pair['incoming_cue_seconds'])+' sec.</p></div></div>')
        title = display_names[ident] if display_names is not None else ident
        label = ('<small>Nummer '+str(i+1)+'</small><h3>'+h(title)+'</h3>' +
                 ('<small class="identifier">'+h(ident)+'</small>' if title != ident else ''))
        items.append('<li><div class="song"><span class="no">'+str(i+1).zfill(2)+
                     '</span><div>'+label+'</div></div>'+transition+'</li>')
    note = ('De originele WAV-hashes en headers zijn gecontroleerd; de berekende '
            'mixtijd is nog geen gerenderde audio.' if verified else
            'Dit is alleen een handmatig mixplan. Bronhashes en volledige mixtijd '
            'zijn niet gecontroleerd.')
    content = ('<header><span class="eyebrow">MIXLAB / PRIVÉ MIXPLAN</span><h1>Jouw volgende mix.</h1>'
               '<p class="intro">Van tracklijst naar volledige set, zonder ingewikkelde studio.</p>'
               '<p class="notice">'+h(note)+'</p></header>'
               '<section aria-label="Overzicht"><div class="stats">'+stats+'</div></section>'
               '<section aria-labelledby="order"><h2 id="order">Speelvolgorde</h2><ol>'+''.join(items)+'</ol></section>'
               '<section class="next"><h2>Klaar om te mixen?</h2><p>Controleer de handmatig gekozen nummers '
               'en overgangen. Gebruik daarna je oorspronkelijke opdracht zonder '
               '<code>--preview</code> en <code>--preview-html</code> om echte audio te maken.</p></section>'
               '<footer>Geen bronbestanden of volledige bronpaden in deze pagina. Lokale bestandsnamen en trackcodes kunnen herkenbaar zijn: houd dit overzicht privé. '
               'M1 blijft open; echte BPM, cues, muzieklicenties en kwaliteit vergen menselijke controle.</footer>')
    css = (':root{color-scheme:dark}*{box-sizing:border-box}'
           'body{font:16px/1.55 system-ui,sans-serif;color:#edf4fa;background:#101820;margin:0}'
           'main{max-width:880px;margin:auto;padding:40px 20px 80px}'
           '.eyebrow{font-size:12px;letter-spacing:.18em;font-weight:800;color:#99e8cb}'
           'h1{font-size:clamp(32px,6vw,58px);letter-spacing:-.045em;margin:12px 0}'
           'h2{font-size:23px;margin:32px 0 16px}h3{font-size:20px;margin:2px 0;overflow-wrap:anywhere}'
           '.intro,footer{color:#bccbd8}.notice{border-left:3px solid #9adbbf;padding:12px 16px;background:#192b31}'
           '.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin-top:25px}'
           '.stats>div{background:#202e3b;border:1px solid #354e5d;border-radius:14px;padding:17px}'
           '.stats b{display:block;font-size:24px}.stats span{display:block;color:#b7c8d4;font-size:13px}'
           'ol{list-style:none;padding:0}.song{display:flex;align-items:center;gap:15px;'
           'border:1px solid #375262;border-radius:14px;background:#1b2a35;padding:16px}'
           '.no{background:#294e50;color:#a6f4d2;padding:11px;border-radius:10px;font-weight:800}'
           '.join{display:flex;gap:20px;align-items:center;margin:8px 0 8px 28px;color:#cbd9e3}'
           '.arrow{font-size:28px;color:#96ddbe}.join p{font-size:13px;margin:1px 0;color:#afc3d0}'
           '.next{background:#1b2a35;border-radius:16px;padding:1px 20px 16px;margin-top:25px}'
           '.identifier{display:block;font-size:12px;opacity:.72;letter-spacing:.02em}'
           'code{font:13px monospace;color:#a6ead6}footer{margin-top:36px;border-top:1px solid #3d5161;padding-top:20px}'
           '@media(max-width:520px){main{padding:24px 14px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}')
    return ('<!doctype html><html lang="nl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
            '<title>MixLab · Privé mixplan</title><style>'+css+'</style></head>'
            '<body><main>'+content+'</main></body></html>')


def publish(plan, output_wav, *, display_names=None):
    target = Path(str(Path(output_wav).absolute()) + '.preview.html')
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError('New private preview path required')
    for parent in (target, *target.parents):
        if parent.is_symlink() or (parent / '.git').exists():
            raise ValueError('Private preview cannot be created in Git or symlink folders')
    data = render(plan, display_names=display_names).encode('utf-8')
    if len(data) > 65536:
        raise ValueError('Private plan HTML exceeds 64 KiB')
    with target.open('xb') as out:
        try:
            os.fchmod(out.fileno(), 0o600)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return target
