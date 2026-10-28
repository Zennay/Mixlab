# MixLab · Transition Lab

An offline AI-DJ research project: understand track segments, discover surprising combinations, render real transitions and eventually build full sets around context and an energy journey.

**Current phase: M1 — Transition Lab (OPEN).** MixLab now has a private real-music import route, a visual two-deck cue editor, a local transition Studio, a two-song full-length WAV exporter, a continuous multi-track WAV+chaptered player, a guided private playlist and transition-idea workflow, and a one-command playable three-song synthetic DJ demo. These are creative product features, not proof of superior musical quality. Equal-BPM/manual-cue constraints remain. Automatic downbeat/phrase/key analysis, actual source separation, approved real-track listening evidence and blinded preference comparisons have **not** passed M1 gates.

- [Notion project](https://app.notion.com/p/3e79e19ac95581a78ee3f24aa5e7e8b6)
- [Current handoff](https://app.notion.com/p/3e79e19ac95581f4bf15c26a833da642)
- [Architecture and evaluation](docs/architecture.md)
- [Infrastructure plan](docs/infrastructure.md)
- [Worker tasks and ownership](docs/worker-plan.md)

## Probeer MixLab direct — geen muziekbestanden nodig

Er is nu een **volledig lokale, luisterbare DJ-productdemo**. Deze maakt
drie originele synthetische 120-BPM-nummers, rendert acht echte
overgangsvarianten verdeeld over twee paren, één complete **drie-track
WAV-set**, een visuele golfvormspeler met hoofdstukken en de Set
Composer om zelf overgangen te kiezen. Er worden geen beschermde muziektracks, modellen of
externe diensten gedownload; voor deze WAV-demo is geen FFmpeg nodig.

~~~bash
python3 -m mixlab.demo /private/mixlab-demo-01
~~~

Open vervolgens **/private/mixlab-demo-01/index.html** in je browser.
Gebruik een nieuwe directory buiten je Git-checkout. De
synthetische productdemo is géén bewijs voor echte muziekkwaliteit of een
geblindeerde gebruikersstudie. Zie [de demo-handleiding](docs/offline-dj-demo.md).

### Eigen muziek: een complete set in één begeleide opdracht

Kies 2–11 nummers in een vaste afspeelvolgorde, leg handmatig de werkelijke
BPM, bronrechten en overgangscues vast en laat MixLab **alle bestaande
DSP-overgangen renderen**. De originele muziek blijft op je eigen computer;
MP3/FLAC/M4A vereisen reeds geïnstalleerde FFmpeg/FFprobe en canonieke
44,1 kHz PCM16-WAV werkt zonder extra runtimepakket.

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 --beats 16 \
  --full-set-wav /private/mixlab-party.wav \
  --family bass_swap
~~~

Met lokaal geïnstalleerde **FFmpeg/FFprobe** kun je in dezelfde
opdracht ook een compacte privé-MP3 of verliesvrije FLAC publiceren.
Voeg bijvoorbeeld `--delivery /private/mixlab-party.mp3 --bitrate-kbps 192`
toe. Als optionele MP3/FLAC-export niet lukt, blijft de echte WAV
beschikbaar. [Private Delivery-handleiding](docs/private-set-delivery.md).

De wizard levert nu **meteen** de volledige
**/private/mixlab-party.wav** én de offline
**/private/mixlab-party.wav.player.html** naast de gewone Studio en Set Composer.
Je kunt tijdens het invoeren ook `--style pair-002:echo_exit` kiezen
om precies die tweede overgang expliciet een andere renderstijl te geven.

Wil je de stijlkeuze juist eerst handmatig beluisteren? Open dan
**/private/mixlab-playlist-01/set-composer/index.html**, kies je route,
download `mixlab-set-plan.private.json` en render die later afzonderlijk:

~~~bash
python3 -m mixlab.set_composer render \
  /private/mixlab-playlist-01 \
  /private/mixlab-set-plan.private.json \
  /private/mixlab-party.wav
~~~

De begeleide `mixlab.playlist_studio --full-set-wav` weigert inmiddels ook
vroegtijdig een al bestaande uitvoer-WAV, onvolledige trackroute of onmogelijke
cues **vóór** dure Studio-import. Het uitvoerresultaat rapporteert afzonderlijk
`complete_set_ready`; een mislukte gevraagde WAV levert een foutcode op terwijl
een reeds succesvol gerenderde Studio behouden blijft.

De afzonderlijke volledige `mixlab.instant_set`-export weigert nu ook een
broncatalogus met vergeten nummers: alle in het SHA-gebonden manifest
opgegeven nummers moeten exact eenmaal in de route staan voordat er
überhaupt een complete WAV wordt gepubliceerd.

Bij het privé oefenen in de Full Set Player kun je de afspeelsnelheid
instellen op **0,75×, 1× of 1,25×** tijdens herhalen of contextluisteren.
Eventmodus zet de speler altijd automatisch terug op **1×**. Dit verandert
niets aan de WAV, mixtijden of SHA-receipts en is **geen** betrouwbare
muzikale kwaliteitsbeoordeling bij een afwijkende afspeelsnelheid.

In de offline speler kun je een bestaande overgang nu ook
**in context beluisteren**: kies 2, 8 of 16 seconden oorspronkelijke muziek
vóór en ná de echte SHA-gebonden overgang, zonder nieuwe rendering.
De begrensde eenmalige contextluistering stopt na het fragment of bij het
wijzigen van die selectie, is beschikbaar bij hoofdstukken en de
persoonlijke aanpassingslijst en wordt tijdens eventmodus geblokkeerd.

De originele PCM16-golfvormeditor weigert ook al vóór het bewerken
**ontbrekende of strijdige handmatige overgangs-BPM**. Hiermee voorkomt
MixLab een visueel plausibele maar later onrenderbare DJ-set; de echte
handmatige BPM-verklaring blijft leidend, zonder automatische beatmatch.

De visuele originele WAV-cue-editor laat geen onvolledige playlist
meer als bruikbare nieuwe cuekeuzes opslaan: alle geregistreerde nummers
moeten exact één keer in de A→B-route staan. Ook de afzonderlijke
`mixlab.cue_editor apply`-opdracht weigert het schrijven van een
onrenderbaar nieuw manifest. De bestaande bronmuziek blijft intact.

Je kunt je persoonlijke overgangsbeoordelingen nu ook als **leesbare
DJ-checklist (.txt)** exporteren: een direct bruikbaar overzicht van
*Nog aan te passen*, *Klinkt goed* en overige notities, met WAV-hash en
werkelijke hoofdstuktijden. Alleen het bestaande privé-JSON is later weer
terug te laden; TXT vervangt geen beveiligde notitieback-up of
onafhankelijk luisteronderzoek.

In de lokale visuele cue-editor zijn de twee **A+B-voorluistervolumes**
nu afzonderlijk regelbaar (0–50%; standaard 30%). Daarmee kun je
handmatig een binnenkomend of uitgaand nummer duidelijker horen tijdens
het vergelijken van huidige en opgeslagen cues. De echte WAV,
renderfamilies, originele rechten en cuekeuzes veranderen niet.

De privé Full Set Player heeft ook een **automatische lijst van overgangen
met de persoonlijke keuze ‘Wil aanpassen’**. Je ziet je notitie bij het
echte WAV-hoofdstuk en kunt iedere overgang opnieuw herhalen of met
**Beluister volgende aanpassing** de nog open fragmenten een voor een
afgaan. De lijst herstelt uit je eigen privé-JSON, niet uit een server;
het is geen automatische DJ-mixbewerking of onafhankelijke luisteraudit.

De offline speler waarschuwt bij nieuw ingevoerde persoonlijke
DJ-notities die nog niet veilig zijn bewaard. **Download de privé-JSON,
controleer het bestand en bevestig pas daarna 'Ik heb mijn JSON opgeslagen'.**
Alleen klikken op Download schakelt de waarschuwing niet uit; nieuwe
wijzigingen zetten hem opnieuw aan. De browser kan de waarschuwing bij
sluiten onderdrukken. Er blijft geen automatische opslag of upload bestaan.

Na het handmatig herhaald beluisteren van een overgang kun je nu in de
volledig offline Full Set Player ook **‘Klinkt goed’ of ‘Wil aanpassen’**
markeren en een korte creatieve notitie toevoegen. Download je persoonlijke
overgangsnotities als apart privé-JSON met WAV-hash, exacte hoofdstuktijden
en de geselecteerde paar-ID's. Niets wordt automatisch opgeslagen, geüpload
of als onafhankelijk luisteronderzoek meegeteld; sla het JSON-bestand zelf
op voordat je de pagina sluit. Je kunt die privé-JSON daarna
**lokaal terugladen in dezelfde WAV-speler**, ook na opnieuw openen van
het HTML-bestand. MixLab weigert een afwijkende WAV-SHA, overgangsstijl
of hoofdstuktijd en beschermt al ingevulde notities tegen stilzwijgend
overschrijven. Wil je alle eerdere beoordelingen bewust intrekken,
dan kun je **Wis alle beoordelingen** gebruiken en ook de lege stand
als nieuwe, SHA-gebonden privé-JSON downloaden en opnieuw laden.
Die reset blijft een onopgeslagen wijziging totdat de gebruiker de download
bevestigt. Er is geen account, server of automatische browseropslag.

Ook in de aparte **Transition Studio** kun je nu met **Vergelijk op
dezelfde positie** direct wisselen tussen de vier écht gerenderde
bass_swap, echo_exit, hard_cut en baseline WAV-varianten, zonder telkens
naar hetzelfde handmatig gekozen overgangsmoment te zoeken. De vorige
variant pauzeert en slechts één lokale speler is tegelijk actief. Dit is
creatief luisteren, geen onafhankelijk blind kwaliteitsonderzoek.

Tijdens het beoordelen met de offline Full Set Player kun je ook zonder
muis navigeren met **J** (vorige passage), **K** (pauze/start) en **L**
(volgende passage). Deze oefentoetsen blijven uit bij typen in velden en
in Eventmodus; de bestaande live-toets **P** blijft beschikbaar.

Ook in de aparte **Transition Studio** kun je nu met **Vergelijk op
dezelfde positie** direct wisselen tussen de vier écht gerenderde
bass_swap, echo_exit, hard_cut en baseline WAV-varianten, zonder telkens
naar hetzelfde handmatig gekozen overgangsmoment te zoeken. De vorige
variant pauzeert en slechts één lokale speler is tegelijk actief. Dit is
creatief luisteren, geen onafhankelijk blind kwaliteitsonderzoek.

De offline speler heeft een interactieve golfvorm, hoofdstukken per
overgang en CUE-export. Je kunt nu **iedere werkelijk gerenderde overgang
lokaal blijven herhalen** voor een handmatige beluistering: kies
`Herhaal overgang` op het betreffende hoofdstuk, spring verder of kies
`Stop herhalen` om af te sluiten. Eventmodus zet deze auditie-loop altijd
uit; de daadwerkelijke set-WAV, private receipts en luisterstudie-evidence
worden door deze afspeelknop niet veranderd. De complete set die je via `playlist_studio` of
`party_mix` maakt, toont daarbij herkenbare lokale songbestandsnamen en
song-A→song-B-overgangen in hoofdstukken en eventmodus. Dit zijn uitsluitend
private weergavenamen; de WAV-SHA, de originele rechtenverklaring en de
DSP-route blijven ongewijzigd. Je kunt
de via het lokale goedkeuringsformulier gekozen **expliciete overgangsstijlen nu brongebonden in het private paar** bewaren, zodat de preview en een latere `--resume --full-set-wav` dezelfde goedgekeurde DSP-stijlen hanteren; strijdige overrides worden vóór import geweigerd. Je kunt ook de handmatige invoer vooraf vastleggen met `--manifest-only --plan-html`, waardoor ook de lokale privé-HTML-speelvolgorde verschijnt zonder audio te renderen. Voeg voor canonieke 44,1 kHz PCM16 WAVs `--plan-verify-wavs` toe voor de SHA-gecontroleerde voorspelde mixtijd; hervat later via `--resume --full-set-wav` op een nieuwe bestemming. Je kunt ook alleen de handmatige invoer vooraf vastleggen met `--manifest-only` en later
zonder opnieuw typen renderen met `--resume`.

Wil je creatieve cuevoorstellen op basis van een **handmatig bevestigd**
beat/downbeat-grid en lokale RMS-energie, gebruik dan `--ideas`
(vereist een expliciet ingevulde eerste downbeat voor iedere track).
Elke keuze vereist handmatige goedkeuring; geen automatische muzikale
kwaliteit of echte phrase-detectie wordt geclaimd.

Lees [de Playlist Studio-handleiding](docs/guided-playlist-studio.md),
[de offline Set Composer](docs/offline-set-composer.md),
[de Full Set Player](docs/private-full-set-player.md) en
[Transition Idea Board](docs/transition-idea-board.md),
[de nieuwe complete cue-goedkeuringsflow](docs/cue-idea-production-workflow.md),
[Instant Set](docs/instant-private-full-set.md) en
[Set Gallery](docs/offline-full-set-gallery.md).

### Vergelijk twee complete mixes zonder opnieuw te beginnen

Render twee privé volledige playlists met verschillende al bestaande,
écht gerenderde overgangsstijlen en wissel in de lokale browser
op dezelfde afspeelpositie:

~~~bash
python3 -m mixlab.set_gallery \
  /private/mixlab-playlist-01 \
  /private/mixlab-variant-gallery
~~~

Open **/private/mixlab-variant-gallery/index.html**. Dit is geen
blinde kwaliteitsmeting: de stijlkeuzes zijn zichtbaar en de muziek
blijft lokaal. Gebruik [de volledige Set Gallery-handleiding](docs/offline-full-set-gallery.md)
voor tot vier varianten.

### Event Brief Studio — stel een DJ-set samen vanuit één lokaal scherm

Vanaf een lokale rechtenveilige muziekmap kun je **een echte event-brief
instellen**, zonder zelf een commando voor elke plannerkeuze te typen.
Kies een gewenste energiecurve, aantal nummers, handmatig geverifieerde BPM,
mood/genre, vaste opener/afsluiter en nummers die niet gedraaid mogen worden.
De browser toont direct een bewerkbare setvolgorde en energiecurve.

~~~bash
python3 -m mixlab.journey notes /private/music /private/music/energy-notes.private.json
python3 -m mixlab.journey_workspace /private/music /private/music/energy-notes.private.json /private/music/event-studio.private.html
~~~

Open `/private/music/event-studio.private.html` lokaal. Exporteer een nieuw
`mixlab-event-journey.private.json` naar je eigen muziekmap en gebruik dat
als `--journey-plan` in de bestaande `mixlab.playlist_studio` (met
`--full-set-wav` voor de werkelijke volledige mix). De Studio checkt de
originele bronhashes opnieuw en vraagt expliciete toestemming, rechten,
herkomst en de echte, door jou gecontroleerde overgangscues.

**Dit analyseert geen geluid automatisch.** De volgorde is een beperkt,
offline voorstel op basis van jouw notities; M1-kwaliteit en luistervoorkeur
zijn niet bewezen. [Volledige Event Brief-handleiding](docs/offline-event-brief-studio.md).

### Eén opdracht: goedgekeurde set → echte WAV, optionele MP3 en draaiboek

Na het lokaal opstellen van een Energy Journey/Event Brief-plan en het
ondertekenen van je handmatig gecontroleerde rechten-/cueformulier kan de
nieuwe **Event Publisher** in één opdracht het hele privéfeestpakket
opleveren: een echte complete WAV uit de bestaande DSP-engine, offline
hoofdstukspeler, eventueel MP3/FLAC en een printbaar operator-draaiboek
met de daadwerkelijke hoofdstukoffsets.

~~~bash
python3 -m mixlab.event_publish \
  /private/music \
  /private/music/event-plan.private.json \
  /private/music/mixlab-event-approved.private.json \
  /private/mixlab-party-01 \
  --delivery mp3 --start 19:30
~~~

De opgegeven outputmap moet **nieuw zijn** en buiten Git en de muziekmap
liggen. MixLab hercontroleert bron- en planhashes en blijft expliciet
vragen of je de gekozen volgorde echt goedkeurt. Per overgang worden de
eigen reeds ondersteunde DSP-families gebruikt. Het audiomasterbestand
blijft behouden als optionele compressie of draaiboekexport mislukt.
Geen bronuploads, automatische rechtencontrole of onbewezen M1-bewijs.
[Private Event Publisher-handleiding](docs/one-command-private-event-production.md).

### Je complete event in één privé startpagina

Dezelfde Event Publisher maakt nu optioneel automatisch
\`/private/mixlab-party-01/index.html\`: open die lokale HTML
om de daadwerkelijke setlengte, echte hoofdstukmarkeringen,
de WAV-speler, eventuele MP3/FLAC en het operator-draaiboek
vanuit één overzichtelijk dashboard te openen. De pagina
is offline en gebouwd op de hashgecontroleerde master-WAV.
[Handleiding](docs/private-event-dashboard.md).

### Neem een complete privésessie mee als één ZIP

Voor een eigen USB-drive of offline backup kun je in dezelfde
\`python3 -m mixlab.event_publish ...\` opdracht de optionele
\`--bundle\` vlag toevoegen. MixLab bouwt dan een nieuw
\`final-set.private.zip\` uit de **werkelijk gerenderde**
WAV/receipts, beschikbare MP3/FLAC, spelers, eventdashboard
en draaiboek. In het ZIP zitten géén originele muzieksources
of interne rechten-/cue-manifests. Alles blijft lokaal;
de rechten om een mix te delen moet je zelf hebben.
De bundel is optioneel zodat grote WAV-bestanden niet
onnodig extra opslag vragen.
[Handleiding](docs/private-portable-event-bundle.md).

### Offline eventdraaiboek uit je échte, complete DJ-set

Heb je een volledige MixLab-WAV mét originele Studio en privéreceipt
gerenderd, dan kan MixLab er direct een **printbaar showdraaiboek** van
maken. Dit gebruikt de exacte, hashgebonden WAV-hoofdstukken in plaats van
geschatte tracklengtes, inclusief per overgang de echte start-offset.
Voer optioneel zelf een geplande lokale begintijd in om kloktijden en
verwacht eindmoment te projecteren; voeg DJ-notities toe, doorloop de
soundcheck-checklist en exporteer een privé CSV-cuesheet.

~~~bash
python3 -m mixlab.show_runbook /private/mixlab-event-session /private/my-event.wav /private/my-event.runbook.private.html
~~~

Open de HTML lokaal. Een ontbrekend of gewijzigd bron-/renderreceipt maakt
geen geldig draaiboek; de bestaande Studio/WAV-bronintegriteitscontrole
blijft verplicht. De afspeelklok, niet de geplande tijd, is leidend bij
pauzes of live onderbrekingen. [Show Runbook-handleiding](docs/offline-dj-show-runbook.md).

### Rechten en overgangscues in één privé-browserformulier

Maak van jouw voorgestelde DJ-set een echte volledige set zonder voor
elk nummer opnieuw BPM/rechten/cues in de terminal over te typen.
Een nieuw offline formulier toont alle SHA-gebonden nummers, verzamelt
jouw expliciete gebruiksrechten en bronherkomst, en de echte door jou
gecontroleerde A/B-cuepunten. Exporteer daarna een nieuw privé-
goedkeuringsbestand en voer een **bestaande Playlist Studio-render**
uit, met één laatste expliciete toestemming vóór er muziek verwerkt wordt.

~~~bash
python3 -m mixlab.playlist_approval /private/music /private/music/set-plan.private.json /private/music/playlist-approval.private.html
# Open de HTML lokaal en exporteer mixlab-event-approved.private.json.
python3 -m mixlab.playlist_studio /private/music /private/music/approved-sources.private.json /private/event-session --journey-plan /private/music/set-plan.private.json --approval-file /private/music/mixlab-event-approved.private.json --beats 16 --full-set-wav /private/event.wav
~~~

In dit formulier kun je inmiddels ook per nummer een **lokaal
audiobestand kiezen en direct beluisteren**: tik op de afspeelkop en
markeer eerste downbeat, outgoing A of incoming B cue. Er wordt alleen
een lokale tijdelijke blob-afspeel-URL gebruikt; de originele audio
wordt niet geüpload. Je handmatig opgegeven BPM ondersteunt
vier-beat-sprongen, niet automatisch beatmatching.

Je kunt vervolgens **twee lokale nummers als overgang samen voorluisteren**:
de nieuwe knop \`Rehearse A→B transition\` maakt een tijdelijke
equal-power browser-crossfade van de exact handmatig opgegeven
startcues en overgangslengte, met stopknop en voortgang.
Dit is een creatieve preview en **geen** rendering of maat voor
kwaliteit van de definitieve DSP-overgang. Er wordt geen audio
geüpload.

Verder kies je voortaan in dit formulier **per overgang de echte
rendermethode** (\`baseline\`, \`bass_swap\`, \`echo_exit\`
of \`hard_cut\`). Bij een volledige \`--full-set-wav\`
past de bestaande MixLab-renderer die expliciete pair-keuzes toe:
geen losse \`--style pair-001:...\` argumenten nodig. De
browser-crossfade is uitsluitend een creatieve vergelijking; de
definitieve uitvoer komt uit de echte canonieke DSP-recepten.

Een browserinvoer is **geen juridisch rechtenbewijs** en vervangt geen
muzikale analyse of echte luisteracceptatie. De renderer controleert bron-
SHA, plan-SHA, cuegrenzen, rechtenverklaring en finale menselijke
goedkeuring opnieuw. [Volledige formulierhandleiding](docs/offline-playlist-approval.md).

### Nieuw: plan een energieboog en laat MixLab de volgorde voorstellen

Je hoeft de volgorde niet meer volledig zelf te verzinnen. Leg eerst per
lokaal nummer de **handmatig geverifieerde BPM**, energie (1–10) en eventueel
genre/mood vast. Laat de offline planner vervolgens een opbouwende, piekende
of aflopende set van 2–11 nummers voorstellen. In een lokale browser kun je
de energiecurve bekijken en nummers omhoog of omlaag bewegen.

~~~bash
python3 -m mixlab.journey notes /private/music /private/music/energy-notes.private.json
python3 -m mixlab.journey plan /private/music /private/music/energy-notes.private.json /private/music/journey.private.json --tracks 5 --shape late-peak
python3 -m mixlab.journey_board /private/music /private/music/journey.private.json /private/music/journey-board.private.html
~~~

Open daarna `/private/music/journey-board.private.html`, bewerk de
voorgestelde volgorde en exporteer de nieuwe privé-JSON in je muziekmap.
Geef die aan de gewone Playlist Studio met
`--journey-plan /private/music/mixlab-journey-curated.private.json` en
eventueel `--full-set-wav /private/my-event.wav`. De Studio verifieert alle
SHA-256-bronnen opnieuw, vraagt expliciet toestemming voor de voorgestelde
volgorde, rechten, herkomst en handmatige cues en rendert pas daarna de
bestaande echte WAV-set. Er wordt **geen BPM of muzikaal oordeel automatisch
uit muziek afgeleid**: dit is heuristische setplanning op menselijke notities.
[Volledige handleiding](docs/energy-journey-planner.md).

### Vier setopbouwen vergelijken in een offline browser

Met dezelfde handmatige BPM- en energie-notities kun je vier complete
trackvolgordes naast elkaar vergelijken, inclusief de voorgestelde
energiecurve, en één route rechtstreeks exporteren als nieuw privéplan.

~~~bash
python3 -m mixlab.journey_compare /private/music /private/music/energy-notes.private.json /private/music/all-journeys.private.html --tracks 5
~~~

Open de HTML lokaal, kies een route en geef het gedownloade plan door
aan Playlist Studio met --journey-plan. Geen automatische muziekanalyse
of blind-luisterbewijs; zie de Energy Journey-handleiding.

### Leg een vaste openingsplaat en afsluiter vast

Voor bruiloften, feesten en optredens kun je MixLab dwingen om een
**specifiek nummer als eerste en laatste** te kiezen, terwijl de
setopbouw ertussen geoptimaliseerd wordt. Sluit bovendien nummers uit
die niet in de set mogen komen. Gebruik bij de Energy Journey Planner
of vierwegvergelijking de extra argumenten
--opening "Welcome Track.wav" --closing "Last Dance.wav"
--exclude-track "Not Tonight.wav". De nummers moeten voorkomen in je
handmatig geverifieerde notities en precies dezelfde BPM hebben. In
de offline editor mag je de volgorde daarna alsnog bewust aanpassen.
[Details](docs/energy-journey-planner.md).

### Alternatief: visuele cue-editor voor één zelfgekozen overgang

MixLab kan privé en lokaal eigen toegestane MP3/FLAC/M4A/WAV verwerken,
cues visueel laten goedkeuren en een volledige mix exporteren.
Bij een handmatig gewijzigd cuepaar kun je in de offline privé-editor nu
**Huidige cues A + B** én **Opgeslagen cues A + B** direct voor/na
beluisteren. Dat gebeurt op de originele, lokaal gehashte audiobronnen,
zonder de wijziging terug te draaien of een nieuwe WAV te renderen.
Dit is een ruwe timingvergelijking, geen MixLab-DSP-crossfade of
onafhankelijke luisterstudie.
Gecomprimeerde audio vereist bestaande FFmpeg/FFprobe; 44,1 kHz PCM16-WAV
werkt ook direct met de Python-standaardbibliotheek.

~~~bash
python3 -m mixlab.project_wizard /private/music /private/music/sources.json
python3 -m mixlab.interactive_session start /private/music/sources.json /private/mixlab-project-01
~~~

Open **/private/mixlab-project-01/sources/cue-editor.html**, beluister de
nummers, selecteer handmatig de A/B-startmomenten en download de keuze-JSON.
Rond vervolgens af en maak optioneel direct één volledig tweetrack-WAV:

~~~bash
python3 -m mixlab.interactive_session finish /private/mixlab-project-01 /private/mixlab-cue-selections.json \
  --pair pair-001 --full-song --full-song-family bass_swap
~~~

Open **/private/mixlab-project-01/studio/index.html** voor de korte
transities of **/private/mixlab-project-01/full-song/index.html** voor de
volledige mix. Zie [interactieve workflow](docs/interactive-private-studio.md),
[complete mix](docs/full-song-mix-export.md) en
[volledige sets met meerdere tracks](docs/continuous-set-export.md).

**Privacy / grens:** bronmuziek blijft buiten Git en wordt niet geüpload.
Een rechtenverklaring is geen juridisch bewijs. Automatische BPM-
matching, echt key/phrase/downbeat-begrip en human-preference bewijs
zijn niet afgerond; experimenteer alleen met bronnen die je mag gebruiken.

### DJ-marathon draaien en operator-cues bewaren

Elke originele of handmatig geblende **Event Marathon** heeft in zijn
bestaande offline `index.html` nu een groot **Stage-paneel** met de
werkelijke WAV-playhead, huidige set, volgende handoff, seconden-aftelling
en fullscreenbediening. Markeer handmatige cues tijdens het beluisteren,
exporteer een bron-SHA-gebonden privé-JSON en maak daarvan een **printbaar
evenementdraaiboek**:

```bash
python3 -m mixlab.marathon_cue_sheet /private/marathon/marathon.wav \
  /private/mixlab-marathon-cues.private.json /private/marathon/cues.private.html
```

Ook terugzetten op een andere computer kan door de JSON in de offline
Stage te importeren. Er is geen upload, automatische rechtencontrole,
audio-opname of nieuwe AI-engine. Bewaar voor echte optredens altijd een
separate WAV-back-up. [Stage-handleiding](docs/marathon-stage.md).

### Offline een reeks bestaande DJ-sets herschikken en écht renderen

De **Marathon Sequence Studio** ordent complete reeds toegestane, privé
DJ-master-WAVs vanuit een offline browser. Verplaats events, sluit ongewenste
events uit en exporteer een plan dat aan de exacte WAV-hashes is gekoppeld.
Daarna verwerkt de canonieke renderer die keuze na expliciet `yes` tot een
**nieuw doorlopend WAV-bestand** met privé player, receipt en optioneel USB-pakket.

```bash
python3 -m mixlab.marathon_sequence prepare /private/mixlab-sequence.html \
  /private/set-a/session /private/set-a/final.wav \
  /private/set-b/session /private/set-b/final.wav \
  /private/set-c/session /private/set-c/final.wav

# Maak met de browser het bestand mixlab-marathon-sequence.private.json.
python3 -m mixlab.marathon_sequence render /private/mixlab-marathon-sequence.private.json \
  /private/new-marathon \
  /private/set-a/session /private/set-a/final.wav \
  /private/set-b/session /private/set-b/final.wav \
  /private/set-c/session /private/set-c/final.wav --bundle
```

Je kunt in de nieuwe offline editor ook **eigen originele WAV-bestanden
lokaal aankoppelen en beluisteren**: de eerste/laatste 12 seconden per
afgeronde DJ-set, en een benaderende tweedeksoverlap voor een gekozen
2/4/8/16-secondenovergang. Alleen naam en bestandsgrootte worden door
de browser gecontroleerd; de daadwerkelijke bron-SHA en authorisatie
worden pas bij de officiële CLI-render volledig opnieuw gevalideerd.
Geen upload, sessieopslag of audio-embedding.

Voor **echt gerenderde handmatige crossfades per overgang** kies je in de
offline editor *Separate manually blended WAV* en de gewenste 2/4/8/16 seconden
per inkomende set. Voeg bij de bovenstaande `render`-opdracht toe:
`--blend-output /private/nieuwe-aparte-crossfade-marathon`. MixLab bewaart
de originele complete WAV, vraagt daarna **opnieuw expliciete goedkeuring**,
en gebruikt de bestaande PCM16-blendengine om een tweede WAV te schrijven.
Ook als de extra crossfade-render niet lukt, blijft het origineel behouden.

Geen muziek wordt geüpload. Zowel bronbestanden als sessiereceipts worden
opnieuw gecontroleerd; handmatige toestemming voor de uiteindelijke nieuwe
WAV blijft verplicht. Muzikale kwaliteit en rechten voor openbaar gebruik
blijven apart te beoordelen. [Sequence Studio-handleiding](docs/marathon-sequence-studio.md).

Als je bij `marathon_sequence render` óók `--review-output
/private/review/mixlab-master-review.private.html` opgeeft, maakt MixLab na
de twee afzonderlijk goedgekeurde echte WAV-renders meteen een nieuwe offline
**Master Review** aan. Zo kun je beide WAVs direct vergelijken en daarna
uitsluitend de menselijke definitieve keuze naar privé-MP3/FLAC of USB
exporteren; de bron-WAVs blijven onveranderd. De doelmap voor de nieuwe
HTML moet vooraf bestaan. [Master Review](docs/marathon-master-review.md).

Een via **Master Review** gekozen privé-Marathon-USB-pakket kan voortaan
optioneel ook de originele operator-keuze en per-overgangsnotities behouden.
`marathon_master_review publish --bundle` levert dit op na de expliciete
keuze; losse `marathon_bundle --master-choice CHOICE.json` kan dezelfde
besloten bijlage meenemen, maar nooit automatisch zonder verzoek. De
`event_restore`-route verifieert na extractie dat het besluit bij de
daadwerkelijk herstelde WAV hoort. Geen externe identiteit/rechtenauthenticatie.

Bij de expliciet aangevinkte keuze-overdracht levert MixLab nu ook
`marathon.master-choice.private.html`: een volledig offline,
printbare DJ-handoff met de werkelijke WAV-overgangstijden, gekozen
fade-duren en de eigen privénotities. Je kunt die ook los maken met
`python3 -m mixlab.marathon_master_review brief SELECTED.wav CHOICE.json NEW.html`.
Na USB-herstel controleert de bestaande herstelroute dat de printbrief
uit de echte SHA-geverifieerde WAV en bijbehorende notities opnieuw
identiek te maken is. Standaard ZIP-pakketten blijven zonder notities.

### Luister naar de twee échte Marathon-masters en lever alleen je keuze op

Na een handmatig gerenderde crossfade bestaat naast het oorspronkelijke WAV
ook een tweede WAV met echte PCM16-overgangen. Met de nieuwe **Marathon Master
Review** vergelijk je die twee reeds bestaande lokale masters direct op hun
werkelijke eventovergangen. Je kiest zelf de definitieve versie en geeft pas
daarna toestemming voor het mobiele bestand of de USB-bundel.

```bash
python3 -m mixlab.marathon_master_review prepare \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  /private/review/mixlab-master-review.private.html

# Open de offline HTML, beluister beide échte WAVs en exporteer
# mixlab-marathon-master-choice.private.json.
python3 -m mixlab.marathon_master_review publish \
  /private/review/mixlab-marathon-master-choice.private.json \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  --delivery mp3 --bundle
```

Deze route controleert opnieuw de originele én afgeleide WAV-receipts en
SHA-256-bronrelatie. De operator moet de exacte selectie met `yes` bevestigen;
alleen de gekozen master wordt als nieuwe privé-uitvoer gecodeerd/verpakt.
Het is geen geblindeerde luisterstudie, geen rechtenverklaring en geen live
kwaliteitscertificaat. [Master Review-handleiding](docs/marathon-master-review.md).

Bij de bestaande `marathon_sequence render`-opdracht kun je nu
`--reels-output /private/nieuwe-luistermap` meegeven naast
`--blend-output /private/nieuwe-blendmap`. Na de echte originele én
apart goedgekeurde blended WAV vraagt MixLab om afzonderlijke toestemming
om korte fragmenten rond alle overgangen uit de echte WAVs te kopiëren.
Daarna is de luistermap meteen klaar. Het optionele luisterpakket faalt
of wordt geweigerd zonder de twee afgewerkte masters weg te halen.

Wil je de **korte echte PCM-overgangen** meenemen naar een andere computer,
zonder de volledige originele en gemixte Marathon-WAVs te kopiëren? Maak de
besloten `join-reels.private.zip` met
`python3 -m mixlab.marathon_reels_transfer pack REELS_DIR REELS_DIR/join-reels.private.zip`
en zet deze op de andere computer terug met
`python3 -m mixlab.marathon_reels_transfer restore ZIP NEW_FOLDER`.
De originele fragmentreceipts en WAVs worden opnieuw gecontroleerd.
De ZIP bewijst geen externe identiteit of muziekrechten.

Een visual-Sequence-Studio-render kan nu ook meteen een privé-USB-bestand
maken van de korte echte PCM-overgangen: voeg expliciet
`--reels-output /private/nieuwe-luistermap --reels-usb` toe naast
`--blend-output /private/nieuw-blendresultaat`.
Na afzonderlijke toestemming voor de originele master, het echte
crossfade-resultaat en de excerpt-kopie verschijnt ook
`join-reels.private.zip` in de nieuwe luistermap. Er gaan géén volledige
Marathon-WAVs of originele tracks mee in dit kleine pakket; mislukte
optionele packaging raakt bestaande outputs niet.

### Hoor de échte overgang zonder complete urenlange WAV te laden

**Real Join Reels** maakt uit twee al officieel geverifieerde private
Marathon-masters (origineel en bestaande PCM16-crossfadeversie) een **compact
offline luisterpakket** met twee werkelijke WAV-fragmenten per event-overgang.
Het zijn exacte frames uit de bestaande audio, geen benadering met twee
browserdecks.

```bash
python3 -m mixlab.marathon_join_reels \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  /private/handoff-listening
```

Na expliciet `yes` krijgt de DJ een besloten map met echte 2×-WAV snippets,
een overzichtelijke lokale A/B-speler en brongebonden frame-/SHA-receipts.
Schakel direct per overgang van originele harde join naar de daadwerkelijk
gerenderde crossfade. De map bevat beperkte media maar géén externe
upload; notities worden pas privé gedownload na eigen actie. Dit is een
niet-blinde handmatige preview, dus geen bewijs van muziekrechten of M1
menselijke voorkeur. [Real Join Reels](docs/marathon-real-join-reels.md).

### Mix de beste echte overgang per join tot één nieuwe master

In dezelfde besloten Real Join Reels-speler kiest de DJ nu bij **elke**
overgang bewust *originele harde join* of *de al bestaande echte crossfade*.
Na het expliciet downloaden van een bron-SHA-gebonden JSON kan MixLab met
beide oorspronkelijke, lokaal goedgekeurde WAV-masters de geselecteerde
overgangen daadwerkelijk als **één nieuwe hybride PCM16-WAV** renderen:

```bash
python3 -m mixlab.marathon_reel_decisions \
  /private/choices/mixlab-marathon-join-master-picks.private.json \
  /private/marathon-original/marathon.wav \
  /private/marathon-blend/marathon.wav \
  /private/new-hybrid-event --bundle
```

Inclusief nieuw volledig audio-receipt, lokale afspeelpagina, printbare
privé-cue-sheet met echte WAV-SHA/notities **én de nieuwe offline live
operator-mode `master-picks.stage.html`**: nu/volgende set, countdown tot
de werkelijke gerenderde join, terug/vooruit en ±15 seconden zoeken,
8 seconden voor overgang cuen en fullscreen op laptop/tablet. **Harde joins blijven
sample-exact**, gekozen fades zijn bestaande 2/4/8/16s PCM16-renderkeuzes.
Afzonderlijke typed-`yes`-goedkeuring blijft vereist. Optioneel
`--reels-output /private/hybrid-reels --reels-usb` maakt na nóg een
toestemming meteen opnieuw een echte korte originele-versus-hybride PCM16
luistermap en besloten USB-ZIP. Privékeuzes gaan
niet automatisch mee in een ZIP, en vormen geen geblindeerd bewijs.
[Human-selected Hybrid Master](docs/marathon-human-hybrid-master.md).

Voor een tweede offline podiumapparaat is nu ook een strikt opt-in
**kleine ZIP met uitsluitend besloten DJ-notities** beschikbaar:
`--operator-notes-usb` vraagt pas na de goedgekeurde echte hybride WAV
nog een afzonderlijke `yes`. Met
`python3 -m mixlab.marathon_operator_transfer pack|restore` neem je de
keuzes veilig mee naar een **reeds apart ontvangen, SHA-geverifieerde**
hybride audiomaster. Restore genereert daarop de printbare cue-sheet en
offline stagepagina opnieuw. Geen muziek in de notitie-ZIP; geen privénotities
automatisch in de reguliere muziekexport.

Hetzelfde offline podiumscherm kan nu bij een repetitie de **werkelijke
afspeelpositie markeren** wanneer je een overgang hoort, met het verschil ten
opzichte van de SHA-/receipt-gebonden join. Expliciete export geeft alleen
een privaat JSON-journal; met
`python3 -m mixlab.marathon_stage_journal WAV LOG NEW_REPORT_HTML`
ontstaat een **printbaar privé-repetitieverslag** naast de reeds geverifieerde
hybride WAV. Dit meet alleen handmatige browserafspeelposities en claimt
geen echte podiumtijden, luisterpreferentie of muziekrechten.




### Nieuw: een volledig evenement bedienen met meerdere echte DJ-sets

Met **Show Conductor** combineer je nu 2–6 onafhankelijke, reeds afgeronde,
SHA-gecontroleerde privé-DJ-masters in **één offline handmatig showdraaiboek**.
MixLab leest de bestaande echte WAVs, officiële receipts en hoofdstukcues
opnieuw; er wordt geen muziek geüpload of verborgen geremixed.

~~~bash
python3 -m mixlab.show_conductor prepare \
  /private/event-ops/mixlab-show-control.html \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav \
  --start 19:30 --break-minutes 10
~~~

Open de HTML lokaal en koppel de complete WAV van elke set handmatig via de
browser; arm en start de volgende set **alleen zelf**. Je ziet de huidige
set, geplande pauzes, echte hoofdstukken en operatornotities. Via het
expliciet gedownloade privé-JSON genereert
`python3 -m mixlab.show_conductor print ...` na hercontrole van alle
volledige WAV-SHAs een afdrukbaar evenementdraaiboek. Geen automatische
crossfade, cloud, browseropslag of garantie voor professioneel livegeluid.
[Show Conductor-handleiding](docs/offline-multi-set-show-conductor.md). Eerder opgeslagen
showplanning terughalen zonder opnieuw pauzes/notities in te voeren kan nu
via `mixlab.show_conductor resume OLD_PRIVATE_PLAN NEW_MIXLAB_HTML DEZELFDE_SESSION_WAV_PAREN`:
volledige WAV- en bron-SHAs worden opnieuw gecontroleerd, alle menselijke
operator-keuzes ingevuld en het plan blijft lokaal bewerkbaar.


### Één echt showbestand uit meerdere goedgekeurde privé-sets

Na het plannen in **Show Conductor** kan MixLab nu ook **één nieuwe,
werkelijk gerenderde PCM16-show-WAV** maken uit 2–6 eerdere complete
MixLab-sets en door jou gekozen echte digitale stilte tussen de sets.
Geen browser- of realtime mix: alle oorspronkelijke complete WAVs worden
opnieuw op SHA/receipt en bronidentiteit gecontroleerd en onveranderd
in begrensde blokken gekopieerd. De 768 MiB-outputgrens beschermt opslag.

~~~bash
python3 -m mixlab.show_master \
  /private/event-ops/mixlab-show-conductor.private.json \
  /private/new-real-show \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav
~~~

Na getypte `yes` komt er een nieuwe besloten outputmap met echte `show.wav`,
volledige SHA-/frames-receipt en een lokale hoofdstuk-/pauzespeler.
De bronnen worden nooit aangepast of automatisch gepubliceerd. Pauzes
zijn letterlijke stilte, geen automatisch gemixte overgangen; bij
flexibele evenementen gebruik je de handmatige Show Conductor.
[Complete Show Master](docs/private-complete-show-master.md).

### Privé-showmaster meenemen als MP3/FLAC of USB-ZIP

Een al afzonderlijk goedgekeurde **echte `show.wav`** kan nu optioneel via
lokaal geïnstalleerde FFmpeg/FFprobe naar een private MP3 of FLAC, of met
een apart getypte `yes` als brongebonden ZIP worden geëxporteerd:

~~~bash
python3 -m mixlab.show_delivery encode /private/new-real-show/show.wav --format mp3
python3 -m mixlab.show_delivery pack /private/new-real-show/show.wav --include-encoded
~~~

Zowel de originele volledige WAV als optionele compressie worden opnieuw op
SHA, receipt, frames en herkomst gecontroleerd. **De lokale originele show-
receipt en HTML bevatten privénotities**: de ZIP exporteert daarom
uitsluitend een nieuw gegenereerde, **opgeschoonde** receipt en offline speler
zonder DJ-notities, eventfoldernamen of de privé-aanvangstijd. Het echte
WAV-bestand blijft onveranderd, brontracks worden niet meegeleverd en er
wordt niets geüpload. Zonder `--include-encoded` bevat de ZIP alleen
originele show-WAV plus opgeschoonde metadata/speler.
[Portable Complete Show](docs/portable-complete-show-delivery.md). Een eenmaal toegestaan
privé-ZIP herstel je op een tweede offline apparaat via
`python3 -m mixlab.show_restore ZIP NEW_PRIVATE_FOLDER`. De applicatie
controleert daarna alle echte WAV-/metadata-SHA's opnieuw en accepteert
alleen de exact opnieuw gegenereerde, opgeschoonde officiële HTML-spelers;
gewijzigde HTML uit een ZIP wordt niet vertrouwd. Geen automatische
muziektoestemming of internetverbinding.

### Één echt showbestand uit meerdere goedgekeurde privé-sets

Na het plannen in **Show Conductor** kan MixLab nu ook **één nieuwe,
werkelijk gerenderde PCM16-show-WAV** maken uit 2–6 eerdere complete
MixLab-sets en door jou gekozen echte digitale stilte tussen de sets.
Geen browser- of realtime mix: alle oorspronkelijke complete WAVs worden
opnieuw op SHA/receipt en bronidentiteit gecontroleerd en onveranderd
in begrensde blokken gekopieerd. De 768 MiB-outputgrens beschermt opslag.

~~~bash
python3 -m mixlab.show_master \
  /private/event-ops/mixlab-show-conductor.private.json \
  /private/new-real-show \
  /private/dinner/studio-session /private/dinner/final-set.wav \
  /private/dance/studio-session /private/dance/final-set.wav
~~~

Na getypte `yes` komt er een nieuwe besloten outputmap met echte `show.wav`,
volledige SHA-/frames-receipt en een lokale hoofdstuk-/pauzespeler.
De bronnen worden nooit aangepast of automatisch gepubliceerd. Pauzes
zijn letterlijke stilte, geen automatisch gemixte overgangen; bij
flexibele evenementen gebruik je de handmatige Show Conductor.
[Complete Show Master](docs/private-complete-show-master.md).

## Implemented

- Canonical Track, Segment, Recipe and TransitionCandidate records.
- Validated, checksum-bound local audio manifests with explicit permission declarations.
- Deterministic PCM16 mono/stereo renderer: equal-power baseline, bass swap, echo exit and hard cut.
- Peak, RMS, clipping, DC offset and sample-jump diagnostics; identical render length and common gain across recipes.
- Original synthetic fixtures for reproducible infrastructure tests.
- Neutral A/B audio filenames, a local listening page, separate answer key and downloadable ratings.
- Strict streaming ingest with recording/PCM split-leakage checks and a JSON Schema.
- Replaceable analysis provider, measured regular-tempo proposals, manual cue/key annotations, content-addressed private feature cache and beat-error evaluation.
- Streaming transition renderer with exclusive complete-file publication, clipping rejection and post-PCM metrics.
- Checksum-bound rating aggregation with duplicate/coverage validation and explicit volume confounds.
- One-command private playlist Studio (2–11 tracks), manual tempo/rights/cues,
  ordered transition pair graph, immutable stage/resume and offline Set Composer.
- Checksum-bound transition-energy Idea Board with explicit DJ approval into a
  new development manifest; no silent changes to frozen evaluations.
- Full private continuous WAV, chaptered offline player, clickable sampled
  waveform, keyboard navigation and CUE/JSON chapter exports.
- No runtime dependencies beyond Python 3.10+ standard library.

## Reproduce on the VPS runner

Shell/build/test/render execution goes through the existing GitHub self-hosted runner on `vps-bb300bba`. Do not provision another server or install models for this slice.

```bash
python3 -m unittest discover -s tests -v
python3 -m mixlab fixture /tmp/mixlab-example-library
python3 -m mixlab validate /tmp/mixlab-example-library/library.json
python3 -m mixlab benchmark /tmp/mixlab-example-library/library.json /tmp/mixlab-example-pack --seed 42
```

Use fresh output directories; existing packs are never overwritten. Open `review/index.html` locally. Only the `review/` directory goes to listeners; `private/` contains identity mappings, recipes, source paths and metrics. Omit `--seed` for real listening pilots. The synthetic fixture is **not** a music benchmark.

The canonical M1 benchmark still consumes short uncompressed PCM16 WAV excerpts with identical source channel count/sample rate (8–96 kHz), manual equal BPM, and max 32 MiB / 2 million frames per excerpt. **Separate new product modules do accept bounded full-length WAV and optionally FFmpeg-decoded MP3/FLAC/M4A**, and can export private continuous mixes. Tempo stretching and automatic musical alignment remain separate, unfinished work. The benchmark renderer now processes bounded blocks and a compact delay ring; the original array renderer remains as a regression reference. The exact-source VPS run must establish measured memory and timing.

The current pilot uses common gain, not matched perceived loudness; this is a known listening confound to fix before a milestone-quality benchmark. Objective diagnostics are not a musical preference score. Do not tune on a frozen evaluation set.

## Local library manifest

The fixture command writes a complete example. Replace sources only with explicitly permitted local excerpts and recompute their SHA-256 values. Each track requires `id`, relative `path`, `sha256`, `bpm`, `rights` and nonempty `provenance`. Supported manifest permissions: `synthetic`, `licensed`, `user-permitted`, `public-domain`. A permission declaration is provenance metadata, not verification of legal ownership. `pairs` declares distinct `a`/`b` IDs, BPM, integer beat count and start offsets in seconds.

Keep source media, derived stems, private renders, manifests with personal paths and credentials outside this public repository. Only synthetic CI fixtures and sanitized aggregate evidence may be uploaded by the foundation workflow.

## Direct een complete lokale WAV-set maken

De nieuwe private `party_mix` route voert bestaande stappen achter elkaar
uit: rechten- en SHA-gebonden lokale muziekinvoer → handmatige cue-Studio →
zelfgekozen overgangen → één doorlopende PCM16-WAV.

```bash
python3 -m mixlab.party_mix /private/music/project.json /private/new-studio /private/full-set.wav \
  --transition pair-001:bass_swap --transition pair-002:echo_exit
```

Het offline visuele mixplan kun je als A4 DJ-draaiboek afdrukken via Ctrl+P / Cmd+P. De nieuwe zwart-op-wit printweergave houdt de trackvolgorde, handmatige cues en geverifieerde tijdlijn leesbaar, zonder extra audiobestand of server.

Met `--preview --verify-wavs --preview-html` toont MixLab nu ook
**een statische, proportionele mixkaart** waarin alle solo's en overgangen
de echte onderlinge duurverhouding uit PCM-frames krijgen. Je kunt met
muis of toetsenbord van elk vak naar de exacte hoofdstuktijd springen,
zonder netwerk, scripts of een nieuw audio-bestand. Daaronder staan
**de echte vooraf berekende tijdlijn van ieder nummer en elke overgang**,
met exact aan de PCM-frametelling gekoppelde starttijden. In de JSON staat
de volledige `planned_chapters`-lijst; die kan na het renderen één-op-één
met de SHA-gebonden hoofdstukspeler worden vergeleken. Zonder originele
PCM16-bronverificatie wordt geen gerenderde duur of precieze setpositie
verzonnen.

Heb je de handmatige playlist al bewaard? Je kunt die later ook **opnieuw
als privé-visueel plan openen** met `--resume --plan-html` zonder nieuwe
Studio of WAV. Voeg `--plan-verify-wavs` toe voor exacte SHA-gecontroleerde
PCM16-bron-/hoofdstuktijden. MixLab hergebruikt de oorspronkelijke muziek,
playlistvolgorde en gekozen overgangsstijl, en wijzigt het bronmanifest niet.
Als je voor de heropende visuele preview bewust een **andere**
`--family` kiest, toont de pagina diezelfde verplichte `--family` ook in de
latere renderopdracht. Zo kan de uiteindelijke WAV niet ongemerkt terugvallen
op de oudere opgeslagen standaardstijl; handmatig goedgekeurde per-paarstijlen
blijven onaangetast.

De originele offline **cue-editor toont nu Nederlandse bediening en
herkenbare lokale songbestandsnamen** naast de oorspronkelijke, voor alle
SHA-gebonden exports onveranderde track-ID's. Tijdens handmatig verschuiven
van cues laat de editor ook **direct de verwachte volledige DJ-settijdlijn**
zien: solo- en overgangshoofdstukken, de totale duur en verschil met de
vorige handmatige versie. Je kunt rechtstreeks op een voorgestelde
overgang klikken om die verder te corrigeren, zonder een nieuwe mix te
renderen. Alle tijden zijn een PCM-framegebaseerde inschatting; echte
muzikale kwaliteit of rechten worden daardoor niet gevalideerd. Een handmatige wijziging
laat expliciet zien dat je eerst de nieuwe privé-cuekeuzes moet downloaden.
Dit is geen automatisch herkende songtitel of rechtenbewijs.

De offline A/B-cue-editor heeft nu ook **1×, 4× en 16× lokale waveformzoom per deck**, met een rond de handmatig gekozen cue gecentreerde tijdbalk. Inzoomen zelf verandert geen cues of bronbestanden; klikken in de zoomweergave kiest een echte absolute WAV-tijd.

De offline A/B-cue-editor ondersteunt nu ook precieze **± 0,10 s**
handmatige cue-aanpassingen op beide decks, via knoppen of Shift +
pijltjestoetsen op de golfvorm. Die stappen omzeilen het optionele
beatgrid; normale beat-/vier-beatknoppen, Undo/Redo en de complete
SHA-gebonden WAV-tijdlijn blijven werken. Dit is handmatige afstelling,
geen automatische beat- of muziekkwaliteitsdetectie.

In de offline A/B-cue-editor kun je nu ook je eerder gedownloade
`mixlab-cue-selections.json` **terugladen**. De browser herstelt alle
handmatige cues tegelijk, inclusief de verwachte complete-settijdlijn,
als bronmanifest-SHA, echte PCM-cuegrenzen en elk geregistreerd paar exact
kloppen. Een import is één ongedaan-maakbare stap; ongeldige bestanden
veranderen geen bestaande invoer. De bron-WAVs en originele manifesten
blijven ongemoeid: de daadwerkelijke toepassing schrijft pas daarna een
apart, nieuw bronmanifest. Geen upload of automatische browseropslag.

Als handmatig verplaatste A/B-cuepunten twee overgangen laten overlappen,
blokkeert de privé-editor het opslaan en biedt **Ga naar probleemovergang**.
Via **Gebruik veilige startcue** kan de DJ vervolgens bewust de eerste
framegeldige Deck A-startcue toepassen en met Undo/Redo terugdraaien.
Bij een onoplosbare overlap blijft die knop uitgeschakeld; er wordt nooit
automatisch een muzikaal cuepunt of goedkeuring verzonnen.
Daarmee opent de juiste Deck A-waveform en zie je de vroegste geldige
uitgaande cuepositie op basis van echte bron-PCM-frames. Er verandert niets
automatisch aan muziek, cues of rechten; de DJ beluistert en kiest zelf.

De offline A/B-cue-editor heeft nu **Ongedaan maken, Opnieuw en Herstel dit paar** voor bewuste handmatige experimenten. Je kunt ook over meerdere overgangsparen terug en vooruit in je bewerkingen (maximaal 40 stappen): cuepunten, de verwachte volledige setlengte en de geldigheid van de nieuwe cuekeuzes bewegen mee. Herstel dit paar zet uitsluitend dat paar terug naar de originele broncues en is zelf ongedaan te maken. De geschiedenis wordt niet opgeslagen of geüpload: je kiest zelf wanneer je de definitieve cue-JSON downloadt en in een nieuw manifest toepast.

Vanuit een **opgeslagen** handmatige playlist kun je met
`--resume --plan-html --plan-cue-editor /private/music/new-editor.html`
nu ook de bestaande offline visuele cue-editor starten, zonder Studio-
of WAV-rendering. Daarmee pas je A/B-cues bewust aan via de lokale
waveforms en exporteer je de selectie naar een **nieuw** SHA-gebonden
manifest met `mixlab.cue_editor apply`; geef desgewenst meteen
`--plan-html --plan-verify-wavs` mee om in **dezelfde opdracht** een nieuwe
privéplanpagina inclusief SHA-geverifieerde mixtijd en hoofdstukken te maken,
zonder Studio of WAV te renderen. Het oorspronkelijke bronmanifest,
audio en goedgekeurde stijlen worden niet overschreven. Alleen voor originele
SHA-gecontroleerde PCM16-WAVs; dit is geen automatische beatdetectie.

De offline playlist-planpagina toont nu de **juiste volgende stap per productroute**: de wizard geeft `--resume --full-set-wav` in plaats van ongeldige previewinstructies, de directe partijmix vraagt alle previewvlaggen weg te halen. De wizard bewaart bovendien een expliciet gekozen standaard-`--family` in de private bronmanifest zodat later hervatten de oorspronkelijke handmatige stijl volgt. Expliciet goedgekeurde per-paarstijlen blijven beschermd.

De visuele playlistpagina toont nu de herkenbare lokale bestandsnaam zonder extensie boven de oorspronkelijke technische track-ID, zodat de volgorde daadwerkelijk leesbaar is. De pagina blijft privé; bronmappen en audiobestanden worden niet toegevoegd.

Gebruik `--preview --preview-html` op `mixlab.party_mix` voor een responsive, standalone en privé lokaal tracklijstoverzicht (zonder audiobestanden); voeg optioneel `--verify-wavs` toe voor de gecontroleerde verwachte mixtijd. De HTML wordt alleen op expliciet verzoek nieuw aangemaakt naast de geplande WAV; een normale `--preview` blijft volledig bestandsloos.

Voeg voor originele 44,1 kHz PCM16-WAVs `--preview --verify-wavs` toe om alleen lokaal de bronhashes/WAV-headers te controleren en vóór het renderen het exacte aantal frames, de mixtijd en verwachte bestandsgrootte te zien. Een complete mix moet nu alle gedeclareerde nummers precies één keer gebruiken; een vergeten track of herhaalde track wordt geweigerd. Bronrechten en luisterkwaliteit worden niet automatisch vastgesteld.

Voeg `--preview` toe aan dezelfde `mixlab.party_mix`-opdracht om vóór audiobewerking de handmatige trackvolgorde, stijlen en cuepunten te zien. Er wordt dan **geen** muziek geladen of bestand gepubliceerd. Bij echte rendering worden overlappende cues voortaan al vóór de zware import geweigerd.

Een snellere volledige route is `python3 -m mixlab.party_mix /private/music/project.json /private/new-studio /private/full-set.wav --family bass_swap`: alle geregistreerde paren behouden hun reeds handmatig geverifieerde afspeelvolgorde, BPM en cues. `--family` of `--transition` zijn alternatieven. Bij expliciete paren worden ontbrekende of omgegooide playlistovergangen nog vóór het renderen geweigerd.

Bij succesvolle export wordt naast de echte `full-set.wav` ook automatisch `full-set.wav.player.html` gemaakt. Open die privépagina lokaal voor volledige audiopreview, golfvorm, hoofdstukken en CUE-export. Als alleen de speler faalt, blijven WAV en brongebonden receipt geldig en geeft MixLab een `player_warning` terug.

De volgorde van de paren is expliciet en moet één doorlopende route vormen;
er wordt geen maat, BPM of muziekrecht automatisch geraden. Bekijk
[de complete set-handleiding](docs/continuous-set-export.md) en
[de één-commando route](docs/one-command-studio.md) voor grenzen,
herstel na fouten en de niet-bewezen muzikale kwaliteit.

## Engine tools

```bash
python3 -m mixlab.ingest /private/library/library.json
python3 -m mixlab.analysis /private/library/clip.wav --cache /private/features
python3 -m mixlab.evaluation /private/pack /private/ratings/listener-*.json
```

The analyzer proposes a constant beatgrid from regular percussive excerpts and abstains on insufficient evidence. It does not identify musical phrases, vocals or key automatically, and never silently overwrites manual rendering metadata. ManualProvider accepts verified downbeats/phrases/key; these stay labelled manual. See [analysis decisions](docs/adr/analysis-provider.md), [renderer decisions](docs/adr/renderer-quality.md), [manifest contract](docs/dataset-manifest.md) and [evaluation rules](docs/benchmark-report.md).

## Continue

> Werk verder aan MixLab. Kijk in Notion naar de huidige fase en wat er nog moet gebeuren, claim een vrije taak en werk die uit.

Detailed coordination belongs in [AGENTS.md](AGENTS.md) and the worker plan. GitHub holds code and task specifications; the zCloud VPS SQLite queue holds live claims and scheduling. Notion is the product/decision/handoff mirror. Do not infer a live queue entry from an issue or a plan file.

### Revisie van reeds afgeronde hybride DJ-masters

Nieuwe `python3 -m mixlab.marathon_revision_desk CURRENT_HYBRID_WAV ORIGINAL_WAV BLEND_WAV NEW_MIXLAB_HTML` opent een **besloten revisiestudio** voor de reeds werkelijk afgemaakte hybride WAV. De DJ kan per overgang de eerdere harde join/echte crossfade wijzigen, eerdere keuzes herstellen en het effect op de echte WAV-duur zien. Het nieuwe plan bindt aan de exacte SHA van de vorige master. `mixlab.marathon_reel_decisions ... --previous-hybrid CURRENT_HYBRID_WAV` verifieert oorspronkelijke én vorige complete WAVs/keuzelog opnieuw en rendert na typed `yes` een **aparte nieuwe versie**, zonder oudere masters of muziekbronnen aan te passen. [Hybrid Revision Desk](docs/marathon-human-hybrid-master.md#7-reopen-revise-and-re-render-a-completed-real-hybrid-set).

Na de revisie kan `python3 -m mixlab.marathon_revision_reels OLD_HYBRID_WAV NEW_REVISED_WAV NEW_PRIVATE_LISTEN_FOLDER` de **werkelijk gewijzigde overgangen in de twee echte WAVs** als losse korte PCM16-vergelijkingsfragmenten publiceren. Beide volledige SHA-/receipt-gebonden masters en de echte ouder-kind-herkomst worden gecontroleerd, de DJ moet opnieuw `yes` typen, en de originele WAVs blijven intact. Je kunt dit ook in één renderroute aanvragen met `marathon_reel_decisions --previous-hybrid OLD_WAV --revision-reels-output NEW_FOLDER`; de nieuwe lokale A/B-speler bevat alleen werkelijk gewijzigde joins, geen gegenereerde browserovergangen. [Handleiding](docs/marathon-human-hybrid-master.md#8-audition-only-the-real-wav-joins-changed-by-your-revision).

### Eén daadwerkelijke DJ-master selecteren uit versies

`python3 -m mixlab.marathon_revision_history prepare NEW_MIXLAB_HTML HYBRID_V1.wav HYBRID_V2.wav [...]`
maakt na verificatie van elke complete WAV, receipts en ononderbroken
SHA-ouderketen een **besloten offline geschiedenis** met echte duur,
gewijzigde overgangen en handmatig geselecteerde lokale WAV-voorluistering.
De DJ kiest één al gerenderde master en exporteert een brongebonden privé-
selectie. Met `marathon_revision_history publish CHOICE_JSON DEZELFDE_WAVS
--bundle [--delivery mp3|flac]` wordt uitsluitend die versie na een nieuwe
getypte `yes` via de officiële besloten USB-/MP3-/FLAC-route gepubliceerd.
Geen her-render, automatische beoordeling, muziek-upload of ongevraagde
privénotities in het audiopakket.

De bestaande hybride **Revision Desk** kan optioneel meteen echte korte
originele/crossfade-WAVs bij elke overgang laten horen: maak of herstel eerst
de officiële SHA-geverifieerde `Real Join Reels` en plaats het nieuwe
`mixlab-revision.html` in diezelfde besloten map met de extra optie
`--reels-folder PRIVATE_REAL_REELS_DIR`. De CLI controleert de volledige
masterbron-SHA's, de daadwerkelijke PCM16-fragmenten en exacte joinfades;
de browser gebruikt alleen deze lokaal bestaande WAVs, zonder eigen fades of
uploads. [Hybrid Revision Desk](docs/marathon-human-hybrid-master.md#10-audition-genuine-originalblend-wav-excerpts-while-revising).

The private offline cue editor also offers **Herstel alle cues** to reset all manual pair positions together after confirmation. The reset can be undone as one action; original sources stay unchanged.
