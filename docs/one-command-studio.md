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

Wil je de hele keten in één keer uitvoeren zonder eerst de Studio en daarna de losse set-export CLI te starten? Voor een playlist met 2–11 nummers is **één stijlkeuze genoeg**; de al door jou handmatig vastgelegde trackvolgorde en beide cuepunten per paar blijven ongewijzigd:

```bash
python3 -m mixlab.party_mix \
  /private/songs/input.json \
  /private/mixlab-sessie \
  /private/volledige-set.wav \
  --family bass_swap
```

Voor meer creatieve controle kun je in plaats van `--family` elk paar in de oorspronkelijke playlistvolgorde een eigen overgangsstijl geven:

```bash
python3 -m mixlab.party_mix \
  /private/songs/input.json \
  /private/mixlab-sessie \
  /private/volledige-set.wav \
  --transition pair-001:bass_swap \
  --transition pair-002:echo_exit
```

### Eerst bekijken, pas daarna renderen

Met dezelfde opdracht en `--preview` kun je de volledige handmatig gekozen
route controleren **zonder audiobronnen te importeren of bestanden aan te
maken**:

```bash
python3 -m mixlab.party_mix \
  /private/songs/input.json \
  /private/mixlab-sessie \
  /private/volledige-set.wav \
  --family bass_swap --preview
```

Wil je de route liever als **visueel overzicht** op je telefoon of computer
bekijken? Gebruik `--preview --preview-html` of combineer
`--preview --verify-wavs --preview-html` voor een SHA-gebonden tijdsindicatie:

```bash
python3 -m mixlab.party_mix \
  /private/songs/input.json \
  /private/mixlab-sessie \
  /private/volledige-set.wav \
  --family bass_swap --preview --verify-wavs --preview-html
```

Dit maakt expliciet **alleen** een nieuw privébestand
`/private/volledige-set.wav.preview.html` aan (0600). Open dat lokale
HTML-bestand in een browser om de volledige tracklijst, volgorde, overgangs-
stijlen, handmatig gekozen BPM en cuepunten te bekijken. Bij gecontroleerde
WAV-bronnen toont de pagina ook de berekende mixtijd. De pagina gebruikt
de **herkenbare lokale bestandsnamen zonder extensie** als songtitels en
toont de technische track-ID er kleiner onder. Dit zijn geen geverifieerde
muziekmetadata. De pagina bevat **geen muziek, volledige bronpaden, scripts,
externe links of netwerkaanvragen**. Bestandsnamen kunnen privé-informatie
onthullen; houd het lokale overzicht dus privé. Een bestaand overzicht
wordt niet overschreven. Verwijder daarna `--preview` én `--preview-html`
om de echte WAV-set te renderen; de pagina kan dat niet zelfstandig starten.

Zonder `--preview-html` blijft de bestaande voorvertoning 100% zonder
bestandsaanmaak. `--preview-html` is alleen toegestaan bij `--preview`.

