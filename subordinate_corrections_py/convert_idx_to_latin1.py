#!/usr/bin/env python3
"""
Convert harmonic_subordinate_corrections idx file from mixed UTF-8/Latin-1 to pure Latin-1.
"""

import sys

def convert_to_latin1(input_file, output_file):
    with open(input_file, 'rb') as f:
        data = f.read()

    print(f"Input: {input_file}")
    print(f"Original size: {len(data)} bytes")

    # Step 1: Fix the broken character (E2 80 9D should be ö for Tönning)
    # U+201D (right double quote) -> ö (0xF6)
    data = data.replace(b'\xe2\x80\x9d', b'\xf6')
    print("Fixed: Tönning (replaced broken U+201D with ö)")

    # Step 2: Convert UTF-8 sequences to Latin-1
    # Map of UTF-8 2-byte sequences to Latin-1 single bytes
    utf8_to_latin1 = {
        b'\xc3\xa0': b'\xe0',  # à
        b'\xc3\xa1': b'\xe1',  # á
        b'\xc3\xa3': b'\xe3',  # ã
        b'\xc3\xa5': b'\xe5',  # å
        b'\xc3\xa7': b'\xe7',  # ç
        b'\xc3\xa8': b'\xe8',  # è
        b'\xc3\xa9': b'\xe9',  # é
        b'\xc3\xad': b'\xed',  # í
        b'\xc3\xb3': b'\xf3',  # ó
        b'\xc3\xb4': b'\xf4',  # ô
        b'\xc3\xb6': b'\xf6',  # ö
        b'\xc3\xb8': b'\xf8',  # ø
        b'\xc3\xbc': b'\xfc',  # ü
        b'\xc3\x8e': b'\xce',  # Î
    }

    for utf8_seq, latin1_byte in utf8_to_latin1.items():
        count = data.count(utf8_seq)
        if count > 0:
            data = data.replace(utf8_seq, latin1_byte)
            char = latin1_byte.decode('latin-1')
            print(f"Converted: {char} ({count}x)")

    # Step 3: Verify result
    # Check for remaining high bytes that look like UTF-8
    remaining_utf8 = 0
    i = 0
    while i < len(data):
        if data[i] >= 0xC0 and data[i] < 0xF0:
            if i + 1 < len(data) and 0x80 <= data[i + 1] <= 0xBF:
                remaining_utf8 += 1
                print(f"  Warning: Possible remaining UTF-8 at pos {i}: {data[i:i+2].hex()}")
        i += 1

    if remaining_utf8 > 0:
        print(f"\nWarning: {remaining_utf8} possible UTF-8 sequences remain!")
    else:
        print("\nAll UTF-8 sequences converted successfully!")

    # Save result
    with open(output_file, 'wb') as f:
        f.write(data)

    print(f"\nOutput: {output_file}")
    print(f"New size: {len(data)} bytes")
    print(f"Saved: {304570 - len(data)} bytes")

    # Verify the output is valid Latin-1
    try:
        text = data.decode('latin-1')
        print("\nVerification: Output is valid Latin-1 ✓")

        # Show some examples
        if 'Tönning' in text:
            print("  - Tönning: OK")
        if 'Steubenhöft' in text:
            print("  - Steubenhöft: OK")
        if 'Québec' in text:
            print("  - Québec: OK")

    except Exception as e:
        print(f"\nError: {e}")

if __name__ == '__main__':
    input_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9.idx'
    output_file = '/home/oliver/subordinate_corrections/harmonic_subordinate_corrections_no_us_no_dupes9_latin1.idx'

    convert_to_latin1(input_file, output_file)
