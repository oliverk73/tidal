#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import requests
import time
from typing import Optional, Dict

# GeoNames API username
GEONAMES_USERNAME = "oliver_k73"

def parse_harmonics_file(filename: str) -> list:
    """
    Extrahiert alle Tidenstationen aus der harmonics-Datei.

    Returns:
        Liste von Dicts mit: name, latitude, longitude, timezone
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

def query_geonames(lat: float, lon: float, username: str = GEONAMES_USERNAME) -> Optional[Dict]:
    """
    Fragt GeoNames API nach dem nächstgelegenen Ort.

    API Dokumentation: http://www.geonames.org/export/web-services.html
    """
    try:
        # findNearbyPlaceName API
        url = f"http://api.geonames.org/findNearbyPlaceNameJSON"
        params = {
            'lat': lat,
            'lng': lon,
            'username': username,
            'style': 'FULL',
            'maxRows': 1
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()

            # Check for API errors
            if 'status' in data:
                # GeoNames returned an error
                return None

            if 'geonames' in data and len(data['geonames']) > 0:
                place = data['geonames'][0]

                # Timezone ist entweder direkt im place dict oder in einem separaten dict
                tz = ''
                if 'timezone' in place:
                    if isinstance(place['timezone'], dict):
                        tz = place['timezone'].get('timeZoneId', '')
                    else:
                        tz = place['timezone']

                return {
                    'name': place.get('name', ''),
                    'toponymName': place.get('toponymName', ''),
                    'adminName1': place.get('adminName1', ''),  # Region/State
                    'countryName': place.get('countryName', ''),
                    'distance': place.get('distance', 0),
                    'timezone': tz
                }

        # Rate limiting: max 1 request/second für kostenlosen Account
        time.sleep(1.1)

    except Exception as e:
        pass  # Silent fail, return None

    return None

def main():
    input_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2.txt'
    output_file = '/home/oliver/harmonics_working/stations_verification.csv'

    print("📖 Extrahiere Tidenstationen aus harmonics-Datei...")
    stations = parse_harmonics_file(input_file)
    print(f"✓ {len(stations)} Stationen gefunden\n")

    print("🌍 Verifiziere Stationen über GeoNames API...")
    print("⚠️  WICHTIG: GeoNames benötigt kostenlosen Account (geonames.org/login)")
    print("⚠️  Bitte GEONAMES_USERNAME im Script anpassen!\n")

    # CSV Header
    fieldnames = [
        'Original_Name', 'Original_Lat', 'Original_Lon', 'Original_Timezone',
        'GeoNames_Name', 'GeoNames_Region', 'GeoNames_Country',
        'GeoNames_Distance_km', 'GeoNames_Timezone',
        'Corrected_Name', 'Corrected_Region', 'Corrected_Country',
        'Status', 'Notes'
    ]

    verified_count = 0
    failed_count = 0

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()

        for idx, station in enumerate(stations, 1):
            # Zeige Fortschritt
            if idx % 100 == 0:
                print(f"  Verarbeitet: {idx}/{len(stations)} ({verified_count} verifiziert, {failed_count} fehlgeschlagen)")

            # Frage GeoNames API
            geonames_data = query_geonames(station['latitude'], station['longitude'])

            row = {
                'Original_Name': station['original_name'],
                'Original_Lat': station['latitude'],
                'Original_Lon': station['longitude'],
                'Original_Timezone': station['timezone'],
            }

            if geonames_data:
                distance = float(geonames_data.get('distance', 999))

                row.update({
                    'GeoNames_Name': geonames_data['name'],
                    'GeoNames_Region': geonames_data['adminName1'],
                    'GeoNames_Country': geonames_data['countryName'],
                    'GeoNames_Distance_km': round(distance, 2),
                    'GeoNames_Timezone': geonames_data['timezone'],
                    'Status': 'verified',
                })

                # Vorschlag für korrigierten Namen
                # Nutze GeoNames Name wenn Distanz < 10km
                if distance < 10:
                    row['Corrected_Name'] = geonames_data['name']
                    row['Corrected_Region'] = geonames_data['adminName1']
                    row['Corrected_Country'] = geonames_data['countryName']
                else:
                    row['Corrected_Name'] = station['original_name'].split(',')[0].strip()
                    row['Notes'] = f"Distanz zu groß: {distance}km"

                verified_count += 1

                # Zeige erste paar Ergebnisse
                if idx <= 10:
                    print(f"  ✓ {station['original_name'][:40]:40s} → {geonames_data['name']}")
            else:
                row.update({
                    'Status': 'failed',
                    'Notes': 'GeoNames API Fehler'
                })
                failed_count += 1

            writer.writerow(row)

    print(f"\n{'='*80}")
    print("📊 ZUSAMMENFASSUNG:")
    print(f"   Gesamt:      {len(stations)} Stationen")
    print(f"   Verifiziert: {verified_count}")
    print(f"   Fehlgeschlagen: {failed_count}")
    print(f"\n✅ CSV-Datei erstellt: {output_file}")
    print("="*80)
    print("\n💡 NÄCHSTE SCHRITTE:")
    print("   1. GeoNames Account erstellen (kostenlos): https://www.geonames.org/login")
    print("   2. Username im Script eintragen")
    print("   3. Script erneut ausführen für vollständige Verifizierung")

if __name__ == '__main__':
    main()
