#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv

def check_timezone_country_match(timezone, country):
    """Prüft, ob Zeitzone und Land zusammenpassen"""
    timezone_country_map = {
        'America/El_Salvador': 'El Salvador',
        'America/': 'Americas',
        'Europe/': 'Europe',
        'Asia/': 'Asia',
        'Africa/': 'Africa',
        'Pacific/': 'Pacific',
        'Atlantic/': 'Atlantic',
    }
    
    # Grundlegende Plausibilitätsprüfung
    if 'America/' in timezone and country in ['Poland', 'Russia', 'China', 'Japan', 'India']:
        return False
    if 'Europe/' in timezone and country in ['El Salvador', 'Brazil', 'Argentina', 'Mexico']:
        return False
    if 'Asia/' in timezone and country in ['El Salvador', 'Brazil', 'Argentina', 'United States']:
        return False
    
    return True

input_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'

print("🔍 Prüfe auf Geo-Koordinaten/Land Fehler...\n")

errors = []

with open(input_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    
    for row_num, row in enumerate(reader, start=2):
        timezone = row['Original_Timezone']
        country = row['Corrected_Country']
        original_name = row['Original_Name']
        
        if not check_timezone_country_match(timezone, country):
            errors.append({
                'line': row_num,
                'original': original_name,
                'timezone': timezone,
                'country': country,
                'lat': row['Original_Lat'],
                'lon': row['Original_Lon'],
                'corrected_name': row['Corrected_Name'],
                'full_name': row['Full_Corrected_Name']
            })

if errors:
    print(f"❌ {len(errors)} potenzielle Fehler gefunden:\n")
    for err in errors:
        print(f"Zeile {err['line']}: {err['original']}")
        print(f"   Koordinaten: {err['lat']}, {err['lon']}")
        print(f"   Zeitzone: {err['timezone']}")
        print(f"   Zugeordnetes Land: {err['country']} ⚠️")
        print(f"   Korrigiert zu: {err['full_name']}")
        print()
else:
    print("✓ Keine offensichtlichen Geo-Fehler gefunden")

print(f"\n{'='*80}")
print(f"Gesamt geprüft: {row_num-1} Stationen")
print(f"Fehler gefunden: {len(errors)}")
