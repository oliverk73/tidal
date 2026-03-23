#!/usr/bin/env python3
"""
Extrahiert Tidenstationen aus der Harmonics-Datei und berechnet Hoch-/Niedrigwasser für heute.
"""

import re
import csv
import subprocess

def parse_harmonics_file(filepath):
    """
    Parst eine Harmonics-Datei und gibt eine Liste von Stationen zurück.
    """
    stations = []

    with open(filepath, 'r', encoding='latin-1') as f:
        content = f.read()

    blocks = re.split(r'# BEGIN HOT COMMENTS\n', content)

    for block in blocks[1:]:
        station = {
            'name': None,
            'timezone': None,
            'longitude': None,
            'latitude': None,
            'harmonic_count': 0
        }

        lines = block.split('\n')

        i = 0
        while i < len(lines) and lines[i].startswith('#'):
            line = lines[i]
            if '!longitude:' in line:
                match = re.search(r'!longitude:\s*([-\d.]+)', line)
                if match:
                    station['longitude'] = float(match.group(1))
            elif '!latitude:' in line:
                match = re.search(r'!latitude:\s*([-\d.]+)', line)
                if match:
                    station['latitude'] = float(match.group(1))
            i += 1

        if i < len(lines) and lines[i].strip():
            station['name'] = lines[i].strip()
            i += 1

        if i < len(lines) and lines[i].strip():
            station['timezone'] = lines[i].strip()
            i += 1

        if i < len(lines) and ('meters' in lines[i] or 'feet' in lines[i] or 'knots' in lines[i]):
            i += 1

        harmonic_count = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('#'):
                if '# BEGIN HOT COMMENTS' in line or line == '':
                    break
                i += 1
                continue

            if line and not line.startswith('x '):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        amp = float(parts[1])
                        if amp != 0:
                            harmonic_count += 1
                    except ValueError:
                        pass
            i += 1

        station['harmonic_count'] = harmonic_count

        if station['name']:
            stations.append(station)

    return stations

def get_tides_for_station(station_name):
    """
    Ruft tide-Befehl auf und extrahiert Hoch-/Niedrigwasser-Zeiten und Wasserstände.
    Gibt Liste von (Zeit, Wasserstand, Typ) Tupeln zurück.
    """
    tides = []

    try:
        result = subprocess.run(
            ['tide', '-l', station_name, '-b', '2026-01-02 00:00', '-e', '2026-01-02 23:59'],
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout + result.stderr

        # Parse Zeilen mit High Tide oder Low Tide
        for line in output.split('\n'):
            if 'High Tide' in line or 'Low Tide' in line:
                # Format: 2026-01-02 12:02 AM GMT   6.44 meters  High Tide
                match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s+[AP]M\s+\w+)\s+([\d.]+)\s+(\w+)\s+(High|Low)\s+Tide', line)
                if match:
                    time_str = match.group(1).strip()
                    water_level = match.group(2)
                    unit = match.group(3)
                    tide_type = match.group(4)
                    tides.append((time_str, f"{water_level} {unit}", tide_type))

    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        pass

    return tides

def main():
    input_file = '/home/oliver/harmonics_working/harmonics_pierre_lavergne_v10_no_dupes4.txt'
    output_csv = '/home/oliver/stations_with_tides.csv'

    print(f"Lese {input_file}...")
    stations = parse_harmonics_file(input_file)
    print(f"  -> {len(stations)} Stationen gefunden")

    print(f"\nBerechne Gezeiten und schreibe nach {output_csv}...")

    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')

        header = [
            'Name', 'Timezone', 'Longitude', 'Latitude', 'HarmonicCount',
            'Tide1_Time', 'Tide1_Level', 'Tide1_Type',
            'Tide2_Time', 'Tide2_Level', 'Tide2_Type',
            'Tide3_Time', 'Tide3_Level', 'Tide3_Type',
            'Tide4_Time', 'Tide4_Level', 'Tide4_Type'
        ]
        writer.writerow(header)

        for idx, station in enumerate(stations):
            print(f"  [{idx+1}/{len(stations)}] {station['name'][:50]}...", end='\r')

            # Überspringe Strömungsstationen
            if station['name'] and station['name'].rstrip().endswith('Current'):
                tides = []
            else:
                tides = get_tides_for_station(station['name'])

            row = [
                station['name'],
                station['timezone'],
                station['longitude'],
                station['latitude'],
                station['harmonic_count']
            ]

            # Füge bis zu 4 Gezeiten hinzu
            for i in range(4):
                if i < len(tides):
                    time_str, level, tide_type = tides[i]
                    row.extend([time_str, level, tide_type])
                else:
                    row.extend(['', '', ''])

            writer.writerow(row)

    print(f"\n\nFertig! Ergebnis gespeichert in: {output_csv}")

if __name__ == '__main__':
    main()
