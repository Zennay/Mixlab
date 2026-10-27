# MixLab — volledige rechten- en cue-invoer in een lokaal formulier

De bestaande Playlist Studio kan een complete lokale WAV-set bouwen, maar
vroeg voorheen voor elke track en overgang aparte terminalinvoer. Met de
**Private Playlist Approval** hoef je die handmatig gecontroleerde informatie
niet twee keer over te typen. De browser maakt een **nieuw, niet-uitvoerend**
goedkeuringsbestand. De gewone renderer blijft alle veiligheids-, rechten-
en bronchecks uitvoeren.

## Vereisten: eerst een SHA-gebonden voorstel

Gebruik een eerdere [Event Brief Studio](offline-event-brief-studio.md),
[Energy Journey Planner](energy-journey-planner.md) of een andere bestaande
MixLab lokale creatieve planroute om een privé JSON te maken naast de
oorspronkelijke, rechtenveilige muziekbestanden:

~~~bash
python3 -m mixlab.journey notes /private/music /private/music/energy.private.json
python3 -m mixlab.journey plan /private/music /private/music/energy.private.json /private/music/set-plan.private.json --tracks 5 --shape build
~~~

De audio en plannen staan **buiten Git**. Er worden geen bronrechten,
cuepunten, lyrics of muzikale kwaliteitsclaims automatisch afgeleid.

## Bewaar en hervat een onvoltooid privéwerkconcept

Het lokale goedkeuringsformulier kan nu een **niet-goedgekeurd concept**
downloaden via **Download private working draft**. Dit bewaart alleen
de exact aan het oorspronkelijke playlistplan gekoppelde bron-SHA's,
handmatig ingevulde rights/provenance-velden, optionele downbeats,
A/B-cues, overgangsstijlen en de gekozen overgangsduur. Er wordt
geen muziek opgeslagen, geanalyseerd of geüpload.

Open je later hetzelfde brongebonden formulier opnieuw, kies
**Reopen a private working draft** en selecteer het eerder gedownloade
`mixlab-playlist-working-draft.private.json`. Het formulier weigert
concepten van een andere plan-hash, andere trackvolgorde of andere
bronhashes, extra velden en ongeldige cue-invoer. Het bestand is
maximaal 64 KiB. **Het overnemen van een concept is nooit akkoord:**
de twee toestemmingsvakjes worden bewust altijd *uitgevinkt*,
ook als je ze eerder had aangezet. Herbeluister de broncues,
controleer de originele rechtenverklaring en geef daarna zelf opnieuw
akkoord. Het concept bevat jouw privé-provenance-notities: bewaar
het alleen lokaal en voeg het niet aan publieke ZIPs toe.

## Stap 1 — browserformulier voor rechten en echte cues

~~~bash
python3 -m mixlab.playlist_approval \
  /private/music \
  /private/music/set-plan.private.json \
  /private/music/playlist-approval.private.html
~~~

Open `/private/music/playlist-approval.private.html` lokaal.
Je ziet alle geselecteerde tracks in de **reeds voorgestelde volgorde**,
met hun handmatig geverifieerde BPM en private bronbinding.

**Meerdere originele nummers tegelijk koppelen:** gebruik bovenaan het
formulier onder *Song rights and human-verified grid* de nieuwe
**Attach original playlist music in one step**-bestandskiezer. Kies jouw
originele lokale nummers (maximaal 20 selectie-items; een playlist bevat
2–11 nummers). MixLab zoekt de exacte bronbestandsnaam en controleert
**ieder volledig bestand** lokaal tegen de SHA-256 van de gekozen
playlist. Alleen een geslaagde inhoudscontrole ontgrendelt de
bijbehorende oorspronkelijke audiospeler en twee-deck-voorluistering.
De pagina meldt welke bronbestanden wel of niet gekoppeld konden
worden. Niets wordt automatisch afgespeeld, verzonden of aan
muziekrechten toegekend. De bestaande bestandskiezer per nummer blijft
beschikbaar.

