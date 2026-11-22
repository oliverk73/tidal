#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gegenprobe der Saint-Laurent-Atlassaetze (CHS-ATLAS-STL) gegen die DFO-Modellwoche mpoStleCourants 8.-15.4.2026
(ERDDAP cioos -> ogsl, 400 m; curl -L, Browser-User-Agent). Je Satz: Box +-700 m, Modellstrom auf der Satzachse gegen die
Satzkurve (r, Faktor), beste Zelle im Umkreis, Einheitlichkeit der Modellzellen. 22.11.2026: Median r 0,93; Abschnitt S9
im April-Hochwasser nur ~0,5 (Modell dort teils trocken). Ausgabe scratchpad-CSV, Pfade unten anpassen.
"""
import sys, re, os, io, json, math, subprocess, numpy as np, pandas as pd, datetime as dt
sys.path.insert(0, '/home/oliver/weather/py')
import xtide_modell as X
P = '/home/oliver/weather/harmonics/utide/harmonics_utide_current_tables.txt'
T = open(P, encoding='iso-8859-1').read().split('\n')
S = []
for n, z in enumerate(T):
    m = re.match(r'# station_id_context: CHS-ATLAS-STL-(S\d|TABLE)', z)
    if m:
        la = lo = ax = None
        for q in range(n, n + 40):
            if T[q].startswith('# !latitude'): la = float(T[q].split(':')[1])
            if T[q].startswith('# !longitude'): lo = float(T[q].split(':')[1])
            if T[q].startswith('# major_axis_deg_true'): ax = float(T[q].split(':')[1])
            if not T[q].startswith('#'):
                S.append((T[q], m.group(1), la, lo, ax)); break
CACHE = os.path.join('/home/oliver/weather/quellen/tidal_streams/Canada_CHS_atlas', 'dfo_woche_cache')
os.makedirs(CACHE, exist_ok=True)
namen, speeds, arg, fak = X.kopf_lesen('/home/oliver/weather/harmonics/utide/harmonics_fes2022.txt')
res = []
for name, art, la, lo, ax in S:
    f = os.path.join(CACHE, '%.4f_%.4f.csv' % (la, lo))
    if not os.path.exists(f):
        url = ('https://erddap.cioos.ca/erddap/griddap/mpoStleCourants.csv?u%%5B(2026-04-08T01:00:00Z):1:(2026-04-15T00:00:00Z)%%5D%%5B(%.4f):1:(%.4f)%%5D%%5B(%.4f):1:(%.4f)%%5D,v%%5B(2026-04-08T01:00:00Z):1:(2026-04-15T00:00:00Z)%%5D%%5B(%.4f):1:(%.4f)%%5D%%5B(%.4f):1:(%.4f)%%5D'
               % (la - .0065, la + .0065, lo - .0095, lo + .0095, la - .0065, la + .0065, lo - .0095, lo + .0095))
        r = subprocess.run(['curl', '-s', '-L', '-m', '300', '-A', 'Mozilla/5.0', '-o', f, url])
    try:
        d = pd.read_csv(f, skiprows=[1])
    except Exception as e:
        print('FEHLT', name, e); continue
    if 'u' not in d.columns:
        print('FEHLER', name); os.remove(f); continue
    d = d.dropna()
    d = d[(d.u.abs() < 100)]
    if d.empty:
        print('LEER', name); continue
    d['t'] = pd.to_datetime(d.time, utc=True).map(lambda x: x.timestamp())
    z0, werte, einheit, mer = X.satz_lesen(P, name)
    tt = np.sort(d.t.unique())
    pred = X.kurve(tt, z0, werte, namen, speeds, arg, fak)
    a = math.radians(ax)
    zellen = d.groupby(['latitude', 'longitude'])
    best = None; ser = {}
    for (cla, clo), g in zellen:
        g = g.set_index('t').reindex(tt)
        if g.u.isna().sum() > 5 or (g.u.std() < 0.01 and g.v.std() < 0.01): continue
        ua = (g.u * math.sin(a) + g.v * math.cos(a)).values / 0.514444
        ser[(cla, clo)] = (g.u.values, g.v.values, ua)
    if not ser: print('LAND', name); continue
    # Zelle am Satz
    k0 = min(ser, key=lambda c: (c[0] - la) ** 2 + ((c[1] - lo) * 0.68) ** 2)
    ua = ser[k0][2]; m = np.isfinite(ua)
    r = np.corrcoef(pred[m], ua[m])[0, 1]
    fakt = np.std(pred[m]) / np.std(ua[m])
    # Heterogenitaet: Korrelation der Vektorreihen der Nachbarzellen mit der Satzzelle (ohne Mittel)
    u0, v0 = ser[k0][0] - np.nanmean(ser[k0][0]), ser[k0][1] - np.nanmean(ser[k0][1])
    rn = []
    for c, (u, v, _) in ser.items():
        if c == k0: continue
        u, v = u - np.nanmean(u), v - np.nanmean(v)
        mm = np.isfinite(u) & np.isfinite(u0)
        rn.append(np.sum(u[mm] * u0[mm] + v[mm] * v0[mm]) / np.sqrt(np.sum(u[mm]**2 + v[mm]**2) * np.sum(u0[mm]**2 + v0[mm]**2)))
    # bester Fit der Satzkurve an irgendeine Zelle im Umkreis
    rmax = max(np.corrcoef(pred[np.isfinite(s[2])], s[2][np.isfinite(s[2])])[0, 1] for s in ser.values())
    res.append(dict(name=name, art=art, lat=la, lon=lo, r=round(r, 3), faktor=round(fakt, 2), r_bester=round(rmax, 3),
                    nachbar_min=round(min(rn), 2) if rn else np.nan, zellen=len(ser)))
    print('%-70s %-5s r %+.2f  x%.2f  bester %+.2f  Nachbar-min %+.2f  (%d)' % (name[:70], art, r, fakt, rmax, min(rn) if rn else np.nan, len(ser)), flush=True)
pd.DataFrame(res).to_csv('/home/oliver/weather/harmonics/help/stlorenz_dfo_probe.csv', index=False)
