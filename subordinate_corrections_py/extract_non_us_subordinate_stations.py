#!/usr/bin/env python3
"""
Extract non-US subordinate tide/current stations from harmonic_subordinate_corrections.idx.
Removes all US stations (including territories) and saves the rest.
"""

import re

def is_us_station(line1, line2):
    """Check if a station pair belongs to the US or its territories."""

    # Parse region from line1
    # Format: tZone:Region:Subregion: ...
    match = re.match(r'^[tc]([^:]+):([^:]*):([^:]*):(.*)$', line1)
    if not match:
        return False

    zone = match.group(1)
    region = match.group(2)
    subregion = match.group(3)
    rest = match.group(4).strip()

    # US mainland
    if region == 'US':
        return True

    # Puerto Rico
    if region == 'PR':
        return True

    # Virgin Islands (US)
    if region == 'Virgn':
        return True

    # Northern Mariana Islands (US Commonwealth)
    if region == 'Mari':
        return True

    # Check for Guam (US territory)
    if 'Guam' in rest:
        return True

    # Check for American Samoa
    if 'American Samoa' in rest:
        return True

    # Check for other US Pacific territories
    us_pacific_keywords = [
        'Wake Island',
        'Midway',
        'Johnston Atoll',
        'Palmyra',
        'Howland',
        'Baker Island',
        'Jarvis Island'
    ]
    for keyword in us_pacific_keywords:
        if keyword in rest:
            return True

    return False


def extract_non_us_stations(input_file, output_file):
    """Remove all US stations and save the rest."""

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    non_us_stations = []
    us_count = 0
    non_us_count = 0

    i = 0
    while i < len(lines):
        line1 = lines[i].strip()

        # Check if this is a station line (starts with 't' for tide or 'c' for current)
        if line1 and (line1.startswith('t') or line1.startswith('c')):
            # Get the correction line
            line2 = ''
            has_line2 = False
            if i + 1 < len(lines) and lines[i + 1].strip().startswith('&'):
                line2 = lines[i + 1].strip()
                has_line2 = True

            if is_us_station(line1, line2):
                us_count += 1
                i += 2 if has_line2 else 1
            else:
                non_us_count += 1
                non_us_stations.append(lines[i])
                if has_line2:
                    non_us_stations.append(lines[i + 1])
                i += 2 if has_line2 else 1
        else:
            i += 1

    # Write non-US stations
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(non_us_stations)

    print(f"US stations removed: {us_count}")
    print(f"Non-US stations kept: {non_us_count}")
    print(f"Saved to: {output_file}")

    return non_us_count


if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections.idx'
    output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us.idx'

    extract_non_us_stations(input_file, output_file)
