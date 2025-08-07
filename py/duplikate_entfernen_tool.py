
import unicodedata
import re
from geopy.distance import geodesic
from difflib import SequenceMatcher

def normalize_name(text):
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().strip()
    text = re.sub(r"\(\d+\)", "", text)
    text = re.sub(r"- read.*$", "", text)
    return text

def fuzzy_match(a, b, threshold=0.85):
    return SequenceMatcher(None, a, b).ratio() >= threshold

def extract_alternatives(name):
    if not name:
        return set()
    clean = normalize_name(name)
    parts = set()
    parts.add(clean.strip())
    if "(" in clean and ")" in clean:
        inner = clean.split("(")[1].split(")")[0].strip()
        outer = clean.split("(")[0].strip()
        parts.add(inner)
        parts.add(outer)
    if "germany" in clean:
        parts.add(clean.replace("germany", "").strip())
    return parts

def are_probably_duplicates(key1, key2, dist_threshold_km=1.0):
    name1, region1, country1, lat1, lon1, tz1 = key1
    name2, region2, country2, lat2, lon2, tz2 = key2

    if not country1 and "germany" in normalize_name(name1):
        country1 = "Germany"
    if not country2 and "germany" in normalize_name(name2):
        country2 = "Germany"

    if tz1 != tz2:
        return False

    if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
        try:
            if geodesic((lat1, lon1), (lat2, lon2)).km > dist_threshold_km:
                return False
        except:
            return False
    else:
        return False

    names1 = extract_alternatives(name1)
    names2 = extract_alternatives(name2)

    for n1 in names1:
        for n2 in names2:
            if fuzzy_match(n1, n2):
                return True

    return False

def get_constituent_count(path):
    with open(path, 'r', encoding='ISO-8859-1') as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if "# Number of constituents" in line.lower():
            return int(lines[i + 1].strip())
    raise ValueError("Constituent count not found.")

def parse_stations(path):
    count = get_constituent_count(path)
    with open(path, 'r', encoding='ISO-8859-1') as f:
        lines = f.readlines()

    start_idx = 0
    counter = 0
    for i, line in enumerate(lines):
        if "# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE." in line:
            counter += 1
            if counter == 2:
                start_idx = i + 1
                break

    stations = {}
    i = start_idx
    while i < len(lines):
        block = []
        while i < len(lines) and lines[i].startswith("#"):
            block.append(lines[i])
            i += 1

        if i + 2 < len(lines):
            block.extend(lines[i:i+3])
            i += 3
        else:
            break

        if i + count <= len(lines):
            block.extend(lines[i:i+count])
            i += count
        else:
            break

        name_line = tz_line = lat = lon = region = country = None
        for line in block:
            if line.startswith("# country:"):
                country_raw = line.strip().split(":", 1)[1].strip()
                country = country_raw if country_raw else None
            elif line.startswith("# !latitude:"):
                try:
                    lat = float(line.strip().split(":", 1)[1])
                except:
                    lat = None
            elif line.startswith("# !longitude:"):
                try:
                    lon = float(line.strip().split(":", 1)[1])
                except:
                    lon = None
            elif not line.startswith("#"):
                if name_line is None:
                    name_line = line.strip()
                elif tz_line is None:
                    tz_line = line.strip()

        if name_line and tz_line:
            clean_name = name_line.split("- READ")[0].replace("(2)", "").replace("(3)", "").strip()
            parts = clean_name.split(",")
            name = parts[0].strip()
            region = parts[1].strip() if len(parts) >= 2 else None
            if not country and "germany" in clean_name.lower():
                country = "Germany"
            tz = tz_line.split(" ", 1)[1] if " " in tz_line else None
            key = (name, region, country, lat, lon, tz)
            stations[key] = block

        while i < len(lines) and lines[i].strip() == "":
            block.append(lines[i])
            i += 1

    return stations

def remove_duplicates(source_path, reference_path, output_path):
    source = parse_stations(source_path)
    reference = parse_stations(reference_path)

    cleaned_lines = []
    removed_keys = []

    for key, block in source.items():
        if any(are_probably_duplicates(key, rk) for rk in reference):
            removed_keys.append(key)
            continue
        cleaned_lines.extend(block)

    with open(output_path, "w", encoding="ISO-8859-1") as f:
        for line in cleaned_lines:
            f.write(line if line.endswith("\n") else line + "\n")

    print(f"{len(removed_keys)} Duplikate entfernt.")
    return removed_keys

# Beispiel:
# remove_duplicates("harmonics-2004-06-14_no_us_no_dupes.txt",
#                   "harmonics-dwf-20070318_no_us_no_dupes.txt",
#                   "harmonics-2004-06-14_no_us_no_dupes_cleaned.txt")
