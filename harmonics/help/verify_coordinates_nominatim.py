#!/usr/bin/env python3
"""
Prüft Stationskoordinaten gegen Nominatim.

Strategie zur Vermeidung von False Positives:
1. Forward-Geocoding: Stationsname suchen → Nominatim-Koordinaten
2. Bei Abweichung > Schwellwert: Reverse-Geocoding der gespeicherten Koordinaten
   → Prüfen ob das Land stimmt und was tatsächlich an den Koordinaten liegt
3. Klassifizierung:
   - FEHLER:  Reverse-Geocoding der gespeicherten Koordinaten ergibt falsches Land
   - PRÜFEN:  Forward- und Reverse-Geocoding im richtigen Land, aber Abweichung groß
   - UNKLAR:  Nominatim hat vermutlich den falschen Ort gefunden (mehrdeutiger Name)

Nutzung:
  python3 verify_coordinates_nominatim.py [--threshold 5] [--file classic/harmonics-1997-05-25_mod.txt]
"""

import argparse
import math
import json
import os
import re
import time
import csv
import urllib.request
import urllib.parse
from pathlib import Path

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
USER_AGENT = "TideHarmonicsCoordVerify/1.0 (oliver@tideproject)"
RATE_LIMIT = 1.1  # seconds between requests

HARMONICS_DIR = Path("/home/oliver/harmonics")
EXCLUDE_DIRS = {"backup", "binary", "help", "template"}

DEFAULT_FILES = [
    "classic/harmonics-1997-05-25_mod.txt",
    "classic/harmonics-2004-06-14_mod.txt",
    "classic/harmonics-dwf-20070318_mod.txt",
    "classic/harmonics-dwf-20100529-nonfree_mod.txt",
    "classic/harmonics-pierre-lavergne-v10_mod.txt",
    "classic/harmonics-pierre-lavergne-v9-europe_mod.txt",
    "ticon/harmonics_ticon4_worldwide.txt",
]

OUTPUT_CSV = HARMONICS_DIR / "help" / "coordinate_corrections.csv"

# Map country names to ISO codes
COUNTRY_CODES = {
    "Germany": "de", "France": "fr", "Netherlands": "nl", "Belgium": "be",
    "Denmark": "dk", "Norway": "no", "Sweden": "se", "Finland": "fi",
    "Iceland": "is", "Ireland": "ie", "United Kingdom": "gb", "UK": "gb",
    "England": "gb", "Scotland": "gb", "Wales": "gb",
    "Spain": "es", "Portugal": "pt", "Italy": "it", "Greece": "gr",
    "Turkey": "tr", "Croatia": "hr", "Poland": "pl", "Russia": "ru",
    "Estonia": "ee", "Latvia": "lv", "Lithuania": "lt",
    "USA": "us", "United States": "us", "Canada": "ca", "Mexico": "mx",
    "Brazil": "br", "Argentina": "ar", "Chile": "cl", "Colombia": "co",
    "Peru": "pe", "Uruguay": "uy", "Venezuela": "ve", "Ecuador": "ec",
    "Australia": "au", "New Zealand": "nz", "Japan": "jp", "China": "cn",
    "Taiwan": "tw", "South Korea": "kr", "North Korea": "kp",
    "India": "in", "Pakistan": "pk", "Bangladesh": "bd", "Sri Lanka": "lk",
    "Thailand": "th", "Vietnam": "vn", "Myanmar": "mm", "Cambodia": "kh",
    "Indonesia": "id", "Philippines": "ph", "Malaysia": "my", "Singapore": "sg",
    "South Africa": "za", "Egypt": "eg", "Morocco": "ma", "Tunisia": "tn",
    "Kenya": "ke", "Tanzania": "tz", "Mozambique": "mz", "Angola": "ao",
    "Nigeria": "ng", "Ghana": "gh", "Senegal": "sn", "Madagascar": "mg",
    "Greenland": "gl", "Faroe Islands": "fo", "Kuwait": "kw",
    "Saudi Arabia": "sa", "United Arab Emirates": "ae", "Iran": "ir",
    "Guadeloupe": "gp", "Martinique": "mq", "Reunion": "re",
    "French Guiana": "gf", "New Caledonia": "nc", "French Polynesia": "pf",
    "Azores": "pt", "Madeira": "pt", "Canary Islands": "es",
    "Bahamas": "bs", "Cuba": "cu", "Jamaica": "jm",
    "Eritrea": "er", "Somalia": "so", "Sudan": "sd",
    "Guinea-Bissau": "gw", "Equatorial Guinea": "gq",
    "Papua New Guinea": "pg", "Fiji": "fj", "Tonga": "to", "Samoa": "ws",
}

