#!/usr/bin/env python3
import csv
import os

# Paths
csv_file = '/home/oliver/harmonics_working/Geokoordinaten-Korrektur.csv'
harmonics_dir = '/home/oliver/harmonics_edited'

# Read CSV
encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
used_encoding = None
csv_data = []

for encoding in encodings:
    try:
        with open(csv_file, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Tidenstation']:
                    csv_data.append(row)
        used_encoding = encoding
        print(f"Successfully read CSV with {encoding} encoding")
        break
    except (UnicodeDecodeError, KeyError) as e:
        csv_data = []
        continue

print(f"Loaded {len(csv_data)} stations from CSV")

# Get harmonics files
harmonics_files = [
    'harmonics-2004-06-14_no_us_no_dupes2.txt',
    'harmonics-dwf-20241229-free.txt',
    'harmonics_old_no_us_no_dupes3.txt',
    'harmonics-dwf-20100529-nonfree_mod.txt',
    'harmonics-dwf-20070318_no_us_no_dupes.txt',
    'harmonics_pierre_lavergne_v10_no_dupes4.txt',
    'harmonics_pierre_lavergne_v9_europe_no_us_no_dupes5.txt',
    'harmonics_pierre_lavergne_v9_europe_no_us_no_dupes_final.txt'
]

# Search for "Nicht gefunden" stations
total_searched = 0
found_matches = 0

for row in csv_data:
    if row.get('Status') == 'Nicht gefunden':
        station_name = row['Tidenstation']
        total_searched += 1

        print(f"\nSearching for: {station_name}")

        # Get the main part of the name (before first comma)
        search_parts = station_name.split(',')
        main_name = search_parts[0].strip()

        # Clear existing matches
        for i in range(1, 5):
            row[f'Treffer_{i}'] = ''
            row[f'Datei_{i}'] = ''
            row[f'Lat_{i}'] = ''
            row[f'Lon_{i}'] = ''

        matches = []

        for harmonics_file in harmonics_files:
            file_path = os.path.join(harmonics_dir, harmonics_file)
            if not os.path.exists(file_path):
                continue

            try:
                # Read with ISO 8859-1 for harmonics files
                with open(file_path, 'r', encoding='iso-8859-1') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    if not line.startswith('#') and not line.startswith('x '):
                        stripped = line.strip()

                        if stripped and not stripped.startswith('+') and not stripped.startswith('-') and 'meters' not in stripped and 'feet' not in stripped and 'knots' not in stripped:
                            # Check for match
                            is_match = False

                            # Try full name first
                            if station_name.lower() in stripped.lower():
                                is_match = True
                            # Try main part of name
                            elif main_name.lower() in stripped.lower() and len(main_name) > 3:
                                is_match = True

                            if is_match:
                                # Look for coordinates
                                lat_line = None
                                lon_line = None
                                for j in range(max(0, i-5), i):
                                    if lines[j].startswith('# !latitude:'):
                                        lat_line = j
                                    if lines[j].startswith('# !longitude:'):
                                        lon_line = j

                                if lat_line is not None and lon_line is not None:
                                    lat = lines[lat_line].replace('# !latitude:', '').strip()
                                    lon = lines[lon_line].replace('# !longitude:', '').strip()

                                    matches.append({
                                        'file': harmonics_file,
                                        'station_text': stripped,
                                        'lat': lat,
                                        'lon': lon
                                    })
            except Exception as e:
                continue

        # Update row with matches
        if matches:
            print(f"  Found {len(matches)} match(es)")
            found_matches += 1

            for i, match in enumerate(matches[:4], 1):
                row[f'Treffer_{i}'] = match['station_text']
                row[f'Datei_{i}'] = match['file']
                row[f'Lat_{i}'] = match['lat']
                row[f'Lon_{i}'] = match['lon']
                print(f"    {i}. {match['station_text']}")
                print(f"       File: {match['file']}")
                print(f"       Coordinates: {match['lat']}, {match['lon']}")

            if len(matches) == 1:
                row['Status'] = 'Treffer gefunden'
            else:
                row['Status'] = f'{len(matches)} Treffer gefunden'
        else:
            print(f"  No matches found")

# Write updated CSV
new_fieldnames = ['Tidenstation', 'Breitengrad', 'Längengrad', 'Status',
                  'Treffer_1', 'Datei_1', 'Lat_1', 'Lon_1',
                  'Treffer_2', 'Datei_2', 'Lat_2', 'Lon_2',
                  'Treffer_3', 'Datei_3', 'Lat_3', 'Lon_3',
                  'Treffer_4', 'Datei_4', 'Lat_4', 'Lon_4']

with open(csv_file, 'w', encoding=used_encoding, newline='') as f:
    writer = csv.DictWriter(f, fieldnames=new_fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(csv_data)

print(f"\n=== SUMMARY ===")
print(f"Total stations searched: {total_searched}")
print(f"Stations with matches found: {found_matches}")
print(f"Stations still not found: {total_searched - found_matches}")
print(f"\n✓ CSV file updated")
