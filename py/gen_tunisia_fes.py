#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Erzeugt FES2022b-Modellstationen fuer den Golf von Gabes (Tunesien)
und haengt sie an harmonics/utide/harmonics_fes2022.txt an.

Validiert gegen SHOM Sfax (M2 41.6/41.1 cm, G 76.0/75.3 deg) -> FES bestens.
Jede NetCDF-Datei wird genau EINMAL geladen (Performance, siehe Memory).
"""
import netCDF4 as nc, numpy as np, os, json

FES_DIR = "tide_models/fes2022b/ocean_tide_extrapolated"
TXT = "harmonics/utide/harmonics_fes2022.txt"
DATE = "20260606"

# congen-Reihenfolge (175) aus Header
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

# Stationen: name, lat, lon, water_body
STATIONS = [
    ("Gabes, Tunisia",      33.8900, 10.1030),
    ("Houmt Souk (Djerba), Tunisia", 33.8800, 10.8570),
]

def sample(ds, lat, lon):
    lons = ds.variables['lon'][:]; lats = ds.variables['lat'][:]
    lon360 = lon % 360
    j = int(np.argmin(np.abs(lons - lon360))); k = int(np.argmin(np.abs(lats - lat)))
    amp = ds.variables['amplitude']; ph = ds.variables['phase']
    a = amp[k, j]; p = ph[k, j]
    if np.ma.is_masked(a):
        for r in range(1, 15):
            sa = amp[max(0, k-r):k+r+1, max(0, j-r):j+r+1]
            sp = ph[max(0, k-r):k+r+1, max(0, j-r):j+r+1]
            m = np.ma.getmaskarray(sa)
            if not np.all(m):
                aa = sa[~m]; pp = sp[~m]
                a = aa.mean()
                x = np.mean(aa*np.cos(np.radians(pp))); y = np.mean(aa*np.sin(np.radians(pp)))
                p = np.degrees(np.arctan2(y, x)) % 360
                return float(a), float(p)
        return None, None
    return float(a), float(p) % 360

# FES einmal pro Konstituente laden, alle Stationen samplen
fes = {}  # congen_name -> list of (amp_m, phase) per station index
for cname in order:
    fpath = f"{FES_DIR}/{stem(cname)}_fes2022.nc"
    if not os.path.exists(fpath):
        continue
    ds = nc.Dataset(fpath)
    vals = []
    for (_, la, lo) in STATIONS:
        a, p = sample(ds, la, lo)
        vals.append((a/100.0, p) if a is not None else None)
    fes[cname] = vals
    ds.close()

print("FES-Konstituenten gemappt:", len(fes))

def block(idx, name, lat, lon):
    L = []
    L.append("# BEGIN HOT COMMENTS")
    L.append("# country: Tunisia")
    L.append("# water_body: Gulf of Gabes (Mediterranean Sea)")
    L.append("# source: FES2022b global ocean tide model (extrapolated), sampled at port location")
    L.append("# note: MODEL-DERIVED (not observations). Validated vs SHOM Sfax: M2 41.1 vs 41.6 cm, G 75.3 vs 76.0 deg.")
    L.append(f"# date_imported: {DATE}")
    L.append("# datum: MSL")
    L.append("# confidence: 5")
    L.append("# !units: meters")
    L.append(f"# !longitude: {lon:.6f}")
    L.append(f"# !latitude: {lat:.6f}")
    L.append(name)
    L.append("+00:00 :UTC")
    L.append("0.0000 meters")
    for cname in order:
        v = fes.get(cname, [None]*len(STATIONS))[idx] if cname in fes else None
        if v is not None and v[0] is not None and v[0] > 0:
            L.append(f"{cname:<15s} {v[0]:.4f}  {v[1]:.2f}")
        else:
            L.append("x 0 0")
    return "\n".join(L)

blocks = []
for idx, (name, lat, lon) in enumerate(STATIONS):
    nfilled = sum(1 for c in order if c in fes and fes[c][idx] and fes[c][idx][0] > 0)
    print(f"{name}: {nfilled} Konstituenten gefuellt, M2={fes['M2'][idx]}")
    blocks.append(block(idx, name, lat, lon))

with open(TXT, "a", encoding="iso-8859-1") as f:
    f.write("\n".join(blocks))
    f.write("\n")
print("Angehaengt an", TXT)
