#!/usr/bin/env python3
"""
Remove incomplete US station blocks (blocks without station name).
"""

def find_block_boundaries(lines):
    """Find start and end of each block."""
    blocks = []
    current_block_start = None

    for i, line in enumerate(lines):
        # A block starts with a comment line after data lines
        if line.startswith('# '):
            # Check if previous line was data (not comment)
            if i > 0 and not lines[i-1].startswith('#'):
                # This is a new block start
                if current_block_start is not None:
                    blocks.append((current_block_start, i - 1))
                current_block_start = i
            elif current_block_start is None:
                current_block_start = i

    # Don't forget the last block
    if current_block_start is not None:
        blocks.append((current_block_start, len(lines) - 1))

    return blocks

def is_incomplete_block(lines, start, end):
    """Check if a block is incomplete (missing station name after latitude)."""
    for i in range(start, min(end + 1, len(lines))):
        if lines[i].startswith('# !latitude:'):
            # Check next line
            if i + 1 <= end:
                next_line = lines[i + 1].strip()
                # If next line starts with - and contains 'knots', it's incomplete
                if next_line.startswith('-') and 'knots' in next_line:
                    return True
                # If next line is empty or a comment, it's incomplete
                if not next_line or next_line.startswith('#'):
                    return True
    return False

def main():
    input_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us2_no_dupes2.txt'

    with open(input_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()

    print(f"Gesamtzahl Zeilen: {len(lines)}")

    # Find all blocks
    blocks = find_block_boundaries(lines)
    print(f"Gefundene Blöcke: {len(blocks)}")

    # Find incomplete blocks
    incomplete = []
    for start, end in blocks:
        if is_incomplete_block(lines, start, end):
            incomplete.append((start, end))

    print(f"Unvollständige Blöcke: {len(incomplete)}")

    if not incomplete:
        print("Keine unvollständigen Blöcke gefunden.")
        return

    # Show first few incomplete blocks
    print("\nBeispiele unvollständiger Blöcke:")
    for start, end in incomplete[:5]:
        print(f"  Zeilen {start+1}-{end+1}: {lines[start].strip()[:50]}...")

    # Remove incomplete blocks
    lines_to_remove = set()
    for start, end in incomplete:
        for i in range(start, end + 1):
            lines_to_remove.add(i)

    print(f"\nEntferne {len(lines_to_remove)} Zeilen...")

    # Create new content without incomplete blocks
    new_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]

    print(f"Neue Zeilenzahl: {len(new_lines)}")

    # Write output
    with open(input_file, 'w', encoding='latin-1') as f:
        f.writelines(new_lines)

    print(f"\nDatei aktualisiert: {input_file}")
    print(f"Entfernte Blöcke: {len(incomplete)}")

if __name__ == '__main__':
    main()
