#!/usr/bin/env python3
import csv
import os

# Paths
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

print(f"Loaded {len(csv_data)} stations from current CSV")

# Find stations with unique matches (status = "Treffer gefunden")
unique_matches = []
for row in csv_data:
    if row.get('Status') == 'Treffer gefunden' and row.get('Treffer_1') and row.get('Datei_1'):
        unique_matches.append({
            'name': row['Tidenstation'],
            'new_lat': row['Breitengrad'].replace(',', '.'),
            'new_lon': row['Längengrad'].replace(',', '.'),
            'station_text': row['Treffer_1'],
            'file': row['Datei_1'],
            'old_lat': row['Lat_1'],
            'old_lon': row['Lon_1']
        })

print(f"\nFound {len(unique_matches)} stations with unique matches to update")

# Update the harmonics files
updated_files = {}

for station in unique_matches:
    file_path = os.path.join(harmonics_dir, station['file'])
    station_text = station['station_text']

    # Read file if not already loaded
    if file_path not in updated_files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                updated_files[file_path] = f.readlines()
        except Exception as e:
            print(f"  Error reading {station['file']}: {e}")
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

                print(f"\n✓ Updated {station['name']}")
                print(f"  Station: {station_text}")
                print(f"  File: {station['file']}")
                print(f"  Old: {old_lat} / {old_lon}")
                print(f"  New: # !latitude: {station['new_lat']} / # !longitude: {station['new_lon']}")
                break

# Write updated files
print(f"\n=== Saving updated files ===")
for file_path, lines in updated_files.items():
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"✓ Saved: {os.path.basename(file_path)}")

print(f"\n✓ Successfully updated {len(unique_matches)} stations")

# Now restore all previously updated stations to CSV
# These are the 50 stations that were updated and removed from CSV earlier

previously_updated = [
    # 47 unique matches from first update
    {"name": "Den Oever", "lat": "52,9418", "lon": "5,0299", "status": "Aktualisiert"},
    {"name": "Immingham Dock, Humberside", "lat": "53,6308", "lon": "-0,1879", "status": "Aktualisiert"},
    {"name": "Clarence Harbor, Long Island", "lat": "23,102", "lon": "-74,9597", "status": "Aktualisiert"},
    {"name": "Cocagne Harbour", "lat": "46,336", "lon": "-64,6159", "status": "Aktualisiert"},
    {"name": "Caissie Point", "lat": "46,3135", "lon": "-64,51", "status": "Aktualisiert"},
    {"name": "Arichat", "lat": "45,5095", "lon": "-61,024", "status": "Aktualisiert"},
    {"name": "Portage Island, New Brunswick", "lat": "47,177", "lon": "-65,037", "status": "Aktualisiert"},
    {"name": "Saint-Godefroi", "lat": "48,074", "lon": "-65,113", "status": "Aktualisiert"},
    {"name": "Pointe Howatson", "lat": "48,138", "lon": "-65,837", "status": "Aktualisiert"},
    {"name": "Victoria, Prince Edward Island", "lat": "46,217", "lon": "-63,5", "status": "Aktualisiert"},
    {"name": "Pointe-Au-Pic", "lat": "47,622", "lon": "-70,141", "status": "Aktualisiert"},
    {"name": "Natashquan", "lat": "50,189", "lon": "-61,842", "status": "Aktualisiert"},
    {"name": "Lance Cove", "lat": "47,083", "lon": "-52,9", "status": "Aktualisiert"},
    {"name": "Valleyfield", "lat": "49,122", "lon": "-53,608", "status": "Aktualisiert"},
    {"name": "Cape Acadia", "lat": "61,5736", "lon": "-79,8292", "status": "Aktualisiert"},
    {"name": "Bill Of Portland Island", "lat": "55,3626", "lon": "-77,7435", "status": "Aktualisiert"},
    {"name": "Roggan-River", "lat": "54,391", "lon": "-79,493", "status": "Aktualisiert"},
    {"name": "North Twin Island", "lat": "53,2252", "lon": "-80,0203", "status": "Aktualisiert"},
    {"name": "Ship Sands Island", "lat": "51,333", "lon": "-80,433", "status": "Aktualisiert"},
    {"name": "Finnerty Cove", "lat": "48,474", "lon": "-123,296", "status": "Aktualisiert"},
    {"name": "Maple Bay", "lat": "48,816", "lon": "-123,61", "status": "Aktualisiert"},
    {"name": "Harmac", "lat": "49,14", "lon": "-123,846", "status": "Aktualisiert"},
    {"name": "Tumbo Channel", "lat": "48,793", "lon": "-123,109", "status": "Aktualisiert"},
    {"name": "Narvaez Bay", "lat": "48,774", "lon": "-123,098", "status": "Aktualisiert"},
    {"name": "Bedwell Harbour", "lat": "48,748", "lon": "-123,227", "status": "Aktualisiert"},
    {"name": "Burgoyne Bay", "lat": "48,7934", "lon": "-123,5216", "status": "Aktualisiert"},
    {"name": "Canoe Pass", "lat": "49,0779", "lon": "-123,1283", "status": "Aktualisiert"},
    {"name": "Stanovan", "lat": "49,2919", "lon": "-123,0039", "status": "Aktualisiert"},
    {"name": "Squitty Bay", "lat": "49,4526", "lon": "-124,1653", "status": "Aktualisiert"},
    {"name": "Gowlland Harbour", "lat": "50,065", "lon": "-125,217", "status": "Aktualisiert"},
    {"name": "Mereworth Sound", "lat": "51,176", "lon": "-127,409", "status": "Aktualisiert"},
    {"name": "Morse Basin", "lat": "54,258", "lon": "-130,238", "status": "Aktualisiert"},
    {"name": "Chesterfield Inlet", "lat": "63,333", "lon": "-90,7", "status": "Aktualisiert"},
    {"name": "Coats Island", "lat": "62,6074", "lon": "-82,1581", "status": "Aktualisiert"},
    {"name": "Crown Prince Frederick", "lat": "69,997", "lon": "-87,1", "status": "Aktualisiert"},
    {"name": "Port Leopold", "lat": "73,833", "lon": "-90,333", "status": "Aktualisiert"},
    {"name": "Airstrip Point", "lat": "76,07", "lon": "-97,59", "status": "Aktualisiert"},
    {"name": "Pim Island", "lat": "78,672", "lon": "-74,172", "status": "Aktualisiert"},
    {"name": "Pisiktarfik Island", "lat": "72,576", "lon": "-80,353", "status": "Aktualisiert"},
    {"name": "North Point, Pier 41, San Francisco", "lat": "37,8104", "lon": "-122,4127", "status": "Aktualisiert"},
    {"name": "Kirby Park, Elkhorn Slough, Monterey Bay", "lat": "36,8399", "lon": "-121,7435", "status": "Aktualisiert"},
    {"name": "Jazireh-ye Lavan", "lat": "26,8", "lon": "53,3833", "status": "Aktualisiert"},
    {"name": "Low Wooded Isle", "lat": "-15,0929", "lon": "145,3792", "status": "Aktualisiert"},
    {"name": "Thistle Island", "lat": "-35", "lon": "136,183333", "status": "Aktualisiert"},
    {"name": "Shortland Island", "lat": "-7,0345", "lon": "155,8532", "status": "Aktualisiert"},
    {"name": "Avarua", "lat": "-21,2052", "lon": "-159,7709", "status": "Aktualisiert"},
    {"name": "Toguti, Okinawa", "lat": "26,6614", "lon": "127,8885", "status": "Aktualisiert"},
    # 3 multiple matches from second update
    {"name": "Crofton", "lat": "48,875", "lon": "-123,644", "status": "Aktualisiert"},
    {"name": "Jacksonville, Acosta Bridge", "lat": "30,322667", "lon": "-81,664617", "status": "Aktualisiert"},
    {"name": "Harwich, England", "lat": "51,948", "lon": "1,2921", "status": "Aktualisiert"},
]

