#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""FES2022b-Modellstationen fuer indonesische Hafenstaedte ohne Quelle.

Wie gen_tunisia_fes.py. Punkte = BIG-Pegelkoordinaten (srgi.big.go.id,
api/pasut/stations) bzw. Kuestenpunkte. Validierung 2026-06-12:
FES2022b vs UHSLC-Messfits Surabaya (M2 32.5/34.0cm @115.1/115.6;
K1 46.6/46.6cm @206.1/205.8) und Benoa (M2 65.7/64.4 @50.1/51.8) sowie
vs BIG Model Pasut 2024 (Phasen Greenwich, Abweichung <3 Grad).

Schreibt Bloecke mit Z0=0 (MSL) nach harmonics/help/; LAT-Z0 wird danach
per 19y-XTide-Rekonstruktion gesetzt (set_fes_indonesia_z0.py).

Usage: python3 py/gen_indonesia_fes.py
"""
import netCDF4 as nc
import numpy as np
import os

FES_DIR = "/home/oliver/tide_models/fes2022b/ocean_tide_extrapolated"
TXT = "/home/oliver/harmonics/utide/harmonics_fes2022.txt"
OUT = "/home/oliver/harmonics/help/fes_indonesia_blocks_msl.txt"
DATE = "20260612"

raw = open(TXT, encoding="iso-8859-1").read().splitlines()
ncst = int(raw[35])
order = []
i = 43
while len(order) < ncst:
    if raw[i].strip() and not raw[i].startswith("#"):
        order.append(raw[i].split()[0])
    i += 1
assert len(order) == 175


def stem(name):
    return "lambda2" if name == "LDA2" else name.lower()


# name, lat, lon, tz, water_body
STATIONS = [
    ("Batam (Kabil), Indonesia", 1.07314, 104.13760, "Asia/Jakarta", "Singapore Strait"),
    ("Bandar Lampung (Pelabuhan Panjang), Sumatra, Indonesia", -5.46999, 105.32000, "Asia/Jakarta", "Lampung Bay (Sunda Strait)"),
    ("Kupang, Timor, Indonesia", -10.19534, 123.52724, "Asia/Makassar", "Savu Sea"),
    ("Cilegon (Ciwandan), Java, Indonesia", -6.01769, 105.95260, "Asia/Jakarta", "Sunda Strait"),
    ("Jayapura, Papua, Indonesia", -2.54451, 140.71082, "Asia/Jayapura", "Pacific Ocean"),
    ("Bengkulu (Pulau Baai), Sumatra, Indonesia", -3.91944, 102.28180, "Asia/Jakarta", "Indian Ocean"),
    ("Palu (Pantoloan), Sulawesi, Indonesia", -0.71167, 119.85720, "Asia/Makassar", "Makassar Strait (Palu Bay)"),
    ("Kendari, Sulawesi, Indonesia", -3.97361, 122.58330, "Asia/Makassar", "Banda Sea (Kendari Bay)"),
    ("Cirebon, Java, Indonesia", -6.73386, 108.58460, "Asia/Jakarta", "Java Sea"),
    ("Dumai, Sumatra, Indonesia", 1.68916, 101.44410, "Asia/Jakarta", "Malacca Strait (Rupat Strait)"),
    ("Pekalongan, Java, Indonesia", -6.85848, 109.69275, "Asia/Jakarta", "Java Sea"),
    ("Sorong, Papua, Indonesia", -0.87715, 131.24365, "Asia/Jayapura", "Seram Sea (Sele Strait)"),
    ("Banda Aceh (Ulee Lheue), Sumatra, Indonesia", 5.56652, 95.29478, "Asia/Jakarta", "Malacca Strait approaches"),
    ("Tarakan, Borneo, Indonesia", 3.28155, 117.59380, "Asia/Makassar", "Celebes Sea"),
    ("Probolinggo, Java, Indonesia", -7.71494, 113.21569, "Asia/Jakarta", "Madura Strait"),
    ("Pasuruan, Java, Indonesia", -7.61500, 112.90500, "Asia/Jakarta", "Madura Strait"),
    ("Tegal, Java, Indonesia", -6.84000, 109.13000, "Asia/Jakarta", "Java Sea"),
    ("Singkawang, Borneo, Indonesia", 0.90000, 108.95000, "Asia/Jakarta", "Karimata Strait (South China Sea)"),
    ("Pontianak (Muara Kapuas), Borneo, Indonesia", 0.05000, 109.15000, "Asia/Jakarta", "Karimata Strait"),
]


def sample(ds, lat, lon):
    lons = ds.variables['lon'][:]
    lats = ds.variables['lat'][:]
    j = int(np.argmin(np.abs(lons - lon % 360)))
    k = int(np.argmin(np.abs(lats - lat)))
    amp = ds.variables['amplitude']
    ph = ds.variables['phase']
    a = amp[k, j]
    p = ph[k, j]
    if np.ma.is_masked(a):
        for r in range(1, 15):
            sa = amp[max(0, k - r):k + r + 1, max(0, j - r):j + r + 1]
            sp = ph[max(0, k - r):k + r + 1, max(0, j - r):j + r + 1]
            m = np.ma.getmaskarray(sa)
            if not np.all(m):
                aa = sa[~m]
                pp = sp[~m]
                x = np.mean(aa * np.cos(np.radians(pp)))
                y = np.mean(aa * np.sin(np.radians(pp)))
                return float(aa.mean()), float(np.degrees(np.arctan2(y, x)) % 360)
        return None, None
    return float(a), float(p) % 360


fes = {}
for cname in order:
    fpath = f"{FES_DIR}/{stem(cname)}_fes2022.nc"
    if not os.path.exists(fpath):
        continue
    ds = nc.Dataset(fpath)
    vals = []
    for (_, la, lo, _, _) in STATIONS:
        a, p = sample(ds, la, lo)
        vals.append((a / 100.0, p) if a is not None else None)
    fes[cname] = vals
    ds.close()

print("FES-Konstituenten gemappt:", len(fes))


def block(idx, name, lat, lon, tz, wb):
    L = ["#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Indonesia",
         f"# water_body: {wb}",
         "# source: FES2022b global ocean tide model (extrapolated), sampled at port location",
         "# note: MODEL-DERIVED (not observations). Validated vs UHSLC Surabaya/Benoa fits (M2/K1 <2%, <2 deg) and BIG Model Pasut 2024.",
         f"# date_imported: {DATE}",
         "# datum: MSL",
         "# confidence: 5",
         "# !units: meters",
         f"# !longitude: {lon:.6f}",
         f"# !latitude: {lat:.6f}",
         name,
         f"+00:00 :{tz}",
         "0.0000 meters"]
    for cname in order:
        v = fes[cname][idx] if cname in fes else None
        if v is not None and v[0] is not None and v[0] > 0:
            L.append(f"{cname:<15s} {v[0]:.4f}  {v[1]:.2f}")
        else:
            L.append("x 0 0")
    return "\n".join(L)


blocks = []
for idx, (name, lat, lon, tz, wb) in enumerate(STATIONS):
    nfilled = sum(1 for c in order if c in fes and fes[c][idx] and fes[c][idx][0] > 0)
    m2 = fes['M2'][idx]
    k1 = fes['K1'][idx]
    print(f"{name}: {nfilled} Konst., M2={m2[0]:.3f}@{m2[1]:.1f}, K1={k1[0]:.3f}@{k1[1]:.1f}")
    blocks.append(block(idx, name, lat, lon, tz, wb))

with open(OUT, "w", encoding="iso-8859-1") as f:
    f.write("\n".join(blocks) + "\n")
print("Geschrieben:", OUT)
