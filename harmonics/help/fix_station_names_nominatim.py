#!/usr/bin/env python3
"""
Korrigiert Stationsnamen mit fehlenden Akzenten via Nominatim Reverse-Geocoding.
Erzeugt eine CSV-Vorschlagsliste zur Prüfung.
"""

import re
import json
import time
import csv
import urllib.request
import urllib.parse
from pathlib import Path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "TideHarmonicsNameFix/1.0 (oliver@tideproject)"
RATE_LIMIT = 1.1  # Sekunden zwischen Requests

OUTPUT_CSV = "/home/oliver/station_name_corrections.csv"

FILES_TO_CHECK = [
    "harmonics/classic/harmonics-2004-06-14_mod.txt",
    "harmonics/ticon/harmonics_ticon4_worldwide.txt",
]


def extract_stations(filepath):
    """Extrahiere Stationen mit verdächtigen Namen und Koordinaten."""
    with open(filepath, "r", encoding="iso-8859-1") as f:
        lines = f.readlines()

    stations = []
    for i, line in enumerate(lines):
        if line.startswith("# !latitude:"):
            lat = line.strip().split(":")[1].strip()
            lon_line = lines[i - 1].strip() if i > 0 and lines[i - 1].startswith("# !longitude:") else ""
            lon = lon_line.split(":")[1].strip() if lon_line else None

            # Stationsname: nächste nicht-leere, nicht-Kommentar-Zeile
            name = None
            name_line = None
            for j in range(i + 1, min(i + 5, len(lines))):
                l = lines[j].strip()
                if l and not l.startswith("#"):
                    name = l
                    name_line = j + 1  # 1-basiert
                    break

            if name and lon:
                # Prüfen ob der Name verdächtig ist
                suspicious = False
                reasons = []

                if "ubec" in name and "Québec" not in name:
                    suspicious = True
                    reasons.append("Qubec→Québec")
                if "Rivire" in name:
                    suspicious = True
                    reasons.append("Rivire→Rivière")
                if "St-" in name.split(",")[0]:
                    suspicious = True
                    reasons.append("St-→Saint-?")
                if "Bsum" in name:
                    suspicious = True
                    reasons.append("Bsum→Büsum")

                # ALL CAPS Wörter im Ortsnamen (vor dem Komma)
                place = name.split(",")[0]
                words = place.split()
                caps_words = [w for w in words if len(w) > 2 and w == w.upper() and w.isalpha()]
                if caps_words:
                    suspicious = True
                    reasons.append(f"CAPS: {' '.join(caps_words)}")

                if suspicious:
                    stations.append({
                        "file": filepath,
                        "line": name_line,
                        "name": name,
                        "lat": float(lat),
                        "lon": float(lon),
                        "reasons": ", ".join(reasons),
                    })

    return stations


def reverse_geocode(lat, lon, lang="fr"):
    """Nominatim Reverse-Geocoding."""
    params = urllib.parse.urlencode({
        "lat": lat,
        "lon": lon,
        "format": "json",
        "accept-language": lang,
        "zoom": 14,
        "addressdetails": 1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def build_suggestion(station, nominatim_data):
    """Erzeuge Namensvorschlag aus Nominatim-Daten und Original."""
    if "error" in nominatim_data or "address" not in nominatim_data:
        return ""

    addr = nominatim_data["address"]
    display = nominatim_data.get("display_name", "")

    original = station["name"]
    parts = original.split(",")
    original_place = parts[0].strip()
    original_region = ", ".join(p.strip() for p in parts[1:])

    # Versuche passenden Ortsnamen aus Nominatim zu finden
    # Priorität: village > town > city > suburb > municipality
    place_keys = ["village", "town", "city", "suburb", "municipality",
                  "hamlet", "locality", "neighbourhood"]
    nom_place = ""
    for key in place_keys:
        if key in addr:
            nom_place = addr[key]
            break

    # Region korrigieren
    state = addr.get("state", "")
    country = addr.get("country", "")

    # Für Kanada: Province als Region
    if addr.get("country_code") == "ca":
        region = state if state else country
        suggestion = f"{nom_place}, {region}" if nom_place else ""
    else:
        region = original_region  # Region beibehalten
        suggestion = f"{nom_place}, {region}" if nom_place else ""

    return suggestion


def main():
    all_stations = []
    for filepath in FILES_TO_CHECK:
        print(f"Prüfe {filepath}...")
        stations = extract_stations(filepath)
        all_stations.extend(stations)
        print(f"  {len(stations)} verdächtige Stationen gefunden")

    print(f"\nGesamt: {len(all_stations)} Stationen zu prüfen")
    print(f"Geschätzte Dauer: {len(all_stations) * RATE_LIMIT / 60:.0f} Minuten\n")

    results = []
    for idx, station in enumerate(all_stations):
        print(f"  [{idx+1}/{len(all_stations)}] {station['name'][:50]}...", end="", flush=True)

        # Sprache je nach Region wählen
        name_lower = station["name"].lower()
        if any(x in name_lower for x in ["japan"]):
            lang = "en"
        elif any(x in name_lower for x in ["france", "qubec", "québec", "quebec"]):
            lang = "fr"
        elif any(x in name_lower for x in ["germany", "deutschland"]):
            lang = "de"
        elif any(x in name_lower for x in ["spain", "españa"]):
            lang = "es"
        else:
            lang = "en"

        data = reverse_geocode(station["lat"], station["lon"], lang=lang)
        suggestion = build_suggestion(station, data)

        display = data.get("display_name", "")
        error = data.get("error", "")

        results.append({
            "file": station["file"],
            "line": station["line"],
            "original": station["name"],
            "lat": station["lat"],
            "lon": station["lon"],
            "reasons": station["reasons"],
            "suggestion": suggestion,
            "nominatim_display": display,
            "error": error,
        })

        status = "✓" if suggestion else ("✗ " + error[:30] if error else "? kein Ort")
        print(f" → {status}")

        time.sleep(RATE_LIMIT)

    # CSV schreiben
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file", "line", "original", "suggestion",
            "lat", "lon", "reasons", "nominatim_display", "error"
        ], delimiter=";")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nErgebnis gespeichert in: {OUTPUT_CSV}")
    print(f"  {sum(1 for r in results if r['suggestion'])} mit Vorschlag")
    print(f"  {sum(1 for r in results if not r['suggestion'] and not r['error'])} ohne Treffer")
    print(f"  {sum(1 for r in results if r['error'])} mit Fehler")


if __name__ == "__main__":
    main()
