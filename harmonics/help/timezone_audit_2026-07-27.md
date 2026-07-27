# Anzeige-Zeitzonen der Stationen — Audit vom 2026-07-27

## Worum es geht

In der XTide-Stationszeile stehen zwei verschiedene Dinge:

```
+02:00 :Asia/Riyadh
   |         |
   |         +--- Zone, in der die Vorhersage ANGEZEIGT wird
   +------------- Zone, in der die PHASEN liegen (Rechengrösse)
```

Der Meridian ist eine Rechengrösse und muss zur Herkunft der Konstituenten passen.
Die Anzeigezone dahinter ist reine Darstellung. Beides ist unabhängig — die
Zypern-Stationen etwa haben `+00:00 :Asia/Nicosia` (Greenwich-Phasen, Anzeige in
zyprischer Zeit), und das ist richtig so.

**Eine Korrektur der Anzeigezone ändert keinen einzigen Rechenwert.** Sie ändert
nur, welche Uhrzeit der Nutzer sieht.

## Wie der Fehler entsteht

Zwei Wege:

1. **Sekundärhafen-Transfer.** `py/build_np203_secondary.py` erbt Meridian *und*
   Anzeigezone vom Bezugshafen (`return dict(..., mer=rr['mer'], tz=rr['tz'], ...)`).
   Den Meridian zu Recht — die Phasen stehen ja in dessen Zone. Die Anzeigezone
   nicht. Dadurch zeigten alle saudischen Rotmeer-Stationen ägyptische Zeit,
   weil ihr Bezugshafen Suez ist.
2. **Altbestand.** Ältere Sammlungen tragen teils historisch falsche Zonen, ohne
   dass ein Transfer beteiligt wäre. Sämtliche Spitzbergen-Stationen standen auf
   `Europe/Moscow` (zwei Stunden daneben), Jan Mayen auf `Atlantic/Reykjavik`.

## Prüfmethode

`py/audit_station_timezones.py` vergleicht für jede Station mit Koordinaten die
eingetragene Anzeigezone mit der, die laut `timezonefinder` an genau diesen
Koordinaten gilt. Gemeldet wird nur, wenn sich der **UTC-Versatz** unterscheidet —
im Januar oder im Juli. Reine Namensunterschiede bei gleichem Versatz
(`Europe/Rome` vs `Europe/Zagreb`) sind kein Befund.

Ergebnis in `timezone_audit_2026-07-27.csv` (eine Zeile pro Befund, mit Datei,
Station, Koordinaten, Ist- und Soll-Zone sowie beiden Versätzen).

## Befund: 18 465 Stationen geprüft

### Gruppe A — Anzeige in UTC statt Ortszeit: 2819 Stationen

| Datei | Anzahl |
|---|---:|
| `harmonics_utide_tidetables.txt` | 2349 |
| `harmonics_utide_observations.txt` | 265 |
| `harmonics_utide_current_observations.txt` | 111 |
| `harmonics_utide_current_tables.txt` | 33 |
| `harmonics_utide_australia_oceancurrent.txt` | 30 |
| übrige | 31 |

Das ist eine Konvention des utide-Zweigs, kein Fehler im engeren Sinn: die
Stationen stehen auf `+00:00 :UTC`, also Greenwich-Phasen mit UTC-Anzeige. Für
den Endanwender ist es trotzdem irreführend — „Tréguier, France" mit UTC-Zeiten
liegt im Winter eine, im Sommer zwei Stunden daneben.

**Das ist eine Produktentscheidung, kein Datenfehler.** Nicht ohne Rückfrage ändern.

### Gruppe B — fremde Ortszeitzone: 557 gefunden, **alle abgearbeitet**

Stand 2026-07-27: 537 korrigiert, 20 bewusst stehen gelassen (siehe unten).

