# MixLab in één opdracht — lokale muziekbibliotheek naar Transition Studio

Deze opdracht verbindt vier al beschikbare M1-productmodules tot een direct
bruikbare **offline mix-sessie**. Je hebt alleen een privé JSON-manifest met
toegestane muziek, handmatig gecontroleerde BPM en cuepunten nodig.

```bash
python3 -m mixlab.session /private/songs/input.json /private/mixlab-sessie
```

Dit doet MixLab achter elkaar:
1. Verifieert je opgegeven bestanden, SHA256, rechtenverklaringen,
   herkomst, BPM en handmatige beginpunten. Alle bewerkingen zijn lokaal.
2. Importeert MP3/FLAC/M4A/andere ondersteunde audio met een reeds
   geïnstalleerde **FFmpeg**, naar privé 44,1 kHz stereo PCM16-WAV.
3. Snijdt de ingest-compatibele fragmenten uit met exact de opgegeven
   A/B-starttijden en beatlengte; bestaande 2M-frame/32MiB limieten blijven.
4. Rendert echte, lokaal afspeelbare baselines, bass swap, echo exit en
   hard cut in de bestaande DSP-engine.
5. Maakt `studio/index.html` zodat je alle kandidaat-overgangen in je
   browser kunt beluisteren en als WAV kunt opslaan. Een private sessie-receipt
   bindt het originele manifest, de fragmentlijst en Studio-output aan hashes.

Een paar filteren voor het zware afluisterwerk:

```bash
python3 -m mixlab.session /private/songs/input.json /private/mixlab-paar-001 --pair pair-001
```

Dit bereidt nog steeds alle gedeclareerde fragmenten voor, maar rendert
in Studio alleen dit paar.

Extra energie-gebaseerde instap/uitstapvoorstellen laten berekenen:

```bash
python3 -m mixlab.session /private/songs/input.json /private/mixlab-met-suggesties --suggestions
```

Hiervoor moet iedere brontrack handmatig geverifieerde
`first_downbeat_seconds` hebben. Suggesties verschijnen als
`cue-suggestions.private.json`. Ze worden **niet** automatisch in de
overgangen verwerkt: dit zou zonder menselijke controle ten onrechte als
automatische maat- of fraseherkenning worden gepresenteerd. Kopieer
goedgekeurde tijden naar je oorspronkelijke pair-definitie en start een
**nieuwe** sessie.

## Minimale invoer

De structuur is gelijk aan de [private media-importer](private-media-import.md).
Bijvoorbeeld twee lokale nummers met:

```json
{
  "schema_version": 1,
  "purpose": "development-pilot",
  "tracks": [
    {
      "id": "song-01",
      "path": "music/one.mp3",
      "sha256": "PASTE_ACTUAL_LOWERCASE_SHA256",
      "bpm": 120,
      "rights": "user-permitted",
      "provenance": "Private music I am permitted to process"
    },
    {
      "id": "song-02",
      "path": "music/two.flac",
      "sha256": "PASTE_ACTUAL_LOWERCASE_SHA256",
      "bpm": 120,
      "rights": "user-permitted",
      "provenance": "Private music I am permitted to process"
    }
  ],
  "pairs": [
    {
      "id": "pair-001",
      "a": "song-01",
      "b": "song-02",
      "beats": 16,
      "a_start_seconds": 48.0,
      "b_start_seconds": 64.0
    }
  ]
}
```

**Voor de een-commando-route moeten beide starttijden aanwezig zijn.**
MixLab kiest niet stiekem een ongeschikte passage op tijdstip 0. De
achterliggende import-module staat wel ontbrekende cuepunten toe zodat je
eerst handmatig kunt selecteren.

## Output en veiligheid

Maak de doelmap **niet** vooraf aan. De bovenliggende map moet al bestaan.
Houd muziekbibliotheek en resultaten buiten een Git-checkout. Output:

```text
/private/mixlab-sessie/
    sources/
        audio/*.wav
        source_manifest.json
        import-receipt.private.json
    excerpts/
        *.wav
        library.json
        cue-provenance.private.json
    studio/
        auditions/<pair>/*.wav
        index.html
        studio-receipt.private.json
    session-receipt.private.json
    cue-suggestions.private.json     # alleen met --suggestions
```

De sessiemap is alleen toegankelijk voor de eigenaar (0700); gevoelige
metadata en bronconversies blijven lokaal. Muziek of metadata wordt nooit
naar een dienst gestuurd. Bij mislukking wordt uitsluitend de voor deze
opdracht nieuw aangemaakte projectmap opgeruimd; bronmuziek blijft intact.
De bestaande module-specifieke beperkingen voor bronkwaliteit, tijdelijke
CPU-belasting, opgegeven rechten, fragmentlengte en audio-output gelden nog.

**M1-status:** dit is een bruikbare creatieve route voor echte lokale muziek,
maar geen automatisch beatmatching-systeem, commerciële muziekdienst,
source-separation-engine of bewijs dat een overgang beter klinkt dan een
crossfade. Blind luisteren en rechtenbewijzen blijven afzonderlijke gates.

## Nieuwe route: één opdracht tot een complete WAV-set

Wil je de hele keten automatisch *uitvoeren*, zonder zelf eerst de Studio
en daarna de losse set-export CLI te starten? Gebruik de nieuwe lokale
`mixlab.party_mix` opdracht met **expliciet handmatig geselecteerde** paren
en stijlen:

```bash
python3 -m mixlab.party_mix \
  /private/songs/input.json \
  /private/mixlab-sessie \
  /private/volledige-set.wav \
  --transition pair-001:bass_swap \
  --transition pair-002:echo_exit
```

De bronbibliotheek en beide doelpaden moeten vooraf veilig gekozen zijn.
De sessiemap en WAV **mogen niet bestaan**; bestaande resultaten worden
niet overschreven. De opdracht valideert eerst de handmatige keuzes en
paden, bouwt vervolgens de bestaande import/Studio, en gebruikt de
gecontroleerde [continuous set-export](continuous-set-export.md).

Bij succes ontstaat de gehele afspeelbare WAV plus een private, checksum-
gebonden receipt. Als de Studio succesvol is gemaakt maar de laatste
playlistcompositie faalt (bijv. een A→B→C-route die terugloopt), blijft
die **nieuwe eigen private Studio-map** bestaan, zodat je de fout kunt
corrigeren en alleen de set-export opnieuw kunt uitvoeren. Originele
muziek en bestaande exports blijven onaangetast.

Dit is geen automatische DJ-routeplanning: de gebruiker kiest de
specifieke paren en overgangsstijlen vooraf. Vereist een reeds
geïnstalleerde lokale FFmpeg, en mist nog menselijk luisterbewijs op
echte tracks.
