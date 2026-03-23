#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re

# Mapping für Ländernamen in Landessprache (lateinisch, ISO 8859-1 kompatibel)
COUNTRY_NAMES_LOCAL = {
    'Brazil': 'Brasil',
    'Spain': 'España',
    'Germany': 'Deutschland',
    'Netherlands': 'The Netherlands',
    'Portugal': 'Portugal',
    'France': 'France',
    'Italy': 'Italia',
    'Greece': 'Elláda',
    'Japan': 'Japan',  # In lateinischer Schrift
    'China': 'China',  # In lateinischer Schrift
    'South Korea': 'South Korea',
    'North Korea': 'North Korea',
    'Norway': 'Norge',
}

# Erweiterte Korrekturen für "not_found" Stationen
MANUAL_CORRECTIONS = {
    # Spanien
    'La Coruna, Spain': ('A Coruña', 'Galicia', 'España', 'high'),
    'Marn, Spain': ('Marín', 'Galicia', 'España', 'high'),
    'Vigo, Spain': ('Vigo', 'Galicia', 'España', 'high'),
    'Vilagarcía de Arousa, Spain': ('Vilagarcía de Arousa', 'Galicia', 'España', 'high'),
    
    # Kanada/Quebec
    'Qubec City, Qubec': ('Québec City', 'Québec', 'Canada', 'high'),
    'Sept-les, Qubec': ('Sept-Îles', 'Québec', 'Canada', 'high'),
    
    # Frankreich
    'Pointe--Pitre, Guadeloupe (2)': ('Pointe-à-Pitre', 'Guadeloupe', 'France', 'high'),
    'Les Heaux de Brehat, France': ('Les Héaux de Bréhat', 'Bretagne', 'France', 'high'),
    'Vieux-Boucau, France': ('Vieux-Boucau-les-Bains', 'Nouvelle-Aquitaine', 'France', 'high'),
    
    # Italien
    'Venezia, Italy (2)': ('Venezia', 'Veneto', 'Italia', 'high'),
    
    # Portugal
    'Viana do Castelo, Portugal': ('Viana do Castelo', 'Norte', 'Portugal', 'high'),
    'Vila Real de Santo Antonio, Portugal': ('Vila Real de Santo António', 'Faro', 'Portugal', 'high'),
    'Vila do Porto, Santa Maria, Azores (2)': ('Vila do Porto', 'Azores', 'Portugal', 'high'),
    
    # Chile
    'Valparaiso, Chile': ('Valparaíso', 'Valparaíso', 'Chile', 'high'),
    
    # China (alte Namen)
    'Swatow, China': ('Shantou', 'Guangdong', 'China', 'high'),
    'Xiamen, China': ('Xiamen', 'Fujian', 'China', 'high'),
    'Yingkou, China': ('Yingkou', 'Liaoning', 'China', 'high'),
    'Wei-Hai-Wei, China': ('Weihai', 'Shandong', 'China', 'high'),
    'Pei-Hai, China': ('Beihai', 'Guangxi', 'China', 'high'),
    'Makung, China': ('Magong', 'Penghu', 'Taiwan', 'high'),
    'Wangjia Wan, China': ('Wangjiawan', 'Shandong', 'China', 'high'),
    'Zhanjiang, China': ('Zhanjiang', 'Guangdong', 'China', 'high'),
    
    # Japan
    'Yokohama, Japan': ('Yokohama', 'Kanagawa', 'Japan', 'high'),
    'Yawata, Japan': ('Yawata', 'Kyoto', 'Japan', 'high'),
    'Miojin Hana, Japan': ('Miojin Hana', 'Nagasaki', 'Japan', 'medium'),
    
    # Malaysia
    'Kuala Trengganu, Malaysia': ('Kuala Terengganu', 'Terengganu', 'Malaysia', 'high'),
    'Tanjong Baram, Malaysia': ('Tanjong Baram', 'Sarawak', 'Malaysia', 'high'),
    'Tanjong Sedili Kechil, Malaysia': ('Tanjong Sedili Kecil', 'Johor', 'Malaysia', 'high'),
    'Sungai Sarawak, Malaysia': ('Sungai Sarawak', 'Sarawak', 'Malaysia', 'high'),
    'Victoria (Labuan), Malaysia': ('Victoria', 'Labuan', 'Malaysia', 'high'),
    
    # Indonesien
    'Menado, Sulawesi, Indonesia': ('Manado', 'North Sulawesi', 'Indonesia', 'high'),
    'Sungai Kutei, Borneo, Indonesia': ('Sungai Kutai', 'East Kalimantan', 'Indonesia', 'high'),
    
    # Korea
    'Kacho To, South Korea': ('Gachodo', 'Jeollanam-do', 'South Korea', 'medium'),
    'Komun Do, South Korea': ('Geomundo', 'Jeollanam-do', 'South Korea', 'medium'),
    'Kunjan, South Korea': ('Gunsan', 'Jeollabuk-do', 'South Korea', 'medium'),
    'Ochong Do, South Korea': ('Ochong-do', 'Chungcheongnam-do', 'South Korea', 'medium'),
    'Samchonpo, South Korea': ('Samcheonpo', 'Gyeongsangnam-do', 'South Korea', 'medium'),
    'Sogwipo, Cheju Do, South Korea': ('Seogwipo', 'Jeju', 'South Korea', 'high'),
    'Sonok Do, South Korea': ('Sorok-do', 'Jeollanam-do', 'South Korea', 'medium'),
    'Taechon, South Korea': ('Taecheon', 'Chungcheongnam-do', 'South Korea', 'medium'),
    'Taehuksan Do, South Korea': ('Daehuksan-do', 'Jeollanam-do', 'South Korea', 'medium'),
    'Tokchok To, South Korea': ('Deokjeok-do', 'Incheon', 'South Korea', 'medium'),
    'Tongyong (Chungmu), South Korea': ('Tongyeong', 'Gyeongsangnam-do', 'South Korea', 'high'),
    'Ulneung Do, South Korea': ('Ulleungdo', 'Gyeongsangbuk-do', 'South Korea', 'high'),
    'Usuyong, South Korea': ('Usuyeong', 'Jeollanam-do', 'South Korea', 'medium'),
    'Wan Do, South Korea': ('Wando', 'Jeollanam-do', 'South Korea', 'high'),
    
    # Nordkorea
    'Taeyonpyong Do, North Korea': ('Taeyonpyong-do', 'South Hwanghae', 'North Korea', 'medium'),
    'Wonsan, North Korea': ('Wonsan', 'Kangwon', 'North Korea', 'high'),
    
    # Indien
    'Nagappattinam, India': ('Nagapattinam', 'Tamil Nadu', 'India', 'high'),
    'Pamban (Passe), India': ('Pamban Pass', 'Tamil Nadu', 'India', 'high'),
    'Paradwip, India': ('Paradeep', 'Odisha', 'India', 'high'),
    'Veraval, India': ('Veraval', 'Gujarat', 'India', 'high'),
    'Vishakhapatnam, India': ('Visakhapatnam', 'Andhra Pradesh', 'India', 'high'),
    
    # Vereinigte Arabische Emirate
    'Jazirat Das, U.A.E.': ('Das Island', 'Abu Dhabi', 'United Arab Emirates', 'high'),
    'Mina Zayed, U.A.E.': ('Mina Zayed', 'Abu Dhabi', 'United Arab Emirates', 'high'),
    
    # Qatar
    'Jazirat Halul, Qatar': ('Halul Island', 'Al Rayyan', 'Qatar', 'high'),
    'Musay'id, Qatar': ('Mesaieed', 'Al Wakrah', 'Qatar', 'high'),
    
    # Kuwait
    'Mina Su`ud, Kuwait': ('Mina Saud', 'Al Ahmadi', 'Kuwait', 'high'),
    
    # Iran
    'Jazireh-ye Khark, Iran': ('Khark Island', 'Bushehr', 'Iran', 'high'),
    
    # Irak
    'Shaat al Arab, Iraq': ('Shatt al-Arab', 'Basra', 'Iraq', 'high'),
    
    # Angola (alter Name)
    'Mocamedes, Angola': ('Namibe', 'Namibe', 'Angola', 'high'),
    
    # Namibia
    'Luderitz Bay, Namibia': ('Lüderitz', 'Karas', 'Namibia', 'high'),
    'Walvis Bay, Namibia': ('Walvis Bay', 'Erongo', 'Namibia', 'high'),
    
    # Nigeria
    'Lagos Bar, Nigeria': ('Lagos Bar', 'Lagos', 'Nigeria', 'medium'),
    
    # Kenia
    'Wasini Island, Kenya': ('Wasini Island', 'Kwale', 'Kenya', 'high'),
    
    # Suriname
    'Nickerie Rivir, Suriname': ('Nickerie River', 'Nickerie', 'Suriname', 'high'),
    
    # Venezuela
    'Malecon, Venezuela': ('El Malecón', 'Zulia', 'Venezuela', 'medium'),
    
    # Brasilien
    'So Francisco do Sul, Brazil': ('São Francisco do Sul', 'Santa Catarina', 'Brasil', 'high'),
    'Salinpolis, Brazil': ('Salinópolis', 'Pará', 'Brasil', 'high'),
    'Tubaro, Brazil': ('Tubarão', 'Santa Catarina', 'Brasil', 'high'),
    'Tutia, Baia da, Brazil': ('Baía de Turiá', 'Maranhão', 'Brasil', 'medium'),
    'Vitria, Brazil': ('Vitória', 'Espírito Santo', 'Brasil', 'high'),
    
    # Ecuador
    'Puerto Bolvar, Ecuador': ('Puerto Bolívar', 'El Oro', 'Ecuador', 'high'),
    'Puerto Lpez, Ecuador': ('Puerto López', 'Manabí', 'Ecuador', 'high'),
    'Puerto de Baha Caraquez, Ecuador': ('Bahía de Caráquez', 'Manabí', 'Ecuador', 'high'),
    'San Cristbal, Galapagos Islands': ('San Cristóbal', 'Galápagos', 'Ecuador', 'high'),
    
    # Argentinien
    'San Romn, Argentina': ('San Román', 'Chubut', 'Argentina', 'medium'),
    'Vancouver, Argentina': ('Puerto Vancouver', 'Tierra del Fuego', 'Argentina', 'medium'),
    
    # Mexiko
    'Puerto ngel, Oaxaca, Mexico': ('Puerto Ángel', 'Oaxaca', 'Mexico', 'high'),
    
    # Äquatorialguinea
    'Puerto Iradier, Equatorial Guinea': ('Puerto Iradier', 'Litoral', 'Equatorial Guinea', 'medium'),
    
    # Myanmar
    'Pulau Besin, Myanmar': ('Pulau Besin', 'Tanintharyi', 'Myanmar', 'medium'),
    
    # Bangladesh
    'Pusur River, Bangladesh': ('Pashur River', 'Khulna', 'Bangladesh', 'high'),
    
    # Thailand
    'Tachin, Thailand': ('Tha Chin River', 'Samut Sakhon', 'Thailand', 'high'),
    
    # Vietnam
    'Vung Tau, Vietnam': ('Vũng Tàu', 'Bà Rịa-Vũng Tàu', 'Vietnam', 'high'),
    
    # Singapur
    'Singapore (Victoria Dock) (2)': ('Victoria Dock', 'Singapore', 'Singapore', 'high'),
    
    # Tonga
    'Nuku`alofa, Tonga (2)': ('Nuku\'alofa', 'Tongatapu', 'Tonga', 'high'),
    
    # Französisch-Polynesien
    'Motuoini, Tahiti': ('Motuoini', 'Windward Islands', 'French Polynesia', 'medium'),
    'Mururoa Atoll, Tuamotu Archipelago': ('Mururoa Atoll', 'Tuamotu-Gambier', 'French Polynesia', 'high'),
    'Taihoae, Marquesas Islands': ('Taiohae', 'Marquesas Islands', 'French Polynesia', 'high'),
    
    # Mikronesien
    'Moen Island, Chuuk, F.S.M.': ('Weno', 'Chuuk', 'Micronesia', 'high'),
    
    # Hawaii (US)
    'Mokuoloe, Kaneohe Bay, Oahu Island, Hawaii': ('Moku o Loʻe', 'Hawaii', 'United States', 'high'),
    
    # Russland
    'Petropavlosk, Russia': ('Petropavlovsk-Kamchatsky', 'Kamchatka Krai', 'Russia', 'high'),
    'Port Kem, Russia': ('Kem', 'Republic of Karelia', 'Russia', 'high'),
    'Yekaterininskaya, Russia': ('Yekaterininskaya Gavan', 'Murmansk Oblast', 'Russia', 'medium'),
    'Zaliv Baykal, Russia': ('Zaliv Baykal', 'Sakhalin Oblast', 'Russia', 'medium'),
    'Zaliv Chikhacheva, Russia': ('Zaliv Chikhacheva', 'Sakhalin Oblast', 'Russia', 'medium'),
    'Rrvik, Norway': ('Rørvik', 'Trøndelag', 'Norge', 'high'),
    'Vard, Norway': ('Vardø', 'Finnmark', 'Norge', 'high'),
    
    # Kroatien
    'Zadar, Croatia': ('Zadar', 'Zadar County', 'Croatia', 'high'),
    
    # Belgien
    'Zeebrugge, Belgium': ('Zeebrugge', 'Flanders', 'Belgium', 'high'),
    
    # England/UK
    'Walton-on-the-Naze, England': ('Walton-on-the-Naze', 'England', 'United Kingdom', 'high'),
    'Wellhouse Rock, River Severn, England': ('Wellhouse Rock', 'England', 'United Kingdom', 'medium'),
    'River Tyne Entrance, England (2)': ('River Tyne Entrance', 'England', 'United Kingdom', 'high'),
    
    # Kanada (British Columbia)
    'Sandheads (Station Harry), British Columbia': ('Sandheads', 'British Columbia', 'Canada', 'high'),
    
    # Falkland Islands
    'Stanley Harbor, Falkland Islands': ('Stanley Harbour', 'East Falkland', 'Falkland Islands', 'high'),
    
    # Papua Neuguinea
    'Port Dreger, Papua New Guinea': ('Dreger Harbour', 'Madang', 'Papua New Guinea', 'medium'),
    'Port Seeadler, Manus, Admiralty Islands': ('Seeadler Harbour', 'Manus', 'Papua New Guinea', 'high'),
    
    # Pakistan
    'Port Muhammad Bin Qasin, Pakistan': ('Port Qasim', 'Sindh', 'Pakistan', 'high'),
    
    # Kapverden
    'Porto Grande, Cape Verde Islands': ('Porto Grande', 'São Vicente', 'Cape Verde', 'high'),
    
    # Westsahara
    'Villa Cisneros, Western Sahara': ('Dakhla', 'Dakhla-Oued Ed-Dahab', 'Western Sahara', 'high'),
    
    # Südliche Shetlandinseln/Antarktis
    'Puerto Soberania, South Shetland Islands': ('Puerto Soberanía', 'Antarctic Peninsula', 'Antarctica', 'medium'),
    'Port Foster, Deception Island, South Shetlands': ('Port Foster', 'South Shetland Islands', 'Antarctica', 'high'),
    'Isla Neny, Antarctica': ('Neny Island', 'Antarctic Peninsula', 'Antarctica', 'medium'),
    
    # Australien
    'Westernport, Australia': ('Western Port', 'Victoria', 'Australia', 'high'),
    
    # Kuba
    'Willemstad, Curaao': ('Willemstad', 'Curaçao', 'Curaçao', 'high'),
    
    # Ägypten
    'Za`farana, Egypt': ('Zafarana', 'Red Sea', 'Egypt', 'high'),
    
    # Tansania
    'Zanzibar, Tanzania': ('Zanzibar', 'Zanzibar Urban/West', 'Tanzania', 'high'),
    
    # Wallis und Futuna
    'les Wallis': ('Wallis Island', 'Wallis', 'Wallis and Futuna', 'high'),
}


