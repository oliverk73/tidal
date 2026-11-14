#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X-TRACK-Kuestentidenkonstanten (AVISO/CTOH, Oliver 14.11.2026) an Messsaetzen eichen.

Quelle: tide_models/xtrack/<REGION>/<TP+J1+J2|TPN+J1N>/*.mgr.nc(.lzma), T/P-Jason 1993-2015, Punkte alle 6-7 km,
Greenwich-Phasen. Frage: Taugt X-TRACK als Zeuge gegen FES? Je Messsatz (utide_observations, TICON) der naechste
X-TRACK-Punkt bis MAXKM; verglichen ueber M2 S2 N2 K1 O1 (Vektor-RMS cm und % wie fes_neu_geeicht):
  X   = X-TRACK am Punkt P gegen den Pegel G
  F   = FES am Pegel G gegen den Pegel (der FES-Fehler, den ein Zeuge finden soll)
  F+X = FES(G) + [X(P) - FES(P)]  (FES am Pegel, um die X-TRACK-Abweichung bei P berichtigt)
Wenn F+X deutlich unter F liegt, sagt X-TRACK den FES-Fehler voraus.

Usage: venv/bin/python py/xtrack_eichung.py [--maxkm 15]  -> harmonics/help/xtrack_eichung.csv
"""
import cmath, csv, glob, lzma, math, os, statistics as st, sys, tempfile
import numpy as np
import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR, ROOT                # noqa: E402
from fes_neu_geeicht import stem                                   # noqa: E402

XT = os.path.join(ROOT, 'tide_models/xtrack')
C = ['M2', 'S2', 'N2', 'K1', 'O1']


def xtrack_punkte():
    """Alle Spurpunkte: (lat, lon, {c: z}, mse_M2, n, datei). z = a*e^(-ig) wie health_check."""
    P = []
    for f in sorted(glob.glob(XT + '/*/*/*.nc*')):
        if f.endswith('.lzma'):
            if os.path.exists(f[:-5]):
                continue
            with lzma.open(f) as q, open(f[:-5], 'wb') as z:
                z.write(q.read())
            f = f[:-5]
        d = nc.Dataset(f)
        namen = [s.strip().upper() for s in nc.chartostring(np.asarray(d['constituentname'][:]))]
        ix = {c: namen.index(c) for c in C if c in namen}
        A, G = d['amplitude'][:], d['phase_lag'][:]
        E, N = d['mean_square_error'][:], d['sample'][:]
        for i in range(len(d['lat'])):
            if np.ma.is_masked(A[i, ix['M2']]) or np.ma.is_masked(d['lat'][i]) or np.ma.is_masked(d['lon'][i]):
                continue                                           # 14.11.: Spurpunkte ohne Koordinaten (NaN) gibt es
            z = {c: cmath.rect(float(A[i, k]), -math.radians(float(G[i, k]))) for c, k in ix.items() if not np.ma.is_masked(A[i, k])}
            P.append((float(d['lat'][i]), float(d['lon'][i]) if d['lon'][i] <= 180 else float(d['lon'][i]) - 360,
                      z, float(E[i, ix['M2']]), int(N[i]), os.path.basename(f)))
    return P


ds = {}


def fes(la, lo):
    out = {}
    for c in C:
        if c not in ds:
            ds[c] = nc.Dataset(os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc'))
        a, g = sample(ds[c], la, lo)
        if a:
            out[c] = cmath.rect(a, -math.radians(g))
    return out


def fehler(a, b):
    cs = [c for c in C if c in a and c in b]
    cm = 100 * math.sqrt(sum(abs(a[c] - b[c]) ** 2 for c in cs) / 2)
    return cm, cm / 100 / max(0.15, sum(abs(b[c]) for c in cs))   # 14.11.: cm/m-Fehler (Faktor 100) behoben


def main(argv):
    maxkm = float(argv[argv.index('--maxkm') + 1]) if '--maxkm' in argv else 15.0
    P = xtrack_punkte()
    print(len(P), 'X-TRACK-Punkte')
    lat = np.radians([p[0] for p in P]); lon = np.radians([p[1] for p in P])
    zeilen = []
    for r in H.load_records():
        b = os.path.basename(r['file'])
        if r['current'] or not r['lat'] or not ('utide_observations' in b or 'ticon' in b) or 'M2' not in r['z']:
            continue
        la, lo = math.radians(r['lat']), math.radians(r['lon'])
        d = 6371 * np.arccos(np.clip(np.sin(la) * np.sin(lat) + np.cos(la) * np.cos(lat) * np.cos(lon - lo), -1, 1))
        i = int(np.nanargmin(d))
        if d[i] > maxkm:
            continue
        p = P[i]
        g = r['z']
        fg, fp = fes(r['lat'], r['lon']), fes(p[0], p[1])
        if not all(c in fg and c in fp and c in p[2] for c in C):
            continue
        fx = {c: fg[c] + p[2][c] - fp[c] for c in C}
        ex, ef, efx = fehler(p[2], g), fehler(fg, g), fehler(fx, g)
        zeilen.append(dict(name=r['name'], datei=b, lat=r['lat'], lon=r['lon'], km=round(float(d[i]), 1),
                           m2_cm=round(100 * abs(g['M2']), 1), n=p[4], mse_m2_cm=round(100 * p[3], 2),
                           x_cm=round(ex[0], 1), x_pct=round(100 * ex[1], 1), fes_cm=round(ef[0], 1),
                           fes_pct=round(100 * ef[1], 1), fesx_cm=round(efx[0], 1), fesx_pct=round(100 * efx[1], 1),
                           spur=p[5]))
    aus = os.path.join(ROOT, 'harmonics/help/xtrack_eichung.csv')
    if not zeilen:
        sys.exit('keine Pegel mit X-TRACK-Punkt')
    with open(aus, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen[0]))
        w.writeheader(); w.writerows(zeilen)
    print(len(zeilen), 'Pegel mit X-TRACK-Punkt bis %.0f km -> %s' % (maxkm, os.path.relpath(aus, ROOT)))
    md = lambda L, k: st.median([z[k] for z in L]) if L else float('nan')
    for a, b in [(0, 5), (5, 10), (10, 15), (15, 30)]:
        L = [z for z in zeilen if a <= z['km'] < b]
        print('%2d-%2d km: %4d Pegel  X %.1f %%  FES %.1f %%  FES+X %.1f %%' % (a, b, len(L), md(L, 'x_pct'), md(L, 'fes_pct'), md(L, 'fesx_pct')))
    for s in (5, 10, 20):                                          # FES-Fehler, die X-TRACK erkennen soll
        L = [z for z in zeilen if z['fes_pct'] >= s]
        print('FES >= %2d %%: %4d Pegel, FES %.1f %% -> FES+X %.1f %%, besser bei %d' % (
            s, len(L), md(L, 'fes_pct'), md(L, 'fesx_pct'), sum(z['fesx_pct'] < z['fes_pct'] for z in L)))


if __name__ == '__main__':
    main(sys.argv[1:])
