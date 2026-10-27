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
- **Luister met context** naast elk gerenderd overgangshoofdstuk:
  kies boven de tijdlijn **2, 8 of 16 seconden** oorspronkelijke muziek
  **vóór én ná** die overgang. MixLab speelt vervolgens eenmalig dezelfde
  complete WAV af binnen de echte WAV-grenzen. De standaard is 2 seconden;
  langere opties helpen een volledige muzikale frase te beoordelen.
  De browser pauzeert na het fragment op de gebruikelijke
  `timeupdate`-gebeurtenissen: **niet sample-nauwkeurig**.
  Een andere contextlengte kiezen stopt de huidige contextluisterbeurt;
  klik opnieuw op een overgang om met de nieuwe lengte te luisteren.
  Er is geen nieuwe render, automatische BPM-/phrase-analyse of wijziging
  aan het oorspronkelijke WAV-bestand. Dit werkt ook vanuit de
  privé-aanpassingslijst; exact overgangsherhalen annuleert context.
  Handmatig buiten het fragment springen of eventmodus openen stopt context;
  eventmodus blokkeert ook de selector;
- **Afspeelsnelheid bij oefenen** met 0,75×, 1× (standaard) of 1,25×
  voor het privé beluisteren van overgangshoofdstukken, geïsoleerde loops
  en contextluisteren. Dit is alleen de afspeelsnelheid van de browser:
  de originele WAV, PCM-duur, cuepunten, hoofdstuktijden, toestemming en
  SHA-gebonden receipts worden **niet** gewijzigd. Een browser kan de
  toonhoogte bij een afwijkende snelheid anders behandelen; beoordeel de
  uiteindelijke muzikale kwaliteit daarom altijd op **1×**. Wanneer je
  **Eventmodus** opent, herstelt MixLab altijd 1× en vergrendelt de
  oefensnelheidskeuze tot je die modus weer verlaat;
- knop voor vorige/volgende passage en actieve hoofdstukmarkering;
- download een lokale JSON-hoofdstukkenlijst gebonden aan de WAV-SHA;
- download een standaard `.cue` voor muziekspelers die CUE-sheets ondersteunen.

## Creatieve overgangsnotities — privé en zonder account

Gebruik onder de hoofdstuklijst **Je eigen overgangsnotities** om elk
werkelijk gerenderd overgangsfragment na het beluisteren te markeren als
**Klinkt goed** of **Wil aanpassen**, met een vrije notitie van maximaal
280 tekens. De reeds beschikbare **Herhaal overgang**-knop laat je
herhaald luisteren vóór je iets invult; de originele mix zelf verandert niet.

De knop **Download privé-overgangsnotities JSON** wordt beschikbaar zodra
je ten minste één keuze of notitie hebt gemaakt. Het bestand
`mixlab-transition-notes.private.json` bevat alleen de door jou ingevulde
overgangen, originele paar-ID, uit je lokale bestanden afgeleide zichtbare
naam, renderfamilie, exacte hoofdstukstart-/fragmentduur en de bij het maken
van de speler vastgelegde **WAV SHA-256**. Daardoor weet je bij welk
compleet mixresultaat de opmerkingen horen. Het is geen hercontrole van
een later gewijzigd WAV-bestand en geen onafhankelijke blinde beoordeling.

**Beluisteren met een stukje muziek ervoor en erna** helpt beoordelen of
het eerste nummer natuurlijk wegloopt en het volgende nummer goed inzet.
Met **Luister met context** in de aanpassingslijst hoor je dezelfde
reeds gerenderde overgang inclusief de begrensde omgeving. Het blijft een
persoonlijke DJ-luisterhulp, geen onafhankelijke muzikale kwaliteitsmeting.

**Aanpassingen direct opnieuw beluisteren:** zodra je een overgang als
**Wil aanpassen** markeert, verschijnt die automatisch in de sectie
**Nog aan te passen overgangen** met de originele lokaal zichtbare songnamen,
WAV-hoofdstukstart en je persoonlijke notitie. Gebruik **Herhaal deze
overgang** om precies het al gerenderde fragment te horen of
**Beluister volgende aanpassing** om automatisch naar de volgende nog aan
te passen overgang in afspeelvolgorde te springen (met rondgang aan het
einde). Een overgang die je verandert in **Klinkt goed** verdwijnt direct uit
de lijst. Na het terugladen van je bestaande SHA-gebonden privénotities
wordt de lijst opnieuw opgebouwd. Er vindt geen aanpassing van de audio,
handmatige cues, originele rechtenverklaring of bronmanifest plaats; dit
is uitsluitend een eigen creatieve werk-/luisterlijst. In Eventmodus
zijn deze herhaal- en navigatieknoppen uitgeschakeld. Je aantekeningen
blijven alleen in het geopende browservenster totdat je zelf het
privé-JSON-bestand downloadt.

**Eerder opgeslagen notities weer openen:** kies onder *Je eigen overgangsnotities*
het lokaal bewaarde `mixlab-transition-notes.private.json` en klik
**Laad privé-overgangsnotities**. De pagina herstelt je keuzes en tekst
alleen als de oorspronkelijke WAV-SHA, de duur, het exacte overgangspaar,
de werkelijke overgangsstijl en de hoofdstuktijden allemaal overeenkomen.
Verkeerde of gewijzigde mixen worden geweigerd en de huidige aantekeningen
blijven intact. Bestanden groter dan 64 KiB, ongeldige/gedupliceerde
records en te lange notities worden geweigerd. Als je al nieuwere notities
hebt ingevuld, vraagt MixLab eerst expliciet of die vervangen mogen
worden; je kunt annuleren en je notities zelf eerst downloaden.
Je oorspronkelijke WAV wordt bij import **niet opnieuw gehasht**: de controle
betreft de SHA-binding die de speler bij het oorspronkelijke renderen
heeft vastgelegd, geen latere onafhankelijke audio-audit. Ook import is
onmogelijk in Eventmodus. Een bestand kiezen is géén upload.

**Bewaar je JSON voordat je dit browservenster sluit of vernieuwt.**
MixLab slaat deze aantekeningen niet automatisch op: geen browseropslag,
geen achtergrondservice, geen netwerk, geen aanpassing van de SHA-gebonden
muziekbron, rechtenverklaring, originele WAV of receipts. De notities zijn
persoonlijk en kunnen herkenbare muzieknamen bevatten; houd het bestand
privé. Bij activering van **Eventmodus** zijn bewerken en downloaden
uitgeschakeld; na verlaten van eventmodus kun je verder.

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
  herhaling wordt bij het openen van eventmodus **altijd gestopt**, en
  de afspeelsnelheid teruggezet naar **1×**, zodat de DJ-set normaal
  kan doorlopen.
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
