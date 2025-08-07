
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

def remove_duplicates(reference_keys, station_dict):
    cleaned_lines = []
    removed_keys = []

    for key, block in station_dict.items():
        if any(are_probably_duplicates(key, ref_key) for ref_key in reference_keys):
            removed_keys.append(key)
            continue
        cleaned_lines.extend(block)

    return cleaned_lines, removed_keys
