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
| Ozeanstrom für „Total current“ in der Gezeitenstrom-Ebene (Copernicus GLO12, ohne Gezeiten, 10 Tage) | `venv/bin/python py/download_ocean_cmems.py` | ca. 5 Minuten |
| Wassertemperatur | `venv/bin/python py/download_sst.py` (Copernicus OSTIA 0,1°; fällt Copernicus aus, nimmt es NOAA OISST) | ca. 1 Minute |
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
    venv/bin/python py/download_ocean_cmems.py

Meeresströmung, Wassertemperatur und Nowcast ändern sich langsamer bzw. sind seltener gebraucht; bei Bedarf dazunehmen.

Stand der Kartendaten am 18.11.2026 abends: Wind, Druck, Niederschlag, Wellen, Windstau aktuell; Wassertemperatur 18.11. (seit 19.11. Copernicus OSTIA statt NOAA), Nowcast 18.11. 22 Uhr (pysteps + opencv seit 18.11. im venv), Meeresströmung 13.5.