| Datei | korrigiert | offen |
|---|---:|---:|
| `harmonics_att_np203_secondary.txt` | 79 | 3 |
| `harmonics_ticon4_worldwide.txt` | 103 | 0 |
| `harmonics-2004-06-14_mod.txt` | 106 | 1 |
| `harmonics_att_np202_secondary.txt` | 88 | 0 |
| `harmonics_noaa_currents.txt` | 74 | 0 |
| `harmonics_att_np208_secondary.txt` | 63 | 1 |
| `harmonics_utide_observations.txt` | 30 | 0 |
| `harmonics-dwf-20251228-free.txt` | 6 | 0 |
| `harmonics-1997-05-25_mod.txt` | 4 | 0 |
| `harmonics_utide_tidetables.txt` | 3 | 4 |
| `harmonics_att_np204_secondary.txt` | 2 | 0 |
| `harmonics_att_np207.txt` | 2 | 0 |
| `harmonics_att_np203_currents.txt` | 1 | 10 |
| `harmonics_noaa_pacif.txt` | 0 | 1 |

Die 20 verbliebenen stehen in `SKIP` in `py/fix_station_timezones.py`, mit
Begründung je Fall. Drei Klassen:

**Grenznah — der Bestand ist richtig, der Vorschlag ein Artefakt.**
Cap Blanc (Nouadhibou ist mauretanisch, UTC+0 wie Dakar), Dhalqut (53.05 E liegt
in Dhofar/Oman), Khowr-e Musa Approaches (iranisches Fahrwasser), Khawr Abd
Allah Current, Dandong (chinesische Stadt am Yalu), Sulawesi Current (2×,
Sulawesi ist WITA), Finsch Islands (Zonengrenze in NO-Grönland unklar).

**Umstritten oder offshore — keine eindeutige Landzone.**
El Bunduq Oilfield (Feld VAE/Katar gemeinsam), Hoang Sa (Paracel), Shuangzijiao
(Spratly).

**Konvention schlägt Geografie.**
Singapore Strait Current (7×) — ADMIRALTY rechnet die Straße in Singapur-Zeit,
obwohl ein Teil der Punkte in indonesischem Wasser liegt.

**Koordinatenfehler, nicht Zeitzonenfehler.**
Niue Island (169.92 muss West sein) und Shortland Island (−10.53/151.08 liegt in
der Milne Bay, PNG; die echten Shortlands: −7.05/155.85).

Auffällige Gruppen:

- **Französische Überseegebiete auf `Europe/Paris`** — Neukaledonien, Wallis,
  Futuna, Tahiti, Tuamotu. Bis zu 11 Stunden daneben.
- **Russische Fernost-Stationen auf europäischen Zonen** — Pitlekaj auf
  `Europe/Berlin`, Providenya auf `Europe/Kaliningrad`. 10–11 Stunden.
- **Kanada** — meist eine Stunde: `America/Iqaluit` statt `America/Rankin_Inlet`,
  `America/Halifax` statt `America/Toronto`, `America/Goose_Bay` statt
  `America/St_Johns`. Der grosse Block steckte in `harmonics-2004-06-14_mod.txt`.
- **Karibik und Golf von Mexiko auf `America/Chicago`, `America/Port_of_Spain`
  oder `Atlantic/Bermuda`** — Kuba, Bahamas, Kleine Antillen, Mittelamerika.
  1–2 Stunden, rund 60 Stationen in `harmonics_att_np202_secondary.txt`.
- **Mittelmeer und Atlantikinseln auf `Europe/London`** — Türkei (3 h), Griechen-
  land, Libanon, Tunesien, dazu Azoren, Kanaren, Madeira und Kapverden auf der
  jeweiligen Festlandzone. Rund 60 Stationen in `harmonics_att_np208_secondary.txt`.

- **Doppelte Stationsnamen.** In `harmonics-2004-06-14_mod.txt` kommen 13 Namen
  mehrfach vor, zwei davon mit unterschiedlichen Zonen (Becher Bay, L'Île-d'Anticosti).
  `py/fix_station_timezones.py` ordnet deshalb über Name **und** Ist-Zone zu, nicht
  über den Namen allein -- sonst bleibt der zweite Block still stehen.

## Fallstricke bei der Korrektur

