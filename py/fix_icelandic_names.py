#!/usr/bin/env python3
"""
Fix corrupted Icelandic station names in harmonics file.
The original characters were replaced by UTF-8 replacement characters (U+FFFD).
"""

import re

# Mapping of corrupted names to correct Icelandic names
# Using the exact patterns extracted from the file
ICELANDIC_CORRECTIONS = {
    'Akureyri, \ufffdsland': 'Akureyri, Ísland',
    'Grundarfj\ufffdr\ufffdur, \ufffdsland': 'Grundarfjörður, Ísland',
    'H\ufffdfn in Hornafj\ufffdr\ufffdur, \ufffdsland': 'Höfn in Hornafjörður, Ísland',
    'H\ufffdlmav\ufffdk, \ufffdsland': 'Hólmavík, Ísland',
    'H\ufffdsav\ufffdk, \ufffdsland': 'Húsavík, Ísland',
    'K\ufffdpasker, \ufffdsland': 'Kópasker, Ísland',
    'Njar\ufffdv\ufffdk, \ufffdsland': 'Njarðvík, Ísland',
    'Patreksfj\ufffdr\ufffdur, \ufffdsland': 'Patreksfjörður, Ísland',
    'Reykjavik (Ing\ufffdlfsgar\ufffdur Lighthouse), \ufffdsland': 'Reykjavik (Ingólfsgarður Lighthouse), Ísland',
    'Reykjavik (Container Terminal), \ufffdsland': 'Reykjavik (Container Terminal), Ísland',
    'Sandger\ufffdi, \ufffdsland': 'Sandgerði, Ísland',
    'Sau\ufffd\ufffdrk\ufffdkur, \ufffdsland': 'Sauðárkrókur, Ísland',
    'Sau\ufffd\ufffdrkr\ufffdkur, \ufffdsland': 'Sauðárkrókur, Ísland',  # Alternative pattern
    'Sey\ufffdisfj\ufffdr\ufffdur, \ufffdsland': 'Seyðisfjörður, Ísland',
    'Siglufj\ufffdr\ufffdur, \ufffdsland': 'Siglufjörður, Ísland',
    'Skagastr\ufffdnd, \ufffdsland': 'Skagaströnd, Ísland',
    'Vopnafj\ufffdr\ufffdur, \ufffdsland': 'Vopnafjörður, Ísland',
    '\ufffdsafj\ufffdr\ufffdur, \ufffdsland': 'Ísafjörður, Ísland',
    '\ufffdlafsfj\ufffdr\ufffdur, \ufffdsland': 'Ólafsfjörður, Ísland',
    '\ufffdingeyri, \ufffdsland': 'Þingeyri, Ísland',
    # Also fix the source comment and other comments
    'Sjm\ufffdlingar \ufffdslands': 'Sjómælingar Íslands',
    'REKYJAVIK, \ufffdsland': 'REYKJAVIK, Ísland',
    'REYKJAVIK, \ufffdsland': 'REYKJAVIK, Ísland',
}

def fix_icelandic_names(input_file, output_file):
    """Read file and fix all corrupted Icelandic names."""

    # Read the file as binary first to handle the encoding issues
    with open(input_file, 'rb') as f:
        content = f.read()

    # Decode with UTF-8, replacing errors
    text = content.decode('utf-8', errors='replace')

    # Count replacements
    total_replacements = 0

    # Apply all corrections
    for corrupted, correct in ICELANDIC_CORRECTIONS.items():
        count = text.count(corrupted)
        if count > 0:
            text = text.replace(corrupted, correct)
            print(f"  Replaced: {repr(corrupted)} -> '{correct}' ({count}x)")
            total_replacements += count

    # Also try to catch any remaining patterns with replacement character followed by "sland"
    remaining = re.findall(r'^[^\n]*\ufffd[^\n]*sland[^\n]*$', text, re.MULTILINE)
    if remaining:
        print(f"\n  Warning: {len(remaining)} lines still contain corrupted Ísland patterns:")
        for line in remaining[:10]:
            print(f"    {repr(line.strip())}")

    # Check for any remaining replacement characters in station names (lines not starting with #)
    remaining_all = re.findall(r'^[^#\n][^\n]*\ufffd[^\n]*$', text, re.MULTILINE)
    if remaining_all:
        print(f"\n  Note: {len(remaining_all)} non-comment lines still contain replacement characters")

    # Write the corrected file as UTF-8
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"\nTotal replacements: {total_replacements}")
    print(f"Output written to: {output_file}")

    return total_replacements

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2.txt'
    output_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2_fixed.txt'

    print("Fixing Icelandic station names...")
    print("=" * 60)

    fix_icelandic_names(input_file, output_file)