MixLab geeft de exacte route (track-ID's), overgangsstijlen, handmatig
vastgelegde BPM, beginpunten, beattellingen en de totale **overgangsduur**
als leesbare JSON terug. Het standaardoverzicht is géén voorspelling van de lengte van de
complete set; dat zou zonder broncontrole misleidend zijn. Voor **originele
lokale 44,1 kHz PCM16-WAVs** is er optioneel een volledige tijdscontrole:

```bash
python3 -m mixlab.party_mix \
  /private/songs/input.json \
  /private/mixlab-sessie \
  /private/volledige-set.wav \
  --family bass_swap --preview --verify-wavs
```

Hiermee leest MixLab alléén de originele WAV-headers en de volledige bron-SHA256's,
en controleert of alle handmatige beginpunten inclusief het einde van elke
transitie **binnen de werkelijke lokale tracklengte** vallen. Het overzicht
meldt het exact verwachte aantal PCM-frames, WAV-grootte en de mixtijd op
basis van de bestaande 44,1 kHz stereo PCM16-renderer. De normale renderer
controleert tijdens de latere echte import/export opnieuw alle bestanden.
Er wordt geen muziek gedecodeerd, getranscodeerd, geüpload of als WAV
geëxporteerd tijdens de preview. Voor MP3/FLAC en andere bronnen gebruik je
de gewone `--preview`; voor die bronnen kan de exacte lengte **zonder
daadwerkelijke audio-import niet eerlijk worden voorspeld**. Het vlaggetje
`--verify-wavs` is uitsluitend geldig samen met `--preview`.
In de gewone preview worden bronhashes en audiokwaliteit niet gecontroleerd.
Met `--verify-wavs` worden de volledige bronhashes en WAV-headers juist
**wel** gecontroleerd, maar niet de volledige decodekwaliteit of onafhankelijke
muziekrechten. De uiteindelijke
render valideert die altijd opnieuw. Als een volgende uitgaande cue vóór
het einde van de vorige binnenkomende overgang ligt, weigert MixLab de
playlist nu zowel bij preview als bij een normale opdracht **vóór het
kostbare importeren/renderen**. Corrigeer je zelf opgegeven cues eerst in
het private manifest en gebruik daarna dezelfde opdracht zonder `--preview`.

Een complete playlist gebruikt bovendien **ieder in de broncatalogus
opgegeven nummer precies één keer**. Extra vergeten nummers en routes die
terugkeren naar een eerder nummer worden nu al vóór het renderen geweigerd;
alleen alle paar-ID's aflopen was daarvoor onvoldoende.

Een *complete* set moet nu **alle** in het bronmanifest geregistreerde paren bevatten, in hun exacte afspeelvolgorde. Een ontbrekende of omgewisselde overgang wordt **vóór** CPU-zwaar importeren/renderen geweigerd, zonder een nieuwe studiosessie of half eindbestand achter te laten. `--family` en `--transition` zijn onderling exclusief: geef nooit beide tegelijk. Automatische pairselectie betekent hier uitsluitend het toepassen van een gekozen **stijl** op de reeds door jou goedgekeurde overgangen, niet automatische BPM-, muziek- of rechtenanalyse.

De bronbibliotheek en beide doelpaden moeten vooraf veilig gekozen zijn.
De sessiemap en WAV **mogen niet bestaan**; bestaande resultaten worden
niet overschreven. De opdracht valideert eerst de handmatige keuzes en
paden, bouwt vervolgens de bestaande import/Studio, en gebruikt de
gecontroleerde [continuous set-export](continuous-set-export.md).

Bij succes ontstaan **direct drie bruikbare bestanden** naast elkaar: de complete afspeelbare WAV, de private checksum-gebonden WAV-receipt, en automatisch een nieuwe offline `volledige-set.wav.player.html`. Open deze HTML rechtstreeks in een lokale browser om de **hele mix** te beluisteren, de gesamplede golfvorm te zien en via de track- en overgangshoofdstukken naar een specifiek fragment te springen. De speler kan ook hoofdstukken als JSON of CUE exporteren. Alle hoofdstukposities en de WAV-identiteit worden afgeleid uit de **echte** Studio→WAV-export en de geverifieerde private receipt; er worden geen BPM, rechten of muziektitels bij verzonnen. De speler toont nu **de lokale bestandsnaam zonder extensie** bij de solohoofdstukken en **nummer A → nummer B** bij overgangen, ook in eventmodus en privé-CUE/JSON. Het zijn geen geverifieerde muziektitels; houd deze bestanden privé. Alles werkt zonder server, analytics of uploads.

Als alleen het maken van de optionele speler mislukt, bevat de opdracht een `player_warning` maar blijven de correcte WAV en private receipt **behouden**. De speler kan later met `python3 -m mixlab.set_player PRIVATE_STUDIO COMPLETE.wav` afzonderlijk worden gegenereerd, zolang dat HTML-bestand nog niet bestaat.

Bij succes ontstaat de gehele afspeelbare WAV plus een private, checksum-
gebonden receipt. Als de Studio succesvol is gemaakt maar de laatste
playlistcompositie faalt (bijv. een A→B→C-route die terugloopt), blijft
die **nieuwe eigen private Studio-map** bestaan, zodat je de fout kunt
corrigeren en alleen de set-export opnieuw kunt uitvoeren. Originele
muziek en bestaande exports blijven onaangetast.

Dit is geen automatische DJ-routeplanning: de volgorde, de BPM, de cues en de rechten blijven expliciet door de gebruiker gekozen en gecontroleerd. Voor correcte reeds aanwezige 44,1 kHz PCM16-WAV is geen FFmpeg nodig; voor MP3/FLAC/M4A of niet-canonieke WAVs is reeds geïnstalleerde FFmpeg vereist. Muzikale kwaliteitsvoorkeur met echte tracks en echte luisteraars blijft onbewezen.