def generate_full_corrected_name(row):
    """Generiert den Full_Corrected_Name aus den vorhandenen Daten"""
    corrected_name = row['Corrected_Name'].strip()
    region = row['Corrected_Region'].strip()
    country = row['Corrected_Country'].strip()
    original_name = row['Original_Name'].strip()

    # Ländername in Landessprache konvertieren
    if country in COUNTRY_NAMES_LOCAL:
        country = COUNTRY_NAMES_LOCAL[country]

    # Prüfe, ob Original-Name eine Nummer hat (z.B. "(2)")
    suffix_match = re.search(r'\((\d+)\)$', original_name)
    suffix = f' ({suffix_match.group(1)})' if suffix_match else ''

    # Full_Corrected_Name zusammenbauen
    if region:
        full_name = f"{corrected_name}, {region}, {country}{suffix}"
    else:
        full_name = f"{corrected_name}, {country}{suffix}"

    return full_name


def main():
    input_file = '/home/oliver/harmonics_working/station_name_corrections.csv'
    output_file = '/home/oliver/harmonics_working/station_name_corrections_updated.csv'

    print("🔄 Lade CSV-Datei...")
    rows = []
    corrections_count = 0
    supplements_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            status = row.get('Status', '').strip()
            full_name = row.get('Full_Corrected_Name', '').strip()
            original_name = row.get('Original_Name', '').strip()

            # Fall 1: found Status, aber leerer Full_Corrected_Name
            if status == 'found' and not full_name:
                row['Full_Corrected_Name'] = generate_full_corrected_name(row)
                supplements_count += 1
                if supplements_count <= 5:  # Nur erste 5 anzeigen
                    print(f"✓ Ergänzt: {original_name} → {row['Full_Corrected_Name']}")

            # Fall 2: not_found Status - versuche manuelle Korrekturen anzuwenden
            elif status == 'not_found':
                if original_name in MANUAL_CORRECTIONS:
                    correction = MANUAL_CORRECTIONS[original_name]
                    row['Corrected_Name'] = correction[0]
                    row['Corrected_Region'] = correction[1]
                    row['Corrected_Country'] = correction[2]
                    row['Confidence'] = correction[3]
                    row['Status'] = 'found'
                    row['Full_Corrected_Name'] = generate_full_corrected_name(row)
                    corrections_count += 1
                    print(f"✓ Korrigiert: {original_name} → {row['Full_Corrected_Name']}")

            rows.append(row)

    if supplements_count > 5:
        print(f"... und {supplements_count - 5} weitere Ergänzungen")

    print(f"\n💾 Schreibe korrigierte Daten nach {output_file}...")

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    # Statistik
    found_with_full_name = sum(1 for r in rows if r['Status'] == 'found' and r['Full_Corrected_Name'])
    not_found = sum(1 for r in rows if r['Status'] == 'not_found')

    print("\n" + "="*80)
    print("📊 Statistik:")
    print(f"   Gesamt: {len(rows)} Stationen")
    print(f"   ✓ Gefunden mit Full_Corrected_Name: {found_with_full_name}")
    print(f"   ❌ Noch nicht gefunden: {not_found}")
    print(f"   📝 In dieser Sitzung ergänzt: {supplements_count}")
    print(f"   🔧 In dieser Sitzung korrigiert: {corrections_count}")
    print("="*80)

    # Liste der noch nicht gefundenen Stationen
    if not_found > 0:
        print(f"\n⚠️  Noch nicht gefundene Stationen ({not_found}):")
        print("="*80)
        for i, row in enumerate([r for r in rows if r['Status'] == 'not_found'], 1):
            print(f"{i}. {row['Original_Name']}")
            print(f"   Koordinaten: {row['Original_Lat']}, {row['Original_Lon']}")


if __name__ == '__main__':
    main()
