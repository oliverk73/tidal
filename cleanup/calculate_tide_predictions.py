#!/usr/bin/env python3
"""
Berechnet Tidenvorhersagen für alle Matches und schreibt sie in eine CSV-Datei.
"""

import csv
import subprocess
import re
from datetime import datetime

def get_tide_predictions(station_name: str, date: str = "2026-01-03") -> dict:
    """
    Ruft tide auf und parst die Hoch-/Niedrigwasser-Zeiten.
    """
    try:
        cmd = [
            'tide', '-l', station_name,
            '-b', f'{date} 00:00',
            '-e', f'{date} 23:59',
            '-m', 'p'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout

        # Parse die Tiden (nur High/Low Tide Zeilen)
        tides = []
        unit = 'm'  # Default

        for line in output.split('\n'):
            # Suche nach "High Tide" oder "Low Tide" Zeilen
            if 'High Tide' in line or 'Low Tide' in line:
                # Format: "2026-01-03  6:00 AM GMT  10.63 meters  High Tide"
                match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)\s+\w+\s+([\d.]+)\s+(meters|feet)', line)
                if match:
                    time_str = match.group(1)
                    water_level = float(match.group(2))
                    unit_str = match.group(3)
                    unit = 'm' if unit_str == 'meters' else 'f'

                    # Konvertiere zu 24-Stunden-Format
                    try:
                        time_obj = datetime.strptime(time_str.strip(), '%I:%M %p')
                        time_24h = time_obj.strftime('%H:%M')
                    except:
                        time_24h = time_str

                    tides.append((time_24h, water_level))

        return {'tides': tides, 'unit': unit}

    except Exception as e:
        print(f"  Fehler bei {station_name}: {e}")
        return {'tides': [], 'unit': 'm'}


def read_matches_csv(filepath: str) -> list:
    """
    Liest die Matches-CSV und gibt eine Liste von Stationen zurück.
    """
    stations = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # PLV Station
            stations.append({
                'source': 'harmonics_pierre_lavergne_v10_no_dupes4',
                'name': row['Name_PLV'],
                'timezone': row['Timezone_PLV'],
                'lat': row['Lat_PLV'],
                'lon': row['Lon_PLV'],
                'constants': row['Constants_PLV']
            })

            # OLD Stationen (kann mehrere geben)
            i = 1
            while f'Name_OLD_{i}' in row and row[f'Name_OLD_{i}']:
                stations.append({
                    'source': 'harmonics_old_no_us_no_dupes3',
                    'name': row[f'Name_OLD_{i}'],
                    'timezone': row[f'Timezone_OLD_{i}'],
                    'lat': row[f'Lat_OLD_{i}'],
                    'lon': row[f'Lon_OLD_{i}'],
                    'constants': row[f'Constants_OLD_{i}']
                })
                i += 1

    return stations


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 calculate_tide_predictions.py <plv|old>")
        print("  plv = Berechne Vorhersagen für Pierre Lavergne Stationen")
        print("  old = Berechne Vorhersagen für Harmonics Old Stationen")
        sys.exit(1)

    mode = sys.argv[1]
    matches_csv = 'harmonics_station_matches_pierre_lavergne_v10_harmonics_old.csv'
    output_csv = 'tide_predictions_comparison.csv'

    print(f"Lese Matches aus {matches_csv}...")
    all_stations = read_matches_csv(matches_csv)

    # Filtere nach Modus
    if mode == 'plv':
        stations = [s for s in all_stations if s['source'] == 'harmonics_pierre_lavergne_v10_no_dupes4']
        print(f"Berechne Vorhersagen für {len(stations)} PLV-Stationen...")
    elif mode == 'old':
        stations = [s for s in all_stations if s['source'] == 'harmonics_old_no_us_no_dupes3']
        print(f"Berechne Vorhersagen für {len(stations)} OLD-Stationen...")
    else:
        print(f"Unbekannter Modus: {mode}")
        sys.exit(1)

    # Dedupliziere Stationen (gleicher Name kann mehrfach vorkommen)
    seen = set()
    unique_stations = []
    for s in stations:
        if s['name'] not in seen:
            seen.add(s['name'])
            unique_stations.append(s)

    print(f"  {len(unique_stations)} einzigartige Stationen")

    # Berechne Vorhersagen
    results = []
    for i, station in enumerate(unique_stations):
        print(f"  [{i+1}/{len(unique_stations)}] {station['name'][:50]}...")
        preds = get_tide_predictions(station['name'])

        # Ermittle Einheit aus dem Stationsnamen oder Tide-Output
        unit = preds['unit']
        if '[feet]' in station['name'] or '(feet)' in station['name']:
            unit = 'f'

        result = {
            'source': station['source'],
            'name': station['name'],
            'timezone': station['timezone'],
            'lat': station['lat'],
            'lon': station['lon'],
            'constants': station['constants'],
            'unit': unit
        }

        # Füge bis zu 4 Tiden hinzu
        for j in range(4):
            if j < len(preds['tides']):
                result[f'time_{j+1}'] = preds['tides'][j][0]
                result[f'level_{j+1}'] = str(preds['tides'][j][1]).replace('.', ',')
            else:
                result[f'time_{j+1}'] = ''
                result[f'level_{j+1}'] = ''

        results.append(result)

    # Schreibe/Append CSV
    file_exists = False
    try:
        with open(output_csv, 'r') as f:
            file_exists = True
    except:
        pass

    write_mode = 'a' if file_exists and mode == 'old' else 'w'

    print(f"\nSchreibe {output_csv} (Modus: {write_mode})...")
    with open(output_csv, write_mode, newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        if write_mode == 'w':
            writer.writerow([
                'Quelldatei', 'Name', 'Zeitzone', 'Breitengrad', 'Laengengrad',
                'Harmonic_Constants', 'Einheit',
                'Zeit_1', 'Wasserstand_1', 'Zeit_2', 'Wasserstand_2',
                'Zeit_3', 'Wasserstand_3', 'Zeit_4', 'Wasserstand_4'
            ])

        for r in results:
            writer.writerow([
                r['source'], r['name'], r['timezone'], r['lat'], r['lon'],
                r['constants'], r['unit'],
                r['time_1'], r['level_1'], r['time_2'], r['level_2'],
                r['time_3'], r['level_3'], r['time_4'], r['level_4']
            ])

    print(f"Fertig! {len(results)} Vorhersagen geschrieben.")


if __name__ == '__main__':
    main()
