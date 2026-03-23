#!/usr/bin/env python3
"""
Remove Hawaii (US) stations from the harmonics file.
"""

import re

def remove_stations(input_path, output_path, patterns_to_remove):
    """Remove station blocks matching the given patterns."""

    with open(input_path, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    # Find all station name lines and their positions
    station_starts = []
    for i, line in enumerate(lines):
        # Station names start with capital letter, contain comma, not a comment
        if not line.startswith('#') and not line.startswith('x ') and re.match(r'^[A-Z][a-z].*,', line.strip()):
            station_starts.append(i)

    # Find blocks to remove
    blocks_to_remove = []

    for i, start_idx in enumerate(station_starts):
        station_name = lines[start_idx].strip()

        # Check if this station matches any removal pattern
        for pattern in patterns_to_remove:
            if pattern in station_name:
                # Find the start of comments for this station (go backwards)
                comment_start = start_idx
                for j in range(start_idx - 1, -1, -1):
                    if lines[j].startswith('#'):
                        comment_start = j
                    else:
                        break

                # Find the end of this station block (next station or end of file)
                if i + 1 < len(station_starts):
                    # Go back from next station to find where comments start
                    next_station = station_starts[i + 1]
                    block_end = next_station
                    for j in range(next_station - 1, start_idx, -1):
                        if lines[j].startswith('#'):
                            block_end = j
                        else:
                            break
                else:
                    block_end = len(lines)

                blocks_to_remove.append((comment_start, block_end, station_name))
                break

    # Remove blocks (in reverse order to maintain indices)
    removed_stations = []
    for start, end, name in sorted(blocks_to_remove, reverse=True):
        removed_stations.append(name)
        del lines[start:end]

    # Write output
    with open(output_path, 'w', encoding='latin-1') as f:
        f.writelines(lines)

    return list(reversed(removed_stations))

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'

    # Patterns to remove (Hawaii = US territory)
    patterns = ['Hawaii']

    removed = remove_stations(input_file, output_file, patterns)

    print(f"Entfernte {len(removed)} Hawaii-Stationen:")
    for name in removed:
        print(f"  - {name}")
