#!/usr/bin/env python3
"""
Add SHOM comparison data for all stations in the ODS file.
"""

import subprocess
import json
import re
import unicodedata
import time
from odf.opendocument import load, OpenDocumentSpreadsheet
from odf.table import Table, TableRow, TableCell
from odf.text import P


def normalize_name(name):
    """Normalize station name for comparison."""
    # Remove accents
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    # Lowercase and remove special chars
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    name = ' '.join(name.split())
    return name


def load_shom_harbors():
    """Load SHOM harbors from JSON file."""
    with open('/home/oliver/shom_harbors.json', 'r') as f:
        return json.load(f)


def find_matching_harbor(station_name, shom_harbors):
    """Find matching SHOM harbor for a station name."""
    # Remove country suffix
    station_clean = re.sub(r',\s*(France|England|United Kingdom|Ireland|Netherlands|Monaco|Italia).*$', '', station_name, flags=re.IGNORECASE)
    station_clean = station_clean.strip()

    # Skip current stations
    if 'Current' in station_name:
        return None

    station_norm = normalize_name(station_clean)

    # Direct mapping for known difficult cases
    direct_mapping = {
        'brest (estuaire penfeld)': 'BREST',
        'cherbourg-en-cotentin': 'CHERBOURG',
        'le havre': 'LE_HAVRE',
        'saint-malo': 'SAINT-MALO',
        'saint-nazaire': 'SAINT-NAZAIRE',
        'la rochelle - la pallice': 'LA_PALLICE',
        'ile d ouessant (baie de lampaul)': 'OUESSANT_LAMPAUL',
        'ile de brehat': 'BREHAT',
        'ile de sein': 'ILE_DE_SEIN',
        'ile molene': 'ILE_MOLENE',
        'granville': 'GRANVILLE',
        'concarneau': 'CONCARNEAU',
        'lorient': 'LORIENT',
        'roscoff': 'ROSCOFF',
        'paimpol': 'PAIMPOL',
        'dieppe': 'DIEPPE',
        'fecamp': 'FECAMP',
        'honfleur': 'HONFLEUR',
        'calais': 'CALAIS',
        'boulogne-sur-mer': 'BOULOGNE-SUR-MER',
        'dunkerque': 'DUNKERQUE',
        'nice': 'NICE',
        'monte carlo': 'MONTE_CARLO',
        'bastia': 'BASTIA',
        'ajaccio': 'AJACCIO',
        'arcachon (jetee eyrac)': 'ARCACHON_EYRAC',
        'royan': 'ROYAN',
        'cordouan': 'CORDOUAN',
        'saint-jean-de-luz': 'SAINT-JEAN-DE-LUZ',
        'boucau-bayonne': 'BOUCAU-BAYONNE',
        'douarnenez': 'DOUARNENEZ',
        'camaret-sur-mer': 'CAMARET-SUR-MER',
        'audierne (quai pelletan)': 'AUDIERNE',
        'le conquet': 'LE_CONQUET',
        'le guilvinec': 'GUILVINEC',
        'loctudy': 'LOCTUDY',
        'benodet (l odet)': 'BENODET',
        'port tudy (ile de groix)': 'PORT_TUDY',
        'le palais (belle-ile)': 'LE_PALAIS',
        'la trinite-sur-mer': 'LA_TRINITE',
        'vannes': 'VANNES',
        'le croisic': 'LE_CROISIC',
        'pornic': 'PORNIC',
        'saint-gilles-croix-de-vie': 'SAINT-GILLES-CROIX-DE-VIE',
        'les sables-d olonne': 'LES_SABLES-D_OLONNE',
        'l herbaudiere (ile de noirmoutier)': 'HERBAUDIERE',
        'port-joinville (ile d yeu)': 'PORT_JOINVILLE',
        'saint-martin-de-re (ile de re)': 'SAINT-MARTIN',
        'ile-d aix frankreich': 'ILE_D_AIX',
        'ouistreham': 'OUISTREHAM',
        'courseulles-sur-mer (large)': 'COURSEULLES-SUR-MER',
        'arromanches-les-bains': 'ARROMANCHES-LES-BAINS',
        'port-en-bessin': 'PORT-EN-BESSIN',
        'grandcamp (entree chenal de carentan)': 'GRANDCAMP',
        'saint-vaast-la-hougue': 'SAINT-VAAST-LA-HOUGUE',
        'barfleur': 'BARFLEUR',
        'carteret': 'CARTERET',
        'divers-sur-mer': 'DIVES-SUR-MER',
        'le treport': 'LE_TREPORT',
        'saint-valery-en-caux': 'SAINT-VALERY-EN-CAUX',
        'etretat': 'ETRETAT',
        'trouville-deauville': 'TROUVILLE',
        'gravelines': 'GRAVELINES',
        'cancale': 'CANCALE',
        'saint-cast': 'SAINT-CAST',
        'erquy': 'ERQUY',
        'dahouet': 'DAHOUET',
        'binic': 'BINIC',
        'saint-quay-portrieux': 'SAINT-QUAY-PORTRIEUX',
        'paimpol': 'PAIMPOL',
        'lezardrieux': 'LEZARDRIEUX',
        'treguier': 'TREGUIER',
        'perros-guirec': 'PERROS-GUIREC',
        'trebeurden': 'TREBEURDEN',
        'locquirec': 'LOCQUIREC',
        'anse de primel': 'PRIMEL',
        'carantec chateau du taureau': 'CARANTEC',
        'brignogan-plage': 'BRIGNOGAN',
        'l aber wrac h': 'ABER_WRAC_H',
        'l aber benoit': 'ABER_BENOIT_MEAN_RENEAT',
        'portsall': 'PORTSALL',
        'l aber ildut': 'ABER_ILDUT',
        'le legue (bouee)': 'LE_LEGUE',
        'morgat': 'MORGAT',
        'banyuls-sur-mer': 'BANYULS',
        'goury': 'GOURY',
        'omonville-la-rogue': 'OMONVILLE-LA-ROGUE',
        'dielette': 'DIELETTE',
        'portbail': 'PORTBAIL',
        'regmeville-sur-mer': 'REGNEVILLE',
        'le senequet': 'LE_SENEQUET',
        'grande-ile (iles chausey)': 'CHAUSEY',
        'saint-germain-sur-ay': 'SAINT-GERMAIN-SUR-AY',
        'ploumanac h': 'PLOUMANACH',
        'les heaux-de-brehat': 'LES_HEAUX_DE_BREHAT',
        'port-beni': 'PORT-BENI',
        'ile des hebihens': 'ILE_DES_HEBIHENS',
        'ile d hoedic': 'HOEDIC',
        'ile d houat': 'HOUAT',
        'penfret (iles de glenan)': 'PENFRET',
        'lesconil': 'LESCONIL',
        'saint-guenole (pointe de penmarch)': 'SAINT-GUENOLE',
        'port d etel': 'ETEL',
        'penerf': 'PENERF',
        'port-haliguen': 'PORT-HALIGUEN',
        'port-maria': 'PORT-MARIA',
        'port-navalo': 'PORT-NAVALO',
        'le logeo': 'LE_LOGEO',
        'saint-armel (le passage)': 'SAINT-ARMEL',
        'arradon': 'ARRADON',
        'auray (st-goustan)': 'AURAY_SAINT-GOUSTAN',
        'trehiguier (la vilaine)': 'TREHIGUIER',
        'le pouliguen': 'LE_POULIGUEN',
        'pornichet': 'PORNICHET',
        'pointe de saint-gildas': 'POINTE_DE_SAINT-GILDAS',
        'fromentine (embarcadere)': 'FROMENTINE',
        'pointe de gatseau': 'POINTE_DE_GATSEAU',
        'lacanau': 'LACANAU',
        'biscarrosse': 'BISCARROSSE',
        'mimizan': 'MIMIZAN',
        'vieux-boucau-les-bains': 'VIEUX-BOUCAU',
        'cap ferret': 'CAP_FERRET',
        'banc de sandettie': 'SANDETTIE_EST',
        'cayeux-sur-mer': 'CAYEUX-SUR-MER',
        'berck plage - fort mahon': 'BOUEE_FORT-MAHON',
        'le touquet-etaples': 'LE_TOUQUET',
        'iles saint-marcouf': 'SAINT-MARCOUF',
        'port-louis (locmalo)': 'PORT-LOUIS',
    }

    # Check direct mapping first
    if station_norm in direct_mapping:
        harbor_code = direct_mapping[station_norm]
        if harbor_code in shom_harbors:
            return harbor_code

    # Try to find by normalized name comparison
    best_match = None
    best_score = 0

    for code, info in shom_harbors.items():
        toponyme_norm = normalize_name(info['toponyme'])

        # Exact match
        if station_norm == toponyme_norm:
            return code

        # Check if station name is contained in toponyme or vice versa
        if station_norm in toponyme_norm or toponyme_norm in station_norm:
            score = len(set(station_norm.split()) & set(toponyme_norm.split()))
            if score > best_score:
                best_score = score
                best_match = code

        # Check word overlap
        station_words = set(station_norm.split())
        toponyme_words = set(toponyme_norm.split())
        overlap = len(station_words & toponyme_words)
        if overlap > best_score and overlap >= 2:
            best_score = overlap
            best_match = code

    return best_match


