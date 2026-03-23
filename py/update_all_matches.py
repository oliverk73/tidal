#!/usr/bin/env python3
import csv
import os

# Paths
csv_file = '/home/oliver/harmonics_working/Geokoordinaten-Korrektur.csv'
harmonics_dir = '/home/oliver/harmonics_edited'

# Try different encodings
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

# Find all stations that have matches (Treffer_1 filled and not already "Aktualisiert")
stations_to_update = []

for row in csv_data:
    # Skip already updated stations
    if row.get('Status') == 'Aktualisiert':
        continue

    # Check if there are any matches
    has_matches = False
    matches = []

    for i in range(1, 5):
        if row.get(f'Treffer_{i}') and row.get(f'Datei_{i}'):
            has_matches = True
            # Check if this match has coordinates
            if row.get(f'Lat_{i}') and row.get(f'Lon_{i}'):
                matches.append({
                    'station_text': row[f'Treffer_{i}'],
                    'file': row[f'Datei_{i}'],
                    'old_lat': row[f'Lat_{i}'],
                    'old_lon': row[f'Lon_{i}']
                })

    if has_matches and matches:
        station_name = row['Tidenstation']
        new_lat = row['Breitengrad'].replace(',', '.')
        new_lon = row['Längengrad'].replace(',', '.')

        stations_to_update.append({
            'row': row,
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon,
            'matches': matches
        })

print(f"\nFound {len(stations_to_update)} stations with matches to update")

# Update the harmonics files
updated_files = {}
total_updates = 0

for station_info in stations_to_update:
    station = station_info['name']
    new_lat = station_info['new_lat']
    new_lon = station_info['new_lon']
    matches = station_info['matches']

    print(f"\n=== {station} ===")
    print(f"New coordinates: {new_lat}, {new_lon}")

    for match in matches:
        file_path = os.path.join(harmonics_dir, match['file'])
        station_text = match['station_text']

        # Read file if not already loaded
        if file_path not in updated_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    updated_files[file_path] = f.readlines()
            except Exception as e:
                print(f"  Error reading {match['file']}: {e}")
                continue

        lines = updated_files[file_path]

        # Find the station and update coordinates
        updated = False
        for i, line in enumerate(lines):
            if station_text in line.strip() and not line.startswith('#'):
                # Look back for coordinates
                lat_line = None
                lon_line = None
                for j in range(max(0, i-5), i):
                    if lines[j].startswith('# !latitude:'):
                        lat_line = j
                    if lines[j].startswith('# !longitude:'):
                        lon_line = j

                if lat_line is not None and lon_line is not None:
                    # Update the coordinates
                    old_lat = lines[lat_line].strip()
                    old_lon = lines[lon_line].strip()

                    lines[lat_line] = f"# !latitude: {new_lat}\n"
                    lines[lon_line] = f"# !longitude: {new_lon}\n"

                    print(f"  ✓ Updated: {station_text}")
                    print(f"    File: {match['file']}")
                    print(f"    Old: {old_lat} / {old_lon}")
                    print(f"    New: # !latitude: {new_lat} / # !longitude: {new_lon}")

                    updated = True
                    total_updates += 1
                    break

        if not updated:
            print(f"  ⚠ Could not find: {station_text} in {match['file']}")

    # Update status in CSV row
    station_info['row']['Status'] = 'Aktualisiert'

# Write updated harmonics files
print(f"\n=== Saving updated files ===")
for file_path, lines in updated_files.items():
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"✓ Saved: {os.path.basename(file_path)}")

print(f"\n✓ Successfully updated {total_updates} station entries in {len(updated_files)} files")

# Write updated CSV (keep all stations)
new_fieldnames = ['Tidenstation', 'Breitengrad', 'Längengrad', 'Status',
                  'Treffer_1', 'Datei_1', 'Lat_1', 'Lon_1',
                  'Treffer_2', 'Datei_2', 'Lat_2', 'Lon_2',
                  'Treffer_3', 'Datei_3', 'Lat_3', 'Lon_3',
                  'Treffer_4', 'Datei_4', 'Lat_4', 'Lon_4']

with open(csv_file, 'w', encoding=used_encoding, newline='') as f:
    writer = csv.DictWriter(f, fieldnames=new_fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(csv_data)

# Count final status
aktualisiert = sum(1 for row in csv_data if row.get('Status') == 'Aktualisiert')
nicht_gefunden = sum(1 for row in csv_data if row.get('Status') == 'Nicht gefunden')
multiple = sum(1 for row in csv_data if 'Treffer gefunden' in row.get('Status', ''))

print(f"\n=== CSV Updated ===")
print(f"Total stations in CSV: {len(csv_data)}")
print(f"\nStatus breakdown:")
print(f"  - Aktualisiert: {aktualisiert}")
print(f"  - Nicht gefunden: {nicht_gefunden}")
print(f"  - Mehrfache Treffer: {multiple}")
