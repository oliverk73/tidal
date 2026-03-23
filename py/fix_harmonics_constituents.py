#!/usr/bin/env python3
"""
Fix harmonics file by adding missing constituents as 'x 0 0' placeholders.
XTide expects exactly 175 constituents per station in the correct order.
"""
import sys
import re

# The 175 constituents in the exact order from the harmonics header
CONSTITUENTS = [
    "J1", "K1", "K2", "L2", "M1", "M2", "M3", "M4", "M6", "M8",
    "N2", "2N2", "O1", "OO1", "P1", "Q1", "2Q1", "R2", "S1", "S2",
    "S4", "S6", "T2", "LDA2", "MU2", "NU2", "RHO1", "MK3", "2MK3", "MN4",
    "MS4", "2SM2", "MF", "MSF", "MM", "SA", "SSA", "SA-IOS", "MF-IOS", "S1-IOS",
    "OO1-IOS", "R2-IOS", "A7", "2MK5", "2MK6", "2MN2", "2MN6", "2MS6", "2NM6", "2SK5",
    "2SM6", "3MK7", "3MN8", "3MS2", "3MS4", "3MS8", "ALP1", "BET1", "CHI1", "H1",
    "H2", "KJ2", "ETA2", "KQ1", "UPS1", "M10", "M12", "MK4", "MKS2", "MNS2",
    "EPS2", "MO3", "MP1", "TAU1", "MPS2", "MSK6", "MSM", "MSN2", "MSN6", "NLK2",
    "NO1", "OP2", "OQ2", "PHI1", "KP1", "PI1", "TK1", "PSI1", "RP1", "S3",
    "SIG1", "SK3", "SK4", "SN4", "SNK6", "SO1", "SO3", "THE1", "2PO1", "2NS2",
    "MLN2S2", "2ML2S2", "SKM2", "2MS2K2", "MKL2S2", "M2(KS)2", "2SN(MK)2", "2KM(SN)2", "NO3", "2MLS4",
    "ML4", "N4", "SL4", "MNO5", "2MO5", "MSK5", "3KM5", "2MP5", "3MP5", "MNK5",
    "2NMLS6", "MSL6", "2ML6", "2MNLS6", "3MLS6", "2MNO7", "2NMK7", "2MSO7", "MSKO7", "2MSN8",
    "2(MS)8", "2(MN)8", "2MSL8", "4MLS8", "3ML8", "3MK8", "2MSK8", "2M2NK9", "3MNK9", "4MK9",
    "3MSK9", "4MN10", "3MNS10", "4MS10", "3MSL10", "3M2S10", "4MSK11", "4MNS12", "5MS12", "4MSL12",
    "4M2S12", "M1C", "3MKS2", "OQ2-HORN", "MSK2", "MSP2", "2MP3", "4MS4", "2MNS4", "2MSK4",
    "3MN4", "2MSN4", "3MK5", "3MO5", "3MNS6", "4MS6", "2MNU6", "3MSK6", "MKNU6", "3MSN6",
    "M7", "2MNK8", "2(MS)N10", "MNUS2", "2MK2"
]

def parse_station_constituents(lines):
    """Parse constituent data from station lines, return dict name -> (amp, phase)"""
    constituents = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Match constituent line: NAME amplitude phase
        match = re.match(r'^([A-Z0-9\(\)\-]+)\s+(\d+\.\d+)\s+(\d+\.\d+)$', line)
        if match:
            name, amp, phase = match.groups()
            constituents[name] = (amp, phase)
    return constituents


def format_station_with_all_constituents(station_data, station_constituents):
    """Format station with all 175 constituents in order."""
    output_lines = []

    # Output station metadata (comments before station name)
    for line in station_data['comments']:
        output_lines.append(line)

    # Station name
    output_lines.append(station_data['name'])

    # Timezone
    output_lines.append(station_data['timezone'])

    # Datum
    output_lines.append(station_data['datum'])

    # All 175 constituents in order
    for const in CONSTITUENTS:
        if const in station_constituents:
            amp, phase = station_constituents[const]
            output_lines.append(f"{const:16s} {amp}  {phase}")
        else:
            output_lines.append("x 0 0")

    return output_lines


def process_harmonics_file(input_file, output_file):
    """Process harmonics file, adding missing constituents."""

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output_lines = []
    i = 0
    in_stations = False
    second_end_found = False
    end_count = 0

    while i < len(lines):
        line = lines[i].rstrip('\n\r')

        # Track *END* markers
        if line == '*END*':
            end_count += 1
            output_lines.append(line)
            if end_count == 2:
                second_end_found = True
                in_stations = True
            i += 1
            continue

        # Before stations section, just copy lines
        if not in_stations:
            output_lines.append(line)
            i += 1
            continue

        # In stations section - look for station blocks
        # Station block starts with comments, then station name, timezone, datum, constituents

        # Check if this is a station name (not starting with # and contains comma)
        if not line.startswith('#') and ', ' in line and not line.startswith('x '):
            # Found a station name - collect the whole station block

            # Collect comments before this station (go back)
            comments = []
            j = len(output_lines) - 1
            while j >= 0 and output_lines[j].startswith('#'):
                comments.insert(0, output_lines[j])
                j -= 1
            # Remove those comments from output (we'll re-add them formatted)
            output_lines = output_lines[:j+1]

            station_name = line
            i += 1

            # Timezone
            timezone = lines[i].rstrip('\n\r')
            i += 1

            # Datum
            datum = lines[i].rstrip('\n\r')
            i += 1

            # Collect constituent lines until we hit a comment or empty line
            constituent_lines = []
            while i < len(lines):
                cline = lines[i].rstrip('\n\r')
                if cline.startswith('#') or cline == '':
                    break
                constituent_lines.append(cline)
                i += 1

            # Parse constituents
            station_constituents = parse_station_constituents(constituent_lines)

            # Format with all 175 constituents
            station_data = {
                'comments': comments,
                'name': station_name,
                'timezone': timezone,
                'datum': datum
            }
            formatted = format_station_with_all_constituents(station_data, station_constituents)
            output_lines.extend(formatted)
        else:
            # Just a comment or other line
            output_lines.append(line)
            i += 1

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(line + '\n')

    print(f"Processed {input_file}")
    print(f"Output written to {output_file}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_file> <output_file>")
        sys.exit(1)

    process_harmonics_file(sys.argv[1], sys.argv[2])
