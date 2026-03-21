#!/usr/bin/env python3
"""
Download astronomical water level data (Waterhoogte astronomisch t.o.v. NAP)
from Rijkswaterstaat for all available tide stations.

Uses ddlpy (pip install rws-ddlpy) to access the RWS Waterwebservices API.
Data is saved as CSV files per station in water_levels/Netherlands/.

The astronomical tide predictions can then be analyzed with UTide to extract
harmonic constants/constituents for XTide.
"""

import os
import sys
import datetime
import time
import ddlpy
import pandas as pd

OUTPUT_DIR = '/home/oliver/water_levels/Netherlands'
START_DATE = datetime.datetime(2007, 4, 1)
END_DATE = datetime.datetime(2026, 3, 18)


def get_astronomical_stations():
    """Get all stations with astronomical water height data relative to NAP."""
    print("Lade Stationskatalog von RWS...")
    locations = ddlpy.locations()

    sel = locations[
        (locations['Grootheid.Code'] == 'WATHTE') &
        (locations['Hoedanigheid.Code'] == 'NAP') &
        (locations['ProcesType'] == 'astronomisch') &
        (locations['Groepering.Code'] == '')
    ]

    print(f"{len(sel)} Stationen mit astronomischer Waterhoogte (NAP) gefunden.")
    return sel


def download_station(station_row, start_date, end_date, output_dir):
    """Download data for a single station and save as CSV."""
    code = station_row.name if isinstance(station_row.name, str) else station_row.get('Code', 'unknown')
    name = station_row.get('Naam', code)

    # Sanitize filename
    safe_name = code.replace('/', '_').replace('\\', '_').replace(' ', '_')
    csv_path = os.path.join(output_dir, f"{safe_name}.csv")

    # Skip if already downloaded
    if os.path.exists(csv_path):
        # Check if file has reasonable size (> 1KB means it has data)
        if os.path.getsize(csv_path) > 1024:
            print(f"  ✓ {name} — bereits vorhanden, überspringe.")
            return True

    print(f"  ↓ {name} ({code})...", end='', flush=True)

    try:
        measurements = ddlpy.measurements(station_row, start_date=start_date, end_date=end_date)

        if measurements is None or len(measurements) == 0:
            print(f" KEINE DATEN")
            return False

        # Only keep relevant columns: timestamp (index), water level, unit
        slim = measurements[['Meetwaarde.Waarde_Numeriek']].copy()
        slim.columns = ['waterlevel_cm_NAP']

        # Save to CSV
        slim.to_csv(csv_path)
        n_rows = len(slim)
        years = n_rows / (6 * 24 * 365.25)  # ~6 values/hour * 24h * 365.25 days
        print(f" {n_rows} Werte ({years:.1f} Jahre)")
        return True

    except Exception as e:
        print(f" FEHLER: {e}")
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    stations = get_astronomical_stations()

    print(f"\nDownload-Zeitraum: {START_DATE.strftime('%d.%m.%Y')} bis {END_DATE.strftime('%d.%m.%Y')}")
    print(f"Ausgabeverzeichnis: {OUTPUT_DIR}")
    print(f"{'='*60}\n")

    success = 0
    failed = 0
    skipped = 0

    for i, (idx, station) in enumerate(stations.iterrows()):
        name = station.get('Naam', idx)
        print(f"[{i+1}/{len(stations)}] {name}")

        result = download_station(station, START_DATE, END_DATE, OUTPUT_DIR)
        if result:
            success += 1
        else:
            failed += 1

        # Kleine Pause zwischen Downloads um die API nicht zu überlasten
        if i < len(stations) - 1:
            time.sleep(1)

    print(f"\n{'='*60}")
    print(f"ERGEBNIS")
    print(f"{'='*60}")
    print(f"Erfolgreich: {success}")
    print(f"Fehlgeschlagen: {failed}")
    print(f"Gesamt: {len(stations)}")


if __name__ == '__main__':
    main()
