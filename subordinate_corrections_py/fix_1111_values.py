#!/usr/bin/env python3
"""
Fix 1111 and 111.1 placeholder values in subordinate corrections file.

Rules:
1. If lmin=1111 and hmin!=1111: lmin = hmin
2. If loff=111.1 and hoff!=111.1: loff = hoff
3. If both hmin=1111 AND lmin=1111: both = 0
4. If hoff=111.1 and/or loff=111.1: those values = 0
"""

import re

input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9_ref_mapped_no_1111.idx'
output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9_ref_mapped_fixed.idx'

def fix_correction_line(line):
    """Fix a correction line starting with &"""
    if not line.startswith('&'):
        return line, False

    parts = line.split()
    if len(parts) < 7:
        return line, False

    # Format: &hmin hmult hoff lmin lmult loff ...
    # Position: 0     1     2    3    4     5
    modified = False

    try:
        hmin = int(parts[0][1:])  # Remove & prefix
        hmult = float(parts[1])
        hoff = float(parts[2])
        lmin = int(parts[3])
        lmult = float(parts[4])
        loff = float(parts[5])
    except ValueError:
        # Try with comma as decimal separator
        try:
            hmin = int(parts[0][1:])
            hmult = float(parts[1].replace(',', '.'))
            hoff = float(parts[2].replace(',', '.'))
            lmin = int(parts[3])
            lmult = float(parts[4].replace(',', '.'))
            loff = float(parts[5].replace(',', '.'))
        except ValueError:
            return line, False

    original_values = (hmin, hoff, lmin, loff)

    # Rule 3: If both hmin=1111 AND lmin=1111: both = 0
    if hmin == 1111 and lmin == 1111:
        hmin = 0
        lmin = 0
        modified = True
    # Rule 1: If only lmin=1111: lmin = hmin
    elif lmin == 1111:
        lmin = hmin
        modified = True
    # Rule 1b: If only hmin=1111: hmin = lmin
    elif hmin == 1111:
        hmin = lmin
        modified = True

    # Rule 4: If hoff=111.1: hoff = 0
    if abs(hoff - 111.1) < 0.01:
        hoff = 0
        modified = True

    # Rule 2 & 4: If loff=111.1
    if abs(loff - 111.1) < 0.01:
        # If hoff was also 111.1 (now 0), use 0
        if abs(original_values[1] - 111.1) < 0.01:
            loff = 0
        else:
            # Otherwise use hoff value
            loff = hoff
        modified = True

    if modified:
        # Reconstruct the line
        rest = ' '.join(parts[6:])

        # Format numbers properly
        def format_num(val, is_int=False):
            if is_int:
                return str(int(val))
            elif val == int(val):
                return str(int(val))
            else:
                return str(val)

        new_line = f"&{format_num(hmin, True)} {format_num(hmult)} {format_num(hoff)} {format_num(lmin, True)} {format_num(lmult)} {format_num(loff)} {rest}"
        return new_line, True

    return line, False

# Process the file
changes = []
with open(input_file, 'r', encoding='iso-8859-1') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    line = line.rstrip('\n')
    new_line, modified = fix_correction_line(line)
    new_lines.append(new_line)
    if modified:
        changes.append((i+1, line, new_line))

# Write output
with open(output_file, 'w', encoding='iso-8859-1') as f:
    f.write('\n'.join(new_lines))
    f.write('\n')

# Print changes
print(f"Total lines processed: {len(lines)}")
print(f"Lines modified: {len(changes)}")
print("\nChanges made:")
for line_num, old, new in changes:
    print(f"\nLine {line_num}:")
    print(f"  OLD: {old}")
    print(f"  NEW: {new}")