# Reverse: ISO code → country name(s) for matching
CODE_TO_COUNTRIES = {}
for name, code in COUNTRY_CODES.items():
    CODE_TO_COUNTRIES.setdefault(code, []).append(name)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_country_code(country_name):
    if not country_name:
        return None
    if country_name in COUNTRY_CODES:
        return COUNTRY_CODES[country_name]
    for name, code in COUNTRY_CODES.items():
        if name.lower() in country_name.lower():
            return code
    return None


def nominatim_request(endpoint, params):
    """Generic Nominatim request with rate limiting."""
    url = f"{NOMINATIM_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def forward_geocode(query, country_code=None):
    """Nominatim forward geocoding — search by name."""
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "accept-language": "en",
    }
    if country_code:
        params["countrycodes"] = country_code

    data = nominatim_request("search", params)
    if isinstance(data, list) and data:
        return {
            "lat": float(data[0]["lat"]),
            "lon": float(data[0]["lon"]),
            "display_name": data[0].get("display_name", ""),
            "type": data[0].get("type", ""),
            "country_code": data[0].get("address", {}).get("country_code", ""),
        }
    if isinstance(data, dict) and "error" in data:
        return data
    return None


def reverse_geocode(lat, lon):
    """Nominatim reverse geocoding — what's at these coordinates?"""
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "accept-language": "en",
        "zoom": 10,
        "addressdetails": 1,
    }
    data = nominatim_request("reverse", params)
    if isinstance(data, dict) and "address" in data:
        addr = data["address"]
        return {
            "display_name": data.get("display_name", ""),
            "country": addr.get("country", ""),
            "country_code": addr.get("country_code", ""),
            "place": (addr.get("city") or addr.get("town") or
                      addr.get("village") or addr.get("municipality") or ""),
        }
    if isinstance(data, dict) and "error" in data:
        return {"error": data["error"]}
    return None


