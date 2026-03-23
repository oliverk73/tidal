
import argparse
from duplikate_entfernen_robust_v2 import get_constituent_count_and_start, parse_stations, normalize_name
import pandas as pd

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
    stations_alt = parse_stations(lines_alt, start_alt, count_alt)

    i = start_alt
    cleaned = []
    deleted = []

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
            deleted.append(block)
        else:
            cleaned.extend(block)
            cleaned.append("\n")

    with open(args.ausgabe, "w", encoding="ISO-8859-1") as f:
        f.writelines(lines_alt[:start_alt])
        f.writelines(cleaned)

    if args.csv:
        df = pd.DataFrame(
            [s for s in stations_alt if normalize_name(s[0]) in cmp_lookup],
            columns=["Ortsname", "Region", "Land", "Latitude", "Longitude", "Zeitzone"]
        )
        df.to_csv(args.csv, sep=";", index=False)

if __name__ == "__main__":
    main()