def fetch_shom_tides(harbor_code, date="2026-01-22", duration=4):
    """Fetch tide predictions from SHOM API."""
    url = f"https://services.data.shom.fr/b2q8lrcdl4s04cbabsj4nhcb/hdm/spm/hlt?harborName={harbor_code}&date={date}&utc=standard&correlation=0&duration={duration}"

    result = subprocess.run([
        'curl', '-s', url,
        '-H', 'Accept: application/json',
        '-H', 'Referer: https://maree.shom.fr/',
        '-H', 'Origin: https://maree.shom.fr'
    ], capture_output=True, text=True)

    try:
        data = json.loads(result.stdout)
        if 'error_code' in data:
            return None
        return data
    except json.JSONDecodeError:
        return None


def extract_tides_flat(tide_data):
    """Extract tide times and levels as flat list."""
    tides = []
    if not tide_data:
        return tides
    for date in sorted(tide_data.keys()):
        for entry in tide_data[date]:
            tide_type, time_str, level, _ = entry
            if time_str != "--:--" and level != "---":
                tides.append({
                    'time': time_str,
                    'level': level
                })
    return tides


def get_cell_text(cell):
    """Extract text from a cell."""
    for p in cell.getElementsByType(P):
        if p.firstChild:
            try:
                return str(p.firstChild.data) if hasattr(p.firstChild, 'data') else str(p.firstChild)
            except:
                return str(p.firstChild)
    return ''


