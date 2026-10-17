# MixLab Transition Idea Board — DJ kiest, audio stelt mogelijkheden voor

De **Transition Idea Board** werkt uitsluitend op eigen toegestane
lokale nummers in de **development**-partitie. MixLab bepaalt niet welke
muzikale overgang de beste is. Het laat hoogstens vier alternatieven per
bestaand overgangspaar zien, op basis van de bestaande energie-suggesties
(`mixlab.cue_suggest`). Elk alternatief is gebonden aan de handmatig
bevestigde BPM en het eerste downbeatpunt. Je kunt ook steeds de
oorspronkelijke handmatige cue behouden.

De hele workflow is offline en blijft bij bestaande rechten-, audio- en
bronhashcontroles. De nieuwe pagina bevat geen bronbestanden, geen
absolute audiopaden en geen netwerkfunctionaliteit.

## Stap 1 — Bestaande privé Studio en lokale energie-ideeën

Bereid een Studio voor met **handmatig** bevestigde `bpm`,
`first_downbeat_seconds`, rechtenverklaring en `a_start_seconds` /
`b_start_seconds` per overgang. Gebruik bijvoorbeeld
[Playlist Studio](guided-playlist-studio.md) om deze gegevens in te voeren.

Op een reeds genormaliseerde private Studio:

~~~bash
python3 -m mixlab.cue_suggest \
  /private/mixlab-playlist-01/sources/source_manifest.json \
  /private/mixlab-playlist-01/cue-ideas.private.json \
  --beats 16 --phrase-bars 8 --max-cues 5
~~~

De BPM, het eerste downbeatpunt en het gebruikte grid komen van jou.
Een energie-idee is niet hetzelfde als een gedetecteerde phrase of
sterke DJ-overgang; het signaal betreft slechts sampled-RMS-energie.

## Stap 2 — Bekijken in de offline browser

~~~bash
python3 -m mixlab.idea_board create \
  /private/mixlab-playlist-01/sources/source_manifest.json \
  /private/mixlab-playlist-01/cue-ideas.private.json \
  /private/mixlab-playlist-01/sources/idea-board.html
~~~

Open `idea-board.html` lokaal. Vergelijk de alternatieven per overgang.
De oorspronkelijke handmatige cue is standaard geselecteerd. Beslis
zelf en download `mixlab-approved-cues.private.json` naar een map
**buiten** de originele sessie.

## Stap 3 — Keuzes toepassen op een nieuw bronmanifest

~~~bash
python3 -m mixlab.idea_board apply \
  /private/mixlab-playlist-01/sources/source_manifest.json \
  /private/mixlab-playlist-01/cue-ideas.private.json \
  /private/downloads/mixlab-approved-cues.private.json \
  /private/mixlab-playlist-01/sources/approved-development.json
~~~

Dit creëert een nieuw ontwikkelingsmanifest met **alleen** de door jou
goedgekeurde cuewijzigingen. Het originele bronmanifest en originele
WAV-bestanden worden nooit overschreven. Het bronmanifest en de
suggestiefile worden op SHA-256 gebonden: als een bron of de suggesties
tussentijds veranderen, faalt het toepassen. Een cuecombinatie die een
eerder afgespeeld deel van de track terugspoelt wordt ook geweigerd.

Je kunt daarna met de bestaande `mixlab.session` het nieuwe manifest
renderen in **een nieuwe privémixsessie**. Het board is een
creatieve beslisinterface, **geen blind luisterexperiment** en geeft geen
wetenschappelijk bewijs voor betere audio- of publieksvoorkeur.
Het systeem wijzigt geen evaluatie- of frozen-holdoutdata.