**Lokaal beluisteren in hetzelfde formulier:** kies per track de originele
muziekfile via de browser. De ingesloten afspeelknoppen gebruiken een
tijdelijke lokale blob-URL: er gaat geen audio naar een server. De browser
controleert nu de bestandsnaam, de limiet van 512 MiB én de
**volledige SHA-256 van het originele nummer uit het brongebonden plan**.
Dit gebeurt in lokale 1 MiB-blokken en toont voortgang. Verkeerde of
gewijzigde nummers krijgen geen audio-URL en kunnen ook niet in de
twee-deck repetitie worden gebruikt. Zet pas na volledige verificatie de afspeelkop op een door jou gecontroleerde positie en klik
**Set first downbeat**, **Mark outgoing A cue** of **Mark incoming B cue**.
De knop **4 beats vooruit/achteruit** springt op basis van jouw al
handmatig geverifieerde BPM, niet van een automatisch gevonden beat.
Kan de browser een bestand niet afspelen, beluister het in je eigen
muziekspeler en voer de seconden handmatig in.

**Twee-decks prelisten voordat je rendert.** Na het selecteren van de
originele nummers, rechtenverklaring/bronbasis en het handmatig markeren
van een outgoing A-cue en incoming B-cue, kun je bij de betreffende
overgang nu op **Rehearse A→B transition** klikken. De browser start de
twee geselecteerde lokale bestanden bij hun eigen vastgelegde cuepositie
en laat A geleidelijk uit- en B geleidelijk invloeien over het ingestelde
aantal beats. **Stop rehearsal** stopt beide lokale audiospelers meteen.

De afspeelvolumes volgen bij benadering de equal-power curve:
A = cos(pi * t/2), B = sin(pi * t/2). Er is geen extern
geluidsbestand, service, upload of FFmpeg nodig voor dit creatieve
voorluisteren. De browser moet het lokale codec-formaat wel kunnen
afspelen; als een file niet kan worden geopend, een cue buiten de
bronduur ligt of playback geblokkeerd wordt, meldt de pagina dat en
blijft handmatige tijdsinvoer beschikbaar. Bij opnieuw selecteren
van een bronbestand stopt de actieve preview.

