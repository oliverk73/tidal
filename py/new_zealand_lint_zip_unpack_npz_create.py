# -*- coding: utf-8 -*-
import os
import zipfile
import pandas as pd
import numpy as np
from pathlib import Path

BASE_PATH = Path("/home/oliver/water_levels/New_Zealand_LINZ")
NPZ_PATH = BASE_PATH / "NPZ_Exports"

def process_all():
    NPZ_PATH.mkdir(parents=True, exist_ok=True)
    
    # Gehe durch jede Station (z.B. AUCT)
    stations = [d for d in BASE_PATH.iterdir() if d.is_dir() and d.name != "NPZ_Exports"]
    
    for station_path in stations:
        station = station_path.name
        all_data = []
        print(f"--- Verarbeite {station} ---")
        
        # 1. ZIPs entpacken
        zip_files = list(station_path.rglob("*.zip"))
        if zip_files:
            print(f"  Entpacke {len(zip_files)} ZIP-Dateien...")
            for zf in zip_files:
                try:
                    with zipfile.ZipFile(zf, 'r') as zip_ref:
                        zip_ref.extractall(zf.parent)
                    os.remove(zf)
                except Exception as e:
                    print(f"  Fehler bei {zf.name}: {e}")

        # 2. Daten sammeln (CSV und TXT)
        data_files = list(station_path.rglob("*.[ct][sx][vt]"))
        print(f"  Gefundene Datendateien: {len(data_files)}")
        
        for df_path in sorted(data_files):
            try:
                # Versuche mit verschiedenen Trennern, da LINZ-Files variieren koennen
                df = pd.read_csv(df_path, on_bad_lines='skip', low_memory=False)
                if not df.empty:
                    all_data.append(df.values)
            except Exception:
                continue

        # 3. NPZ speichern
        if all_data:
            combined = np.vstack(all_data)
            np.savez_compressed(NPZ_PATH / f"{station}_sea_level.npz", data=combined)
            print(f"  [OK] NPZ erstellt mit {len(combined)} Zeilen.")
        else:
            print(f"  [!] Keine Daten fuer {station} gefunden.")

if __name__ == "__main__":
    if not BASE_PATH.exists():
        print(f"FEHLER: Pfad {BASE_PATH} existiert nicht!")
    else:
        process_all()
