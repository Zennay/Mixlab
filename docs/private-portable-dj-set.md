# MixLab Portable DJ Set — MP3, CUE en M3U8

Een volledige DJ-set is standaard een **verliesloze PCM16-WAV** met een
eigen SHA-gebonden `receipt.private.json` en een offline HTML-speler.
Voor een telefoon, USB-stick of andere lokale muziekspeler kun je daarnaast
een losse portable export maken. De originele WAV en onderzoeksmetadata
worden **nooit** gewijzigd of overschreven.

## Eén lokaal uitvoercommando

Eerst [een echte volledige set](offline-set-composer.md) renderen:

~~~bash
python3 -m mixlab.set_composer render \
  /private/session-01 \
  /private/mixlab-set-plan.private.json \
  /private/final-set.wav
~~~

Daarna naar een portable pakket met al aanwezige **FFmpeg en FFprobe**.
Er wordt geen software gedownload of vanaf een externe server gewerkt:

~~~bash
python3 -m mixlab.set_delivery \
  /private/session-01 \
  /private/final-set.wav \
  /private/final-set-portable.mp3
~~~

MixLab maakt uitsluitend **nieuwe** bestanden:

- `final-set-portable.mp3`: lokaal geëncodeerde MP3 van **192 kbit/s**,
  met vaste CPU-threadlimiet en zonder nieuwe effecten of beatmatching;
- `final-set-portable.cue`: optionele cue-sheet voor muziekspelers die
  de bijbehorende MP3 kunnen lezen, gebaseerd op de oorspronkelijke
  werkelijk gerenderde hoofdstukgrenzen;
- `final-set-portable.m3u8`: een simpele lokale playlist die de MP3
  via bestandsnaam verwijst, zonder server of absolute bronpaden;
- `final-set-portable.mp3.receipt.private.json`: uitgaande MP3-SHA,
  oorspronkelijke WAV-SHA en hoofdstukken zonder commerciële metadata,
  bronpaden of licentieclaims.

**Belangrijk:** MP3 is verliesgevend gecomprimeerd. Encoder-padding kan
de start van een hoofdstuk enigszins verschuiven; de CUE-tijden zijn
navigatieschattingen. De originele PCM16-WAV is de enige exacte
sample-/framegebonden referentie. De lossy MP3 is **geen** nieuw
blindluisterbewijs of bewijs voor betere DJ-overgangen.

## Veiligheid, prestaties en gebruik

De tool weigert oude/gewijzigde WAV's door vóór encoderen eerst de
officiële `mixlab.set_player.build_chapters` en daarmee **alle bestaande**
source/Studio WAV-hashes, route- en toestemming-/provenancegates te
controleren. Na het converteren moet de exacte originele WAV-SHA
ongewijzigd zijn, inclusief bestandenidentiteit. De encoder schrijft
zijn uitvoer via een begrensde streaming-pijp, niet via een volledig MP3
in het geheugen. Outputbudget: maximaal **128 MiB**; standaard deadline
**600 seconden** (maximaal 900). Bij een fout worden alleen de **nieuw
aangemaakte** portable bestanden verwijderd, niet de bronmix.

Dit pakket is bedoeld voor **privégebruik en daadwerkelijk toegestane
muziek**. De gebruiker is verantwoordelijk voor rechten en
gebruikslimieten; een MP3-export creëert geen licentie. MixLab slaat
niets in de cloud op of in Git. Zet de MP3, CUE en M3U8 samen in één
privémap als je ze naar een externe offline speler overzet. Controleer
of die speler het formaat ondersteunt voordat je de mix tijdens een
evenement gebruikt.
