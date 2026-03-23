#!/usr/bin/env python3
"""
Script to normalize block separators in harmonics files.
Ensures exactly 2 lines with '#' between data blocks (no empty lines or lines with only spaces).
"""

import re
import sys

def normalize_separators(input_file, output_file=None):
    """Normalize block separators to exactly 2 lines with '#'."""

    if output_file is None:
        output_file = input_file.replace('.txt', '_normalized.txt')

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')

    # Find positions where we need to fix separators
    # Pattern: after data lines (x 0 0, constituents, *END*, etc.) and before # comments

    result_lines = []
    i = 0
    fixes = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is a potential separator area
        # (empty line or line with only whitespace between data and next block)
        if stripped == '' or (stripped == '' and line != ''):
            # Collect consecutive empty/whitespace lines
            empty_start = i
            while i < len(lines) and lines[i].strip() == '':
                i += 1

            # Check what comes after
            if i < len(lines) and lines[i].strip().startswith('#'):
                # This is a block separator - normalize to 2 lines with #
                result_lines.append('#')
                result_lines.append('# ')
                fixes += 1
            else:
                # Not a block separator - keep original empty lines
                for j in range(empty_start, i):
                    result_lines.append(lines[j])
        else:
            result_lines.append(line)
            i += 1

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(result_lines))

    print(f"Processed {len(lines)} lines")
    print(f"Fixed {fixes} block separators")
    print(f"Output: {output_file}")

    return fixes


def analyze_separators(input_file):
    """Analyze current separator patterns in the file."""

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    issues = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        # Check for empty lines or whitespace-only lines
        if stripped == '':
            start = i
            count = 0
            has_whitespace = False

            while i < len(lines) and lines[i].strip() == '':
                if lines[i].rstrip('\n') != '':  # Has whitespace
                    has_whitespace = True
                count += 1
                i += 1

            # Check if followed by #
            if i < len(lines) and lines[i].strip().startswith('#'):
                if has_whitespace or count != 2:
                    issues.append({
                        'line': start + 1,
                        'count': count,
                        'has_whitespace': has_whitespace,
                        'next_line': lines[i].strip()[:50] if i < len(lines) else ''
                    })
        else:
            i += 1

    return issues


def main():
    if len(sys.argv) < 2:
        input_file = '/home/oliver/harmonics_working/harmonics_old_no_us_no_dupes3.txt'
    else:
        input_file = sys.argv[1]

    print(f"Analyzing: {input_file}\n")

    issues = analyze_separators(input_file)

    if issues:
        print(f"Found {len(issues)} separator issues:")
        for issue in issues[:20]:  # Show first 20
            ws = " (has whitespace)" if issue['has_whitespace'] else ""
            print(f"  Line {issue['line']}: {issue['count']} empty lines{ws}")
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more")

        print("\nFixing separators...")
        output_file = input_file.replace('.txt', '_normalized.txt')
        normalize_separators(input_file, output_file)
    else:
        print("No separator issues found.")


if __name__ == '__main__':
    main()
