#!/usr/bin/env python3
"""Alle 10 PLA-Stationen: Download (Cache), UTide-Fit (auto + erweitert), OOS-Validierung 2027."""
import csv, io, time, subprocess, statistics, os, json
from datetime import datetime, timedelta
import numpy as np, pandas as pd, utide

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
BASE = "https://tidepredictions.pla.co.uk"
CACHE = "/tmp/pla/cache"
os.makedirs(CACHE, exist_ok=True)

STATIONS = [
    ("0103", 51.3920, "Margate"),
    ("0110", 51.5180, "Southend"),
    ("0110A", 51.5128, "Coryton"),
    ("0111", 51.4500, "Tilbury"),
    ("0112", 51.4983, "North Woolwich"),
    ("0113", 51.5067, "London Bridge"),
    ("0113A", 51.4847, "Chelsea Bridge"),
    ("0116", 51.4630, "Richmond"),
    ("0116A", 51.4990, "Shivering Sand"),
    ("0129", 51.8483, "Walton on the Naze"),
]

# Erweitertes Flachwasser-Set zusätzlich zu UTide-auto
EXTRA = ['M8','M10','3MK7','2MK5','MSK6','2SM6','3MS8','MK4','SK4','2MN6','MSN6',
         'M3','SO3','MO3','SK3','2MS6','M6','M4','MS4','MN4','S4','2SM2','MSF']

def get(url, tries=3):
    for i in range(tries):
        r = subprocess.run(["curl","-s","-A",UA,"--max-time","60",url], capture_output=True, text=True)
        t = r.stdout
        if r.returncode == 0 and t and "Server Error" not in t[:100] and "Not Found" not in t[:100]:
            return t
        time.sleep(3*(i+1))
    return None

def fetch_hourly(code):
    cache_f = f"{CACHE}/hourly_{code}.csv"
    if os.path.exists(cache_f):
        df = pd.read_csv(cache_f, parse_dates=["dt"])
        return pd.DatetimeIndex(df["dt"]), df["h"].values
    rows = {}
    start, end = datetime(2025,1,1), datetime(2027,1,1)
    cur, last, skipped = start, False, 0
    while cur < end:
        if cur + timedelta(days=30) > end:
            cur = max(start, end - timedelta(days=30)); last = True
        txt = get(f"{BASE}/listing_page/{code}/{cur.year}/{cur.month}/{cur.day}/30/60/0/30/csv/")
        if txt is None:
            skipped += 1
            print(f"  {code}: Chunk {cur.date()} übersprungen", flush=True)
        else:
            for row in csv.reader(io.StringIO(txt)):
                if len(row) == 3 and row[0] != "Date":
                    try:
                        dt = datetime.strptime(row[0]+" "+row[1], "%Y-%m-%d %H:%M")
                        if start <= dt < end: rows[dt] = float(row[2])
                    except ValueError: pass
        cur += timedelta(days=30); time.sleep(0.6)
        if last: break
    items = sorted(rows.items())
    df = pd.DataFrame(items, columns=["dt","h"])
    df.to_csv(cache_f, index=False)
    return pd.DatetimeIndex(df["dt"]), df["h"].values

def fetch_events(code):
    ev = []
    for (yy,mm) in [(2027,1),(2027,7)]:
        txt = get(f"{BASE}/tide_page/{code}/{yy}/{mm}/1/1/0/1/csv/")
        if txt is None: continue
        for row in csv.reader(io.StringIO(txt)):
            if len(row) >= 6 and row[5] in "HL":
                ev.append((datetime.strptime(row[0]+" "+row[3], "%Y-%m-%d %H:%M"), float(row[4]), row[5]))
        time.sleep(0.6)
    return ev

def oos_stats(coef, ev):
    grid = pd.date_range("2027-01-01","2027-08-01",freq="5min")
    hg = utide.reconstruct(grid, coef, verbose=False)["h"]
    fev = []
    for i in range(1,len(hg)-1):
        if hg[i] >= hg[i-1] and hg[i] > hg[i+1]: fev.append((grid[i].to_pydatetime(), hg[i], "H"))
        elif hg[i] <= hg[i-1] and hg[i] < hg[i+1]: fev.append((grid[i].to_pydatetime(), hg[i], "L"))
    dts, dhs = [], []
    for pdt, ph, pty in ev:
        best = None
        for fdt, fh, fty in fev:
            if fty != pty: continue
            d = abs((fdt-pdt).total_seconds())
            if best is None or d < best[0]: best = (d, fdt, fh)
        if best and best[0] <= 10800:
            dts.append((best[1]-pdt).total_seconds()/60); dhs.append(best[2]-ph)
    if not dts: return None
    return (len(dts), statistics.median(dts), statistics.pstdev(dts),
            statistics.median(dhs), statistics.pstdev(dhs))

results = {}
for code, lat, label in STATIONS:
    t, h = fetch_hourly(code)
    if len(h) < 8000:
        print(f"{label}: zu wenig Daten ({len(h)})"); continue
    ev = fetch_events(code)
    best = None
    for variant, constit in [("auto","auto"), ("ext", None)]:
        if constit == "auto":
            coef = utide.solve(t, h, lat=lat, nodal=True, trend=False, method="ols",
                               conf_int="linear", verbose=False, constit="auto")
            auto_names = [n.strip() for n in coef["name"]]
        else:
            names = sorted(set(auto_names) | set(EXTRA))
            try:
                coef = utide.solve(t, h, lat=lat, nodal=True, trend=False, method="ols",
                                   conf_int="linear", verbose=False, constit=names)
            except Exception as e:
                print(f"  {label} ext fehlgeschlagen: {e}"); continue
        rec = utide.reconstruct(t, coef, verbose=False)
        res = h - rec["h"]
        r2 = 1 - np.sum(res**2)/np.sum((h-h.mean())**2)
        rms = float(np.sqrt(np.mean(res**2)))
        st = oos_stats(coef, ev)
        print(f"{label:20s} [{variant}] pts={len(h)} const={len(coef['name'])} r2={r2:.5f} rms={rms:.4f} | "
              f"OOS dt_med={st[1]:+.1f} sigma_t={st[2]:.1f}min dh_med={st[3]:+.3f} sigma_h={st[4]:.3f}m", flush=True)
        if best is None or st[2] < best[1][2]:
            best = (variant, st, r2, rms, len(coef['name']))
    results[label] = best

print("\n===== BESTE VARIANTE PRO STATION =====")
for label, (variant, st, r2, rms, nc) in results.items():
    print(f"{label:20s} [{variant}] r2={r2:.5f} rms={rms:.3f}m const={nc} | OOS sigma_t={st[2]:.1f}min sigma_h={st[4]:.3f}m dt_med={st[1]:+.1f}min")
json.dump({k: {"variant": v[0], "sigma_t": v[1][2], "sigma_h": v[1][4], "r2": v[2]} for k,v in results.items()},
          open("/tmp/pla/eval_results.json","w"), indent=1)
