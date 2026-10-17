# MixLab Stem Studio — vocal/instrumental transitions

MixLab kan nu **echte combinaties van aangeleverde losse stemmen** renderen.
Dit is nieuw DSP-productgedrag naast de bestaande bass-swap/echo/crossfade
transition families. Het draait volledig offline met de Python-standard
library en vraagt geen GPU, eigen modeltraining of externe API.

**Belangrijk:** dit onderdeel *scheidt geen vocals van bestaande nummers*.
Een producer, DAW of eerder toegestane offline stem-tool moet de vier WAVs
al aanleveren. Het zijn daadwerkelijk aparte vocal- en instrumentalbronnen,
geen door MixLab uit een gemasterde track geraden stems.

## Input

Bewaar precies vier korte, gelijk uitgelijnde PCM16-stems in een eigen
privémap, elk mono of stereo, 8–96 kHz en maximaal 2 miljoen frames / 32 MiB.
Dezelfde sample rate en hetzelfde kanaalformaat zijn verplicht.

Maak in dezelfde privémap een JSON-spec met bron-SHA256, bijvoorbeeld:

```json
{
  "schema_version": 1,
  "pair_id": "pair-001",
  "rights": "user-permitted",
  "provenance": "Private licensed stem exports with permission for derivative mixes",
  "bpm": 120,
  "beats": 16,
  "a_start_seconds": 0,
  "b_start_seconds": 0,
  "stems": {
    "a_instrumental": {
      "path": "song-a-instrumental.wav",
      "sha256": "REPLACE_WITH_64_CHARACTER_LOWERCASE_SHA256"
    },
    "a_vocals": {
      "path": "song-a-vocals.wav",
      "sha256": "REPLACE_WITH_64_CHARACTER_LOWERCASE_SHA256"
    },
    "b_instrumental": {
      "path": "song-b-instrumental.wav",
      "sha256": "REPLACE_WITH_64_CHARACTER_LOWERCASE_SHA256"
    },
    "b_vocals": {
      "path": "song-b-vocals.wav",
      "sha256": "REPLACE_WITH_64_CHARACTER_LOWERCASE_SHA256"
    }
  }
}
```

De vier bestanden zijn onafhankelijk, moeten rechtmatig bruikbaar zijn en
mogen geen symlinks zijn. Het opgegeven startmoment is een handmatig
goedgekeurde beatcue in de eigen stem-export, geen automatische analyse.

## Renderen en beluisteren

```bash
python3 -m mixlab.stem_render /private/stems/pair.json /private/stem-studio-01
```

Open lokaal `/private/stem-studio-01/index.html` en beluister/drain
de drie nieuwe echte WAV-renderfamilies:

- **Vocal handoff** — de eerste track behoudt zijn vocal langer terwijl
  de instrumentale begeleiding gelijkmatig naar track B beweegt;
  de tweede vocal wordt later ingevoerd.
- **Instrumental bridge** — beide vocals nemen ruimte tijdens het midden
  terwijl de instrumentals worden gemengd, met de inkomende vocals pas
  tegen het einde.
- **Drop swap** — een snel maar glad 4%-venster rond het midden wisselt
  instrumentals om, met onafhankelijk ingestelde vocal-uitloop en
  vocal-inloop om plotselinge sampleklikken te beperken.

Iedere kandidaat heeft gelijke handmatig opgegeven beatlengte en
exacte duur. De DSP leest en verwerkt maximaal 4096 frames per blok;
er zijn geen hele WAV's in RAM nodig. Kanaalgelijkheid en clipgrenzen
worden afgedwongen. Output wordt pas na volledig renderen als WAV
gepubliceerd via een exclusieve hardlink, zodat een bestaande kandidaat
nooit wordt overschreven. De default is -12 dB gemeenschappelijke
headroom; bij een clip wordt de kandidaat geweigerd en kun je opnieuw
renderen met `--gain-db -15` (ondergrens -30 dB).

Voor iedere stijl legt
`studio-receipt.private.json` de uitvoer-SHA256, kanaalformaat,
frames, RMS/peak en clipping vast, plus de hash van het private
bronmanifest. De lokale luisterpagina laadt geen externe scripts of
fonts en bevat geen absolute bronpaden.

## Productgrenzen

- Het is een afzonderlijk, lokaal opt-in renderpad; de al bestaande
  renderer, benchmark, analyseproviders en gedeelde CLI blijven
  onveranderd. Eerdere DSP-families blijven ondersteund.
- **Geen stem separation, pitch preserving timestretch of automatische
  downbeat/key/phrase-inferentie**. Bronstems moeten vooraf rechtmatig
  verkregen en handmatig aligned zijn. Verschillende BPM/rate/kanalen
  worden niet heimelijk hersteld.
- Er is geen limiter, auto-mastering, streamingdienst, distributie van
  beschermde muziek, modeldownload of externe service.
- De Studio is een **onblinde creatieve luisteromgeving**; een prettig
  resultaat of goede technische WAV is geen bewijs dat luisteraars deze
  route prefereren boven een simpele crossfade. Het originele M1
  blind-review- en mensen/real-music-bewijs blijft open.

Bewaar de volledige project- en studiomappen buiten GitHub. De
private outputmap wordt aangemaakt met rechten 0700 en audiobestanden
met 0600. Bij fout verwijdert de tool alleen zijn eigen, nieuw
aangemaakte outputmap en nooit de originele stems.
