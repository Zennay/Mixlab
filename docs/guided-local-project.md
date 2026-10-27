# MixLab — begeleide lokale projectmaker

Je hoeft niet langer zelf voor ieder nummer checksums of JSON aan te maken.
De **MixLab projectwizard** toont de bestanden in je privé muziekmap
en vraagt alleen de gegevens die MixLab niet eerlijk kan raden:
wat jij mag verwerken, handmatig gecontroleerde BPM en de momenten
waar de overgangen mogen beginnen.

## In drie stappen een eerste echte overgang

**1. Bewaar toegestane nummers bij elkaar**, bijvoorbeeld:

```text
/private/muziek/
  nummer-een.mp3
  nummer-twee.flac
```

Dit zijn eigen bestanden, geen Spotify- of streaminglinks. Muziek blijft
volledig lokaal en wordt niet naar GitHub, een server of API verstuurd.

**2. Start de projectmaker:**

```bash
python3 -m mixlab.project_wizard /private/muziek /private/muziek/mixlab-bronnen.json
```

Hij vraagt:
- Welke 2–20 nummers je voor MixLab wilt gebruiken (keuze uit de lokale map).
- Per nummer: de door jou gecontroleerde BPM (30–300), je expliciete
  gebruiksrecht (`synthetic`, `licensed`, `user-permitted` of
  `public-domain`) en niet-lege bronherkomst.
- Optioneel de handmatig gecontroleerde eerste downbeat in seconden.
  Alleen wanneer die voor *alle* tracks aanwezig is, kun je later de
  optionele energieberekening met `--suggestions` inschakelen.
- Hoeveel overgangsparen je wilt (1–10), per paar twee verschillende
  nummers met gelijke BPM, het aantal beats (1–64) en de twee door
  jou gekozen starttijdstippen in seconden.

De wizard leest de bestanden lokaal en berekent zelf hun SHA-256-checksum.
Hij schrijft een nieuw privé `mixlab-bronnen.json`-bestand op dezelfde
plek als de bronmuziek. Er wordt niets overschreven. Bestanden in
Git-projecten en onveilige symlinks worden geweigerd; de JSON krijgt
bestandsrechten 0600.

**3. Start de complete MixLab sessie:**

```bash
python3 -m mixlab.session /private/muziek/mixlab-bronnen.json /private/mixlab-project-01
```

Vereist lokaal reeds aanwezige FFmpeg en FFprobe. MixLab importeert
de muziek naar WAV, snijdt fragmenten op jouw cues uit, rendert de
vier bestaande overgangstypen en genereert
`/private/mixlab-project-01/studio/index.html` om direct lokaal te
beluisteren en te exporteren.

Optioneel voor een later te beoordelen shortlist:

```bash
python3 -m mixlab.session /private/muziek/mixlab-bronnen.json /private/mixlab-project-02 --suggestions
```

Dit gebruikt de handmatige beatgrid als startpunt, niet een
automatisch bewezen beat- of phrase-detectie.

## Veiligheid en beperkingen

- De wizard toont tot 200 mapitems en accepteert 2–20 brontracks. Voor
  overzicht en bronpadcontrole kiest hij alleen direct in de geselecteerde
  map aanwezige bestanden, geen submappen. Toegestaan zijn PCM/WAV, MP3,
  FLAC, M4A, AAC, OGG, OPUS en AIFF/AIF (afhankelijk van FFmpeg).
- Je moet per track zelf toestemming en herkomst verklaren; geen
  impliciete licentie, informatie uit bestandsnamen of onbetrouwbare
  BPM-schattingen. A- en B-cues zijn altijd uitdrukkelijk gekozen.
- Alle data blijft op het eigen apparaat. De wizard installeert geen
  software, downloadt geen bestanden, traint geen model en start geen
  netwerkdienst. De programmeercode en documentatie staan in de repo;
  bronbestanden, afgeleide WAV en luisterantwoorden niet.
- De wizard vraagt de benodigde informatie, maar controleert zelf
  **niet** of je daadwerkelijk muziekrechten bezit of of je gekozen
  cue muzikaal goed is. De daaropvolgende media-import en
  fragmentvoorbereiding houden hun eigen checksums, formaat-,
  framelimieten en afwijzingsvoorwaarden.
- Je kunt `--partition evaluation` kiezen om tracks voor een aparte
  evaluatiestudie te labelen. Dat maakt de dataset nog niet automatisch
  blind of juridisch vrijgegeven; de onafhankelijke M1-luistergate blijft
  open.

Dit is een nieuwe **gebruikersworkflow** boven op de bestaande M1-engine,
niet een vervanging van de open PR's voor automatische analyse, echte
tempo-adaptatie en stem separation.
