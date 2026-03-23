#!/usr/bin/env python3
import csv
import os

# Paths
csv_file = '/home/oliver/harmonics_working/Geokoordinaten-Korrektur.csv'
harmonics_dir = '/home/oliver/harmonics_edited'

# Mapping table (correct name → incorrect name in files)
icelandic_corrections = {
    'Njarðvík, Iceland': 'Njarvk, Iceland',
    'Sandgerði, Iceland': 'Sandgeri, Iceland',
    'Grundarfjörður, Iceland': 'Grundarfjrur, Iceland',
    'Ísafjörður, Iceland': 'safjrur, Iceland',
    'Patreksfjörður, Iceland': 'Patreksfjrur, Iceland',
    'Siglufjörður, Iceland': 'Siglufjrur, Iceland',
    'Ólafsfjörður, Iceland': 'lafsfjrur, Iceland',
    'Seyðisfjörður, Iceland': 'Seyisfjrur, Iceland',
    'Hornafjörður, Iceland': 'Hornafjrur, Iceland'
}

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

# Find Icelandic stations with matches
stations_to_update = []

for row in csv_data:
    if row.get('Status') == 'Treffer gefunden' and 'Iceland' in row.get('Tidenstation', ''):
        if row.get('Treffer_1') and row.get('Datei_1'):
            station_name = row['Tidenstation']
            new_lat = row['Breitengrad'].replace(',', '.')
            new_lon = row['Längengrad'].replace(',', '.')

            stations_to_update.append({
                'row': row,
                'name': station_name,
                'new_lat': new_lat,
                'new_lon': new_lon,
                'old_station_text': row['Treffer_1'],
                'file': row['Datei_1'],
                'old_lat': row['Lat_1'],
                'old_lon': row['Lon_1']
            })

print(f"\nFound {len(stations_to_update)} Icelandic stations to update")

# Update the harmonics files
updated_files = {}
total_updates = 0

for station_info in stations_to_update:
    station = station_info['name']
    new_lat = station_info['new_lat']
    new_lon = station_info['new_lon']
    old_station_text = station_info['old_station_text']
    file_name = station_info['file']

    # Get correct name from mapping
    correct_name = None
    for correct, incorrect in icelandic_corrections.items():
        if incorrect == old_station_text:
            correct_name = correct
            break

    if not correct_name:
        print(f"  ⚠ No name correction found for: {old_station_text}")
        correct_name = old_station_text

    print(f"\n=== {station} ===")
    print(f"Old name in file: {old_station_text}")
    print(f"New name: {correct_name}")
    print(f"New coordinates: {new_lat}, {new_lon}")

    file_path = os.path.join(harmonics_dir, file_name)

    # Read file if not already loaded
    if file_path not in updated_files:
        try:
            with open(file_path, 'r', encoding='iso-8859-1') as f:
                updated_files[file_path] = f.readlines()
        except Exception as e:
            print(f"  Error reading {file_name}: {e}")
            continue

    lines = updated_files[file_path]

    # Find and update the station
    updated = False
    for i, line in enumerate(lines):
        if old_station_text in line.strip() and not line.startswith('#'):
            # Look back for coordinates
            lat_line = None
            lon_line = None
            for j in range(max(0, i-5), i):
                if lines[j].startswith('# !latitude:'):
                    lat_line = j
                if lines[j].startswith('# !longitude:'):
                    lon_line = j

            if lat_line is not None and lon_line is not None:
                # Update coordinates
                old_lat = lines[lat_line].strip()
                old_lon = lines[lon_line].strip()

                lines[lat_line] = f"# !latitude: {new_lat}\n"
                lines[lon_line] = f"# !longitude: {new_lon}\n"

                # Update station name
                lines[i] = line.replace(old_station_text, correct_name)

                print(f"  ✓ Updated coordinates:")
                print(f"    Old: {old_lat} / {old_lon}")
                print(f"    New: # !latitude: {new_lat} / # !longitude: {new_lon}")
                print(f"  ✓ Updated station name in line {i+1}")

                updated = True
                total_updates += 1
                break

    if not updated:
        print(f"  ⚠ Could not find station in {file_name}")

    # Update CSV row status
    station_info['row']['Status'] = 'Aktualisiert'

# Write updated harmonics files
print(f"\n=== Saving updated files ===")
for file_path, lines in updated_files.items():
    try:
        # Save with ISO 8859-1 encoding to preserve the file format
        with open(file_path, 'w', encoding='iso-8859-1') as f:
            f.writelines(lines)
        print(f"✓ Saved: {os.path.basename(file_path)}")
    except Exception as e:
        print(f"  Error saving {os.path.basename(file_path)}: {e}")

print(f"\n✓ Successfully updated {total_updates} Icelandic stations")

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

# Count final status
aktualisiert = sum(1 for row in csv_data if row.get('Status') == 'Aktualisiert')
nicht_gefunden = sum(1 for row in csv_data if row.get('Status') == 'Nicht gefunden')
multiple = sum(1 for row in csv_data if 'Treffer gefunden' in row.get('Status', ''))

print(f"\n=== CSV Updated ===")
print(f"Total stations in CSV: {len(csv_data)}")
print(f"\nStatus breakdown:")
print(f"  - Aktualisiert: {aktualisiert}")
print(f"  - Treffer gefunden: {multiple}")
print(f"  - Nicht gefunden: {nicht_gefunden}")
