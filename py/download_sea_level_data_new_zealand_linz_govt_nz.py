# -*- coding: utf-8 -*-
import os
import zipfile
import pandas as pd
import numpy as np
from pathlib import Path

# --- KONFIGURATION ---
BASE_PATH = Path("/home/oliver/water_levels/New_Zealand_LINZ")
NPZ_PATH = BASE_PATH / "NPZ_Exports"

def process_station(station_path):
    station = station_path.name
    all_data = []
    
    # Nutze os.walk statt rglob fuer bessere Performance bei vielen Dateien
    print(f"Verarbeite Station: {station}...")
    
    for root, dirs, files in os.walk(station_path):
        # NPZ_Exports Verzeichnis ignorieren
        if "NPZ_Exports" in root: continue
        
        for file in sorted(files):
            file_path = Path(root) / file
            
            # 1. ZIP-Dateien entpacken und validieren
            if file.endswith(".zip"):
                try:
                    if file_path.stat().st_size < 500: # 404-Fehlerseiten sind meist klein
                        os.remove(file_path)
                        continue
                        
                    with zipfile.ZipFile(file_path, 'r') as z:
                        z.extractall(root)
                    os.remove(file_path)
                    # Nach Entpacken muessen wir die neuen Dateien im naechsten Loop finden
                except Exception:
                    # Korruptes ZIP einfach loeschen, um Loop zu stoppen
                    if file_path.exists(): os.remove(file_path)
                    continue

    # 2. Daten sammeln (CSV/TXT) nach dem Entpacken
    # Wir machen einen zweiten Pass fuer die Daten, um Sensor-Prioritaet zu wahren
    print(f"  Sammle Daten fuer {station}...")
    for year in range(2009, 2027):
        year_path = station_path / str(year)
        if not year_path.exists(): continue
        
        # Prioritaet: Sensor 40 vor 41
        for day_idx in range(1, 367):
            found = False
            for sensor in ["40", "41"]:
                if found: break
                sensor_path = year_path / sensor
                # Suche nach der Datei fuer diesen Tag (z.B. *2024001*)
                day_str = f"{year}{day_idx:03d}"
                for data_file in sensor_path.glob(f"*{day_str}*.[ct][sx][vt]"):
                    try:
                        df = pd.read_csv(data_file, on_bad_lines='skip', low_memory=False)
                        if not df.empty:
                            all_data.append(df.values)
                            found = True
                    except:
                        continue

    if all_data:
        NPZ_PATH.mkdir(parents=True, exist_ok=True)
        combined = np.vstack(all_data)
        np.savez_compressed(NPZ_PATH / f"{station}_sea_level.npz", data=combined)
        print(f"  [OK] {station} fertig ({len(combined)} Zeilen).")
    else:
        print(f"  [!] Keine Daten fuer {station}.")

def main():
    if not BASE_PATH.exists():
        print(f"Pfad nicht gefunden: {BASE_PATH}")
        return
        
    # Liste alle Stations-Ordner
    stations = sorted([d for d in BASE_PATH.iterdir() if d.is_dir() and d.name != "NPZ_Exports"])
    
    for st_path in stations:
        process_station(st_path)

if __name__ == "__main__":
    main()
