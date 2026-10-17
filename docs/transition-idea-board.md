# MixLab Transition Idea Board — handmatig cue-ideeën kiezen

De Idea Board maakt meerdere **voorstellen voor echte overgangen** uit
reeds bestaande, lokaal berekende RMS-energie en jouw expliciet
vastgelegde downbeat/BPM-grid. Je kunt voor elk geregistreerd nummerpaar
een alternatieve uitgaande en inkomende cue kiezen, zonder de originele
tracks of oude cuepunten te overschrijven.

Dit is een productief hulpmiddel voor de **M1 creatieve workflow**, niet
automatische muzikale phrase-detectie, genre-intelligentie, pair discovery,
loudness-matching of een wetenschappelijk luisterresultaat.

## Begin vanuit een private development-sessie

Je hebt een succesvolle `mixlab.session` of
`mixlab.playlist_studio` nodig, met voor **iedere track** eerder door jou
gecontroleerde `first_downbeat_seconds` en `bpm` in het bronmanifest.
Gebruik uitsluitend ontwikkeltracks; bestaande bevroren evaluatiesets
kunnen niet via deze functie worden gewijzigd.

Maak op de reeds genormaliseerde lokale PCM16-WAVs de officiële
niet-mutatieve suggesties (hier is het een *nieuw* outputbestand):

~~~bash
python3 -m mixlab.cue_suggest \
  /private/session-01/sources/source_manifest.json \
  /private/session-01/cue-suggestions.private.json \
  --beats 16 --phrase-bars 8 --max-cues 5
~~~

Maak vervolgens het offline keuzescherm:

~~~bash
python3 -m mixlab.idea_board create \
  /private/session-01/sources/source_manifest.json \
  /private/session-01/cue-suggestions.private.json \
  /private/session-01/sources/transition-ideas.html
~~~

Open `transition-ideas.html` op je eigen computer.

De pagina bevat per bestaand nummerpaar de **originele handmatige
cuekeuze** en tot vier nieuwe ideeën uit de werkelijke RMS-energie.
Alternatieven worden gerangschikt op het absolute dBFS-verschil tussen
het laatste stukje van de outgoing- en het eerste stukje van de
incoming-audio. Een klein verschil is slechts een volumeheuristiek;
het betekent niet dat twee nummers muzikaal passen.

Selecteer één mogelijkheid per paar en download
`mixlab-approved-cues.private.json`. De browser maakt geen
netwerkverzoeken en importeert geen nieuwe muziek.

## Eerst bevestigen, daarna een nieuwe mix maken

De selectie is gebonden aan de exacte SHA-256 van zowel het oorspronkelijke
PCM16-bronmanifest als het suggestiebestand. Een oude, handmatig gewijzigde,
dubbele of verkeerde selectie wordt geweigerd. Voer uit:

~~~bash
python3 -m mixlab.idea_board apply \
  /private/session-01/sources/source_manifest.json \
  /private/session-01/cue-suggestions.private.json \
  /private/mixlab-approved-cues.private.json \
  /private/session-01/sources/approved-development.json
~~~

Hiermee ontstaat een **nieuw development-manifest** naast de al
genormaliseerde audio; alleen de exact goedgekeurde
`a_start_seconds` en `b_start_seconds` veranderen. MixLab laat nooit
stilzwijgend overlappende teruglopende cuepunten door en bewaart alle
bestaande bronrechten, originele SHA's en track-partitionering.

Om de ideeën écht te horen maak je een **nieuwe** Studio. Hier worden
wederom de originele WAV-hashes, framegrenzen en handmatige BPM gecontroleerd:

~~~bash
python3 -m mixlab.session \
  /private/session-01/sources/approved-development.json \
  /private/session-ideas-02

python3 -m mixlab.set_composer create /private/session-ideas-02
~~~

Beluister de echte audiorenders in de Studio en kies daarna je definitieve
families in de Composer. Indien gewenst kun je met `mixlab.set_composer
render` één volledige, nieuwe, private WAV en offline hoofdstukspeler
maken.

### Grenzen

De voorstellen gebruiken maximaal de eerste acht door de bestaande
`cue_suggest` geproduceerde entry- en exitvensters per track. Het
systeem labelt ze **nooit** als gemeten phrases/keys/genre-match. De
bronbestanden, originele sessie, vaste benchmarksets en oude manifests
worden niet aangepast. Beoordeling van muzikale kwaliteit met echte
rechtenveilige muziek en onafhankelijke luisteraars blijft een apart
M1-acceptatiecriterium.
