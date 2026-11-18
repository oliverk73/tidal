#!/usr/bin/env python3
"""
Parse subordinate tide/current stations from harmonic_subordinate_corrections.idx
and create a CSV file with all station data.
"""

import csv
import re

def parse_subordinate_stations(input_file, output_csv):
    """Parse the idx file and create CSV with subordinate station data."""

    stations = []

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line1 = lines[i].strip()

        # Check if this is a station line (starts with 't' for tide or 'c' for current)
        if line1 and (line1.startswith('t') or line1.startswith('c')):
            station_type = 'tide' if line1.startswith('t') else 'current'

            # Parse first line: zone:region:subregion: lon lat tz name
            # Format: tZone:Region:Subregion: longitude latitude timezone station_name

            # Find the first colon to get the zone
            first_colon = line1.find(':')
            if first_colon == -1:
                i += 1
                continue

            zone = line1[1:first_colon]  # Skip 't' or 'c' prefix

            # Parse the rest: Region:Subregion: lon lat tz name
            rest = line1[first_colon+1:]

            # Split by colons to get region parts
            colon_parts = rest.split(':')

            if len(colon_parts) >= 3:
                region = colon_parts[0]
                subregion = colon_parts[1]
                # The rest after the third colon contains coordinates and name
                data_part = ':'.join(colon_parts[2:]).strip()
            else:
                region = ''
                subregion = ''
                data_part = rest.strip()

            # Parse: longitude latitude timezone station_name
            # Timezone format is like "0:0" or "1:0"
            # Use regex to find the pattern
            match = re.match(r'^([\s]*)(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+:\d+)\s+(.+)$', data_part)

            if match:
                longitude = match.group(2)
                latitude = match.group(3)
                timezone_offset = match.group(4)
                station_name = match.group(5)
            else:
                # Try alternative parsing
                parts = data_part.split()
                if len(parts) >= 4:
                    longitude = parts[0]
                    latitude = parts[1]
                    timezone_offset = parts[2]
                    station_name = ' '.join(parts[3:])
                else:
                    i += 1
                    continue

            # Check for next line with '&' prefix containing correction values
            if i + 1 < len(lines):
                line2 = lines[i + 1].strip()
                if line2.startswith('&'):
                    # Parse second line: &Hmin Hmpy Hoff Lmin Lmpy Loff StaID tzname RefFileNum RefName
                    correction_data = line2[1:]  # Remove '&'
                    parts = correction_data.split()

                    if len(parts) >= 8:
                        hmin = parts[0]
                        hmpy = parts[1]
                        hoff = parts[2]
                        lmin = parts[3]
                        lmpy = parts[4]
                        loff = parts[5]

                        # Find tzname (looks like America/New_York or Pacific/Auckland)
                        # and ref_file_num and ref_name
                        remaining = parts[6:]

                        # tzname typically contains '/'
                        tzname = ''
                        sta_id = ''
                        ref_file_num = ''
                        ref_name = ''

                        # Check if parts[6] is a number (StaID) or contains '/' (tzname)
                        if '/' in parts[6]:
                            # Format: tzname ref_file_num ref_name
                            tzname = parts[6]
                            ref_file_num = parts[7] if len(parts) > 7 else ''
                            ref_name = ' '.join(parts[8:]) if len(parts) > 8 else ''
                        else:
                            # Format: StaID (tzname) ref_file_num ref_name
                            # or: StaID tzname ref_file_num ref_name
                            sta_id = parts[6]
                            if len(parts) > 7:
                                if '/' in parts[7]:
                                    tzname = parts[7]
                                    ref_file_num = parts[8] if len(parts) > 8 else ''
                                    ref_name = ' '.join(parts[9:]) if len(parts) > 9 else ''
                                else:
                                    ref_file_num = parts[7]
                                    ref_name = ' '.join(parts[8:]) if len(parts) > 8 else ''

                        station = {
                            'type': station_type,
                            'zone': zone,
                            'region': region,
                            'subregion': subregion,
                            'longitude': longitude,
                            'latitude': latitude,
                            'station_name': station_name,
                            'timezone_offset': timezone_offset,
                            'hmin': hmin,
                            'hmpy': hmpy,
                            'hoff': hoff,
                            'lmin': lmin,
                            'lmpy': lmpy,
                            'loff': loff,
                            'sta_id': sta_id,
                            'tzname': tzname,
                            'ref_file_num': ref_file_num,
                            'ref_name': ref_name
                        }
                        stations.append(station)

                    i += 2  # Skip both lines
                    continue

        i += 1

    # Write CSV
    fieldnames = ['type', 'zone', 'region', 'subregion', 'longitude', 'latitude',
                  'station_name', 'timezone_offset', 'hmin', 'hmpy', 'hoff',
                  'lmin', 'lmpy', 'loff', 'sta_id', 'tzname', 'ref_file_num', 'ref_name']

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stations)

    print(f"Parsed {len(stations)} subordinate stations")
    print(f"CSV saved to: {output_csv}")

    return stations

if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections.idx'
    output_csv = '/home/oliver/subordinate_corrections/subordinate_stations.csv'

    parse_subordinate_stations(input_file, output_csv)
