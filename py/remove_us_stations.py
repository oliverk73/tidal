import re
import os
import pandas as pd

# === Einstellungen ===
INPUT_FILE = HARMONICS_NO_US.txt  # oder anderer Dateiname
ENCODING = iso-8859-1

# === US-Erkennungsregeln ===
us_keywords = {
    United States, USA, U.S., U.S.A., Guam, Puerto Rico, American Samoa,
    U.S. Virgin Islands, Virgin Islands, Northern Mariana Islands, Johnston Atoll,
    Midway Islands, Wake Island, Navassa Island, Palmyra Atoll, Baker Island,
    Howland Island, Jarvis Island, Kingman Reef, United States Minor Outlying Islands,
    Marshall Islands, Micronesia, Federated States of Micronesia, FSM, Palau
}

non_us_america_tz = {
    AmericaBelize, AmericaCosta_Rica, AmericaEdmonton, AmericaHalifax,
    AmericaToronto, AmericaVancouver, AmericaSt_Johns, AmericaArgentina,
    AmericaSantiago, AmericaMexico_City, AmericaWinnipeg, AmericaRegina
}

# === Hilfsfunktionen ===
def find_data_start(lines)
    phrase = # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    indices = [i for i, line in enumerate(lines) if phrase in line]
    return indices[1] + 1 if len(indices) = 2 else 0

# === Hauptfunktion ===
def remove_us_stations(input_path)
    with open(input_path, r, encoding=ENCODING) as f
        lines = f.readlines()

    data_start = find_data_start(lines)
    output_lines = lines[data_start]
    removed_stations = []

    i = data_start
    while i  len(lines)
        # Überspringe bis zum nächsten Blockbeginn
        if not lines[i].startswith(#)
            i += 1
            continue

        # Kommentarbereich sammeln
        comment_lines = []
        while i  len(lines) and lines[i].startswith(#)
            comment_lines.append(lines[i])
            i += 1

        # Infobereich (3 Zeilen)
        if i + 2 = len(lines)
            break  # Block unvollständig

        name_line = lines[i].strip()
        tz_line = lines[i + 1].strip()
        datum_line = lines[i + 2].strip()
        i += 3

        # Constituents-Bereich überspringen
        while i  len(lines) and not lines[i].startswith(#)
            i += 1

        # Daten extrahieren
        country = 
        lat = 
        lon = 
        for line in comment_lines
            if # country in line
                country = line.split(, 1)[1].strip()
            elif # !latitude in line
                lat = line.split(, 1)[1].strip()
            elif # !longitude in line
                lon = line.split(, 1)[1].strip()

        tz = 
        if re.match(r[+-]d{2}d{2} , tz_line)
            parts = tz_line.split( , 1)
            if len(parts)  1
                tz = parts[1]

        is_us = any(kw.lower() in country.lower() for kw in us_keywords)
        if tz.startswith(America) and tz not in non_us_america_tz
            is_us = True

        block = comment_lines + [name_line + n, tz_line + n, datum_line + n]
        if is_us
            removed_stations.append({
                Station name_line,
                Land country,
                Latitude lat,
                Longitude lon,
                Zeitzone tz
            })
        else
            output_lines.extend(block)

    # Speichern
    base, ext = os.path.splitext(input_path)
    output_txt = f{base}_no_us{ext}
    output_csv = f{base}_us_stations.csv

    with open(output_txt, w, encoding=ENCODING) as f
        f.writelines(output_lines)

    df = pd.DataFrame(removed_stations)
    df.to_csv(output_csv, index=False)

    print(fFertig. Datei ohne US-Stationen {output_txt})
    print(fCSV der entfernten US-Stationen {output_csv})

# === Aufruf ===
if __name__ == __main__
    remove_us_stations(INPUT_FILE)