1. **Ozean-Zonen.** Liefert `timezonefinder` ein `Etc/GMT±n`, hat es keine
   Landzone gefunden — die Station liegt auf offener See. Das sagt nichts über
   die Station aus. Vor dem Ausfiltern meldete der Lauf so 89 Fehlalarme, darunter
   „Anadyr, Russia" (`Asia/Anadyr` ist richtig) und „Banquereau Bank, Nova Scotia"
   (`America/Halifax` ist richtig). Das Skript verwirft solche Treffer inzwischen.

2. **Grenznahe Stationen.** Bei einem Ort dicht an einer Zonengrenze kann der
   Punkt auf der falschen Seite liegen. Sieben solcher Faelle stehen in `SKIP`.
   Gegenbeispiel: die 72 NOAA-Stroemungsstationen `America/Vancouver ->
   America/Sitka` tragen alle `, Canada` im Namen, liegen aber auf Dall Island,
   Prince of Wales und den Tongass-Inseln — also in Alaska. Das Laenderlabel war
   der Sammelfehler, nicht die Position; die Korrektur ist richtig.

3. **Ein Zeitzonen-Treffer kann ein Koordinatenfehler sein.** „Niue Island, Niue"
   steht auf `Pacific/Niue` (richtig), löst aber nach `Pacific/Efate` (Vanuatu)
   auf. Niue liegt bei 169.92 **West**; ein Vorzeichenfehler in der Länge würde
   genau diesen Treffer erzeugen. Solche Fälle nicht bei der Zeitzone korrigieren,
   sondern bei der Koordinate.

## Erledigt

**2026-07-27 — Gruppe B vollstaendig abgearbeitet, 537 Stationen in 13 Dateien.**

Den Anfang machten 24 Stationen am Roten Meer (`py/fix_redsea_tz_and_yanbu.py`),
der Rest lief ueber `py/fix_station_timezones.py`. Alle TCDs neu gebaut und
rueckgewandelt geprueft, Stationszahlen stimmen ueberein.

Stichproben am 15.01.2027 nach der Korrektur: Massawa EAT, Port Sudan CAT,
Eilat IST, Aqaba +03, Pitlekaj +12, Road Town AST, Izmir +03, Beirut EET,
Port Alfred SAST, Port-aux-Francais +05, Papeete −10, Mata Utu +12, Savoonga
AKST, New Amsterdam −04.

## Korrigieren

```
python3 py/fix_station_timezones.py DATEI.txt            # Liste anzeigen
python3 py/fix_station_timezones.py DATEI.txt --write    # schreiben + Sicherung
```

Setzt nur den Teil hinter dem Doppelpunkt. Legt vor dem Schreiben eine Kopie
unter `harmonics/backup/<name>_pre_tzfix_<datum>.txt` ab. Danach die TCD neu
bauen (Zieldatei vorher loeschen -- `build_tide_db` haengt sonst an).

## Nebenbefund: falsche Länderlabel

Beim Durchsehen aufgefallen, nicht korrigiert:

| Station | steht als | liegt laut Koordinaten in |
|---|---|---|
| Clump (−17.85/146.11) | South Australia | Queensland |
| Qaqortoq (60.72/−46.03) | Denmark | Greenland |
| Anewa Bay (−6.18/155.54) | Solomon Islands | Papua-Neuguinea (Bougainville) |
| Yokeko Point (48.42/−122.62) | British Columbia, Canada | Washington, USA |
| Drayton Harbor (48.99/−122.77) | Canada | Washington, USA |
| Cape Lawrence (80.35/−69.28) | Greenland | Ellesmere Island, Kanada |
| 72 NOAA-Stroemungsstationen | Canada | Alaska (Panhandle) |
| Bellfield, New Amsterdam (−57.5…−58.0) | Suriname | Guyana |

## Wiederholen

```
python3 py/audit_station_timezones.py [ZIEL.csv]
```

Läuft rein lesend über `harmonics/{att,noaa,classic,utide,ticon}/*.txt` und
braucht `timezonefinder` aus `weather/venv`.
