# -*- coding: utf-8 -*-
import os
import zipfile
import pandas as pd
import numpy as np
from pathlib import Path

# --- KONFIGURATION ---
BASE_PATH = Path("/home/oliver/water_levels/New_Zealand_LINZ")
NPZ_PATH = BASE_PATH / "NPZ_Exports"

def process_all_stations():
    NPZ_PATH.mkdir(parents=True, exist_ok=True)
    
    # Alle Unterordner (Stationen) finden
    stations = [d for d in BASE_PATH.iterdir() if d.is_dir() and d.name != "NPZ_Exports"]
    
    for station_path in sorted(stations):
        station = station_path.name
        all_data = []
        print(f"\n--- Station: {station} ---")
        
        # 1. Schritt: Radikales Entpacken
        # Wir suchen alle Dateien im Baum
        for root, dirs, files in os.walk(station_path):
            for file in files:
                file_path = Path(root) / file
                if file.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(file_path, 'r') as z:
                            z.extractall(root)
                        os.remove(file_path)
                    except Exception:
                        # Falls korrupt, einfach loeschen
                        os.remove(file_path)

        # 2. Schritt: Datensuche (wir nehmen ALLES, was kein ZIP mehr ist)
        found_files = []
        for root, dirs, files in os.walk(station_path):
            for file in files:
                # Wir ignorieren versteckte Dateien und die NPZ-Exports
                if not file.startswith(".") and "NPZ_Exports" not in root:
                    found_files.append(Path(root) / file)
        
        print(f"  Dateien zum Einlesen gefunden: {len(found_files)}")
        
        # 3. Schritt: Einlesen (Priorisierung Sensor 40)
        # Wir sortieren nach Pfad, damit Sensor 40 vor 41 kommt (falls beide im Baum sind)
        for df_path in sorted(found_files):
            try:
                # Versuche die Datei zu lesen (LINZ hat oft Header, pandas erkennt das meist)
                df = pd.read_csv(df_path, on_bad_lines='skip', low_memory=False)
                if not df.empty:
                    # Wir speichern nur die Werte als Matrix
                    all_data.append(df.values)
            except:
                continue
        
        # 4. Schritt: NPZ Speicherung
        if all_data:
            # Vertikaler Stack der Datenmatrizen
            combined = np.vstack(all_data)
            output_file = NPZ_PATH / f"{station}_sea_level.npz"
            np.savez_compressed(output_file, data=combined)
            print(f"  [ERFOLG] {output_file.name} mit {len(combined)} Zeilen erstellt.")
        else:
            print(f"  [FEHLER] Keine nutzbaren Daten in den Dateien gefunden.")

if __name__ == "__main__":
    if not BASE_PATH.exists():
        print(f"Pfad {BASE_PATH} nicht gefunden!")
    else:
        process_all_stations()
