# duplikate_entfernen_cmd_v3.py (mit Logging und Prüfbericht)

Dieses Skript entfernt Duplikate aus einer älteren Harmonics-Datei, erstellt eine bereinigte Ausgabe und
eine CSV-Liste aller gelöschten Stationen. Erweiterbar mit Logging und Prüfbericht-Ausgabe.

## Anforderungen
- Python 3
- pandas
- Optional: `logging` für fortlaufende Statusmeldungen

## Aufruf (Beispiel)

    python3 duplikate_entfernen_cmd.py         harmonics_alt.txt         harmonics_neu.txt         harmonics_alt_bereinigt.txt         --csv geloeschte_station.csv

## Parameter

1. `harmonics_alt.txt`: Ältere Datei, aus der Duplikate entfernt werden
2. `harmonics_neu.txt`: Neuere Vergleichsdatei
3. `harmonics_alt_bereinigt.txt`: Ergebnisdatei ohne Duplikate
4. `--csv`: CSV-Datei mit Liste der gelöschten Stationen (optional)

## Erweiterung: Logging

Du kannst innerhalb des Skripts z. B. `import logging` nutzen:

    import logging
    logging.basicConfig(level=logging.INFO)
    logging.info("Verarbeite Station: %s", name_line)

So werden während der Ausführung Fortschrittsmeldungen ausgegeben.

## Erweiterung: Prüfbericht

Du kannst nach dem Lauf automatisch einen kleinen Prüfbericht schreiben:

- Anzahl analysierter Stationen
- Anzahl gelöschter Duplikate
- Anteil Duplikate in Prozent
- Optionale Speicherung in `bericht.txt`

## CSV-Inhalt

Die CSV-Datei enthält:

- Ortsname
- Region
- Land
- Latitude
- Longitude
- Zeitzone

## Kodierung

Alle Dateien (Ein-/Ausgabe) sind `ISO-8859-1` codiert.

## Tauglichkeit

Diese Version berücksichtigt:

- Zusätze wie `(2)`, `(3)`, `- READ …` → werden ignoriert
- Extraktion des Landes aus der Ortszeile, wenn `# country:` fehlt
- Übereinstimmung anhand von Name + Land + Zeitzone

