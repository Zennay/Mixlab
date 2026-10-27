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


def render(plan, display_names=None, *, workflow='party_mix'):
    if workflow not in ('party_mix', 'guided'):
        raise ValueError('Invalid private playlist workflow')
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
    # Frame-aligned planned chapters are available only after original WAV
    # hashes/headers and every manual cue boundary have been verified.
    timeline = ''
    chapters = plan.get('planned_chapters') if verified else None
    if chapters is not None:
        if not isinstance(chapters, list) or not 1 <= len(chapters) <= 21:
            raise ValueError('Invalid verified private DJ timeline')
        pair_names = {item['pair']: item for item in pairs}
        chunks = []
        map_items = []
        frame_cursor = 0
        for index, part in enumerate(chapters, 1):
            if not isinstance(part, dict) or part.get('kind') not in ('solo', 'transition'):
                raise ValueError('Invalid planned chapter kind')
            frame_count, frame_start = part.get('frames'), part.get('start_frame')
            if (type(frame_count) is not int or frame_count <= 0 or
                    type(frame_start) is not int or frame_start != frame_cursor):
                raise ValueError('Noncontiguous private DJ chapter timeline')
            frame_cursor += frame_count
            ident = part['label']
            if part['kind'] == 'solo':
                if ident not in route:
                    raise ValueError('Unknown song in planned timeline')
                title = display_names[ident] if display_names is not None else ident
                kind = 'Nummer'
            else:
                if ident not in pair_names:
                    raise ValueError('Unknown transition in planned timeline')
                pair = pair_names[ident]
                a, b = pair['from_track'], pair['to_track']
                title = ((display_names[a] if display_names is not None else a) +
                         ' → ' + (display_names[b] if display_names is not None else b))
                kind = 'Overgang · ' + style_names.get(part['family'], part['family'])
            chapter_id = 'mix-chapter-' + str(index).zfill(2)
            position = (clock(part['start_seconds']) + ' tot ' +
                        clock(part['start_seconds'] + part['duration_seconds']))
            bar_class = 'bar-transition' if part['kind']=='transition' else 'bar-solo'
            map_items.append('<li class="'+bar_class+'" style="flex:'+str(frame_count)+
                ' 1 0"><a href="#'+chapter_id+'" aria-label="'+
                h(kind+' '+title+' · '+position)+'" title="'+
                h(title+' · '+position)+'"><span class="sr-only">'+
                h(kind+' '+title)+'</span></a></li>')
            chunks.append('<li id="'+chapter_id+'" class="chapter"><span class="chapter-time">'+
                h(clock(part['start_seconds']))+'–'+
                h(clock(part['start_seconds'] + part['duration_seconds']))+
                '</span><div><small>'+h(kind)+'</small><strong>'+h(title)+
                '</strong></div></li>')
        if (type(plan.get('exact_expected_pcm_frames')) is not int or
                frame_cursor != plan['exact_expected_pcm_frames']):
            raise ValueError('Private chapter timeline does not cover complete WAV')
        visual_map = ('<div class="map-key" aria-hidden="true">'
                      '<span class="key-solo">Nummer</span>'
                      '<span class="key-transition">Overgang</span></div>'
                      '<ol class="mix-map" aria-label="Klikbare mixkaart met '
                      'verhoudingen van alle echte WAV-fragmenten">'+
                      ''.join(map_items)+'</ol>'
                      '<p class="muted">De gekleurde vakken tonen de relatieve '
                      'duur van de onderdelen. Klik of gebruik Tab en Enter '
                      'voor de exacte begintijd en duur hieronder.</p>')
        timeline = ('<section aria-labelledby="timeline-heading">'
                    '<h2 id="timeline-heading">Wanneer hoor je wat?</h2>'
                    '<p class="muted">Verwachte start- en eindtijd op de complete WAV. '
                    'Gebaseerd op lokale, SHA-gecontroleerde PCM16-bronnen en '
                    'jouw handmatige cues; niet op gehoor geverifieerd.</p>'
                    +visual_map+'<ol class="timeline">'+''.join(chunks)+'</ol></section>')
    elif not verified:
        timeline = ('<section aria-labelledby="timeline-heading">'
                    '<h2 id="timeline-heading">Wanneer hoor je wat?</h2>'
                    '<p class="muted">De exacte tijdlijn is nog onbekend. '
                    'Gebruik <code>--verify-wavs</code> met originele '
                    '44,1 kHz PCM16-WAVs om vóór het renderen '
                    'de echte hoofdstukstarttijden te berekenen.</p></section>')
    if workflow == 'guided':
        next_step = ('<p>Je handmatige bronmanifest is al opgeslagen. Gebruik '
                     '<code>--resume --full-set-wav</code> om dezelfde playlist later '
                     'te renderen. Gebruik dezelfde muziekbibliotheek en manifest, '
                     'maar kies een nieuwe sessiemap en WAV. Laat '
                     '<code>--manifest-only</code>, <code>--plan-html</code> en '
                     '<code>--plan-verify-wavs</code> weg.</p>'
                     '<pre><code>python3 -m mixlab.playlist_studio MUZIEKMAP '
                     'PLAYLIST.json NIEUWE_SESSIE --resume '
                     '--full-set-wav NIEUWE_MIX.wav</code></pre>'
                     '<p>De standaard-overgangsstijl uit je playlist wordt '
                     'hergebruikt. Je kunt die bewust wijzigen met '
                     '<code>--family</code>; expliciet goedgekeurde stijlen '
                     'blijven beschermd.</p>')
    else:
        next_step = ('<p>Voer dezelfde <code>mixlab.party_mix</code>-opdracht '
                     'opnieuw uit zonder <code>--preview</code>, '
                     '<code>--preview-html</code> en '
                     '<code>--verify-wavs</code>. Daarna wordt de echte WAV '
                     'gerenderd; sessiemap en WAV moeten nog nieuw zijn.</p>')
    content = ('<header><span class="eyebrow">MIXLAB / PRIVÉ MIXPLAN</span><h1>Jouw volgende mix.</h1>'
               '<p class="intro">Van tracklijst naar volledige set, zonder ingewikkelde studio.</p>'
               '<p class="print-tip">Wil je dit overzicht op papier of als PDF bij je decks? '+
               'Gebruik Afdrukken in je browser (Ctrl+P / Cmd+P). '+
               'Je originele audio of privébronmanifest wordt daarbij niet veranderd.</p>'
               '<p class="notice">'+h(note)+'</p></header>'
               '<section aria-label="Overzicht"><div class="stats">'+stats+'</div></section>'
               '<section aria-labelledby="order"><h2 id="order">Speelvolgorde</h2><ol>'+''.join(items)+'</ol></section>'+timeline+
               '<section class="next"><h2>Klaar om te mixen?</h2><p>Controleer de '
               'nummers en handmatig gekozen overgangen.</p>'+next_step+'</section>'
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
           '.muted{color:#b7c8d4}.timeline{display:grid;gap:8px}'
           '.mix-map{display:flex;gap:2px;height:60px;margin:16px 0 10px;'
           'padding:0;background:#263645;border-radius:12px;overflow:hidden}'
           '.mix-map li{display:flex;min-width:3px}'
           '.mix-map a{display:block;width:100%;min-width:0;outline-offset:-4px}'
           '.mix-map a:focus-visible{outline:3px solid #fff;z-index:1}'
           '.mix-map .bar-solo{background:#267b78}'
           '.mix-map .bar-transition{background:#8c64ce}'
           '.mix-map a:hover{background:#ffffff30}'
           '.map-key{display:flex;gap:20px;flex-wrap:wrap;margin-top:12px;color:#d8e7ee}'
           '.map-key span{display:flex;align-items:center;gap:7px}'
           '.map-key span:before{content:"";width:12px;height:12px;display:inline-block;border-radius:3px}'
           '.map-key .key-solo:before{background:#267b78}'
           '.map-key .key-transition:before{background:#8c64ce}'
           '.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;'
           'clip:rect(0,0,0,0);white-space:nowrap}'
           '.chapter:target{border-color:#d7b9ff;outline:2px solid #d7b9ff;scroll-margin-top:24px}'
           '.chapter{display:flex;align-items:center;gap:14px;background:#162733;'
           'border:1px solid #385062;border-radius:12px;padding:12px 16px}'
           '.chapter-time{min-width:100px;font-variant-numeric:tabular-nums;font-weight:750;color:#a6f4d2}'
           '.chapter strong{display:block;overflow-wrap:anywhere}'
           'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1d26;padding:14px;border-radius:9px}'
           'code{font:13px monospace;color:#a6ead6}footer{margin-top:36px;border-top:1px solid #3d5161;padding-top:20px}'
           '@media(max-width:520px){main{padding:24px 14px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.chapter{align-items:flex-start;gap:8px;flex-direction:column}}'
           '@page{size:A4;margin:13mm}'
           '@media print{'
           '*{color:#151515!important;background:transparent!important;'
           'box-shadow:none!important;text-shadow:none!important}'
           'html,body{color:#151515!important;background:#fff!important;'
           'font:10.5pt/1.38 system-ui,sans-serif}'
           'main{max-width:none;padding:0;margin:0}'
           '.eyebrow{color:#222!important;letter-spacing:.08em}'
           'h1{font-size:27pt;margin:5mm 0 2mm}h2{font-size:15pt;margin:5mm 0 2mm}'
           'h3{font-size:12pt}.intro{font-size:10pt}.print-tip{display:none}'
           '.stats{grid-template-columns:repeat(4,1fr);gap:2mm;margin-top:3mm}'
           '.stats>div{padding:2mm;border:1px solid #aaa!important;border-radius:0}'
           '.stats b{font-size:14pt}.stats span{font-size:8pt}'
           '.song,.chapter{padding:2.5mm;border:1px solid #aaa!important;'
           'border-radius:0}.join{margin:1.5mm 0 1.5mm 9mm;gap:3mm}'
           '.arrow{font-size:12pt}.join p{font-size:9pt}'
           '.no{padding:1mm;border:1px solid #666!important;border-radius:0}'
           '.notice{padding:2mm;border:1px solid #aaa!important}'
           '.mix-map,.map-key{display:none!important}'
           '.timeline{gap:1mm}.chapter-time{min-width:26mm}'
           '.next{border:1px solid #aaa!important;padding:2mm;border-radius:0}'
           'pre{border:1px solid #aaa!important;padding:2mm;white-space:pre-wrap}'
           'section,li,.song,.join,.chapter,.stats>div,.next,footer,pre{'
           'break-inside:avoid;page-break-inside:avoid}'
           'section{break-inside:auto;page-break-inside:auto}'
           'footer{border-top:1px solid #999!important;padding-top:2mm;margin-top:4mm}'
           '}')
    return ('<!doctype html><html lang="nl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
            '<title>MixLab · Privé mixplan</title><style>'+css+'</style></head>'
            '<body><main>'+content+'</main></body></html>')


def publish(plan, output_wav, *, display_names=None, workflow='party_mix'):
    target = Path(str(Path(output_wav).absolute()) + '.preview.html')
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError('New private preview path required')
    for parent in (target, *target.parents):
        if parent.is_symlink() or (parent / '.git').exists():
            raise ValueError('Private preview cannot be created in Git or symlink folders')
    data = render(plan, display_names=display_names, workflow=workflow).encode('utf-8')
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
