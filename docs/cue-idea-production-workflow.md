# MixLab: van cue-idee tot volledig gerenderde privé DJ Studio

De **Idea Pipeline** vormt de ontbrekende brug tussen de bestaande
[Transition Idea Board](transition-idea-board.md) en de echte
[Set Composer](offline-set-composer.md). Je hoeft geen los
`cue_suggest`-, `idea_board`-, `session`- en
`set_composer`-commando meer in de juiste volgorde te onthouden.

De workflow verandert nooit de originele brontracks, bestaande
luistersessie, renderreceipts of eventuele bevroren studie. Hij verwerkt
uitsluitend lokale tracks met expliciet toegestane rechten, een
**development**-partitie en handmatig vastgestelde BPM/downbeats.

## 1. Maak een reviewbord vanuit een bestaande Studio

Begin met een reeds gemaakte privésessie, bijvoorbeeld uit
[Playlist Studio](guided-playlist-studio.md). Alle nummers moeten een
door jou bevestigde `first_downbeat_seconds` hebben en alle
overgangsparen moeten evenveel beats duren.

~~~bash
python3 -m mixlab.idea_pipeline start \
  /private/mixlab-playlist-01 \
  --phrase-bars 8
~~~

De pipeline controleert de bestaande sessie- en Studioreceipts en maakt:

- `/private/mixlab-playlist-01/idea-suggestions.private.json` —
  hashgebonden, begrensde RMS-cuevoorstellen;
- `/private/mixlab-playlist-01/sources/idea-board.html` —
  een browserpagina waarin je per paar de handmatige cues en maximaal
  vier energievoorstellen vergelijkt en beluistert.

Open `idea-board.html` lokaal, kies elk cuepunt handmatig en download
`mixlab-approved-cues.private.json` buiten de bronsessie.

Dit zijn alleen op **handmatig** gespecificeerde beat/downbeat-grid
gebaseerde RMS-ideeën, geen automatisch gedetecteerde muzikale phrases
en geen bewezen kwalitatief betere mixes.

## 2. Maak direct een nieuwe Studio met jouw goedgekeurde cues

~~~bash
python3 -m mixlab.idea_pipeline finish \
  /private/mixlab-playlist-01 \
  /private/downloads/mixlab-approved-cues.private.json \
  /private/mixlab-approved-studio-02
~~~

In één opdracht voert MixLab nu achtereenvolgens uit:

1. Vergelijk de bron-, voorstellen- en goedkeurings-SHA-256's en
   controleer alle voorgestelde A/B-cues.
2. Schrijf `sources/idea-approved.private.json` als **nieuw**,
   onveranderlijk bronmanifest. De oorspronkelijke sources blijven staan.
3. Importeer de echte lokaal toegestane WAV-bestanden opnieuw en render
   alle bestaande overgangsfamilies met de officiële DSP-engine naar de
   nieuwe privésessie.
4. Publiceer de optionele visuele cue-editor en de offline Set Composer.
   Een optionele browserpublicatiefout verwijdert niet de geslaagde Studio.

Open vervolgens de gerapporteerde
`/private/mixlab-approved-studio-02/set-composer/index.html`
om overgangen te kiezen, en render de complete WAV met
`python3 -m mixlab.set_composer render` zoals in de
[Set Composer-handleiding](offline-set-composer.md).

## Veilige herstelroute en meerdere concepten

Als FFmpeg of de echte renderer faalt, blijft het
`idea-approved.private.json`-manifest bestaan. Render dan opnieuw
**met een nieuwe sessiemap** via de bestaande
`python3 -m mixlab.session APPROVED_MANIFEST NEW_DIR`-workflow;
geen originele audio of al goedgekeurde keuzes hoeven te worden
overschreven. De volledige Studio en Set Composer kun je in dat geval
apart maken met `python3 -m mixlab.set_composer create NEW_DIR`.

Wil je meer dan één ontwerp uit dezelfde privésessie halen? Geef
`--prefix idea2` mee aan **zowel** `start` als `finish`. Daarmee
blijven verschillende energievoorstellen en goedkeuringen onafhankelijk
en onveranderlijk.

**Onderzoeksstatus:** M1 blijft OPEN voor toestemming-gecontroleerde
échte muziek, automatische downbeat/key/phrase-analyses en onafhankelijke
blind-luistervoorkeursmetingen. Deze creatieve workflow levert geen
beoordeling of bewijs van muzikale superioriteit.
