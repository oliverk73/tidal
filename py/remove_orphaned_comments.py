#!/usr/bin/env python3
"""
Script to remove orphaned comment blocks from harmonics files.

An orphaned block is a station comment block (containing # !latitude: and # !longitude:)
that has no actual station data (station name, timezone, constituents) following it.
"""

import re
import sys

def find_orphaned_blocks(lines):
    """Find orphaned comment blocks that have no station data."""
    orphaned_ranges = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for start of a potential station comment block
        # These typically contain "# !latitude:" or "# !longitude:"
        if line.startswith('#') and ('# !latitude:' in line or '# !longitude:' in line):
            # Found a comment with coordinates - go back to find block start
            block_start = i
            for j in range(i - 1, max(0, i - 50), -1):
                prev_line = lines[j].strip()
                if prev_line.startswith('#') or not prev_line:
                    block_start = j
                else:
                    # Hit non-comment data from previous station
                    break

            # Now look forward to see if there's station data
            # Station data starts with a non-comment, non-empty line that looks like a station name
            block_end = i + 1
            has_station_data = False

            for j in range(i + 1, min(len(lines), i + 10)):
                next_line = lines[j].strip()

                if not next_line:
                    # Empty line - continue
                    block_end = j + 1
                    continue
                elif next_line.startswith('#'):
                    # Another comment - this might be start of next block
                    # Check if it looks like a new station block
                    if '# Merged from' in next_line or '# This entry was converted' in next_line:
                        # Start of next station block - current block is orphaned
                        block_end = j
                        break
                    else:
                        block_end = j + 1
                else:
                    # Non-comment line - this is station data
                    has_station_data = True
                    break

            if not has_station_data:
                # This block has no station data - it's orphaned
                orphaned_ranges.append((block_start, block_end))
                i = block_end
                continue

        i += 1

    return orphaned_ranges


def remove_orphaned_blocks(input_file, output_file):
    """Remove orphaned comment blocks from the file."""
    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    orphaned = find_orphaned_blocks(lines)

    if not orphaned:
        print("No orphaned comment blocks found.")
        return 0

    print(f"Found {len(orphaned)} orphaned comment blocks:")
    for start, end in orphaned:
        # Find station name in the block
        station_name = "Unknown"
        for j in range(start, end):
            line = lines[j].strip()
            # Look for pattern like "# STATION NAME, COUNTRY (#1234)"
            match = re.search(r'^#\s+([A-Z][A-Z\s,\-\.\']+)\s*\(#\d+\)', line)
            if match:
                station_name = match.group(1).strip()
                break
        print(f"  Lines {start+1}-{end}: {station_name}")

    # Build set of lines to remove
    lines_to_remove = set()
    for start, end in orphaned:
        for j in range(start, end):
            lines_to_remove.add(j)

    # Write output without orphaned blocks
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, line in enumerate(lines):
            if i not in lines_to_remove:
                f.write(line)

    print(f"\nRemoved {len(lines_to_remove)} lines from {len(orphaned)} orphaned blocks.")
    print(f"Output written to: {output_file}")

    return len(orphaned)


def main():
    if len(sys.argv) < 2:
        # Default files
        input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
        output_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3_cleaned.txt'
    elif len(sys.argv) == 2:
        input_file = sys.argv[1]
        output_file = input_file.replace('.txt', '_cleaned.txt')
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2]

    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    print()

    remove_orphaned_blocks(input_file, output_file)


if __name__ == '__main__':
    main()
