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
De tweede overgang krijgt expliciet een eigen stijl; alle andere
paren gebruiken `bass_swap`.

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
