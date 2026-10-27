# MixLab Playlist Studio — van lokale muziekmap naar een complete DJ Studio

De Playlist Studio is een **volledige offline onboardingflow** voor een
handmatig samengestelde DJ-set. Je kiest één keer de gewenste afspeelvolgorde;
de app maakt vervolgens de gekoppelde overgangsparen, normaliseert audio,
rendert alle officiële vier transitiestijlen en opent de visuele Set Composer.

Geen model, uploads, auteursrechtelijk onduidelijke catalogus, nieuwe
runtimepackages of verborgen BPM-aanpassing. De tool vraagt de werkelijke
rechtenstatus, herkomst, BPM en exacte cues **van jou**.

## In één opdracht

Vanuit een checkout van [MixLab](https://github.com/Zennay/Mixlab):

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --beats 16
~~~

De bronmap bevat 2–11 toegestane tracks (WAV, of bestanden die jouw
reeds geïnstalleerde FFmpeg/FFprobe kan converteren). Alle nieuwe outputs
moeten buiten Git en in **nog niet bestaande** bestanden/mappen komen.

De begeleide dialoog vraagt:

1. **Volgorde:** geef 2–11 nummers uit de overzichtslijst in de gewenste
   afspeelvolgorde, bijvoorbeeld `2,5,1,4`. Je hoeft geen losse A/B-paren
   meer aan te maken; MixLab verbindt ze automatisch.
2. **Per nummer:** verklaar de werkelijke BPM, optioneel de eerste downbeat,
   rechtenstatus en concrete bron/provenance. De SHA-256 van het lokale
   bestand wordt vastgelegd.
3. **Per overgang:** bevestig handmatig de **outgoing** en **incoming**
   cue in seconden. Cues van een tussenliggend nummer mogen niet
   achteruit lopen ten opzichte van het voorgaande inkomende einde.
   Nummers met verschillende BPM worden geweigerd zolang de officiële
   M1-renderer niet kan timestretchen.

Na bevestiging genereert MixLab een onafhankelijke, privé en SHA-gebonden
bronmanifest in je muziekmap en:

- de gewone, reeds bestaande import/conversie en veilige M1-renders;
- de **Transition Studio** voor het vergelijken van echte gerenderde
  bass-swap, echo-exit, hard-cut en baseline varianten;
- de visuele cue-editor als aanvullende **handmatige** referentie;
- de offline **Set Composer** om een doorlopende route te kiezen,
  het keuzeplan op te slaan en [één complete WAV](offline-set-composer.md)
  plus [hoofdstukspeler](private-full-set-player.md) te maken.

Open na afloop:

    /private/mixlab-playlist-01/set-composer/index.html

Selecteer de familie per overgang en download het keuzeplan. Maak daarna de
volledige WAV met:

~~~bash
python3 -m mixlab.set_composer render \
  /private/mixlab-playlist-01 \
  /private/mixlab-set-plan.private.json \
  /private/mixlab-party.wav
~~~

## Extra: laat MixLab overgangsideeën uit echte PCM-energie voorstellen

Als je de **manueel gecontroleerde eerste downbeat van ieder nummer**
invult, kun je in dezelfde opdracht meteen een privé ideeënboard laten
maken:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --beats 16 --ideas
~~~

Deze optie gebruikt de bestaande energie-analyse op lokale WAV-data. De energievensters volgen **exact het in de playlist vastgelegde aantal overgangsbeats** (bijvoorbeeld 8, 16 of 32); dit wordt ook bij een herstart uit het opgeslagen manifest gelezen en niet vanuit een stilzwijgende standaard vervangen. Een bestaande playlist met onderling verschillende beatlengtes kan de gedeelde suggesties daarom niet in één bundel aanvragen.
Naast de gewone Studio en Set Composer wordt dan
`/private/mixlab-playlist-01/sources/transition-ideas.html` aangemaakt.
Open het bestand, vergelijk handmatige cues met de energievoorstellen
en download jouw **expliciet goedgekeurde** keuzeplan.

Het bord kiest geen definitieve overgang en verandert geen bronmanifest
zonder de aparte `mixlab.idea_board apply`-opdracht. Bekijk de
[volledige Idea Board-workflow](transition-idea-board.md) om de
goedgekeurde cues veilig in een **nieuwe** Studio te renderen.
De nieuwe `python3 -m mixlab.idea_board finish ...`-opdracht verbindt
de hashgebonden DJ-goedkeuring, het nieuwe bronmanifest, alle vier
echt gerenderde overgangstypes en de offline Set Composer in één stap.
De originele track- en sessiebestanden blijven ongewijzigd.

`--ideas` vereist genormaliseerde audio en kan daarom niet met
`--manifest-only` worden gecombineerd. Bij `--resume --ideas`
worden de eerder gecontroleerde downbeats uit je bestaande manifest
opnieuw gebruikt; er wordt niets stilzwijgend geïnterpreteerd.

## Direct een complete WAV uit de muziekwizard

De Playlist Studio kan **in dezelfde eerste opdracht** ook meteen
een volledige mix en offline hoofdstukspeler exporteren. Kies daarbij
zelf de transitiestijl — er is geen automatische muzikale beoordeling.

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --beats 16 \
  --full-set-wav /private/party-ready.wav \
  --family bass_swap \
  --style pair-002:echo_exit
~~~

Hiermee maak je de echte lokale Studio, de visuele cue-editor, Set
Composer, alle reeds gerenderde A/B-overgangen en één continue
`party-ready.wav` met chaptered `party-ready.wav.player.html`.
De **echte afspeelspeler** gebruikt nu, net als de visuele planpreview,
herkenbare lokale bestandsnamen zonder extensie voor hoofdstukken en
songnaam A → songnaam B voor transities. Ook eventmodus en privé-
hoofdstukexports tonen die labels. Ze zijn herleidbaar en blijven daarom
alleen in de lokale HTML/CUE/JSON; de echte WAV/bron-SHA-receipts veranderen niet.
De tweede overgang krijgt expliciet een eigen stijl; alle andere
paren gebruiken `bass_swap`.

**Een volledige WAV is pas geslaagd wanneer er echt een WAV is.**
De wizard controleert nu vóór het zware importeren/renderen de nieuwe
WAV-bestemming, de volledige brontrackvolgorde, de handmatige cue-overlap
en de overgangskeuzes. Een bestaande WAV/receipt of een vergeten nummer
wordt direct met exitcode 2 geweigerd: er wordt geen nieuwe Studiosessie,
WAV of halfvolledige export gemaakt; het bronmanifest blijft bewaard.
Dit voorkomt dat de gebruiker eerst minuten rekent voor een uitvoer die
bij voorbaat niet kon slagen.

Na het renderen geeft het JSON-resultaat onafhankelijk
`complete_set_requested` en `complete_set_ready` terug, met fase
`studio-and-complete-set`, `studio-only` of
`studio-kept-complete-set-failed`. `ready: true` betekent op zichzelf
alleen dat de Studio bestaat. Als onverwacht alleen de WAV-export faalt
**nadat** Studio succesvol is gerenderd, bewaart MixLab die Studio voor
hergebruik, meldt de fout expliciet en beëindigt de CLI met exitcode 2.
Zo wordt de mislukte volledige set niet meer als geslaagde opdracht
beschouwd. Privébronbestanden en bestaande outputs worden niet gewijzigd.

Bij `--resume` mag je `--full-set-wav` ook gebruiken, zodat een
eerder opgeslagen manifest later in één keer het complete resultaat
oplevert. `--manifest-only` kan vanzelfsprekend geen WAV maken.
Als de optionele setexport mislukt, blijft je nieuwe, bruikbare Studio
bestaan. Exporteer dan opnieuw naar een **nieuwe** WAV-naam met
[Instant Set](instant-private-full-set.md).

## Plannen bewaren en later verder renderen

Je kunt de handmatige songvolgorde, bronrechten, BPM en overgangscues eerst
vastleggen **zonder de Studio te renderen**. Ideaal wanneer je meerdere
nummers voorbereidt of FFmpeg/audioverwerking nog niet beschikbaar is.

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --beats 16 --manifest-only
~~~

MixLab schrijft dan alleen `my-playlist.private.json` en stopt vóór de
CPU-intensieve audio-import. De hele begeleide invoer is daarmee veilig bewaard.

Wil je **meteen na het kiezen van de nummers en cuepunten een visueel
mixplan**, zonder een tweede commando te hoeven leren? Voeg de optionele
`--plan-html` toe aan dezelfde begeleide invoer:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --beats 16 --manifest-only --plan-html
~~~

De wizard maakt het echte handmatige SHA-gebonden bronmanifest en daarnaast
één afzonderlijke **privé offline pagina**
`/private/mixlab-playlist-01.wav.preview.html` (0600). Daar zie je de
speelvolgorde, gekozen overgangen, BPM en uitgaande/inkomende cuepunten.
Elke song heeft nu een **herkenbare naam afgeleid van het lokale
bestandsnaamdeel zonder extensie**; de technische track-ID staat er kleiner
bij voor controle. Dit is een bestandsnaam, geen geverifieerde artiest-/titel-
metadata en geen bewijs van muziekrechten. Volledige map- en bronpaden
worden niet in de pagina geplaatst. Omdat bestandsnamen privé-informatie
kunnen verraden, blijft de offline pagina uitsluitend lokaal (modus 0600).
Er wordt nog géén sessiemap, Studio, mix-WAV of audio-speler gemaakt.
De standaardinstelling toont de handmatig opgegeven familiekeuze
(`bass_swap`), behalve bij overgangen waarvoor het officiële
privégoedkeuringsformulier een specifieke stijl heeft vastgelegd. Die
\`approved_family\` wordt **bij het exact SHA-gebonden paar in het
bronmanifest** bewaard: zowel de visuele preview als een latere
\`--resume --full-set-wav\` gebruiken die goedgekeurde stijl.
Een afwijkende expliciete \`--style\` wordt vóór audio-import geweigerd.
Als het formulier geen stijl vastlegde, blijft \`--family\` de
handmatig gekozen standaard voor die overgang.

Voor bestaande **originele lokale 44,1 kHz PCM16-WAVs** kun je bovendien
`--plan-verify-wavs` toevoegen; dan worden de bron-SHA's en de WAV-headers
gecontroleerd en toont de pagina naast de exact verwachte mixtijd ook
**waar alle nummers en overgangen op de uiteindelijke WAV-tijdlijn
starten en eindigen**. De frametijden komen uit de lokaal SHA-gecontroleerde
PCM16-bronnen en dezelfde cue-rekenregels als de echte WAV-export; zonder
deze broncontrole wordt geen tijdlijn verzonnen. Dit valideert nog geen
muziekrechten, gehoorde overgang of muzikale kwaliteit. Voor MP3/FLAC en andere
formaten gebruik je alleen `--plan-html` zonder
`--plan-verify-wavs`; hun exacte lengte vereist later de gewone audio-import.

**De offline planpagina geeft nu per route de juiste volgende stap.**
Een met de wizard aangemaakt plan beschrijft de daadwerkelijke hervatopdracht:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --resume --full-set-wav /private/mixlab-playlist-01.wav
~~~

Laat daarbij `--manifest-only`, `--plan-html` en `--plan-verify-wavs`
weg. De pagina bevat alleen **plaatsaanduidingen** voor paden, nooit je
privé-directory of manifestbestandsnaam. Gebruik dus je eigen oorspronkelijke
paden. De vanuit de wizard gekozen `--family` wordt nu als
`default_family` in het bestaande privé bronmanifest opgeslagen en
bij `--resume` vanzelf hergebruikt; als er geen keuze was, blijft
`bass_swap` de standaard. Een bewust opnieuw opgegeven `--family`
mag die algemene standaard wijzigen, maar kan niet een expliciet
met het goedkeuringsformulier vastgelegde `approved_family` overrulen.
Oude manifesten zonder `default_family` blijven bruikbaar en gebruiken
hun vroegere standaard `bass_swap`.

Het JSON-resultaat geeft `private_plan_html` en `planned_complete_wav` terug.
Dat tweede pad is slechts een **voorstel**, geen geproduceerde WAV. Om later
daadwerkelijk te mixen, gebruik dezelfde bronmanifest met `--resume` en
`--full-set-wav` naar die voorgestelde nieuwe bestandsnaam. Bestaande WAVs of
HTML-bestanden worden nooit overschreven. Als alleen de optionele HTML faalt,
blijft je handmatig ingevulde bronmanifest intact; de wizard geeft een
expliciete waarschuwing, niet een verzonnen successtatus voor de pagina.
`--plan-html` vereist `--manifest-only`; `--plan-verify-wavs` vereist beide.

Maak later met exact diezelfde bronmanifest een **nieuwe** sessie en de
browsergebaseerde Studio. Alle hashes, rechtenverklaringen en handmatige
cuepunten worden ongewijzigd opnieuw gebruikt:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-02 \
  --resume
~~~

Deze `--resume`-route is ook bruikbaar als de eerste import mislukte:
de bronmanifest blijft intact en je kiest een nieuwe projectmap. MixLab
controleert daarna opnieuw de bestaande officiële manifest-,
bronhash-, cue- en audioadmission. Er wordt **niets** stilzwijgend
hersteld, opnieuw getimed of over bestaande uitvoer geschreven.
`--resume` en `--manifest-only` mogen niet tegelijk worden gekozen.

## Privacy, herstel en echte beperkingen

De uitvoer wordt nooit over bestaande bestanden geschreven. Audio en
bronpaden blijven lokaal; de browser krijgt alleen veilige track-/pair-ID's
en relatieve audiolinks. Het bronmanifest is exclusief geschreven met privé
bestandsrechten en vormt een herstelpunt wanneer FFmpeg ontbreekt of een
cue buiten de song valt. Controleer dan je invoer en maak een **nieuwe**
sessiedirectory; herhaal geen QA, benchmark of frozen evaluatie.

De maximale set omvat elf tracks en tien overgangsparen. De bestaande
M1-limieten blijven gelden (o.a. begrensde per-paar audio-excerpts,
PCM16 44,1 kHz, maximaal 512 MiB complete export). Playlist Studio
**kiest de trackvolgorde niet automatisch** en doet geen beat/key/phrase-
herkenning: de operator is verantwoordelijk voor volgorde, tempo en cues.
De output is een creatieve privé-mix, geen proof van menselijk betere DJ
transitions. [M1 Transition Lab](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
blijft OPEN tot echte rechtenveilige brontracks en onafhankelijke
blind-luistervoorkeur zijn vastgelegd.
