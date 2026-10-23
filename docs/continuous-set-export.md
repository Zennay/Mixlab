# MixLab — maak één doorlopende privé DJ-set

De bestaande Transition Studio rendert echte, korte overgangen tussen twee handmatig goed uitgelijnde nummers. Deze extra functie verbindt **jouw gekozen Studio-overgangen** met de tussenliggende passages van je lokaal geïmporteerde nummers. Het resultaat is **één afspeelbare PCM16-WAV**, geen stapel losse previews.

## 1. Eerst een lokale Studio-sessie maken

Gebruik alleen muziek waarvoor je de verwerking mag uitvoeren. Tracks, SHA-256, BPM, beginmaten en A/B cuepunten moeten vooraf gecontroleerd zijn.

    python3 -m mixlab.project_wizard /private/music /private/music/project.json
    python3 -m mixlab.session /private/music/project.json /private/mixlab-session

De Studio maakt per geregistreerd paar vier kandidaten. Beluister ze in de private studio/index.html. Kies zelf welke overgang je werkelijk wilt gebruiken. De import gebruikt een reeds lokaal aanwezige FFmpeg, niet een online dienst.

## 2. Volgorde en overgang kiezen

    python3 -m mixlab.set_export \
      /private/mixlab-session \
      /private/finished-party-set.wav \
      --transition pair-001:bass_swap \
      --transition pair-002:echo_exit

De opties volgen de bedoelde **afspeelvolgorde**. Het inkomende nummer van pair-001 moet hetzelfde zijn als het uitgaande nummer van pair-002. Iedere overgang moet al door Studio gerenderd en met SHA-256 vastgelegd zijn. Er worden **geen nieuwe ongevraagde overgangen** berekend.

Per paar kies je baseline, bass_swap, echo_exit of hard_cut. Een bestaande sessie die met de --pair optie gemaakt is bevat slechts één gerenderd paar. Om meerdere nummers te verbinden heb je een volledige Studio-sessie nodig.

## 3. De werkelijke audiotijdlijn

Voor A → B → C:

1. Speel A vanaf de eerste sample tot aan de handmatig bevestigde A-cue van de overgang A → B.
2. Voeg de exact eerder gerenderde A → B overgang in, met de handmatig gekozen beatlengte.
3. Speel B vanaf de B-cue + overgangsduur tot de A-cue van B → C.
4. Voeg de gekozen B → C overgang in.
5. Speel C vanaf de B-cue + overgangsduur tot het einde.

Solo-passages worden met dezelfde vaste **-6 dB common gain** als de bestaande Studio-varianten weergegeven. Er wordt geen extra gain of compressor op overgangs-WAV's toegepast. Teruglopende of overlappende cuepunten geven een fout in plaats van een verzonnen overgang. De mixer rekt tempo niet op of verandert toonhoogte.

## Output, veiligheid en grenzen

- De volledige WAV wordt pas gepubliceerd nadat de hele stream voltooid en gecontroleerd is. Bestaande bestanden worden **nooit overschreven**.
- De private .wav.receipt.private.json legt gekozen paar/familie, bron-SHA's, output-SHA, frameaantal en duur vast, zonder absolute bronpaden.
- De complete set is maximaal **512 MiB PCM16-WAV**, met hoogstens tien overgangsparen. Streaming gebruikt blokken van maximaal 4096 frames.
- Afwijkende bronhash, verkeerde Studio-sessie, symlink, verkeerde sample rate, inconsistente route en ontbrekende gerenderde kandidaten stoppen de export.
- Import, cuekeuze, export en lokale afspeelactie zijn offline. Geen uploads, account, GPU, modellen of extra runtimepackages.

De voltooide WAV is een **handmatig geprogrammeerde creatieve set**, geen automatische beatmatching, bronseparatie of bewijs van betere DJ-kwaliteit. Beluister lokaal op je eigen tracks of de aansluitingen werkelijk goed klinken. Je eigen bronmuziek blijft privé; exporteer niet naar een Git-repo of publieke map.
