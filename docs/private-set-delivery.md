# MixLab Private Delivery — exporteer MP3 of FLAC van een echte set

MixLab rendert eerst een **volledige PCM16-WAV** via de officiële
Studio en [Instant Set](instant-private-full-set.md). Je kunt daarna
optioneel voor afspelen, archiveren of delen een compactere, lokaal
gecodeerde MP3 of verliesvrije FLAC publiceren zonder de oorspronkelijke
WAV, Studio, masterbronbestanden, SHA's of onderzoeksdata te wijzigen.

**Vereist:** al lokaal geïnstalleerde **FFmpeg én FFprobe** (geen
automatische download of installatie). Je blijft zelf verantwoordelijk
voor muziekrechten; rechten om privé te mixen zijn niet automatisch
rechten om een opname publiek te verspreiden.

## Eén opdracht van muziekbibliotheek tot MP3/FLAC

Je hoeft niet eerst afzonderlijk een complete set of een exportbestand
te publiceren. De bestaande `playlist_studio` en `instant_set`
leveren optioneel een MP3 of FLAC naast hun verplichte originele WAV:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/my-playlist.private.json \
  /private/mixlab-playlist-01 \
  --beats 16 \
  --full-set-wav /private/mixlab-party.wav \
  --family bass_swap \
  --delivery /private/mixlab-party.mp3 \
  --bitrate-kbps 192
~~~

Vanuit een bestaande Studio kan het ook zo:

~~~bash
python3 -m mixlab.instant_set \
  /private/mixlab-playlist-01 \
  /private/mixlab-party.wav \
  --family echo_exit \
  --delivery /private/mixlab-party.flac
~~~

Na expliciete handmatige goedkeuring van nieuwe energiecue-ideeën
kan `mixlab.idea_pipeline finish` hetzelfde doen via
`--full-set-wav ... --delivery ...mp3 --bitrate-kbps 192`.

Wanneer FFmpeg niet is geïnstalleerd of een optionele codec/export
faalt, blijft de **echte complete PCM-WAV** met de bestaande private
Studio en hoofdstukspeler intact. Het commandresultaat bevat dan een
expliciete `delivery_warning`; er wordt geen gecomprimeerde export
voorgewend.

## MP3 192 kbps

~~~bash
python3 -m mixlab.delivery \
  /private/mixlab-playlist-01 \
  /private/mixlab-party.wav \
  /private/mixlab-party.mp3 \
  --bitrate-kbps 192
~~~

Ook 128, 256 en 320 kbps zijn beschikbaar via `--bitrate-kbps`.
De originele WAV blijft ongewijzigd. De encoder gebruikt maximaal twee
FFmpeg-threads en heeft een instelbare timeout, standaard 900 seconden.

## Verliesvrije FLAC

~~~bash
python3 -m mixlab.delivery \
  /private/mixlab-playlist-01 \
  /private/mixlab-party.wav \
  /private/mixlab-party.flac
~~~

De officiële SHA-gebonden WAV-/Studio-/bronreceipt en de werkelijke
WAV-frame- en overgangstijdlijn worden vooraf opnieuw gevalideerd.
MixLab codeert de bestaande voltooide audio lokaal, valideert
achteraf de metadata, samplefrequentie, duur en codec, controleert
dat de originele WAV ondertussen niet is gewijzigd en publiceert
het eindbestand **zonder ooit te overschrijven**. Er verschijnt een
apart privéreceipt met de bron- en outputhash en normalisatiegegevens.

Bij een geslaagde export wordt ook een losse offline
`mixlab-party.mp3.player.html` of
`mixlab-party.flac.player.html` met hoofdstukken gepubliceerd.
De getoonde golfvorm is hergebruikt van de gevalideerde originele
PCM16-WAV (niet verzonnen of herberekend van gecomprimeerde audio);
de duur van MP3 kan door codec-padding minimaal afwijken.
FLAC-afspeelondersteuning is afhankelijk van de lokale browser.

Een fout in de optionele browserpublicatie **verwijdert het echte
MP3-/FLAC-bestand en het privéreceipt niet**. Een fout in de
codecpublicatie laat de originele WAV en Studio intact.
Er wordt geen model uitgevoerd, geen remote dienst gebeld, geen
muziek geüpload en geen onderzoeksholdout aangepast. Dit maakt
een distributieformaat, **geen muzikale kwaliteits- of masteringclaim**.
