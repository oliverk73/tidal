#!/usr/bin/env python3
import csv
import re
import os
from pathlib import Path

# Read the CSV file with corrections
csv_file = '/home/oliver/harmonics_working/Geokoordinaten-Korrektur.csv'
harmonics_dir = '/home/oliver/harmonics_working'

# Read corrections - try different encodings
corrections = []
encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
used_encoding = None
for encoding in encodings:
    try:
        with open(csv_file, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Tidenstation']:  # Skip empty rows
                    station_name = row['Tidenstation'].strip()
                    lat = row['Breitengrad'].replace(',', '.')
                    lon = row['Längengrad'].replace(',', '.')
                    corrections.append({
                        'name': station_name,
                        'lat': lat,
                        'lon': lon
                    })
        used_encoding = encoding
        print(f"Successfully read CSV with {encoding} encoding")
        break
    except (UnicodeDecodeError, KeyError) as e:
        corrections = []
        continue

print(f"Loaded {len(corrections)} coordinate corrections")

# Get all harmonics text files
harmonics_files = [
    'harmonics-dwf-20241229-free.txt',
    'harmonics-dwf-20070318_no_us_no_dupes.txt',
    'harmonics-2004-06-14_no_us_no_dupes2.txt',
    'harmonics_pierre_lavergne_v10_no_dupes4.txt',
    'harmonics_pierre_lavergne_v9_europe_no_us_no_dupes5.txt',
    'harmonics-dwf-20100529-nonfree_mod.txt',
    'harmonics_old_no_us_no_dupes3.txt'
]

# Track results
found_matches = []
multiple_matches = []
no_matches = []

# For each correction
for correction in corrections:
    station_name = correction['name']
    new_lat = correction['lat']
    new_lon = correction['lon']

    # Search for this station in all files
    matches = []

    for harmonics_file in harmonics_files:
        file_path = os.path.join(harmonics_dir, harmonics_file)
        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                # Check if this line contains the station name
                if not line.startswith('#') and not line.startswith('x ') and station_name in line:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('+') and not stripped.startswith('-') and 'meters' not in stripped and 'feet' not in stripped and 'knots' not in stripped:
                        # Look for coordinates in previous lines
                        lat_line = None
                        lon_line = None
                        for j in range(max(0, i-5), i):
                            if lines[j].startswith('# !latitude:'):
                                lat_line = j
                            if lines[j].startswith('# !longitude:'):
                                lon_line = j

                        if lat_line is not None and lon_line is not None:
                            matches.append({
                                'file': harmonics_file,
                                'file_path': file_path,
                                'station_line': i,
                                'station_text': stripped,
                                'lat_line': lat_line,
                                'lon_line': lon_line,
                                'old_lat': lines[lat_line].strip(),
                                'old_lon': lines[lon_line].strip(),
                                'lines': lines
                            })
        except Exception as e:
            print(f"Error reading {harmonics_file}: {e}")
            continue

    if len(matches) == 0:
        no_matches.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon
        })
    elif len(matches) == 1:
        found_matches.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon,
            'match': matches[0]
        })
    else:
        multiple_matches.append({
            'name': station_name,
            'new_lat': new_lat,
            'new_lon': new_lon,
            'matches': matches
        })

print(f"\n=== APPLYING UPDATES ===")
print(f"Updating {len(found_matches)} unique matches...")

# Update the unique matches
updated_files = {}
for item in found_matches:
    match = item['match']
    file_path = match['file_path']

    # Read the file if not already loaded
    if file_path not in updated_files:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            updated_files[file_path] = f.readlines()

    lines = updated_files[file_path]

    # Update latitude and longitude
    lat_line = match['lat_line']
    lon_line = match['lon_line']

    lines[lat_line] = f"# !latitude: {item['new_lat']}\n"
    lines[lon_line] = f"# !longitude: {item['new_lon']}\n"

    print(f"  ✓ Updated {item['name']} in {match['file']}")

# Write updated files
for file_path, lines in updated_files.items():
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"\nSaved: {os.path.basename(file_path)}")

print(f"\n✓ Successfully updated {len(found_matches)} stations in {len(updated_files)} files")

# Now update the CSV file
# Read original CSV
csv_data = []
with open(csv_file, 'r', encoding=used_encoding) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        if row['Tidenstation']:
            csv_data.append(row)

# Create new CSV with updated data
# Remove updated stations and add match information for others
new_csv_data = []
updated_station_names = [item['name'] for item in found_matches]

for row in csv_data:
    station_name = row['Tidenstation'].strip()

    # Skip stations that were updated
    if station_name in updated_station_names:
        continue

    # Add match information for multiple matches
    match_info = None
    for item in multiple_matches:
        if item['name'] == station_name:
            match_info = item
            break

    if match_info:
        # Add columns for each match
        for i, match in enumerate(match_info['matches'], 1):
            row[f'Treffer_{i}'] = match['station_text']
            row[f'Datei_{i}'] = match['file']
    else:
        # Check if it's a no-match station
        for item in no_matches:
            if item['name'] == station_name:
                row['Status'] = 'Nicht gefunden'
                break

    new_csv_data.append(row)

# Write new CSV
new_fieldnames = ['Tidenstation', 'Breitengrad', 'Längengrad', 'Status',
                  'Treffer_1', 'Datei_1', 'Treffer_2', 'Datei_2',
                  'Treffer_3', 'Datei_3', 'Treffer_4', 'Datei_4']

with open(csv_file, 'w', encoding=used_encoding, newline='') as f:
    writer = csv.DictWriter(f, fieldnames=new_fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(new_csv_data)

print(f"\n✓ Updated CSV file:")
print(f"  - Removed {len(found_matches)} updated stations")
print(f"  - Kept {len(new_csv_data)} stations for review")
print(f"  - Added match details for {len(multiple_matches)} stations with multiple matches")
print(f"  - Marked {len(no_matches)} stations as 'Nicht gefunden'")
