# MixLab Show Runbook — exacte hoofdstuktijden voor een echte WAV-set

De **Show Runbook** is een privé, offline operator-draaiboek voor een **al
gerenderde en SHA-/receiptecht verklaarde** complete MixLab-WAV. Het is geen
live mixer en geen vervanging voor een backupspeler.

## Van gemaakte mix naar daadwerkelijk showdraaiboek

Maak eerst met de bestaande Playlist Studio / Event Brief Studio en expliciete
rechten, BPM en cues je echte, private volledige set:

~~~bash
python3 -m mixlab.playlist_studio \
  /private/music /private/music/approved-event.private.json \
  /private/mixlab-event-session \
  --journey-plan /private/music/mixlab-event-journey.private.json \
  --full-set-wav /private/mixlab-event.wav
~~~

Na succesvol renderen bevat de WAV de exacte hoofdstukvolgorde, gebonden
aan zijn private .receipt.private.json en de originele Studio-sessie.

Maak nu een nieuw, apart offline draaiboek:

~~~bash
python3 -m mixlab.show_runbook \
  /private/mixlab-event-session \
  /private/mixlab-event.wav \
  /private/mixlab-event.runbook.private.html
~~~

Je kunt optioneel de vooraf **door de operator gekozen** lokale starttijd
geven als `--start 19:30`. Zonder deze vlag vraagt de offline browser
zelf om de geplande starttijd; hij raadt deze niet. Open de nieuwe HTML in de
browser naast de WAV.

## Wat de operator krijgt

- **Exacte WAV-hoofdstukoffsets**, op basis van de bron-/Studio-/render-
  receiptgebonden PCM16-uitvoer; onderscheid tussen tracks en overgangen.
- **Totale feitelijke WAV-speelduur**, aantal overgangen, toegankelijke
  track/pairlabels, SHA-256-identiteit van het echte exportbestand.
- Een optionele **geprojecteerde kloktijd** per passage en het verwachte
  eindmoment, inclusief dagwisseling na middernacht. Kloktijden veronderstellen
  dat vanaf de gekozen start zonder pauzes, skips, hapering of computer-sleep
  wordt afgespeeld. De WAV-afspeelklok is tijdens een optreden leidend.
- **Per hoofdstuk eigen DJ-notities**, een soundcheck/rights/offline-backup-
  checklist, een printervriendelijke versie en een CSV-export met dezelfde
  hoofdstukgegevens en handmatige notities. Niets wordt online opgeslagen.
- Een veilig rekenbladvriendelijk CSV-formaat dat door een gebruiker ingevoerde
  velden niet als formules aanbiedt. De exports zijn **privé** en bevatten
  uitsluitend hoofdstuk-IDs en tijden, nooit bronpaden of de muziekaudio.

Dit draaiboek toont geen voorspelde brontracklengtes en gebruikt geen
energieheuristiek om echte renderhoofdstukken te verzinnen. Het leest de
bestaande, canonieke MixLab `set_player.build_chapters` met verplichte
bronrechten-/source-/Studio-/WAV-bindingscontrole. Een WAV zonder originele,
ongewijzigde sessie/receipt wordt geweigerd in plaats van toch een showboek
te maken. Er wordt alleen een **nieuwe**, privé chmod-0600 HTML geschreven in
de WAV-map buiten Git. De music/master- en receiptsbestanden blijven intact.

## Begrenzing

Het online zetten of delen van muziek is geen onderdeel van deze workflow.
MixLab is voor dit product een **offline pre-rendered mix player**, geen
professionele live DJ-engine met gegarandeerde audiohardware, latency,
recovery of goedgekeurde songlicenties. Bestaande Eventmodus (in
`WAV.player.html`) biedt tijdens het afspelen de actuele countdown;
de Show Runbook is een planning-, organisatie- en printdocument.
Een mens controleert en beheert het evenement. Muzikale superioriteit en
M1 blind luisteracceptatie zijn niet met dit runbook aangetoond.
