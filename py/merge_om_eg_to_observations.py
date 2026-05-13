#!/usr/bin/env python3
"""
Merge harmonics_utide_om_eg.txt into harmonics_utide_observations.txt.

Strategy: find each "# Harmonic constants" line in the source file, take the
block from that line until the next such line (or EOF). For each block,
identify the station name line (first non-comment, non-tz, non-meters line
following the comment header), check it isn't already in the production file,
and append.
"""
from pathlib import Path
import re

NEW_FILE = Path('/home/oliver/harmonics/utide/harmonics_utide_om_eg.txt')
PROD_FILE = Path('/home/oliver/harmonics/utide/harmonics_utide_observations.txt')


def extract_blocks(text):
    """Yield (station_name, block_text). A block starts at '# Harmonic constants'
    and ends just before the next such line, or at EOF."""
    lines = text.split('\n')
    starts = [i for i, l in enumerate(lines) if l.startswith('# Harmonic constants')]
    starts.append(len(lines))
    blocks = []
    for k in range(len(starts) - 1):
        block_lines = lines[starts[k]:starts[k+1]]
        # Find station name: first line that doesn't start with '#' or '+' and isn't '<float> meters'
        name = None
        for line in block_lines:
            if line.startswith('#') or line.startswith('+') or not line.strip():
                continue
            if re.match(r'^[\d.+-]+\s+meters?$', line):
                continue
            # First valid candidate IS the name
            name = line.strip()
            break
        if name:
            # Drop trailing empty lines
            while block_lines and not block_lines[-1].strip():
                block_lines.pop()
            blocks.append((name, '\n'.join(block_lines)))
    return blocks


def existing_station_names(text):
    """Pull all station-name lines."""
    names = set()
    in_header = False
    for line in text.split('\n'):
        if line.startswith('# BEGIN HOT COMMENTS'):
            in_header = True
            continue
        if in_header and not line.startswith('#') and not line.startswith('+') and line.strip():
            if not re.match(r'^[\d.+-]+\s+meters?$', line):
                names.add(line.strip())
                in_header = False
    return names


def main():
    new_text = NEW_FILE.read_text(encoding='latin-1')
    prod_text = PROD_FILE.read_text(encoding='latin-1')

    blocks = extract_blocks(new_text)
    existing = existing_station_names(prod_text)

    print(f"Blocks in new file: {len(blocks)}")
    print(f"Existing stations in observations.txt: {len(existing)}")

    to_add = []
    skipped = []
    for name, block in blocks:
        if name in existing:
            skipped.append(name)
        else:
            to_add.append((name, block))

    print(f"\nTo add: {len(to_add)}")
    for n, _ in to_add:
        print(f"  + {n}")
    print(f"\nSkipped (already present): {len(skipped)}")
    for n in skipped:
        print(f"  = {n}")

    if not to_add:
        print("\nNothing to merge.")
        return

    if not prod_text.endswith('\n'):
        prod_text += '\n'
    for _, block in to_add:
        prod_text += '\n' + block.rstrip() + '\n'

    PROD_FILE.write_text(prod_text, encoding='latin-1')
    print(f"\nWrote {len(to_add)} new blocks to {PROD_FILE}")


if __name__ == '__main__':
    main()
