
import argparse
from duplikate_entfernen_tool import remove_duplicates

def main():
    parser = argparse.ArgumentParser(description="Entfernt Duplikate aus Harmonics-Dateien.")
    parser.add_argument("quelle", help="Pfad zur älteren Harmonics-Datei (daraus werden Duplikate gelöscht)")
    parser.add_argument("vergleich", help="Pfad zur neueren Harmonics-Datei (enthält gültige Datenblöcke)")
    parser.add_argument("ausgabe", help="Pfad zur bereinigten Zieldatei")

    args = parser.parse_args()

    entfernte = remove_duplicates(args.quelle, args.vergleich, args.ausgabe)
    print(f"✅ {len(entfernte)} Duplikate entfernt. Bereinigte Datei: {args.ausgabe}")

if __name__ == "__main__":
    main()
