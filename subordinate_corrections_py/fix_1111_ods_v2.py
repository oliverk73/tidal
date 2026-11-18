#!/usr/bin/env python3
"""
Fix 1111 and 111.1 placeholder values in ODS files by modifying the XML directly.
"""

import zipfile
import re
import os
from io import BytesIO

def fix_ods_file(input_file, output_file):
    """Fix 1111 and 111.1 values in an ODS file by modifying XML directly."""

    # Read the ODS file (it's a ZIP)
    with zipfile.ZipFile(input_file, 'r') as z:
        content = z.read('content.xml').decode('utf-8')
        other_files = {}
        for name in z.namelist():
            if name != 'content.xml':
                other_files[name] = z.read(name)

    # Find all table rows
    # Pattern for a table row
    row_pattern = r'<table:table-row[^>]*>(.*?)</table:table-row>'

    changes = 0

    def fix_row(match):
        nonlocal changes
        row_content = match.group(0)

        # Extract cell values - find cells with numeric values
        # Cell pattern: <table:table-cell office:value-type="float" office:value="VALUE"...><text:p>VALUE</text:p></table:table-cell>
        cell_pattern = r'<table:table-cell[^>]*office:value="([^"]*)"[^>]*><text:p>([^<]*)</text:p></table:table-cell>'

        cells = re.findall(cell_pattern, row_content)

        if len(cells) < 12:
            return row_content

        # Get values (columns: 6=hmin, 8=hoff, 9=lmin, 11=loff)
        # Note: cells might have repeated columns, so we need to track actual positions

        # Simpler approach: find all cell values and their positions
        all_cells = []
        pos = 0
        for m in re.finditer(r'<table:table-cell([^>]*)>(.*?)</table:table-cell>', row_content):
            attrs = m.group(1)
            cell_content = m.group(2)

            # Check for repeated columns
            repeat_match = re.search(r'table:number-columns-repeated="(\d+)"', attrs)
            repeat = int(repeat_match.group(1)) if repeat_match else 1

            # Get value
            value_match = re.search(r'office:value="([^"]*)"', attrs)
            value = value_match.group(1) if value_match else None

            for _ in range(repeat):
                all_cells.append({'pos': pos, 'value': value, 'match': m, 'attrs': attrs, 'content': cell_content})
                pos += 1

        if len(all_cells) < 12:
            return row_content

        # Get the relevant values
        try:
            hmin_val = float(all_cells[6]['value']) if all_cells[6]['value'] else None
            hoff_val = float(all_cells[8]['value']) if all_cells[8]['value'] else None
            lmin_val = float(all_cells[9]['value']) if all_cells[9]['value'] else None
            loff_val = float(all_cells[11]['value']) if all_cells[11]['value'] else None
        except (ValueError, TypeError):
            return row_content

        if hmin_val is None or lmin_val is None:
            return row_content

        new_row = row_content
        modified = False

        # Fix minutes
        if hmin_val == 1111 and lmin_val == 1111:
            # Both are 1111 -> set to 0
            new_row = fix_cell_value(new_row, 6, all_cells, '0')
            new_row = fix_cell_value(new_row, 9, all_cells, '0')
            modified = True
        elif lmin_val == 1111:
            # lmin=1111 -> use hmin
            new_row = fix_cell_value(new_row, 9, all_cells, str(int(hmin_val)))
            modified = True
        elif hmin_val == 1111:
            # hmin=1111 -> use lmin
            new_row = fix_cell_value(new_row, 6, all_cells, str(int(lmin_val)))
            modified = True

        # Fix offsets
        hoff_is_111 = hoff_val is not None and abs(hoff_val - 111.1) < 0.1
        loff_is_111 = loff_val is not None and abs(loff_val - 111.1) < 0.1

        if hoff_is_111 and loff_is_111:
            new_row = fix_cell_value(new_row, 8, all_cells, '0')
            new_row = fix_cell_value(new_row, 11, all_cells, '0')
            modified = True
        elif loff_is_111:
            new_row = fix_cell_value(new_row, 11, all_cells, str(hoff_val))
            modified = True
        elif hoff_is_111:
            new_row = fix_cell_value(new_row, 8, all_cells, str(loff_val))
            modified = True

        if modified:
            changes += 1

        return new_row

    def fix_cell_value(row_content, target_col, all_cells, new_value):
        """Replace value in a specific cell column."""
        cell = all_cells[target_col]
        old_match = cell['match']
        old_text = old_match.group(0)

        # Create new cell with updated value
        new_attrs = re.sub(r'office:value="[^"]*"', f'office:value="{new_value}"', cell['attrs'])
        new_content = re.sub(r'<text:p>[^<]*</text:p>', f'<text:p>{new_value}</text:p>', cell['content'])

        new_text = f'<table:table-cell{new_attrs}>{new_content}</table:table-cell>'

        return row_content.replace(old_text, new_text, 1)

    # Process all rows
    new_content = re.sub(row_pattern, fix_row, content, flags=re.DOTALL)

    # Write the new ODS file
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('content.xml', new_content.encode('utf-8'))
        for name, data in other_files.items():
            z.writestr(name, data)

    return changes

if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111.ods.backup_before_fix'
    output_file = '/home/oliver/subordinate_corrections/subordinate_stations_tide_prediction3_no_1111_fixed_v2.ods'

    changes = fix_ods_file(input_file, output_file)
    print(f'Total rows modified: {changes}')

    # Verify
    with zipfile.ZipFile(output_file, 'r') as z:
        content = z.read('content.xml').decode('utf-8')

    count_1111 = len(re.findall(r'office:value="1111"', content))
    count_111_1 = len(re.findall(r'office:value="111\.1"', content))
    print(f'Remaining 1111: {count_1111}')
    print(f'Remaining 111.1: {count_111_1}')
