# MixLab Offline DJ Demo — hoor een complete drie-track DJ-set

Deze **productdemo** maakt drie originele tracks volledig lokaal aan en
gebruikt vervolgens de normale MixLab-ingest, Transition Studio, visuele
cue-editor, offline Set Composer en Full Set Player. De drie audiobronnen
bestaan uitsluitend uit door MixLab gegenereerde eigen synthesizergeluiden:
geen samples van artiesten, streamingcatalogus, AI-model of upload.

De demo is **geen QA-suite of bewijs van muzikale superioriteit**.
Voor canonieke PCM16-WAV volstaat Python 3.10+; FFmpeg en internet zijn niet
nodig.

## Start

Gebruik vanuit een lokale MixLab checkout een nieuw privépad **buiten Git**:

~~~bash
python3 -m mixlab.demo /private/mixlab-demo-01
~~~

Open daarna `/private/mixlab-demo-01/index.html`. De landingspagina biedt:

- **Complete set beluisteren:** één echt gerenderde `three-song-set.wav`
  met drie tracks, twee verschillende DSP-overgangen, interactieve
  hoofdstukken, vorige/volgende knoppen en een downloadbare CUE-sheet.
- **Zelf een mix programmeren:** de volledige Set Composer met alle acht
  reeds gerenderde audio-overgangen, de vier families voor beide paren,
  routeopbouw en privé keuzeplan-download.
- **Korte overgangen vergelijken:** de bestaande Transition Studio voor
  baseline, bass swap, echo exit en hard cut.
- **Waveform-cues aanpassen:** dezelfde visuele editor als bij eigen muziek.
- **Klassieke tweetrackmix:** de eerdere two-song export blijft beschikbaar.

Alle drie de tracks duren 24 seconden, hebben handmatig vastgelegde
120 BPM en zijn 44,1 kHz PCM16 stereo. A → B gebruikt 16 beats vanaf
A=16 seconden en B=0; B → C eveneens 16 beats vanaf B=16 en C=0.
Er ontstaat zo een **56 seconden doorlopende set**, met 8 seconden
overlapping per overgang. Dit is een bewust gekunstelde voorbeeldset
op originele synthetische drums, bass en pads; er wordt geen muzikaal
begrip of mensenvoorkeur geclaimd.

## Resultaatbestanden

~~~text
/private/mixlab-demo-01/
  index.html                              # Open deze startpagina
  sources/
    demo-song-01.wav
    demo-song-02.wav
    demo-song-03.wav
    demo-source-spec.json                # Rechtendeclaratie: synthetic
  audition/
    sources/cue-editor.html
    sources/source_manifest.json
    excerpts/library.json
    studio/index.html
    studio/auditions/demo-pair-001/*.wav
    studio/auditions/demo-pair-002/*.wav
    set-composer/index.html
  full-song/index.html                   # Eerdere 2-track export
  three-song-set.wav                     # Complete 3-track mix
  three-song-set.wav.receipt.private.json
  three-song-set.wav.player.html         # Offline hoofdstukspeler
~~~

De toepassing maakt uitsluitend een nieuw projectpad aan, slaat gegevens
privé op en opent geen poorten. Bij fouten verwijdert ze alleen de volledig
nieuw aangemaakte demo, geen bronbestanden of eerder werk.

## Schakel daarna over op je eigen muziek

Voor echte opnames gebruik je [de begeleide projectmaker](guided-local-project.md)
en [de interactieve MixLab-sessie](interactive-private-studio.md).
De [offline Set Composer](offline-set-composer.md) en
[Full Set Player](private-full-set-player.md) werken daarop op dezelfde
manier. Ondersteunde 44,1 kHz PCM16-WAV's werken zonder FFmpeg; MP3, FLAC en
M4A vragen een reeds geïnstalleerde lokale FFmpeg/FFprobe.

M1 blijft **OPEN** totdat een onafhankelijk rechtenveilig muziekexperiment
met echte luisteraars de vooraf gedefinieerde acceptatiecriteria haalt.
De demo is geen bewijs van auteursrecht op andermans tracks of van
automatisch beat-, key-, phrase- of stembegrip.
