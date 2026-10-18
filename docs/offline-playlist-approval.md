# MixLab — volledige rechten- en cue-invoer in een lokaal formulier

De bestaande Playlist Studio kan een complete lokale WAV-set bouwen, maar
vroeg voorheen voor elke track en overgang aparte terminalinvoer. Met de
**Private Playlist Approval** hoef je die handmatig gecontroleerde informatie
niet twee keer over te typen. De browser maakt een **nieuw, niet-uitvoerend**
goedkeuringsbestand. De gewone renderer blijft alle veiligheids-, rechten-
en bronchecks uitvoeren.

## Vereisten: eerst een SHA-gebonden voorstel

Gebruik een eerdere [Event Brief Studio](offline-event-brief-studio.md),
[Energy Journey Planner](energy-journey-planner.md) of een andere bestaande
MixLab lokale creatieve planroute om een privé JSON te maken naast de
oorspronkelijke, rechtenveilige muziekbestanden:

~~~bash
python3 -m mixlab.journey notes /private/music /private/music/energy.private.json
python3 -m mixlab.journey plan /private/music /private/music/energy.private.json /private/music/set-plan.private.json --tracks 5 --shape build
~~~

De audio en plannen staan **buiten Git**. Er worden geen bronrechten,
cuepunten, lyrics of muzikale kwaliteitsclaims automatisch afgeleid.

## Stap 1 — browserformulier voor rechten en echte cues

~~~bash
python3 -m mixlab.playlist_approval \
  /private/music \
  /private/music/set-plan.private.json \
  /private/music/playlist-approval.private.html
~~~

Open `/private/music/playlist-approval.private.html` lokaal.
Je ziet alle geselecteerde tracks in de **reeds voorgestelde volgorde**,
met hun handmatig geverifieerde BPM en private bronbinding.

**Lokaal beluisteren in hetzelfde formulier:** kies per track de originele
muziekfile via de browser. De ingesloten afspeelknoppen gebruiken een
tijdelijke lokale blob-URL: er gaat geen audio naar een server. De browser
controleert de exacte bestandsnaam en een bestandsgrootte van maximaal
512 MiB. Zet de afspeelkop op een door jou gecontroleerde positie en klik
**Set first downbeat**, **Mark outgoing A cue** of **Mark incoming B cue**.
De knop **4 beats vooruit/achteruit** springt op basis van jouw al
handmatig geverifieerde BPM, niet van een automatisch gevonden beat.
Kan de browser een bestand niet afspelen, beluister het in je eigen
muziekspeler en voer de seconden handmatig in.

De browser controleert bewust **niet zelf** het volledige audiobestand
op SHA-256 (dit kan honderden MiB browsergeheugen vereisen). De bestaande
serverloze Playlist Studio doet wél opnieuw de verplichte, echte lokale
source-hashcontrole voordat import en render starten.

Vul vervolgens in:

- Per track expliciet het soort gebruiksrecht (synthetic, licensed,
  user-permitted of public-domain), en concrete provenance/rechtengrond.
- Desgewenst de eerste handmatig gecontroleerde downbeat in seconden.
- Per overgang de precieze **outgoing A**- en **incoming B**-cues in seconden,
  terwijl je de eigen, lokale opname daadwerkelijk beluistert.
- De gedeelde overgangsduur in beats (1–64). De interface controleert
  teruglopende uitgangen t.o.v. het voorgaande B-eind.
- Twee expliciete vakjes: eigen rechtenverklaring en akkoord met de volgorde.

Klik **Export my private approved cues**. Dit downloadt een nieuw
`mixlab-event-approved.private.json` met **geen audio**. Verplaats
het nieuwe bestand naast de originele songs en het eerder gebruikte
plan. Het bevat wel gevoelige gebruiksmetadata; verspreid het niet.

## Stap 2 — echte Studio en volledige WAV met bestaande engine

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music \
  /private/music/confirmed-event-sources.private.json \
  /private/my-event-studio \
  --journey-plan /private/music/set-plan.private.json \
  --approval-file /private/music/mixlab-event-approved.private.json \
  --beats 16 \
  --full-set-wav /private/my-event.wav \
  --family bass_swap
~~~

Gebruik bij `--beats` **precies hetzelfde** aantal als in het
browserformulier. Playlist Studio:

1. Controleert de individuele lokale opnamen opnieuw met SHA-256 tegen
   het originele, ongewijzigde plan.
2. Vereist dat het nieuwe goedkeuringsbestand aan de **exacte bytes**
   van dat plan is gebonden en dat alle nummers, volgorde, rechtenvelden,
   secondenwaarden en pair-aantallen kloppen. Onbekende of gewijzigde
   muzieksources, ongeldige rechten, niet-numerieke/NaN-cues, teruglopende
   overgangen of ongeldige beatlengte worden geweigerd.
3. Toont nogmaals de gekozen volgorde en vraagt expliciet
   **Accept this exact suggested order? Type yes**. Zonder dat akkoord
   wordt geen nieuw source manifest gemaakt.
4. Gebruikt daarna de bestaande canonieke, rechten- en hash-gebonden
   privé manifest/import/Studio/Set Composer/volledige-WAV-rendering,
   zonder een tweede reeks los ingetikte rechten- en cuevragen.
5. Als later decoderen/renderen fout gaat, blijft het nieuwe,
   goedgekeurde bronmanifest behouden voor expliciet herstarten met
   `--resume` (dan zonder `--journey-plan` en `--approval-file`).

Optionele MP3/FLAC via `--delivery` vereist reeds lokaal
geïnstalleerde FFmpeg/FFprobe, zoals in de bestaande
[private set delivery](private-set-delivery.md).

## Grenzen

- De browser is **geen rechtencontroleur**. Alleen de gebruiker kan
  aantonen dat de muziek gebruikt mag worden. Het formulier doet
  evenmin automatische BPM/beat/downbeat/key/phrase-analyse.
- De exact gebonden goedkeuringsdata is niet equivalent aan
  een M1-geaccepteerde set; de blind-human-preference en andere
  onderzoeksintegriteitsvoorwaarden blijven open.
- De browser laadt geen audio. Gebruik een eigen lokale speler
  voor zorgvuldig controleren van de cue-seconden.
- Iedere audio/JSON/HTML blijft privé buiten Git, wordt niet geüpload
  en nieuwe output overschrijft niets. De integratie heeft geen
  productie-deploy, zCloud queue-admission of runtime service nodig.
