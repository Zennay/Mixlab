# MixLab Full Set Player — volledig lokale mix met hoofdstukken

Na het genereren van een complete WAV wil je snel kunnen luisteren, terugspoelen
naar een overgang en de opname meenemen naar een lokale muziekspeler.
De Full Set Player maakt daarvoor een eigen HTML-pagina en audio-tijdlijn.

## Eén opdracht vanuit de visuele Set Composer

Maak eerst een privé [Set Composer](offline-set-composer.md) en download
je keuzeplan. Render daarna:

    python3 -m mixlab.set_composer render \
      /private/session-01 \
      /private/mixlab-set-plan.private.json \
      /private/final-set-01.wav

Deze opdracht rendert de complete WAV en publiceert optioneel automatisch
`/private/final-set-01.wav.player.html`. Open die naast de WAV in je browser:

- één doorlopende speler met alle nummers en goedgekeurde overgangen;
- een **klikbare visuele golfvorm** van de complete set, met overgangsmarkeringen, playhead en toetsenbordnavigatie via links/rechts (stappen van vijf seconden);
- hoofdstukken die rechtstreeks naar elke solo-sectie of transitie springen;
- knop voor vorige/volgende passage en actieve hoofdstukmarkering;
- download een lokale JSON-hoofdstukkenlijst gebonden aan de WAV-SHA;
- download een standaard `.cue` voor muziekspelers die CUE-sheets ondersteunen.

Als alleen het maken van de HTML-speler faalt, blijft de eerder atomair
gepubliceerde WAV intact; de CLI meldt dan `player_warning`. Er worden nooit
bestaande pagina's of muziekbestanden overschreven.

## Een bestaande WAV later van een tijdlijn voorzien

    python3 -m mixlab.set_player \
      /private/session-01 \
      /private/final-set-01.wav

Een nieuw HTML-bestand verschijnt naast de WAV. De originele private receipt
`final-set-01.wav.receipt.private.json` moet aanwezig zijn.

## Integriteits- en privacygrenzen

De golfvorm wordt in maximaal 640 tijdvakken uit vier korte PCM-vensters per vak gesampled (maximaal 655.360 leesframes). Hij geeft een genormaliseerde, **benaderde energievisualisatie**, geen geïntegreerde loudnessmeting of muziekbeoordeling. Daardoor blijft de extra CPU- en geheugendruk begrensd, ook bij langere sets.

De speler verwerkt uitsluitend een **eerder werkelijk geëxporteerde**
`private-continuous-manual-set` en het bijbehorende manifest. Hij leest de
oorspronkelijke sessie/Studio SHA-bindingen, controleert de WAV-SHA en
het PCM16-formaat, reconstrueert exact dezelfde handmatige route met de
canonieke `set_export`-logica en bindt de hoofdstukken aan de echte frameposities.
De chapter-JSON bevat alleen track-/pair-IDs, posities en output-hash; geen
bronlocaties, metadata van commerciële tracks, lyrics of audio-data.

Deze creatieve player doet geen netwerkverzoeken, telemetrie, modelaanroepen of
muziekupload. Omdat alle audio lokaal blijft, moet ook de HTML-pagina privé
worden gehouden. Chapter-labels komen uit handmatig gekozen track-/pair-IDs;
geen automatische beat/key/phrase-detectie of muzikale voorkeur wordt
gesuggereerd. MixLab M1 blijft OPEN tot de echte rechtenveilige
luister-evaluatie is afgerond.