# Add previously updated stations to csv_data
for station in previously_updated:
    csv_data.append({
        'Tidenstation': station['name'],
        'Breitengrad': station['lat'],
        'Längengrad': station['lon'],
        'Status': station['status'],
        'Treffer_1': '',
        'Datei_1': '',
        'Lat_1': '',
        'Lon_1': '',
        'Treffer_2': '',
        'Datei_2': '',
        'Lat_2': '',
        'Lon_2': '',
        'Treffer_3': '',
        'Datei_3': '',
        'Lat_3': '',
        'Lon_3': '',
        'Treffer_4': '',
        'Datei_4': '',
        'Lat_4': '',
        'Lon_4': ''
    })

# Update status for newly updated unique matches
for row in csv_data:
    if row.get('Status') == 'Treffer gefunden':
        row['Status'] = 'Aktualisiert'

# Write complete CSV
new_fieldnames = ['Tidenstation', 'Breitengrad', 'Längengrad', 'Status',
                  'Treffer_1', 'Datei_1', 'Lat_1', 'Lon_1',
                  'Treffer_2', 'Datei_2', 'Lat_2', 'Lon_2',
                  'Treffer_3', 'Datei_3', 'Lat_3', 'Lon_3',
                  'Treffer_4', 'Datei_4', 'Lat_4', 'Lon_4']

with open(csv_file, 'w', encoding=used_encoding, newline='') as f:
    writer = csv.DictWriter(f, fieldnames=new_fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(csv_data)

print(f"\n=== CSV Updated ===")
print(f"✓ Added {len(previously_updated)} previously updated stations back to CSV")
print(f"✓ Total stations in CSV: {len(csv_data)}")

# Count by status
aktualisiert = sum(1 for row in csv_data if row.get('Status') == 'Aktualisiert')
nicht_gefunden = sum(1 for row in csv_data if row.get('Status') == 'Nicht gefunden')
multiple = sum(1 for row in csv_data if 'Treffer gefunden' in row.get('Status', ''))

print(f"\nStatus breakdown:")
print(f"  - Aktualisiert: {aktualisiert}")
print(f"  - Nicht gefunden: {nicht_gefunden}")
print(f"  - Mehrfache Treffer: {multiple}")
