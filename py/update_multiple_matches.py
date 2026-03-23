#!/usr/bin/env python3
import csv
import os

# Read the CSV file
csv_file = '/home/oliver/harmonics_working/Geokoordinaten-Korrektur.csv'
harmonics_dir = '/home/oliver/harmonics_working'

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

# Find stations with multiple matches (those that have Treffer_1 and Treffer_2)
stations_to_update = []

for row in csv_data:
    if row.get('Treffer_1') and row.get('Treffer_2'):
        station_name = row['Tidenstation']
        new_lat = row['Breitengrad'].replace(',', '.')
        new_lon = row['Längengrad'].replace(',', '.')

        # Collect all matches
        matches = []
        for i in range(1, 5):
            if row.get(f'Treffer_{i}') and row.get(f'Datei_{i}'):
                matches.append({
                    'station_text': row[f'Treffer_{i}'],
                    'file': row[f'Datei_{i}'],
                    'old_lat': row.get(f'Lat_{i}', ''),
                    'old_lon': row.get(f'Lon_{i}', '')
                })

        stations_to_update.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon,
            'matches': matches
        })

print(f"\nFound {len(stations_to_update)} stations with multiple matches to update")

# Update the harmonics files
updated_files = {}

for station in stations_to_update:
    print(f"\n=== Updating {station['name']} ===")
    print(f"New coordinates: {station['new_lat']}, {station['new_lon']}")

    for match in station['matches']:
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

                    lines[lat_line] = f"# !latitude: {station['new_lat']}\n"
                    lines[lon_line] = f"# !longitude: {station['new_lon']}\n"

                    print(f"  ✓ Updated '{station_text}' in {match['file']}")
                    print(f"    Old: {old_lat} / {old_lon}")
                    print(f"    New: # !latitude: {station['new_lat']} / # !longitude: {station['new_lon']}")
                    break

# Write updated files
print(f"\n=== Saving updated files ===")
for file_path, lines in updated_files.items():
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"✓ Saved: {os.path.basename(file_path)}")

print(f"\n✓ Successfully updated {len(stations_to_update)} stations with multiple matches")

# Update the CSV to remove these stations
print(f"\n=== Updating CSV file ===")
updated_station_names = [s['name'] for s in stations_to_update]
new_csv_data = [row for row in csv_data if row['Tidenstation'] not in updated_station_names]

# Write new CSV
new_fieldnames = ['Tidenstation', 'Breitengrad', 'Längengrad', 'Status',
                  'Treffer_1', 'Datei_1', 'Lat_1', 'Lon_1',
                  'Treffer_2', 'Datei_2', 'Lat_2', 'Lon_2',
                  'Treffer_3', 'Datei_3', 'Lat_3', 'Lon_3',
                  'Treffer_4', 'Datei_4', 'Lat_4', 'Lon_4']

with open(csv_file, 'w', encoding=used_encoding, newline='') as f:
    writer = csv.DictWriter(f, fieldnames=new_fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(new_csv_data)

print(f"✓ Removed {len(updated_station_names)} updated stations from CSV")
print(f"✓ Remaining stations in CSV: {len(new_csv_data)}")
