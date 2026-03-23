#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

# Mapping für Ländernamen in Landessprache (lateinisch, ISO 8859-1 kompatibel)
COUNTRY_NAMES_LOCAL = {
    'Brazil': 'Brasil',
    'Spain': 'España',
    'Germany': 'Deutschland',
    'Netherlands': 'The Netherlands',
    'Norway': 'Norge',
}


def load_corrections_mapping(mapping_file):
    """Lädt die Korrekturen aus der Mapping-Datei"""
    corrections = {}
    with open(mapping_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split('|')
                if len(parts) == 5:
                    original = parts[0]
                    corrections[original] = {
                        'name': parts[1],
                        'region': parts[2],
                        'country': parts[3],
                        'confidence': parts[4]
                    }
    return corrections


def generate_full_corrected_name(row):
    """Generiert den Full_Corrected_Name aus den vorhandenen Daten"""
    corrected_name = row['Corrected_Name'].strip()
    region = row['Corrected_Region'].strip()
    country = row['Corrected_Country'].strip()
    original_name = row['Original_Name'].strip()

    # Ländername in Landessprache konvertieren
    if country in COUNTRY_NAMES_LOCAL:
        country = COUNTRY_NAMES_LOCAL[country]

    # Prüfe, ob Original-Name eine Nummer hat (z.B. "(2)")
    suffix_match = re.search(r'\((\d+)\)$', original_name)
    suffix = f' ({suffix_match.group(1)})' if suffix_match else ''

    # Full_Corrected_Name zusammenbauen
    if region:
        full_name = f"{corrected_name}, {region}, {country}{suffix}"
    else:
        full_name = f"{corrected_name}, {country}{suffix}"

    return full_name


def main():
    input_file = '/home/oliver/harmonics_working/station_name_corrections.csv'
    mapping_file = '/home/oliver/py/station_corrections_mapping.txt'
    output_file = '/home/oliver/harmonics_working/station_name_corrections_updated.csv'

    print("🔄 Lade Korrekturen-Mapping...")
    corrections_mapping = load_corrections_mapping(mapping_file)
    print(f"   {len(corrections_mapping)} Korrekturen geladen")

    print("\n🔄 Lade CSV-Datei...")
    rows = []
    corrections_count = 0
    supplements_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            status = row.get('Status', '').strip()
            full_name = row.get('Full_Corrected_Name', '').strip()
            original_name = row.get('Original_Name', '').strip()

            # Fall 1: found Status, aber leerer Full_Corrected_Name
            if status == 'found' and not full_name:
                row['Full_Corrected_Name'] = generate_full_corrected_name(row)
                supplements_count += 1
                if supplements_count <= 5:
                    print(f"✓ Ergänzt: {original_name[:50]}")

            # Fall 2: not_found Status - versuche Korrekturen anzuwenden
            elif status == 'not_found':
                if original_name in corrections_mapping:
                    correction = corrections_mapping[original_name]
                    row['Corrected_Name'] = correction['name']
                    row['Corrected_Region'] = correction['region']
                    row['Corrected_Country'] = correction['country']
                    row['Confidence'] = correction['confidence']
                    row['Status'] = 'found'
                    row['Full_Corrected_Name'] = generate_full_corrected_name(row)
                    corrections_count += 1
                    print(f"✓ Korrigiert: {original_name} → {row['Corrected_Name']}")

            rows.append(row)

    if supplements_count > 5:
        print(f"... und {supplements_count - 5} weitere Ergänzungen")

    print(f"\n💾 Schreibe korrigierte Daten nach {output_file}...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    # Statistik
    found_with_full_name = sum(1 for r in rows if r['Status'] == 'found' and r['Full_Corrected_Name'])
    not_found = sum(1 for r in rows if r['Status'] == 'not_found')

    print("\n" + "="*80)
    print("📊 Statistik:")
    print(f"   Gesamt: {len(rows)} Stationen")
    print(f"   ✓ Gefunden mit Full_Corrected_Name: {found_with_full_name}")
    print(f"   ❌ Noch nicht gefunden: {not_found}")
    print(f"   📝 In dieser Sitzung ergänzt: {supplements_count}")
    print(f"   🔧 In dieser Sitzung korrigiert: {corrections_count}")
    print("="*80)

    # Liste der noch nicht gefundenen Stationen
    if not_found > 0:
        print(f"\n⚠️  Noch nicht gefundene Stationen ({not_found}):")
        print("="*80)
        remaining = [r for r in rows if r['Status'] == 'not_found']
        for i, row in enumerate(remaining, 1):
            coords = f"{row['Original_Lat']}, {row['Original_Lon']}"
            print(f"{i:3d}. {row['Original_Name'][:60]:<60} ({coords})")


if __name__ == '__main__':
    main()
