# MixLab — offline vergelijking van handmatige DJ-cues

Een bestaande DJ mag vóór/na het handmatig aanpassen van overgangspunten vergelijken **zonder audio te uploaden of opnieuw te renderen**. Beide bronmanifesten moeten naast exact dezelfde toegestane WAV-tracks liggen. Alle WAVs worden opnieuw via de bestaande read-only SHA-256/PCM16-admission gecontroleerd.

## Voorbeeld

```bash
python3 -m mixlab.cue_editor apply /private/music/source_manifest.json /private/music/mixlab-cue-selections.json /private/music/revised.json
python3 -m mixlab.cue_compare /private/music/source_manifest.json /private/music/revised.json
python3 -m mixlab.cue_compare /private/music/source_manifest.json /private/music/revised.json --html /private/music/cue-comparison.html
```

### Makkelijker: bewaar de nieuwe cuepunten en de voor/na-review in één opdracht

Na het downloaden van je handmatige keuzes vanuit de offline editor:

```bash
python3 -m mixlab.cue_editor apply /private/music/source_manifest.json /private/music/mixlab-cue-selections.json /private/music/revised.json --compare-html /private/music/cue-comparison.html
```

De nieuwe privé `revised.json` en het duidelijke mobiele vergelijkingsrapport worden afzonderlijk SHA-gecontroleerd en exclusief aangemaakt met `0600`-bestandsrechten, zonder je originele tracks of bronmanifest te wijzigen. De JSON-consolebevestiging toont het aantal handmatig gewijzigde en indirect verschoven overgangen. Als de rapportnaam al bestaat, stopt de opdracht vóór het maken van een nieuwe manifestversie; als de optionele vergelijking daarna faalt, blijft het geldige nieuwe manifest behouden en staat de fout helder in de terminal. Dit is geen export van audio of automatische kwaliteitskeuring.


De standaarduitvoer is JSON zonder audiopaden. Het optionele, statische lokale HTML-bestand heeft permissies **0600**, bevat geen scripts, netwerkbronnen, audio of volledige originele bestandslocaties en overschrijft nooit een bestaand bestand.

Het brongeverifieerde HTML-vergelijkingsrapport gebruikt dezelfde exclusieve privé-schrijver als de editor en de nieuwe cue-manifesten. Een mislukte schijfsynchronisatie laat geen gedeeltelijk rapport met een definitieve naam achter, en een ander proces dat de gekozen bestandsnaam eerder claimt, verliest zijn bestand niet.


**Privé-bestanden vanaf het eerste moment:** ook het brongebonden HTML-cue-editorbestand (`cue_editor prepare`) en het nieuw opgeslagen cue-manifest (`cue_editor apply`) worden voortaan exclusief als `0600` aangemaakt, dus nooit tijdelijk als voor anderen leesbaar bestand bij een permissieve `umask`. Als een andere bewerking intussen dezelfde bestandsnaam aanmaakt, blijft diens bestand ongemoeid; een mislukte schijfsynchronisatie ruimt alleen het eigen, zojuist gemaakte bestand op. Nieuw aangebrachte cues worden ook niet in een Git-checkout opgeslagen. De originele WAV's en manifesten blijven onveranderd.


### Menselijk vóór/na-oordeel

De nieuwe mobiele HTML-weergave onderscheidt expliciet **cue handmatig aangepast**, **verschoven door eerdere cue** en **ongewijzigd**. Een ongewijzigde overgang kan namelijk toch later beginnen omdat een vorige overgang werd verschoven. Een aparte samenvatting telt deze indirect verplaatste overgangen. De vergelijking bevat een toetsenbord-focusbare horizontale tabel voor smalle schermen, zonder script of externe diensten. Gebruik deze timingverklaring om met toegestaan origineel materiaal zelf A en B te beluisteren; een grotere of kleinere verschuiving betekent niet automatisch dat een mix beter klinkt.


- Controleert dat **alle originele nummers, audio-SHA's, rechten, herkomst, BPM, trackvolgorde, overgangsfamilies en beats** onveranderd zijn. Alleen handmatig gekozen Deck A/B-cuepunten mogen verschillen.
- Rekent beide complete sets uit in originele PCM-frames, zodat het effect van een eerdere edit zichtbaar wordt op latere overgangen, zelfs wanneer die latere cue zelf ongewijzigd bleef.
- Weigert onvolledige of onderbroken routes, overlap van overgangspunten, bronwijzigingen, andere rechten, ongeldige cueposities en output naar een Git-repository.
- Dit is **timingbewijs**, geen nieuwe render, automatische beat/key-analyse, rechtenverklaring of onafhankelijke blinde luistervergelijking. M1 blijft open totdat echte toegestane audio en beoordelaars zijn geverifieerd.

De vergelijking is een nieuwe, zelfstandige read-only workflow en vervangt de bestaande cue-editor, volledige WAV-render en originele manifesten niet.
