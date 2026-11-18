# Daten aktualisieren

Alle Befehle im Ordner `~/weather` starten:

    cd ~/weather

Die Karte liest die neuen Dateien sofort. Die App muss dafür nicht neu gestartet werden; im Browser genügt Neuladen.

---

## 1. Wetter (Karte)

Quelle ist jeweils der neueste GFS-Lauf der NOAA (alle 6 h ein neuer Lauf). Jeder Befehl holt 72 Stunden Vorhersage.

| Ebene | Befehl | Dauer (ca.) |
|---|---|---|
| Wind | `venv/bin/python py/download_wind_forecast.py` | wenige Minuten |
| Luftdruck, Isobaren, Fronten | `venv/bin/python py/download_pressure_forecast.py` | wenige Minuten |
| Niederschlag | `venv/bin/python py/download_precip_forecast.py` | wenige Minuten |
| Wellen weltweit | `venv/bin/python py/download_wave_forecast.py` | wenige Minuten |
| Wellen Ostsee, Mittelmeer, Rotes Meer, Golf | `venv/bin/python py/download_wave_regional.py` | einige Minuten |
| Meeresströmung (HYCOM) | `venv/bin/python py/download_ocean_currents.py` | länger |
| Wassertemperatur | `venv/bin/python py/download_sst.py` (mit `--source mur` feiner, aber größer) | wenige Minuten |
| Regenradar-Nowcast | `venv/bin/python py/compute_radar_nowcast.py` | einige Minuten |

**Reihenfolge:** `download_wave_regional.py` erst **nach** `download_wave_forecast.py`, weil es dessen Zeitschritte übernimmt.

---

## 2. Windstau („Weather Effect on Sea Level“)

Wird von Hand gestartet, es läuft nichts automatisch. Die Copernicus-Skripte brauchen den Zugang in `~/.copernicusmarine` (ist eingerichtet).

| Gebiet | Befehl | Dauer (ca.) |
|---|---|---|
| USA und einige IOC-Pegel (NOAA STOFS) | `venv/bin/python py/windstau.py laden` | wenige Minuten |
| Ostsee, Mittelmeer, Schwarzes Meer, westlicher Limfjord | `venv/bin/python py/windstau_cmems.py` | einige Minuten |
| Nordsee, Ärmelkanal, Britische Inseln, Biskaya | `venv/bin/python py/windstau_nws.py --vorhersage` | ~30 min |
| Kartenebene (Rasterbilder aller Meere) | `venv/bin/python py/windstau_karte.py` | ~7 min |

**Reihenfolge:** erst die drei Pegel-Skripte, **zuletzt** `windstau_karte.py`, weil die Nordsee-Fläche aus den Punkten von `windstau_nws.py` gerechnet wird.

Einzelnes Meer: `--meer=ostsee` (bzw. `mittelmeer`, `schwarz`, `limfjord`, bei der Karte `nordsee`).

Nicht nötig: `windstau_nws.py --modelltide` (einmalig erledigt, nur für neue Pegel).

---

## 3. Gezeiten und Strömungen

| Was | Befehl | Wann |
|---|---|---|
| Gesammelte Messungen holen (EA England, Island, Kuwait, Connemara, Saudi-Arabien) | läuft **automatisch** täglich um 8 Uhr (`sammler-holen.timer`); von Hand: `venv/bin/python py/sammler_holen.py` | nur wenn der Laptop morgens aus war |
| Gezeiten-Datenbank (TCD) und Kartenmarker | `venv/bin/python py/tcd_bauen.py` | nach jeder Änderung an Harmonics-Dateien (macht Claude meist selbst) |
| Flutrichtung der Strömungssätze prüfen | `venv/bin/python py/flutrichtung_pruefen.py` (mit `--schreiben` werden Sätze gedreht) | nach neuen Strömungssätzen |

Die Gezeitenvorhersagen selbst rechnet die App bei jedem Aufruf neu, dafür muss nichts geladen werden. Gemessene Pegelwerte auf der Detailseite (IOC, Pegelonline, NOAA) holt die App ebenfalls selbst beim Öffnen der Seite.

Ob der Sammler läuft: `systemctl --user list-timers sammler-holen.timer`

---

## Alles auf einmal (Vorschlag für morgens)

    cd ~/weather
    venv/bin/python py/download_wind_forecast.py
    venv/bin/python py/download_pressure_forecast.py
    venv/bin/python py/download_precip_forecast.py
    venv/bin/python py/download_wave_forecast.py
    venv/bin/python py/download_wave_regional.py
    venv/bin/python py/windstau.py laden
    venv/bin/python py/windstau_cmems.py
    venv/bin/python py/windstau_nws.py --vorhersage
    venv/bin/python py/windstau_karte.py

Meeresströmung, Wassertemperatur und Nowcast ändern sich langsamer bzw. sind seltener gebraucht; bei Bedarf dazunehmen.

Stand der Kartendaten am 18.11.2026: Wind 14.9., Wellen 29.6., Niederschlag 22.3., Strömung 13.5., Wassertemperatur 23.3., Druck 13.11., Windstau 9.11. — alles veraltet.
