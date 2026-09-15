#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ersetzt NOAA-Uebertragungen an abgelegenen Inseln im offenen Ozean durch FES2022b-Saetze.

Anlass 15.09.2026 (Oliver: Moeglichkeit 2): an sieben Inseln ohne Nachbarn und ohne Messstation unter
150 km lagen die NOAA-Table-2-Uebertragungen gegen FES2022 um 1.5-4 h daneben (Bezugsort tausende km
entfernt). Im offenen Ozean ist FES verlaesslich; der Satz wird als Modellwert vermerkt.
Name, Position, Zeitzone und Z0 (Mean Tide Level ueber Kartennull) kommen vom NOAA-Satz.

Usage: venv/bin/python py/fes_ersatz_inseln.py [--schreiben]
"""
import os
import re
import sys
import datetime as dt

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                        # noqa: E402
import xtide_modell as X                                           # noqa: E402
from health_check import load_records                              # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = P.ROOT
FES_DIR = os.path.join(ROOT, 'tide_models/fes2022b/ocean_tide_extrapolated')
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_fes2022.txt')
INSELN = ['Amsterdam Island, French Southern']
INSELN_15_09_ERSTLAUF = ['Rotumah Island, Fiji', 'Kardamum Island, Laccadive Islands', 'Cherbaniani Reef, Laccadive Islands',
          'Providence Island, Seychelles', 'Fajã de Água (Brava), Cape Verde', 'Cape Guardafui (Raas Caseyr), Somalia',
          'Rocas, Atol das, Brazil']
BEFUND = {'Amsterdam': 'Durban, M2 -144 min, 24 %', 'Rotumah': 'Davao, +176..+311 min', 'Kardamum': 'Colombo, M2 +247 min, eintaegig 0.37x',
          'Cherbaniani': 'Colombo, M2 +206 min, eintaegig 0.4x', 'Providence': 'Dar es Salaam, +77..+120 min',
          'Faj': 'Dakar, -102..-154 min', 'Cape Guardafui': 'Aden, -87..-101 min, S2 4x', 'Rocas': 'Recife, +87..+97 min, 1.5x'}


def stem(c):
    return 'lambda2' if c == 'LDA2' else c.lower()


def sample(ds, lat, lon):
    lons, lats = ds.variables['lon'][:], ds.variables['lat'][:]
    j = int(np.argmin(np.abs(lons - lon % 360))); k = int(np.argmin(np.abs(lats - lat)))
    amp, ph = ds.variables['amplitude'], ds.variables['phase']
    for r in range(0, 15):
        sa = amp[max(0, k - r):k + r + 1, max(0, j - r):j + r + 1]
        sp = ph[max(0, k - r):k + r + 1, max(0, j - r):j + r + 1]
        m = np.ma.getmaskarray(sa)
        if not np.all(m):
            aa, pp = sa[~m], sp[~m]
            x = np.mean(aa * np.cos(np.radians(pp))); y = np.mean(aa * np.sin(np.radians(pp)))
            return float(np.hypot(x, y)) / 100.0, float(np.degrees(np.arctan2(y, x)) % 360)
    return None, None


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and '/noaa/' in r['file']]
    sel = [r for r in recs if any(r['name'].startswith(n) for n in INSELN)]
    assert len(sel) == len(INSELN), [r['name'] for r in sel]
    namen = X.kopf_lesen(ZIEL)[0]
    werte = {id(r): {} for r in sel}
    for c in namen:
        p = os.path.join(FES_DIR, f'{stem(c)}_fes2022.nc')
        if not os.path.exists(p):
            continue
        ds = nc.Dataset(p)
        for r in sel:
            a, g = sample(ds, r['lat'], r['lon'])
            if a:
                werte[id(r)][c] = (a, g)
        ds.close()
    heute = dt.date.today().strftime('%Y%m%d')
    L = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    for r in sel:
        V = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
        i = V.index(r['name'])
        tz = V[i + 1].split(':', 1)[1] if ':' in V[i + 1] else 'UTC'
        z0 = V[i + 2]
        kopf = '\n'.join(V[max(0, i - 40):i])
        land = re.findall(r'# country: (.*)', kopf)[-1]
        prov = re.findall(r'# (province|state|region): (.*)', kopf)
        w = werte[id(r)]
        print(f"{r['name'][:40]:40} {len(w)} Tiden  M2 {w['M2'][0]:.3f}@{w['M2'][1]:.0f}  K1 {w['K1'][0]:.3f}@{w['K1'][1]:.0f}  Z0 {z0}")
        blk = ['#', f"# {r['name']}", '# BEGIN HOT COMMENTS', f'# country: {land}',
               '# source: FES2022b global ocean tide model (extrapolated), sampled at station location',
               '# note: MODEL-DERIVED (not observations). Ersetzt eine NOAA-Table-2-Uebertragung, die gegen FES',
               f"# note: um Stunden daneben lag ({next(v for k, v in BEFUND.items() if r['name'].startswith(k))}); offener Ozean,",
               '# note: kein Nachbar unter 100 km, keine Messstation unter 150 km (15.09.2026, Oliver).',
               f'# date_imported: {heute}', '# datum: Chart Datum (Z0 = mean tide level above CD, aus NOAA Table 2)',
               '# confidence: 5', '# !units: meters', f"# !longitude: {r['lon']:.4f}", f"# !latitude: {r['lat']:.4f}"]
        blk += [f'# {k}: {v}' for k, v in prov[-1:]]
        blk += [r['name'], f'+00:00 :{tz}', z0]
        for c in namen:
            blk.append(f'{c:<15s} {w[c][0]:.4f}  {w[c][1]:.2f}' if c in w and w[c][0] > 0.00005 else 'x 0 0')
        if r['name'] in L:
            print('   existiert schon in harmonics_fes2022'); continue
        L += blk
    if '--schreiben' in argv:
        schreiben(ZIEL, '\n'.join(L) + '\n')
        print('->', os.path.relpath(ZIEL, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
