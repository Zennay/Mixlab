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
- bij volledige exports uit **Playlist Studio** en **party_mix** ook herkenbare
  lokale songnamen (bestandsnaam zonder extensie) en overgangslabels
  **nummer A → nummer B**, in de afspeellijst, eventmodus en privé-CUE/JSON;
  de oorspronkelijke brongebonden technische ID's blijven bewaard;
- per gerenderde overgang een **Herhaal overgang**-knop: beluister zonder
  nieuwe WAV of Studio exact het overgangssegment steeds opnieuw. De knop
  schakelt naar **Stop herhalen** met een zichtbare en voor schermlezers
  herkenbare aan/uitstatus. Een ander overgangssegment kiezen, handmatig
  springen of in de golfvorm zoeken stopt de vorige loop;
- knop voor vorige/volgende passage en actieve hoofdstukmarkering;
- download een lokale JSON-hoofdstukkenlijst gebonden aan de WAV-SHA;
- download een standaard `.cue` voor muziekspelers die CUE-sheets ondersteunen.

Als alleen het maken van de HTML-speler faalt, blijft de eerder atomair
gepubliceerde WAV intact; de CLI meldt dan `player_warning`. Er worden nooit
bestaande pagina's of muziekbestanden overschreven.

## Eventmodus — lokale afspeelbediening tijdens een feest

Klik **⛶ Eventmodus** in de HTML-speler wanneer je de set daadwerkelijk
afspeelt. MixLab gebruikt nog steeds **dezelfde vooraf gerenderde,
hashgebonden complete WAV**; er vindt geen live remix, streaming,
tijdrekmethode of netwerkaanroep plaats.

In deze modus zie je:

- Een groot, duidelijk leesbaar veld met **huidige track/overgang**,
  een aftelklok tot de **eerstvolgende overgang** en, wanneer er
  geen volgende overgang is, de resterende speeltijd van de set.
- Een grote **Speel/Hervat/Pauzeer**-knop. De toets **P** schakelt
  afspelen/pauzeren zolang je niet op een invoerveld of knop staat.
- De al beschikbare golfvorm als visuele feedback. Om per ongeluk
  overslaan tijdens een feest te voorkomen, zijn waveform-klik,
  hoofdstuk-springknoppen, vorige/volgende, de nieuwe overgang-herhaalknoppen
  en de standaard browsertijdlijn **tijdelijk uitgeschakeld**. Een actieve
  herhaling wordt bij het openen van eventmodus **altijd gestopt**, zodat
  de DJ-set normaal kan doorlopen.
- Optioneel schermvullende presentatie als de browser die toestaat.
  Met **Verlaat eventmodus** kun je altijd terug naar de normale
  bewerkings-/luisterweergave; de set blijft afspelen.

Het is een **afspeelmodus**, geen zero-fail professioneel DJ-systeem.
De browser en lokale computer moeten wakker blijven en de WAV moet
naast de privé HTML-speler beschikbaar zijn. Houd een aparte offline
noodafspeeloptie beschikbaar bij echte evenementen. MixLab belooft
geen ononderbroken audiohardware of perfecte latency.

## Een bestaande WAV later van een tijdlijn voorzien

    python3 -m mixlab.set_player \
      /private/session-01 \
      /private/final-set-01.wav

Een nieuw HTML-bestand verschijnt naast de WAV. De originele private receipt
`final-set-01.wav.receipt.private.json` moet aanwezig zijn.

## Offline portable pakket voor telefoon of USB

Wil je de volledige set als één **MP3** meenemen in plaats van een grote
WAV? [MixLab Portable DJ Set](private-portable-dj-set.md) kan op basis
van de exact dezelfde vooraf gerenderde private WAV optioneel een
192 kbit/s MP3, CUE-hoofdstukkenlijst, M3U8-afspeellijst en hashgebonden
conversiereceipt maken. Alleen reeds geïnstalleerde FFmpeg/FFprobe wordt
gebruikt, zonder upload of wijziging aan de originele WAV. De MP3 is
lossy en de CUE-tijden zijn dus indicatief; voor exact framegebonden
bewijs blijft de oorspronkelijke WAV leidend.

## Integriteits- en privacygrenzen

De golfvorm wordt in maximaal 640 tijdvakken uit vier korte PCM-vensters per vak gesampled (maximaal 655.360 leesframes). Hij geeft een genormaliseerde, **benaderde energievisualisatie**, geen geïntegreerde loudnessmeting of muziekbeoordeling. Daardoor blijft de extra CPU- en geheugendruk begrensd, ook bij langere sets.

De speler verwerkt uitsluitend een **eerder werkelijk geëxporteerde**
`private-continuous-manual-set` en het bijbehorende manifest. Hij leest de
oorspronkelijke sessie/Studio SHA-bindingen, controleert de WAV-SHA en
het PCM16-formaat, reconstrueert exact dezelfde handmatige route met de
canonieke `set_export`-logica en bindt de hoofdstukken aan de echte frameposities.
De chapter-JSON bevat originele track-/pair-IDs, posities en de exacte
WAV-outputhash; bij een export rechtstreeks vanuit Playlist Studio of
party_mix staan **ook de herleidbare lokale bestandsnamen zonder extensie**
in de privéhoofdstukken (en CUE-sheet). Geen volledige bronpaden,
commerciële metadataservice, lyrics of originele losse audiobestanden.
Dit is alleen een weergavenaam uit de broncatalogus, geen automatisch
herkende titel, rechtencontrole of artiestmetadata. Deel deze HTML-/CUE-/
JSON-bestanden dus niet zonder de mogelijke privacy-inhoud te controleren.
Een losse oude sessie waarbij je `python3 -m mixlab.set_player` uitvoert,
behoudt veilige technische ID's wanneer originele lokale bestandsnamen niet
meer in de sessie beschikbaar zijn.

Deze creatieve player doet geen netwerkverzoeken, telemetrie, modelaanroepen of
muziekupload. Omdat alle audio lokaal blijft, moet ook de HTML-pagina privé
worden gehouden. Chapter-labels komen uit handmatig gekozen track-/pair-IDs;
geen automatische beat/key/phrase-detectie of muzikale voorkeur wordt
gesuggereerd. MixLab M1 blijft OPEN tot de echte rechtenveilige
luister-evaluatie is afgerond.
