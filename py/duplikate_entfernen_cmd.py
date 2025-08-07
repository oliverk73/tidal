
import argparse
from duplikate_entfernen_robust_v2 import get_constituent_count_and_start, parse_stations, normalize_name
import pandas as pd

def extract_metadata_from_block(block):
    name_line = ""
    tz_line = ""
    lat = lon = None
    country = region = ""

    for line in block:
        if line.startswith("# country:"):
            country = line.strip().split(":", 1)[1].strip()
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
        elif not line.startswith("#") and not name_line:
            name_line = line.strip()
        elif not line.startswith("#") and not tz_line:
            tz_line = line.strip()

    parts = [p.strip() for p in name_line.split(",")]
    if len(parts) >= 2:
        region = parts[-2]
        if not country:
            country = parts[-1]
    elif not country:
        country = ""

    timezone = ""
    if tz_line and " " in tz_line:
        tz_parts = tz_line.split()
        if len(tz_parts) > 1:
            timezone = tz_parts[1]

    return [name_line, region, country, lat, lon, timezone]

def main():
    parser = argparse.ArgumentParser(description="Entfernt Duplikate aus Harmonics-Dateien.")
    parser.add_argument("quelle", help="Pfad zur älteren Datei")
    parser.add_argument("vergleich", help="Pfad zur neueren Datei")
    parser.add_argument("ausgabe", help="Pfad zur bereinigten Ausgabedatei")
    parser.add_argument("--csv", help="Pfad zur CSV-Datei mit gelöschten Einträgen", default=None)
    args = parser.parse_args()

    with open(args.quelle, encoding="ISO-8859-1") as f:
        lines_alt = f.readlines()
    with open(args.vergleich, encoding="ISO-8859-1") as f:
        lines_cmp = f.readlines()

    count_cmp, start_cmp = get_constituent_count_and_start(lines_cmp)
    stations_cmp = parse_stations(lines_cmp, start_cmp, count_cmp)
    cmp_lookup = {normalize_name(s[0]) for s in stations_cmp}

    count_alt, start_alt = get_constituent_count_and_start(lines_alt)

    i = start_alt
    cleaned = []
    deleted_blocks = []

    while i < len(lines_alt):
        block = []
        while i < len(lines_alt) and (lines_alt[i].strip() == "" or lines_alt[i].startswith("#")):
            block.append(lines_alt[i])
            i += 1
        if i + 2 >= len(lines_alt):
            break
        block.extend(lines_alt[i:i+3])
        name_line = lines_alt[i].strip()
        i += 3
        if i + count_alt > len(lines_alt):
            break
        block.extend(lines_alt[i:i+count_alt])
        i += count_alt

        if normalize_name(name_line) in cmp_lookup:
            deleted_blocks.append(block)
        else:
            cleaned.extend(block)
            cleaned.append("\n")

    with open(args.ausgabe, "w", encoding="ISO-8859-1") as f:
        f.writelines(lines_alt[:start_alt])
        f.writelines(cleaned)

    if args.csv:
        records = [extract_metadata_from_block(block) for block in deleted_blocks]
        df = pd.DataFrame(records, columns=["Ortsname", "Region", "Land", "Latitude", "Longitude", "Zeitzone"])
        df.to_csv(args.csv, sep=";", index=False)

if __name__ == "__main__":
    main()
