#!/usr/bin/env python3
import csv
import re
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

print(f"Loaded {len(csv_data)} stations from CSV")

# Get all harmonics text files
harmonics_files = [
    'harmonics-dwf-20241229-free.txt',
    'harmonics-dwf-20070318_no_us_no_dupes.txt',
    'harmonics-2004-06-14_no_us_no_dupes2.txt',
    'harmonics_pierre_lavergne_v10_no_dupes4.txt',
    'harmonics_pierre_lavergne_v9_europe_no_us_no_dupes5.txt',
    'harmonics-dwf-20100529-nonfree.txt',
    'harmonics_old_no_us_no_dupes3.txt'
]

# Function to get coordinates for a station
def get_coordinates_for_station(station_name, file_name):
    """Extract coordinates for a specific station from harmonics file"""
    file_path = os.path.join(harmonics_dir, file_name)

    if not os.path.exists(file_path):
        return None, None

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            # Look for the station name
            if station_name in line.strip() and not line.startswith('#'):
                # Look back for coordinates
                lat = None
                lon = None
                for j in range(max(0, i-5), i):
                    if lines[j].startswith('# !latitude:'):
                        lat = lines[j].replace('# !latitude:', '').strip()
                    if lines[j].startswith('# !longitude:'):
                        lon = lines[j].replace('# !longitude:', '').strip()

                if lat and lon:
                    return lat, lon, line.strip()
    except Exception as e:
        print(f"Error reading {file_name}: {e}")

    return None, None, None

# Search for each "Nicht gefunden" station
for row in csv_data:
    if row.get('Status') == 'Nicht gefunden':
        original_name = row['Tidenstation']

        # Remove " (Tide)" from the station name
        search_name = original_name.replace(' (Tide)', '').replace('(Tide)', '')

        if search_name != original_name:
            print(f"\nSearching for: {original_name}")
            print(f"  → Modified search: {search_name}")
        else:
            print(f"\nSearching for: {original_name}")

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
                    # Check if this line contains the search name
                    if not line.startswith('#') and not line.startswith('x ') and search_name in line:
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
            for i, match in enumerate(matches[:4], 1):  # Max 4 matches
                row[f'Treffer_{i}'] = match['station_text']
                row[f'Datei_{i}'] = match['file']
                row[f'Lat_{i}'] = match['lat']
                row[f'Lon_{i}'] = match['lon']
                print(f"    {i}. {match['station_text']} ({match['lat']}, {match['lon']})")

            # Update status
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

# Count results
found_count = sum(1 for row in csv_data if 'Treffer gefunden' in row.get('Status', ''))
still_not_found = sum(1 for row in csv_data if row.get('Status') == 'Nicht gefunden')

print(f"\n=== SUMMARY ===")
print(f"Stations with matches found: {found_count}")
print(f"Stations still not found: {still_not_found}")
print(f"\n✓ CSV file updated")
