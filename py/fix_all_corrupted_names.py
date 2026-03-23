#!/usr/bin/env python3
"""
Fix all corrupted station names in harmonics file.
Includes Icelandic, Québec/French-Canadian, and Faroese stations.
"""

import re

# All corrections - corrupted pattern -> correct text
PATTERNS = {
    # === ICELANDIC ===
    '(Ing�lfsgar�ur': '(Ingólfsgarður',
    'Grundarfj�r�ur,': 'Grundarfjörður,',
    'Hornafj�r�ur,': 'Hornafjörður,',
    'H�fn': 'Höfn',
    'H�lmav�k,': 'Hólmavík,',
    'H�sav�k,': 'Húsavík,',
    'K�pasker,': 'Kópasker,',
    'Njar�v�k,': 'Njarðvík,',
    'Patreksfj�r�ur,': 'Patreksfjörður,',
    'Sandger�i,': 'Sandgerði,',
    'Sau��rkr�kur,': 'Sauðárkrókur,',
    'Sey�isfj�r�ur,': 'Seyðisfjörður,',
    'Siglufj�r�ur,': 'Siglufjörður,',
    'Skagastr�nd,': 'Skagaströnd,',
    'Vopnafj�r�ur,': 'Vopnafjörður,',
    '�ingeyri,': 'Þingeyri,',
    '�lafsfj�r�ur,': 'Ólafsfjörður,',
    '�safj�r�ur,': 'Ísafjörður,',
    '�sland': 'Ísland',

    # === FAROESE ===
    'F�r�erne': 'Færøerne',
    'T�rshavn,': 'Tórshavn,',
    'Klaksv�k,': 'Klaksvík,',
    'S�rv�gur,': 'Sørvágur,',
    'V�gar,': 'Vágar,',
    'V�gur,': 'Vágur,',
    'Su�uroy,': 'Suðuroy,',
    'Ei�i,': 'Eiði,',
    'Ei�sv�k,': 'Eiðsvík,',
    'Vi�oy,': 'Viðoy,',
    'Gamlar�tt,': 'Gamlarætt,',
    'Nor�rag�ta,': 'Norðragøta,',
    'Oyrargj�gv,': 'Oyrargjógv,',
    'Bor�oy,': 'Borðoy,',

    # === QUÉBEC / FRENCH-CANADIAN ===
    'Qu�bec,': 'Québec,',
    'Gasp�': 'Gaspé',
    'Gasp�,': 'Gaspé,',
    'Rivi�re': 'Rivière',
    'Rivi�re,': 'Rivière,',
    'Rivi�re-Du-Loup,': 'Rivière-Du-Loup,',
    'Grande-Rivi�re,': 'Grande-Rivière,',
    'Trois-Rivi�res,': 'Trois-Rivières,',
    'Grande-Vall�e,': 'Grande-Vallée,',
    'Grande-�le,': 'Grande-Île,',
    '�le': 'Île',
    '�le-Brion,': 'Île-Brion,',
    'Saint-Ir�n�e,': 'Saint-Irénée,',
    "Saint-Laurent-d'Orl�ans,": "Saint-Laurent-d'Orléans,",
    'Sainte-Anne-de-Beaupr�,': 'Sainte-Anne-de-Beaupré,',
    'Pointe-au-P�re,': 'Pointe-au-Père,',
    'Pasp�biac,': 'Paspébiac,',
    'Tabati�re,': 'Tabatière,',
    'Li�vres,': 'Lièvres,',
    'GLotbini�re': 'Lotbinière',
    'bl�),': 'blé),',
    'moulin � bl': 'moulin à bl',
    'T�te-a-la-Baleine,': 'Tête-à-la-Baleine,',

    # Single replacement character (for comments etc.)
    '�': 'í',  # Most common single replacement - handle carefully
}

def fix_all_names(input_file, output_file):
    """Read file and fix all corrupted names."""

    with open(input_file, 'rb') as f:
        content = f.read()

    text = content.decode('utf-8', errors='replace')

    total_replacements = 0

    # Apply replacements (longer patterns first to avoid partial matches)
    sorted_patterns = sorted(PATTERNS.items(), key=lambda x: -len(x[0]))

    for corrupted, correct in sorted_patterns:
        if corrupted == '�':  # Skip single char for now
            continue
        count = text.count(corrupted)
        if count > 0:
            text = text.replace(corrupted, correct)
            print(f"  '{corrupted}' -> '{correct}' ({count}x)")
            total_replacements += count

    # Check for remaining issues
    remaining = re.findall(r'^[^#\n][^\n]*\ufffd[^\n]*$', text, re.MULTILINE)
    if remaining:
        print(f"\n  Still {len(remaining)} lines with replacement characters:")
        for line in sorted(set(remaining))[:20]:
            print(f"    {line}")

    # Convert to ISO-8859-1 for output (original file encoding)
    with open(output_file, 'w', encoding='iso-8859-1') as f:
        f.write(text)

    print(f"\nTotal replacements: {total_replacements}")
    print(f"Output: {output_file} (ISO-8859-1)")

    return total_replacements, remaining

if __name__ == '__main__':
    input_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2.txt'
    output_file = '/home/oliver/harmonics_working/harmonics-2004-06-14_no_us_no_dupes2_fixed.txt'

    print("Fixing all corrupted station names...")
    print("=" * 60)

    fix_all_names(input_file, output_file)
