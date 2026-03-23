#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv

csv_file = '/home/oliver/harmonics_working/station_name_corrections.csv'

print("Analyzing station_name_corrections.csv...")
print("="*80)

# Find entries with found status but empty Full_Corrected_Name
found_empty_full_name = []
not_found = []

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    for row_num, row in enumerate(reader, start=2):  # start at 2 because of header
        status = row.get('Status', '').strip()
        full_name = row.get('Full_Corrected_Name', '').strip()

        if status == 'found' and not full_name:
            found_empty_full_name.append((row_num, row))
        elif status == 'not_found':
            not_found.append((row_num, row))

print(f"\n📊 Summary:")
print(f"   Entries with 'found' status but empty Full_Corrected_Name: {len(found_empty_full_name)}")
print(f"   Entries with 'not_found' status: {len(not_found)}")

print(f"\n\n🔍 Entries with 'found' status but empty Full_Corrected_Name:")
print("="*80)
for row_num, row in found_empty_full_name[:20]:  # Show first 20
    print(f"\nLine {row_num}:")
    print(f"  Original: {row['Original_Name']}")
    print(f"  Corrected: {row['Corrected_Name']}")
    print(f"  Region: {row['Corrected_Region']}")
    print(f"  Country: {row['Corrected_Country']}")
    print(f"  Coordinates: {row['Original_Lat']}, {row['Original_Lon']}")

print(f"\n\n❌ Not found entries (first 30):")
print("="*80)
for row_num, row in not_found[:30]:
    print(f"\nLine {row_num}: {row['Original_Name']}")
    print(f"  Coordinates: {row['Original_Lat']}, {row['Original_Lon']}")
    print(f"  Timezone: {row['Original_Timezone']}")
