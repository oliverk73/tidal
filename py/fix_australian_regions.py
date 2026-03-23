#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv

def determine_region_from_coordinates(original_name, lat, lon, geonames_name):
    """
    Bestimmt die korrekte Region basierend auf Koordinaten und Namen.
    """
    # Coral Sea Islands Territory
    if 'Coral Sea' in original_name or geonames_name == 'Coral Sea Islands':
        return 'Coral Sea Islands Territory'

    # Northern Territory (129-138°E, 10-26°S)
    elif 129 <= lon <= 138 and -26 <= lat <= -10:
        return 'Northern Territory'

    # Queensland (138-154°E, 10-29°S)
    elif 138 <= lon <= 154 and -29 <= lat <= -10:
        return 'Queensland'

    # Western Australia (113-129°E, 13-35°S)
    elif 113 <= lon <= 129 and -35 <= lat <= -13:
        return 'Western Australia'

    # South Australia (129-141°E, 26-38°S)
    elif 129 <= lon <= 141 and -38 <= lat <= -26:
        return 'South Australia'

    # Christmas Island
    elif geonames_name == 'Christmas Island' or 'Christmas Island' in original_name:
        return 'Christmas Island'

    # Cocos (Keeling) Islands
    elif 'Cocos' in original_name:
        return 'Cocos (Keeling) Islands'

    # Norfolk Island
    elif 'Norfolk' in original_name:
        return 'Norfolk Island'

    # Heard Island and McDonald Islands (Antarctica)
    elif 'Heard' in original_name or lat < -50:
        return 'Heard Island and McDonald Islands'

    # Ashmore and Cartier Islands
    elif geonames_name == 'Ashmore and Cartier Islands':
        return 'Ashmore and Cartier Islands'

    return ''

def main():
    input_file = '/home/oliver/harmonics_working/stations_verification_complete.csv'
    output_file = '/home/oliver/harmonics_working/stations_verification_complete.csv'

    # Liste der zu korrigierenden Stationen
    stations_to_fix = [
        'Robe (offshore), Australia',
        'Cato Island, Coral Sea',
        'East Diamond It., Coral Sea',
        'Flinders Reef, Coral Sea',
        'Kirkcaldie Reef, Torres Strait',
        'Marion Reef, Coral Sea',
        'Mellish Reef, Coral Sea',
        'Pith Reef, Australia',
        'Rib Reef, Australia',
        'Unnamed Reef No. 1, Australia',
        'Unnamed Reef No. 2, Australia',
        'Willis Island, Coral Sea',
        'Cape Croker, Australia',
        'Cape Don, Australia',
        'Cape Grey, Australia',
        'Cape Hotham, Australia',
        'Centre Island, Australia',
        'Daly River, Australia',
        'Darwin, Australia',
        'Entrance Island, Australia',
        'Gove Harbour, Australia',
        'Guluwuru Island, Australia',
        'Hopeful Bay, Australia',
        'Jensen Bay, Australia',
        'Mallison Island, Australia',
        'Milner Bay, Australia',
        'North Goulburn Island, Australia',
        'Nw Crocodile Island, Australia',
        'Pearce Point, Australia',
        'Port Keats, Australia',
        'Port Langdon, Australia',
        'Rose River, Australia',
        'Snake Bay, Australia',
        'St. Asaph Bay, Australia',
        'Tapa Bay, Australia',
        'Turtle Islet, Australia',
        'Turtle Point, Australia',
        'Two Hills Bay, Australia',
        'Yabooma Island, Australia',
        'Ashmore Reef, Australia',
        'Heard Island, Antarctica',
        'Christmas Island, Australia',
        'Port Refuge, Cocos Islands',
        'Norfolk Island, Tasman Sea'
    ]

    print("📖 Korrigiere australische Regionen...\n")

    rows = []
    fixed_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            if row['Original_Name'] in stations_to_fix:
                lat = float(row['Original_Lat'])
                lon = float(row['Original_Lon'])
                geonames_name = row.get('GeoNames_Name', '')

                # Bestimme korrekte Region
                correct_region = determine_region_from_coordinates(
                    row['Original_Name'], lat, lon, geonames_name
                )

                if correct_region:
                    old_region = row.get('GeoNames_Region', '')
                    row['GeoNames_Region'] = correct_region

                    # Setze auch GeoNames_Country auf Australia (außer Antarctica)
                    if 'Antarctica' not in row['Original_Name'] and 'Heard Island' not in correct_region:
                        row['GeoNames_Country'] = 'Australia'

                    fixed_count += 1
                    print(f"✓ {row['Original_Name']:45s} → {correct_region}")

            rows.append(row)

    # Schreibe aktualisierte CSV
    print(f"\n💾 Schreibe aktualisierte CSV...")
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {fixed_count} Regionen korrigiert")
    print(f"✅ Datei aktualisiert: {output_file}")

if __name__ == '__main__':
    main()