Dit is **alleen een ruwe browserprelisten**: de daadwerkelijke
\`bass_swap\`, \`echo_exit\`, \`hard_cut\` of kanonieke
\`baseline\`-renderer kan anders klinken door decodeer-, timing-,
DSP- en normalisatieverschillen. De offline Studio rendert
de definitieve bronhashgebonden overgangen; de voorluisterknop geeft
**geen** rechtenbewijs of muzikale voorkeursmeting.

De browser voert nu **wel** een volledige lokale SHA-256-controle uit,
zonder het gehele audiobestand tegelijk in geheugen te laden. Een naam- of
grootte-match alleen geeft nooit toestemming voor afspelen. Een fout,
ongeldig bestand of verschil in SHA laat zowel de individuele audio- als
twee-deck voorluisterfunctie vergrendeld. Dit bewijst alleen byte-identiteit
met je oorspronkelijke notities, geen muziekrechten. De serverloze Playlist
Studio voert later **opnieuw zelfstandig** de bron- en rechtencontrole uit
voordat import of render starten. Handmatige seconden blijven mogelijk
wanneer de browser een formaat niet ondersteunt; dit verleent geen toestemming
om de originele broncontrole over te slaan.

Vul vervolgens in:

- Per track expliciet het soort gebruiksrecht (synthetic, licensed,
  user-permitted of public-domain), en concrete provenance/rechtengrond.
- Desgewenst de eerste handmatig gecontroleerde downbeat in seconden.
- Per overgang de precieze **outgoing A**- en **incoming B**-cues in seconden,
  terwijl je de eigen, lokale opname daadwerkelijk beluistert.
- De gedeelde overgangsduur in beats (1–64). De interface controleert
  teruglopende uitgangen t.o.v. het voorgaande B-eind.
- Twee expliciete vakjes: eigen rechtenverklaring en akkoord met de volgorde.

**Renderstijl per overgang.** Kies in ieder overgangsblok
\`Use --family default\`, \`baseline\`, \`bass_swap\`,
\`echo_exit\` of \`hard_cut\`. Deze stijlen zijn de **bestaande
vier echte MixLab DSP-families**. De door jou gekozen stijlen
gaan mee in de SHA-gebonden privécuegoedkeuring: als je direct een
complete WAV rendert met \`--full-set-wav\`, maakt Playlist Studio
automatisch de juiste pair-specificieke \`pair-NNN:family\`-keuzes
voor de officiële Studio/Instant Set renderer.

Een browserrepetitie speelt slechts een **benaderde equal-power
fade**, ongeacht de geselecteerde renderstijl. Voor de werkelijk
gerenderde \`bass_swap\` en \`echo_exit\` moet je de output
nadien via de lokale WAV Set Player/Set Gallery beluisteren.
Een onbekende stijl wordt geweigerd; combineer de in het formulier
gekozen stijlen niet met een tweede tegenstrijdige \`--style\`
opdracht. Een bewust gekozen \`echo_exit\`, \`hard_cut\`,
\`bass_swap\` of \`baseline\` staat voortaan onder
\`approved_family\` **bij exact het originele SHA-gebonden paar**
in het private bronmanifest. Ook na \`--manifest-only --plan-html\`
of een latere \`--resume --full-set-wav\` krijgen zowel het
visuele mixplan als de officiële Instant Set exporter **dezelfde expliciet
goedgekeurde stijl**. Een afwijkende \`--style PAIR:FAMILY\` wordt
vóór dure import geweigerd; voor een andere stijl maak je een nieuwe
privébrongoedkeuring en een nieuw bronmanifest. Paren waarvoor het formulier
\`Use --family default\` koos, volgen wél je ingestelde
\`--family\` en krijgen geen verzonnen expliciete goedkeuring.

Klik **Export my private approved cues**. Dit downloadt een nieuw
`mixlab-event-approved.private.json` met **geen audio**. Verplaats
het nieuwe bestand naast de originele songs en het eerder gebruikte
plan. Het bevat wel gevoelige gebruiksmetadata; verspreid het niet.

## Stap 2 — echte Studio en volledige WAV met bestaande engine

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/confirmed-event-sources.private.json \
  /private/my-event-studio \
  --journey-plan /private/music/set-plan.private.json \
  --approval-file /private/music/mixlab-event-approved.private.json \
  --beats 16 \
  --full-set-wav /private/my-event.wav \
  --family bass_swap
~~~

Gebruik bij `--beats` **precies hetzelfde** aantal als in het
browserformulier. Playlist Studio:

1. Controleert de individuele lokale opnamen opnieuw met SHA-256 tegen
   het originele, ongewijzigde plan.
2. Vereist dat het nieuwe goedkeuringsbestand aan de **exacte bytes**
   van dat plan is gebonden en dat alle nummers, volgorde, rechtenvelden,
   secondenwaarden en pair-aantallen kloppen. Onbekende of gewijzigde
   muzieksources, ongeldige rechten, niet-numerieke/NaN-cues, teruglopende
   overgangen of ongeldige beatlengte worden geweigerd.
3. Toont nogmaals de gekozen volgorde en vraagt expliciet
   **Accept this exact suggested order? Type yes**. Zonder dat akkoord
   wordt geen nieuw source manifest gemaakt.
4. Gebruikt daarna de bestaande canonieke, rechten- en hash-gebonden
   privé manifest/import/Studio/Set Composer/volledige-WAV-rendering,
   zonder een tweede reeks los ingetikte rechten- en cuevragen.
5. Als later decoderen/renderen fout gaat, blijft het nieuwe,
   goedgekeurde bronmanifest behouden voor expliciet herstarten met
   `--resume` (dan zonder `--journey-plan` en `--approval-file`).

Optionele MP3/FLAC via `--delivery` vereist reeds lokaal
geïnstalleerde FFmpeg/FFprobe, zoals in de bestaande
[private set delivery](private-set-delivery.md).

## Grenzen

- De browser is **geen rechtencontroleur**. Alleen de gebruiker kan
  aantonen dat de muziek gebruikt mag worden. Het formulier doet
  evenmin automatische BPM/beat/downbeat/key/phrase-analyse.
- De exact gebonden goedkeuringsdata is niet equivalent aan
  een M1-geaccepteerde set; de blind-human-preference en andere
  onderzoeksintegriteitsvoorwaarden blijven open.
- De browser laadt geen audio. Gebruik een eigen lokale speler
  voor zorgvuldig controleren van de cue-seconden.
- Iedere audio/JSON/HTML blijft privé buiten Git, wordt niet geüpload
  en nieuwe output overschrijft niets. De integratie heeft geen
  productie-deploy, zCloud queue-admission of runtime service nodig.
