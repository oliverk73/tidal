#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import requests
import time
from typing import Optional, Dict

def query_nominatim(lat: float, lon: float) -> Optional[Dict]:
    """
    Fragt Nominatim (OpenStreetMap) nach dem Ort an den Koordinaten.

    API Dokumentation: https://nominatim.org/release-docs/latest/api/Reverse/
    Usage Policy: Max 1 request/second
    """
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 10,  # City/town level
        }

        headers = {
            'User-Agent': 'TideStationVerifier/1.0'
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if 'error' not in data:
                address = data.get('address', {})

                # Versuche den besten Namen zu finden
                name = (address.get('city') or
                       address.get('town') or
                       address.get('village') or
                       address.get('hamlet') or
                       address.get('suburb') or
                       data.get('name', ''))

                # Region/State
                region = (address.get('state') or
                         address.get('province') or
                         address.get('region') or
                         address.get('county', ''))

                country = address.get('country', '')

                return {
                    'name': name,
                    'region': region,
                    'country': country,
                    'display_name': data.get('display_name', ''),
                }

        # Rate limiting: max 1 request/second
        time.sleep(1.1)

    except Exception as e:
        print(f"  ⚠️  Nominatim Fehler: {e}")
        time.sleep(1.1)

    return None

def main():
    input_file = '/home/oliver/harmonics_working/stations_verification.csv'
    output_file = '/home/oliver/harmonics_working/stations_verification_complete.csv'

    print("📖 Lese fehlgeschlagene Stationen...")

    rows = []
    failed_rows = []

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            rows.append(row)
            if row['Status'] == 'failed':
                failed_rows.append(row)

    print(f"✓ {len(rows)} Stationen geladen")
    print(f"✓ {len(failed_rows)} fehlgeschlagene Stationen gefunden\n")

    print("🌍 Verifiziere fehlgeschlagene Stationen über Nominatim (OpenStreetMap)...")
    print("⏱️  Rate Limit: 1 Request/Sekunde")
    print(f"⏱️  Geschätzte Dauer: ~{len(failed_rows) // 60} Minuten\n")

    verified_count = 0
    still_failed = 0

    for idx, row in enumerate(rows, 1):
        # Nur fehlgeschlagene Stationen neu verifizieren
        if row['Status'] != 'failed':
            continue

        if idx % 100 == 0:
            print(f"  Verarbeitet: {idx}/{len(rows)} ({verified_count} neu verifiziert, {still_failed} weiterhin fehlgeschlagen)")

        lat = float(row['Original_Lat'])
        lon = float(row['Original_Lon'])

        nominatim_data = query_nominatim(lat, lon)

        if nominatim_data and nominatim_data['name']:
            row['GeoNames_Name'] = nominatim_data['name']
            row['GeoNames_Region'] = nominatim_data['region']
            row['GeoNames_Country'] = nominatim_data['country']
            row['GeoNames_Distance_km'] = ''
            row['GeoNames_Timezone'] = ''
            row['Status'] = 'verified_nominatim'

            # Vorschlag für korrigierten Namen
            row['Corrected_Name'] = nominatim_data['name']
            row['Corrected_Region'] = nominatim_data['region']
            row['Corrected_Country'] = nominatim_data['country']
            row['Notes'] = 'Verifiziert via Nominatim/OSM'

            verified_count += 1

            # Zeige erste paar Ergebnisse
            if verified_count <= 15:
                orig_name = row['Original_Name'][:40]
                new_name = nominatim_data['name']
                print(f"  ✓ {orig_name:40s} → {new_name}")
        else:
            still_failed += 1

    print(f"\n{'='*80}")
    print("📊 ERGEBNIS:")
    print(f"   Gesamt:              {len(rows)} Stationen")
    print(f"   Bereits verifiziert: {len(rows) - len(failed_rows)}")
    print(f"   Neu verifiziert:     {verified_count}")
    print(f"   Weiterhin failed:    {still_failed}")
    print(f"   Erfolgsquote:        {(len(rows) - still_failed) / len(rows) * 100:.1f}%")

    # Schreibe aktualisierte CSV
    print(f"\n💾 Schreibe aktualisierte CSV...")
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Datei geschrieben: {output_file}")
    print("="*80)

if __name__ == '__main__':
    main()
