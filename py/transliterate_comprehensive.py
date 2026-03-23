#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

# Comprehensive transliteration mapping
TRANS_MAP = {
    # Macrons and other diacritics
    'ā': 'a', 'ē': 'e', 'ī': 'i', 'ō': 'o', 'ū': 'u',
    'Ā': 'A', 'Ē': 'E', 'Ī': 'I', 'Ō': 'O', 'Ū': 'U',
    
    # Vietnamese
    'Đ': 'D', 'đ': 'd',
    'ạ': 'a', 'ả': 'a', 'ã': 'a', 'ă': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ắ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ấ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẹ': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ê': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ế': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ị': 'i', 'ỉ': 'i', 'ĩ': 'i',
    'ò': 'o', 'ó': 'o', 'ọ': 'o', 'ỏ': 'o', 'õ': 'o', 'ô': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ố': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ớ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ụ': 'u', 'ủ': 'u', 'ũ': 'u', 'ư': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ứ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỵ': 'y', 'ỷ': 'y', 'ỹ': 'y',
    
    # Arabic/Persian diacritics
    'Ḩ': 'H', 'ḩ': 'h',
    'Ţ': 'T', 'ţ': 't',
    'Ş': 'S', 'ş': 's',
    'Ḑ': 'D', 'ḑ': 'd',
    
    # Okina and special apostrophes
    'ʻ': "'", 'ʻ': "'", ''': "'", ''': "'", '`': "'",
    
    # Croatian/Slavic
    'Š': 'S', 'š': 's',
    'Ž': 'Z', 'ž': 'z',
    'Č': 'C', 'č': 'c',
    'Ć': 'C', 'ć': 'c',
    'Đ': 'D', 'đ': 'd',
    
    # Japanese hiragana/katakana - just transliterate to romaji where found
    'し': 'shi', 'ん': 'n', 'み': 'mi', 'な': 'na', 'と': 'to',
}

# Special whole-word replacements for CJK
CJK_REPLACEMENTS = {
    '日本': 'Japan',
    '中国': 'China',
    '千葉市': 'Chiba',
    '上海': 'Shanghai',
    '青岛市': 'Qingdao',
    '硇洲岛': 'Naozhou Dao',
    '那覇港': 'Naha Port',
    '尾道市': 'Onomichi',
    '塩竈': 'Shiogama',
    'しんみなと': 'Shinminato',
    '塘凹': 'Tangao',
    '제주시': 'Jeju',
    '목포': 'Mokpo',
    '부산광역시': 'Busan',
    '울산광역시': 'Ulsan',
    # Russian (Cyrillic)
    'Александровский': 'Aleksandrovskiy',
    'Архангельск': 'Arkhangelsk',
    'Корсаков': 'Korsakov',
    'Остров Топорков': 'Ostrov Toporkova',
    'Советская Гавань': 'Sovetskaya Gavan',
}


def transliterate_text(text):
    """Comprehensive transliteration to ISO-8859-1 compatible characters"""
    result = text
    
    # First, replace whole CJK words
    for cjk, latin in CJK_REPLACEMENTS.items():
        result = result.replace(cjk, latin)
    
    # Then, replace individual characters
    for char, replacement in TRANS_MAP.items():
        result = result.replace(char, replacement)
    
    return result


def main():
    input_file = '/home/oliver/harmonics_working/station_name_corrections_updated.csv'
    output_file = '/home/oliver/harmonics_working/station_name_corrections_final.csv'

    print("🔄 Transliteriere alle Stationen zu ISO-8859-1...")
    
    rows = []
    transliterated_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row_num, row in enumerate(reader, start=2):
            original_full_name = row.get('Full_Corrected_Name', '')
            
            if original_full_name:
                transliterated = transliterate_text(original_full_name)
                
                if transliterated != original_full_name:
                    transliterated_count += 1
                    if transliterated_count <= 10:
                        print(f"✓ Zeile {row_num}: {row['Original_Name'][:40]}")
                        print(f"  {original_full_name} → {transliterated}")
                    
                    row['Full_Corrected_Name'] = transliterated
            
            rows.append(row)

    if transliterated_count > 10:
        print(f"... und {transliterated_count - 10} weitere Transliterationen")

    print(f"\n💾 Schreibe finale CSV-Datei nach {output_file}...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print("\n🧪 Test: Schreibe in ISO-8859-1 Format...")
    test_file = '/home/oliver/harmonics_working/station_name_corrections_iso8859.csv'
    
    failed = []
    for i, row in enumerate(rows, start=2):
        full_name = row.get('Full_Corrected_Name', '')
        if full_name:
            try:
                full_name.encode('iso-8859-1')
            except UnicodeEncodeError as e:
                failed.append((i, row['Original_Name'], full_name, e.object[e.start:e.end]))
    
    if failed:
        print(f"❌ {len(failed)} Einträge können immer noch nicht konvertiert werden:")
        for i, orig, full, char in failed[:20]:
            print(f"   Zeile {i}: {orig[:40]} - Problem: '{char}'")
    else:
        try:
            with open(test_file, 'w', encoding='iso-8859-1', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
                writer.writeheader()
                writer.writerows(rows)
            print(f"✓ ISO-8859-1 Test erfolgreich!")
            print(f"✓ Datei geschrieben: {test_file}")
        except Exception as e:
            print(f"❌ Fehler beim Schreiben: {e}")

    print("\n" + "="*80)
    print("📊 Zusammenfassung:")
    print(f"   Gesamt: {len(rows)} Stationen")
    print(f"   Transliteriert: {transliterated_count}")
    print(f"   Nicht konvertierbar: {len(failed)}")
    print("="*80)


if __name__ == '__main__':
    main()
