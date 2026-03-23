#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

def parse_harmonics_file(filename: str) -> list:
    """
    Extrahiert alle Tidenstationen aus der harmonics-Datei.
    """
    stations = []

    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Suche nach !longitude:
        if line.startswith('# !longitude:'):
            lon_match = re.search(r'!longitude:\s*([-\d.]+)', line)
            if lon_match and i + 1 < len(lines):
                longitude = float(lon_match.group(1))

                # Nächste Zeile sollte !latitude: sein
                i += 1
                lat_line = lines[i].strip()
                lat_match = re.search(r'!latitude:\s*([-\d.]+)', lat_line)

                if lat_match and i + 1 < len(lines):
                    latitude = float(lat_match.group(1))

                    # Nächste Zeile ist der Stationsname
                    i += 1
                    station_name = lines[i].strip()

                    # Nächste Zeile ist die Zeitzone
                    i += 1
                    timezone_line = lines[i].strip()
                    timezone_match = re.search(r':([A-Za-z/_]+)', timezone_line)
                    timezone = timezone_match.group(1) if timezone_match else ""

                    stations.append({
                        'original_name': station_name,
                        'latitude': latitude,
                        'longitude': longitude,
                        'timezone': timezone
                    })

        i += 1

    return stations

def main():
    input_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2.txt'
    output_file = '/home/oliver/harmonics_working/stations_extracted.csv'

    print("📖 Extrahiere Tidenstationen aus harmonics-Datei...")
    stations = parse_harmonics_file(input_file)
    print(f"✓ {len(stations)} Stationen gefunden\n")

    # Analysiere Probleme
    uppercase_count = 0
    no_accents_count = 0
    incomplete_count = 0

    for station in stations:
        name = station['original_name']

        # Prüfe auf Großschreibung
        if name == name.upper() and any(c.isalpha() for c in name):
            uppercase_count += 1

        # Prüfe auf fehlende Kommas (unvollständige Namen)
        parts = name.split(',')
        if len(parts) < 2:
            incomplete_count += 1

    print("📊 ANALYSE:")
    print(f"   Gesamt:                {len(stations)} Stationen")
    print(f"   Komplett Großbuchstaben: {uppercase_count}")
    print(f"   Unvollständige Namen:    {incomplete_count}")
    print()

    # Schreibe CSV
    print("💾 Schreibe CSV-Datei...")

    fieldnames = ['Original_Name', 'Original_Lat', 'Original_Lon', 'Original_Timezone']

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()

        for station in stations:
            writer.writerow({
                'Original_Name': station['original_name'],
                'Original_Lat': station['latitude'],
                'Original_Lon': station['longitude'],
                'Original_Timezone': station['timezone']
            })

    print(f"✅ CSV-Datei erstellt: {output_file}")
    print(f"   {len(stations)} Stationen exportiert")

    # Zeige Beispiele
    print("\n📝 Beispiele:")
    for i, station in enumerate(stations[:10], 1):
        print(f"   {i}. {station['original_name'][:50]:50s} | {station['timezone']:20s} | {station['latitude']:.4f}, {station['longitude']:.4f}")

if __name__ == '__main__':
    main()
