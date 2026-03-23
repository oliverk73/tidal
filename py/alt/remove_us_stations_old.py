# -*- coding: iso-8859-1 -*-
import re
from pathlib import Path

# Liste bekannter US-Zeitzonen (nur starke US-Indikatoren)
us_timezones = {
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Anchorage", "America/Phoenix", "America/Boise", "America/Indiana/Indianapolis",
    "America/Juneau", "America/Metlakatla", "America/Nome", "America/Sitka", "America/Yakutat",
    "Pacific/Honolulu", "Pacific/Samoa", "America/Adak", "America/Detroit"
}

# Liste starker Kanada-Indikatoren zur Rettung (nicht löschen)
canada_indicators = [
    "Nova Scotia", "British Columbia", "Québec", "Quebec", "Newfoundland",
    "Nunavut", "Labrador", "New Brunswick", "Prince Edward Island"
]

# Liste starker Nicht-US-Zeitzonen, z. B. für Mexiko
non_us_timezones = {
    "America/Mexico_City", "America/Tijuana", "America/Hermosillo",
    "America/Chihuahua", "America/Mazatlan", "America/Ensenada"
}

# Bekannte Kürzel für US-Außengebiete und assoziierte Staaten
us_territory_indicators = [
    "Puerto Rico", "Guam", "American Samoa", "U.S. Virgin Islands", "Virgin Islands",
    "Northern Mariana Islands", "Johnston Atoll", "Midway Islands", "Wake Island",
    "Baker Island", "Howland Island", "Jarvis Island", "Kingman Reef", "Palmyra Atoll",
    "FM", "FSM", "Federated States of Micronesia", "Marshall Islands", "Palau",
    "Saipan", "Pohnpei", "Majuro", "Koror"
]

# Stichworte zur Erkennung von USA (inkl. states)
us_indicators = [
    "USA", "U.S.A.", "United States", "US", "U.S.",
    "California", "Florida", "Texas", "New York", "Alaska", "Hawaii",
    "Washington", "Oregon", "South Carolina", "North Carolina",
    "Georgia", "Virginia", "Maryland", "Massachusetts", "Connecticut",
    "New Jersey", "Louisiana", "Mississippi", "Alabama", "Illinois", "Indiana"
]

def should_delete_block(block: str) -> bool:
    # Extrahiere Kommentarzeilen und Infozeilen
    lines = block.strip().splitlines()
    comments = [line for line in lines if line.startswith("#")]
    rest = [line for line in lines if not line.startswith("#")]
    if len(rest) < 2:
        return False  # Ungültiger Block

    station_name = rest[0].strip()
    timezone = rest[1].strip().split()[1] if len(rest[1].split()) > 1 else ""
    comment_text = " ".join(comments)

    # POSITIVE Ausschlüsse zuerst (nicht löschen)
    if any(indicator in station_name for indicator in canada_indicators):
        return False
    if timezone in non_us_timezones:
        return False

    # US-Indikatoren
    if timezone in us_timezones:
        return True
    if any(indicator in station_name for indicator in us_indicators):
        return True
    if any(indicator in comment_text for indicator in us_indicators):
        return True
    if any(indicator in station_name for indicator in us_territory_indicators):
        return True
    if any(indicator in comment_text for indicator in us_territory_indicators):
        return True

    return False

def split_blocks(text: str) -> list:
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("#"):
            i += 1
            continue
        start = i
        while i < len(lines) and lines[i].startswith("#"):
            i += 1
        # Kommentarblock zu Ende, es folgen 3 Infozeilen + 175 Datenzeilen
        block = lines[start:i+3+175] if i+3+175 <= len(lines) else lines[start:]
        blocks.append("\n".join(block))
        i += 3 + 175
    return blocks

def filter_us_stations(input_path: Path, output_path: Path):
    with input_path.open("r", encoding="iso-8859-1") as f:
        content = f.read()

    blocks = split_blocks(content)
    kept_blocks = [block for block in blocks if not should_delete_block(block)]

    with output_path.open("w", encoding="iso-8859-1") as f:
        f.write("\n".join(kept_blocks))

# Beispiel:
# filter_us_stations(Path("harmonics-2004-06-14_harmonic_constants.txt"),
#                    Path("harmonics-2004-06-14_harmonic_constants_no_us.txt"))
