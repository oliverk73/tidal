#!/usr/bin/env python3
"""
Fix 1111 and 111.1 placeholder values in subordinate stations CSV file.

Rules:
1. If lmin=1111 and hmin!=1111: lmin = hmin
2. If hmin=1111 and lmin!=1111: hmin = lmin
3. If both hmin=1111 AND lmin=1111: both = 0
4. If loff=111.1 and hoff!=111.1: loff = hoff
5. If hoff=111.1 and loff!=111.1: hoff = loff
6. If both hoff=111.1 AND loff=111.1: both = 0
"""

import csv
import sys

def fix_values(input_file, output_file):
    changes = []

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames
        rows = list(reader)

    for i, row in enumerate(rows):
        modified = False
        original = dict(row)

        try:
            hmin = int(row['hmin']) if row['hmin'] else 0
            lmin = int(row['lmin']) if row['lmin'] else 0
            hoff = float(row['hoff'].replace(',', '.')) if row['hoff'] else 0
            loff = float(row['loff'].replace(',', '.')) if row['loff'] else 0
        except (ValueError, KeyError) as e:
            continue

        # Fix minutes
        if hmin == 1111 and lmin == 1111:
            row['hmin'] = '0'
            row['lmin'] = '0'
            modified = True
        elif lmin == 1111:
            row['lmin'] = str(hmin)
            modified = True
        elif hmin == 1111:
            row['hmin'] = str(lmin)
            modified = True

        # Fix offsets
        hoff_is_111 = abs(hoff - 111.1) < 0.01
        loff_is_111 = abs(loff - 111.1) < 0.01

        if hoff_is_111 and loff_is_111:
            row['hoff'] = '0'
            row['loff'] = '0'
            modified = True
        elif loff_is_111:
            row['loff'] = str(hoff)
            modified = True
        elif hoff_is_111:
            row['hoff'] = str(loff)
            modified = True

        if modified:
            changes.append((i+2, row['station_name'], original, dict(row)))

    # Write output
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    return changes

if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/subordinate_stations_mapped_bak.csv'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_mapped_bak_fixed.csv'

    changes = fix_values(input_file, output_file)

    print(f"Total changes: {len(changes)}")
    print("\nChanges made:")
    for line, name, old, new in changes:
        print(f"\nLine {line}: {name}")
        if old['hmin'] != new['hmin']:
            print(f"  hmin: {old['hmin']} -> {new['hmin']}")
        if old['lmin'] != new['lmin']:
            print(f"  lmin: {old['lmin']} -> {new['lmin']}")
        if old['hoff'] != new['hoff']:
            print(f"  hoff: {old['hoff']} -> {new['hoff']}")
        if old['loff'] != new['loff']:
            print(f"  loff: {old['loff']} -> {new['loff']}")
