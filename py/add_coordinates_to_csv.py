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

# Function to extract coordinates from harmonics file
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
                    return lat, lon
    except Exception as e:
        print(f"Error reading {file_name}: {e}")

    return None, None

# Process each row and add coordinates for matches
for row in csv_data:
    # Check if there are any matches (Treffer_1, Treffer_2, etc.)
    for i in range(1, 5):  # Check up to 4 possible matches
        treffer_key = f'Treffer_{i}'
        datei_key = f'Datei_{i}'

        if treffer_key in row and row[treffer_key] and datei_key in row and row[datei_key]:
            station_name = row[treffer_key]
            file_name = row[datei_key]

            # Get coordinates
            lat, lon = get_coordinates_for_station(station_name, file_name)

            if lat and lon:
                row[f'Lat_{i}'] = lat
                row[f'Lon_{i}'] = lon
                print(f"Added coordinates for {station_name}: {lat}, {lon}")
            else:
                row[f'Lat_{i}'] = ''
                row[f'Lon_{i}'] = ''

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

print(f"\n✓ CSV file updated with coordinates")
print(f"  - Total stations: {len(csv_data)}")
print(f"  - Fields: {', '.join(new_fieldnames)}")
