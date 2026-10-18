# MixLab Instant Set — één opdracht tot complete DJ-mix

De **Instant Set-export** is de snelle, lokale route van een bestaande
[gerenderde MixLab Studio](guided-playlist-studio.md) naar één echt
PCM16-WAV-bestand. Anders dan het interactieve
[Set Composer-keuzeplan](offline-set-composer.md) hoef je niet eerst
per overgang een JSON-plan te downloaden: geef een **door jou gekozen**
familie op, en laat de reeds gerenderde audio direct aan elkaar bouwen.

~~~bash
python3 -m mixlab.instant_set \
  /private/mixlab-playlist-01 \
  /private/mixlab-complete-set.wav \
  --family bass_swap
~~~

De officiële, eerder gemergede set-exporter verwerkt **alle
geregistreerde paren in hun oorspronkelijke afspeelvolgorde**. De app
eist een aaneengesloten playlist met 1–10 overgangen (2–11 nummers),
controlleert dat iedere gewenste transitiestijl al écht is gerenderd,
controleert alle Studio-, bron- en audio-SHA's, en publiceert één
volledige WAV inclusief privé-exportreceipt. Als beschikbare bijlage
wordt `mixlab-complete-set.wav.player.html` gemaakt, met klikbare
hoofdstukken voor nummerwisselingen, golfvorm en cue-sheet-export.

Je kunt één of meerdere overgangen afzonderlijk van stijl voorzien.
Bijvoorbeeld de eerste overgang bass swap en de tweede echo exit:

~~~bash
python3 -m mixlab.instant_set \
  /private/mixlab-playlist-01 \
  /private/mixlab-complete-set.wav \
  --family bass_swap \
  --style pair-002:echo_exit
~~~

De officiële families zijn `baseline`, `bass_swap`, `echo_exit`
en `hard_cut`. Dit is een **expliciete creatieve gebruikerskeuze**,
niet een AI-voorkeursoordeel.

## Eén productflow vanaf goedgekeurde cue-ideeën

De [Cue Idea Pipeline](cue-idea-production-workflow.md) kan meteen na
handmatige goedkeuring de gerenderde set en de offline speler publiceren.
Er zijn dan helemaal geen losse CLI-stappen meer nodig tussen
goedgekeurde cuekeuze en uiteindelijke WAV:

~~~bash
python3 -m mixlab.idea_pipeline finish \
  /private/mixlab-playlist-01 \
  /private/downloads/mixlab-approved-cues.private.json \
  /private/mixlab-approved-studio-02 \
  --full-set-wav /private/mixlab-approved-complete.wav \
  --family echo_exit
~~~

Als de audio-export faalt, blijft de nieuwe Studio beschikbaar. Als alleen
de optionele browserpagina faalt, blijft de **echte voltooide WAV**
beschikbaar. Je kunt een mislukte optionele export expliciet met een
**nieuwe** WAV-naam opnieuw proberen. Geen bestaande bestanden of
freeze-/evaluatiegegevens worden aangepast.

De Instant Set werkt alleen op een voltooide privésessie met reeds
gerenderde transities en expliciete gebruiksrechten. Hij ontdekt geen
nummers, analyseert geen onbekende BPM of songstructuur en vervangt
geen onafhankelijk muziekkwaliteitsonderzoek; M1 Transition Lab blijft
open.
