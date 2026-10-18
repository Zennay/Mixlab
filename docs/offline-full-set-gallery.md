# MixLab Set Gallery — vergelijk volledige mixen op dezelfde tijdlijn

Met de **Set Gallery** kun je vanuit één bestaande, rechtenveilige
privé-Studio twee tot vier **echt gerenderde volledige WAV-mixen**
publiceren en lokaal beluisteren.

~~~bash
python3 -m mixlab.set_gallery \
  /private/mixlab-playlist-01 \
  /private/mixlab-full-set-gallery
~~~

Deze opdracht maakt standaard `bass_swap.wav` en `echo_exit.wav`
met privéreceipts, losse offline hoofdstukspelers en
`/private/mixlab-full-set-gallery/index.html` als gezamenlijke
vergelijkingspagina.

De pagina toont een audio-player, stijlkeuze, een tijdlijn en alle
hoofdstukken. Je kunt tijdens het luisteren tussen de twee complete
mixen omschakelen **zonder opnieuw bij het eerste nummer te beginnen**.
De vergelijking gebruikt exact dezelfde bestaande cues, nummers en
tijdlijn; alleen de expliciet gekozen renderstijl verschilt. De
audio komt uitsluitend uit jouw eigen bestaande PCM16 Studio.

Voor vier varianten (maximaal vier, minimaal twee):

~~~bash
python3 -m mixlab.set_gallery \
  /private/mixlab-playlist-01 \
  /private/mixlab-gallery-02 \
  --family bass_swap \
  --family echo_exit \
  --family hard_cut \
  --family baseline
~~~

De bron-, rechten-, WAV-, overgangs- en Studio-SHA-controles van de
reeds bestaande canonieke `set_export` en `set_player` blijven van
kracht. MixLab weigert incomplete of niet-aaneensluitende playlists,
een familie zonder reeds gerenderde echte WAV-overgang, schrijfuitvoer
binnen Git of bestaande uitvoermappen en verschillende tijdlijnen
tussen varianten. Alle audiobestanden en receipts zijn privé en
er wordt nooit bestaande muziek overschreven.

**Let op schijfruimte:** ieder alternatief produceert een zelfstandige
complete PCM16-WAV, dus meer varianten betekenen meer lokale opslag.
Als het maken van een latere variant mislukt, blijven reeds afgeronde
varianten beschikbaar. Er wordt geen netwerk, AI-tracker of online
muziekcatalogus gebruikt. Dit is een **niet-geblindeerde creatieve
vergelijking**, geen subjectief of statistisch kwaliteitsonderzoek.
De officiële M1 Transition Lab-acceptatiecriteria blijven OPEN.
