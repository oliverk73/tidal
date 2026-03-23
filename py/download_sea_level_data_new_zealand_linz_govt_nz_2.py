# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import os
import zipfile
from pathlib import Path

# --- KONFIGURATION ---
BASE_PATH = Path("/home/oliver/water_levels/New_Zealand_LINZ")
STATIONS = ["AUCT", "BCRT", "CPTT", "CHRT", "FRRT", "GIST", "KAKT", "KBBT", "LPTT", 
            "MAUT", "NAPT", "NBPT", "NCPT", "OWCT", "PCMT", "PUYT", "SUMT", "TAUT", 
            "WLGT", "SBTX"]
YEARS = range(2009, 2026) # 2026 lassen wir erst mal weg, da das Jahr noch laeuft
BASE_URL = "https://sealevel-data.linz.govt.nz"

def is_garbage(path):
    """Prueft, ob die Datei Schrott ist (zu klein oder kein ZIP)."""
    if not path.exists(): return True
    if path.stat().st_size < 1000: return True # Alles unter 1KB ist Schrott
    return not zipfile.is_zipfile(path)

async def fetch(session, url, dest):
    """Laedt die Datei herunter und validiert sie sofort."""
    if not is_garbage(dest): return # Bereits gultig vorhanden

    if dest.exists(): os.remove(dest) # Loesche Schrott

    try:
        async with session.get(url, timeout=20) as resp:
            if resp.status == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = await resp.read()
                with open(dest, "wb") as f:
                    f.write(data)
                
                # Sofort-Check nach Download
                if is_garbage(dest):
                    os.remove(dest)
                    # print(f"  [!] {dest.name} war wieder Schrott (404/Fehler)")
            else:
                pass # Datei existiert auf dem Server vermutlich nicht
    except:
        pass

async def main():
    # Limit auf 5 parallele Verbindungen, um nicht geblockt zu werden
    connector = aiohttp.TCPConnector(limit_per_host=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        for year in YEARS:
            print(f"Pruefe/Lade Jahr {year}...")
            tasks = []
            days = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
            
            for st in STATIONS:
                for sen in ["40", "41"]:
                    for d in range(1, days + 1):
                        fname = f"{st}_{sen}_{year}{d:03d}.zip"
                        url = f"{BASE_URL}/{st}/{year}/{sen}/{fname}"
                        dest = BASE_PATH / st / str(year) / sen / fname
                        tasks.append(fetch(session, url, dest))
            
            # Batchweise abarbeiten
            await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
    print("\nDownload-Reparatur beendet. Starte danach das Konvertierungs-Skript.")