def extract_stations(filepath):
    """Extrahiere alle Stationen mit Name und Koordinaten."""
    with open(filepath, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    stations = []
    for i, line in enumerate(lines):
        if not line.strip().startswith("# !latitude:"):
            continue
        lat = float(line.strip().split(":")[1].strip())
        if i > 0 and lines[i - 1].strip().startswith("# !longitude:"):
            lon = float(lines[i - 1].strip().split(":")[1].strip())
        else:
            continue

        name = None
        name_line_idx = None
        for j in range(i + 1, min(i + 5, len(lines))):
            l = lines[j].strip()
            if l and not l.startswith("#"):
                name = l
                name_line_idx = j
                break

        if name:
            country = ""
            for j in range(max(0, i - 20), i):
                m = re.match(r"^#\s+country:\s*(.+)", lines[j].strip())
                if m:
                    country = m.group(1).strip()

            stations.append({
                "name": name,
                "lat": lat,
                "lon": lon,
                "country": country,
                "line": name_line_idx + 1,
                "lat_line": i + 1,
            })

    return stations


def country_matches(expected_country, actual_country_code):
    """Prüfe ob der Ländercode zum erwarteten Land passt."""
    if not expected_country or not actual_country_code:
        return True  # can't verify → assume ok
    expected_cc = get_country_code(expected_country)
    if not expected_cc:
        return True
    return expected_cc == actual_country_code.lower()


def extract_place_name(station_name):
    """Extrahiere den Ortsnamen (vor dem ersten Komma) für die Suche."""
    # "Deauville, France" → "Deauville"
    # "Bahía Magdalena, Baja California Sur, México" → "Bahía Magdalena"
    parts = station_name.split(",")
    place = parts[0].strip()
    # Remove parenthetical like "(Port)" but keep as fallback
    place_clean = re.sub(r"\s*\([^)]*\)\s*", " ", place).strip()
    return place_clean or place


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=5,
                        help="Abweichung in km (Standard: 5)")
    parser.add_argument("--file", type=str, default=None,
                        help="Nur diese Datei prüfen (relativ zu harmonics/)")
    args = parser.parse_args()

    if args.file:
        files = [args.file]
    else:
        files = DEFAULT_FILES

    all_stations = []
    for rel_path in files:
        filepath = HARMONICS_DIR / rel_path
        if not filepath.exists():
            print(f"  WARNUNG: {filepath} nicht gefunden")
            continue
        stations = extract_stations(filepath)
        for s in stations:
            s["file"] = rel_path
        all_stations.extend(stations)
        print(f"  {rel_path}: {len(stations)} Stationen")

    # Skip current stations
    all_stations = [s for s in all_stations if "Current" not in s["name"]]

    # Estimate: 1 request per station + 1 extra for each flagged station
    print(f"\nGesamt: {len(all_stations)} Stationen")
    print(f"Geschätzte Dauer: {len(all_stations) * RATE_LIMIT / 60:.0f}+ Minuten")
    print(f"Schwellwert: {args.threshold} km\n")

    results = []
    checked = 0
    requests = 0

    for idx, station in enumerate(all_stations):
        checked += 1
        name = station["name"]
        cc = get_country_code(station["country"])

        print(f"  [{idx+1}/{len(all_stations)}] {name[:60]:<60}", end="", flush=True)

        # Step 1: Forward-geocode the station name
        fwd = forward_geocode(name, country_code=cc)
        requests += 1
        time.sleep(RATE_LIMIT)

        if fwd is None and cc:
            # Retry without country code
            fwd = forward_geocode(name)
            requests += 1
            time.sleep(RATE_LIMIT)

        if fwd is None or "error" in (fwd or {}):
            # Try with just the place name
            place = extract_place_name(name)
            if place != name:
                fwd = forward_geocode(place, country_code=cc)
                requests += 1
                time.sleep(RATE_LIMIT)

        if not fwd or "error" in fwd:
            err = fwd.get("error", "kein Treffer") if fwd else "kein Treffer"
            print(f" ? {err[:40]}")
            continue

        dist = haversine_km(station["lat"], station["lon"], fwd["lat"], fwd["lon"])

        if dist <= args.threshold:
            print(f" ✓ {dist:.1f}km")
            continue

        # Step 2: Distance > threshold → Reverse-geocode the STORED coordinates
        # to check if they're even in the right country
        rev = reverse_geocode(station["lat"], station["lon"])
        requests += 1
        time.sleep(RATE_LIMIT)

        rev_country = ""
        rev_country_code = ""
        rev_place = ""
        rev_display = ""
        if rev and "error" not in rev:
            rev_country = rev.get("country", "")
            rev_country_code = rev.get("country_code", "")
            rev_place = rev.get("place", "")
            rev_display = rev.get("display_name", "")

        # Step 3: Classify the result
        stored_in_right_country = country_matches(station["country"], rev_country_code)
        fwd_country_code = fwd.get("country_code", "")
        fwd_in_right_country = country_matches(station["country"], fwd_country_code)

        if not stored_in_right_country:
            # Stored coordinates are in the WRONG country → definite error
            category = "FEHLER"
        elif not fwd_in_right_country and dist > 100:
            # Nominatim found a different country → probably wrong Nominatim match
            category = "UNKLAR"
        elif dist > 200 and stored_in_right_country:
            # Very large distance but stored coords are in right country
            # → Nominatim probably found wrong place with same name
            category = "UNKLAR"
        else:
            # Both in right country, moderate distance → worth checking
            category = "PRÜFEN"

        symbol = {"FEHLER": "❌", "PRÜFEN": "⚠", "UNKLAR": "~"}[category]
        print(f" {symbol} {dist:.0f}km {category}"
              f" (rev: {rev_place or rev_country or '?'})")

        results.append({
            "category": category,
            "file": station["file"],
            "line": station["line"],
            "station_name": name,
            "country_listed": station["country"],
            "current_lat": station["lat"],
            "current_lon": station["lon"],
            "nominatim_lat": fwd["lat"],
            "nominatim_lon": fwd["lon"],
            "distance_km": round(dist, 1),
            "nominatim_display": fwd["display_name"],
            "reverse_country": rev_country,
            "reverse_place": rev_place,
            "reverse_display": rev_display,
        })

    # Sort: FEHLER first, then PRÜFEN, then UNKLAR; within each by distance desc
    order = {"FEHLER": 0, "PRÜFEN": 1, "UNKLAR": 2}
    results.sort(key=lambda r: (order.get(r["category"], 9), -r["distance_km"]))

    # Write CSV
    if results:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "category", "file", "line", "station_name", "country_listed",
                "current_lat", "current_lon",
                "nominatim_lat", "nominatim_lon",
                "distance_km", "nominatim_display",
                "reverse_country", "reverse_place", "reverse_display",
            ], delimiter=";")
            writer.writeheader()
            writer.writerows(results)
        print(f"\nErgebnis: {OUTPUT_CSV}")

    n_fehler = sum(1 for r in results if r["category"] == "FEHLER")
    n_pruefen = sum(1 for r in results if r["category"] == "PRÜFEN")
    n_unklar = sum(1 for r in results if r["category"] == "UNKLAR")
    print(f"\n{checked} geprüft, {requests} Nominatim-Requests")
    print(f"  ❌ FEHLER:  {n_fehler} (Koordinaten in falschem Land)")
    print(f"  ⚠  PRÜFEN: {n_pruefen} (Abweichung, aber richtiges Land)")
    print(f"  ~  UNKLAR: {n_unklar} (Nominatim hat vermutlich falschen Ort gefunden)")


if __name__ == "__main__":
    main()
