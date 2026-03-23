#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

# Mapping für Ländernamen in Landessprache (lateinisch)
COUNTRY_NAMES_LOCAL = {
    'Brazil': 'Brasil',
    'Spain': 'España',
    'Germany': 'Deutschland',
    'Netherlands': 'The Netherlands',
    'Portugal': 'Portugal',
    'France': 'France',
    'Italy': 'Italia',
    'Greece': 'Elláda',
    'Japan': '日本',
    'China': '中国',
    'South Korea': 'South Korea',
    'North Korea': 'North Korea',
}

# Korrekturen für bekannte "not_found" Stationen
MANUAL_CORRECTIONS = {
    'La Coruna, Spain': {
        'Corrected_Name': 'A Coruña',
        'Corrected_Region': 'Galicia',
        'Corrected_Country': 'España',
        'Confidence': 'high'
    },
    'Marn, Spain': {
        'Corrected_Name': 'Marín',
        'Corrected_Region': 'Galicia',
        'Corrected_Country': 'España',
        'Confidence': 'high'
    },
    'Vigo, Spain': {
        'Corrected_Name': 'Vigo',
        'Corrected_Region': 'Galicia',
        'Corrected_Country': 'España',
        'Confidence': 'high'
    },
    'Qubec City, Qubec': {
        'Corrected_Name': 'Québec City',
        'Corrected_Region': 'Québec',
        'Corrected_Country': 'Canada',
        'Confidence': 'high'
    },
    'Sept-les, Qubec': {
        'Corrected_Name': 'Sept-Îles',
        'Corrected_Region': 'Québec',
        'Corrected_Country': 'Canada',
        'Confidence': 'high'
    },
    'Pointe--Pitre, Guadeloupe (2)': {
        'Corrected_Name': 'Pointe-à-Pitre',
        'Corrected_Region': 'Guadeloupe',
        'Corrected_Country': 'France',
        'Confidence': 'high'
    },
    'Venezia, Italy (2)': {
        'Corrected_Name': 'Venezia',
        'Corrected_Region': 'Veneto',
        'Corrected_Country': 'Italia',
        'Confidence': 'high'
    },
    'Viana do Castelo, Portugal': {
        'Corrected_Name': 'Viana do Castelo',
        'Corrected_Region': 'Norte',
        'Corrected_Country': 'Portugal',
        'Confidence': 'high'
    },
    'Vila Real de Santo Antonio, Portugal': {
        'Corrected_Name': 'Vila Real de Santo António',
        'Corrected_Region': 'Faro',
        'Corrected_Country': 'Portugal',
        'Confidence': 'high'
    },
    'Valparaiso, Chile': {
        'Corrected_Name': 'Valparaíso',
        'Corrected_Region': 'Valparaíso',
        'Corrected_Country': 'Chile',
        'Confidence': 'high'
    },
    'Swatow, China': {
        'Corrected_Name': 'Shantou',
        'Corrected_Region': 'Guangdong',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
    'Xiamen, China': {
        'Corrected_Name': 'Xiamen',
        'Corrected_Region': 'Fujian',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
    'Yingkou, China': {
        'Corrected_Name': 'Yingkou',
        'Corrected_Region': 'Liaoning',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
    'Wei-Hai-Wei, China': {
        'Corrected_Name': 'Weihai',
        'Corrected_Region': 'Shandong',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
    'Pei-Hai, China': {
        'Corrected_Name': 'Beihai',
        'Corrected_Region': 'Guangxi',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
    'Makung, China': {
        'Corrected_Name': 'Magong',
        'Corrected_Region': 'Penghu',
        'Corrected_Country': 'Taiwan',
        'Confidence': 'high'
    },
    'Zhanjiang, China': {
        'Corrected_Name': 'Zhanjiang',
        'Corrected_Region': 'Guangdong',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
    'Wangjia Wan, China': {
        'Corrected_Name': 'Wangjiawan',
        'Corrected_Region': 'Shandong',
        'Corrected_Country': 'China',
        'Confidence': 'high'
    },
}


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
    output_file = '/home/oliver/harmonics_working/station_name_corrections_updated.csv'

    print("🔄 Lade CSV-Datei...")
    rows = []

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
                print(f"✓ Ergänzt: {original_name} → {row['Full_Corrected_Name']}")

            # Fall 2: not_found Status - versuche manuelle Korrekturen anzuwenden
            elif status == 'not_found':
                if original_name in MANUAL_CORRECTIONS:
                    correction = MANUAL_CORRECTIONS[original_name]
                    row['Corrected_Name'] = correction['Corrected_Name']
                    row['Corrected_Region'] = correction['Corrected_Region']
                    row['Corrected_Country'] = correction['Corrected_Country']
                    row['Confidence'] = correction['Confidence']
                    row['Status'] = 'found'
                    row['Full_Corrected_Name'] = generate_full_corrected_name(row)
                    print(f"✓ Korrigiert: {original_name} → {row['Full_Corrected_Name']}")

            rows.append(row)

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
    print("="*80)

    # Liste der noch nicht gefundenen Stationen
    if not_found > 0:
        print("\n⚠️  Noch nicht gefundene Stationen:")
        print("="*80)
        for i, row in enumerate([r for r in rows if r['Status'] == 'not_found'][:30], 1):
            print(f"{i}. {row['Original_Name']}")
            print(f"   Koordinaten: {row['Original_Lat']}, {row['Original_Lon']}")
            print(f"   Timezone: {row['Original_Timezone']}\n")


if __name__ == '__main__':
    main()
