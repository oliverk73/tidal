#!/usr/bin/env python3
"""
Fix reference station names in the mapped CSV to match xtide harmonics names.
"""

import csv

# Mapping from old names to xtide-compatible names
REFERENCE_MAPPINGS = {
    # Philippines - "Philippines" -> "Pilipinas"
    "Cebu, Philippines": "Cebu, Pilipinas",
    "Manila, Philippines": "Manila, Pilipinas",
    "Legaspi, Philippines": "Legaspi, Pilipinas",
    "Davao, Philippines": "Davao, Pilipinas",
    "Jolo, Philippines": "Jolo, Pilipinas",
    "San Fernando, Philippines": "San Fernando, Pilipinas",

    # Korea - Pusan is old name for Busan
    "Pusan, South Korea": "Yeong-do, Busan, South Korea",

    # Panama - encoding issue with ó
    "Cristóbal, Panama": "Cristbal, Panama",

    # Vietnam - "Vietnam" -> "Viet Nam"
    "Do Son, Vietnam": "Do Son, Viet Nam",
    "Vung Tau, Vietnam": "Vung Tau, Viet Nam",

    # Scotland - needs full location name
    "Ullapool, Scotland": "Ullapool (Harbour), Scotland, United Kingdom",

    # Iceland - "Iceland" -> "Ísland"
    "Reykjavik, Iceland": "Reykjavik (Container Terminal), Ísland",

    # Italy - "Italy" -> "Italia"
    "Venezia, Italy": "Venezia, Italia",

    # Norway - "Norway" -> "Norge"
    "Bergen, Norway": "Bergen, Norge",
    "Narvik, Norway": "Narvik, Norge",

    # England - needs full location name
    "Dover, England": "Dover (Prince of Wales Pier), England, United Kingdom",
    "Immingham, England": "Immingham (Docks), England, United Kingdom",
    "Sheerness, England": "Sheerness (Garrison Point), England, United Kingdom",

    # France - needs full location name
    "Brest, France": "Brest (Estuaire Penfeld), France",

    # Thailand - needs full location name
    "Bangkok, Thailand": "Bangkok Bar (Samut Prakan), Thailand",

    # Alaska - needs full location name
    "Sitka, Alaska": "Sitka, Baronof Island, Sitka Sound, Alaska",

    # California - needs full location name
    "San Diego, California": "San Diego, San Diego Bay, California",

    # Mozambique - "Mozambique" -> "Moçambique"
    "Beira, Mozambique": "Beira, Moçambique",

    # Azores/Portugal - needs proper accents
    "Ponta Delgada, Sao Miguel, Azores": "Ponta Delgada, São Miguel, Açores, Portugal",

    # Quebec - different format
    "Québec (Lauzon), Québec": "Lauzon, Québec, Canada",

    # Belgium - "Belgium" -> "België"
    "Antwerpen, Belgium": "Antwerpen, België",

    # Bahrain - needs full name
    "Mina Salman, Bahrain": "Mina Salman, Manamah, Bahrain",

    # Venezuela - slight spelling difference
    "Malecon, Venezuela": "Malecón, Isla de Zapara, Venezuela",
}

def fix_reference_names(input_file, output_file):
    """Read CSV, fix reference names, write output."""

    stations = []
    with open(input_file, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames
        for row in reader:
            stations.append(row)

    print(f"Loaded {len(stations)} stations")

    # Apply mappings
    fixed_count = 0
    for station in stations:
        ref_name = station.get('ref_name', '')
        if ref_name in REFERENCE_MAPPINGS:
            new_name = REFERENCE_MAPPINGS[ref_name]
            station['ref_name'] = new_name
            fixed_count += 1

    print(f"Fixed {fixed_count} reference station names")

    # Show mapping statistics
    print("\nMapping statistics:")
    for old_name, new_name in sorted(REFERENCE_MAPPINGS.items()):
        count = sum(1 for s in stations if s.get('ref_name') == new_name)
        if count > 0:
            print(f"  {old_name} -> {new_name}: {count} stations")

    # Write output
    with open(output_file, 'w', encoding='latin-1', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(stations)

    print(f"\nOutput written to: {output_file}")

if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/subordinate_stations_mapped.csv'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_mapped.csv'

    fix_reference_names(input_file, output_file)