def main():
    input_file = "/home/oliver/harmonics/help/tide_prediction_pierre_lavergne_v10.ods"
    output_file = "/home/oliver/harmonics/help/tide_prediction_pierre_lavergne_v10_with_shom.ods"

    # Load SHOM harbors
    print("Loading SHOM harbors...")
    shom_harbors = load_shom_harbors()
    print(f"Loaded {len(shom_harbors)} SHOM harbors")

    # Load ODS file
    print("Loading ODS file...")
    doc = load(input_file)
    table = doc.spreadsheet.getElementsByType(Table)[0]
    rows = list(table.getElementsByType(TableRow))

    # Get header row
    header_row = rows[0]
    header_cells = list(header_row.getElementsByType(TableCell))
    num_columns = len(header_cells)

    # Collect station data and find SHOM matches
    stations_to_add = []

    for i, row in enumerate(rows[1:], 1):
        cells = list(row.getElementsByType(TableCell))
        if not cells:
            continue

        # Check first cell - if it's "SHOM" or contains URL, skip
        first_cell = get_cell_text(cells[0])
        if first_cell == 'SHOM' or 'maree.shom.fr' in first_cell:
            continue

        # Get station name (second column due to URL column)
        if len(cells) > 1:
            station_name = get_cell_text(cells[1])
        else:
            continue

        # Skip empty rows or header
        if not station_name or station_name == 'Station' or station_name == '':
            continue

        # Find matching SHOM harbor
        harbor_code = find_matching_harbor(station_name, shom_harbors)

        if harbor_code:
            stations_to_add.append({
                'row_index': i,
                'station_name': station_name,
                'harbor_code': harbor_code,
                'shom_info': shom_harbors[harbor_code]
            })
            print(f"  {station_name} -> {harbor_code}")
        else:
            print(f"  {station_name} -> NO MATCH")

    print(f"\nFound {len(stations_to_add)} stations with SHOM matches")

    # Create new document with SHOM comparison rows
    new_doc = OpenDocumentSpreadsheet()
    new_table = Table(name="Tide Predictions")

    # Add header row
    new_header = TableRow()
    for cell in header_cells:
        new_cell = TableCell()
        text = get_cell_text(cell)
        new_cell.addElement(P(text=text))
        new_header.addElement(new_cell)
    new_table.addElement(new_header)

    # Process rows and add SHOM data
    stations_dict = {s['row_index']: s for s in stations_to_add}

    for i, row in enumerate(rows[1:], 1):
        cells = list(row.getElementsByType(TableCell))

        # Copy original row
        new_row = TableRow()
        for cell in cells:
            new_cell = TableCell()
            text = get_cell_text(cell)
            new_cell.addElement(P(text=text))
            new_row.addElement(new_cell)
        new_table.addElement(new_row)

        # Check if this station needs SHOM comparison
        if i in stations_dict:
            station_info = stations_dict[i]
            harbor_code = station_info['harbor_code']
            shom_info = station_info['shom_info']

            print(f"Fetching SHOM data for {harbor_code}...")
            tide_data = fetch_shom_tides(harbor_code)

            if tide_data:
                tides = extract_tides_flat(tide_data)

                # Create SHOM comparison row
                shom_row = TableRow()

                # URL column (empty)
                cell = TableCell()
                cell.addElement(P(text="SHOM"))
                shom_row.addElement(cell)

                # Station name
                cell = TableCell()
                cell.addElement(P(text=f"{shom_info['toponyme']} (SHOM)"))
                shom_row.addElement(cell)

                # Latitude
                cell = TableCell()
                cell.addElement(P(text=str(shom_info['lat']) if shom_info['lat'] else ''))
                shom_row.addElement(cell)

                # Longitude
                cell = TableCell()
                cell.addElement(P(text=str(shom_info['lon']) if shom_info['lon'] else ''))
                shom_row.addElement(cell)

                # Timezone
                cell = TableCell()
                cell.addElement(P(text="Europe/Paris"))
                shom_row.addElement(cell)

                # Constituents (empty)
                cell = TableCell()
                cell.addElement(P(text=""))
                shom_row.addElement(cell)

                # Units
                cell = TableCell()
                cell.addElement(P(text="meters"))
                shom_row.addElement(cell)

                # Add tide times and levels
                for tide in tides:
                    cell = TableCell()
                    cell.addElement(P(text=tide['time']))
                    shom_row.addElement(cell)

                    cell = TableCell()
                    cell.addElement(P(text=tide['level']))
                    shom_row.addElement(cell)

                new_table.addElement(shom_row)
                print(f"  Added {len(tides)} tide events")

            # Small delay to avoid rate limiting
            time.sleep(0.1)

    new_doc.spreadsheet.addElement(new_table)
    new_doc.save(output_file)
    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
