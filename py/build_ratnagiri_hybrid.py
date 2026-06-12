#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ratnagiri-Hybrid-Station: gemessene Hauptkonstituenten + FES2022b-Ergaenzung.

Messbasis: JETIR1810174 (Manikandan & Venkatachalapathy 2018), 21-Tage-
Druckpegel Feb 15 - Mar 13 2015 bei 16.99N 73.27E, t_tide-Analyse, Phasen
IST-lokal (verifiziert: M2/S2 +-4 Grad, Amplituden +-3 cm gegen FES2022).
Gemessen uebernommen: M2, S2, O1, MSF, M3, SK3, M4, MS4, M6.
Aus FES2022b ergaenzt (21d-Record kann sie nicht aufloesen): N2, K2, P1,
Q1, NU2, MU2, L2, T2, 2N2 sowie K1 (Mess-K1 ist P1-verseucht, +21 Grad).
Z0 = |Min| einer 19-Jahres-Rekonstruktion -> Datum ~ LAT/CD.

Usage: python3 py/build_ratnagiri_hybrid.py > block.txt
"""
from __future__ import annotations
import sys
from datetime import datetime

import netCDF4 as nc
import numpy as np

sys.path.insert(0, '/home/oliver/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175

LAT, LON = 16.9900, 73.2700
NAME = 'Ratnagiri, Maharashtra, India'
FES_DIR = '/home/oliver/tide_models/fes2022b/ocean_tide_extrapolated'
TZ_H = 5.5

# XTide-Name -> Speed deg/h (aus CONSTITUENTS_175)
SPEED = {c: s for c, s in CONSTITUENTS_175}

# Paper Table 1, Ratnagiri: (Amp m, Phase IST-lokal)
MEASURED = {
    'M2':  (0.71, 315.17),
    'S2':  (0.29, 351.27),
    'O1':  (0.17, 56.78),
    'MSF': (0.03, 168.56),
    'M3':  (0.01, 347.16),
    'SK3': (0.01, 209.94),
    'M4':  (0.02, 14.68),
    'MS4': (0.02, 55.91),
    'M6':  (0.02, 253.23),
}
# FES-Dateiname -> XTide-Name
FES_ADD = {'k1': 'K1', 'n2': 'N2', 'k2': 'K2', 'p1': 'P1', 'q1': 'Q1',
           'nu2': 'NU2', 'mu2': 'MU2', 'l2': 'L2', 't2': 'T2', '2n2': '2N2'}


def fes_point(cname):
    ds = nc.Dataset(f'{FES_DIR}/{cname}_fes2022.nc')
    lats = ds.variables['lat'][:]
    lons = ds.variables['lon'][:]
    i = int(np.abs(lats - LAT).argmin())
    j = int(np.abs(lons - LON % 360).argmin())
    amp = ds.variables['amplitude']
    pha = ds.variables['phase']
    found = None
    for di in range(0, 10):
        for ii in range(i - di, i + di + 1):
            for jj in range(j - di, j + di + 1):
                a = amp[ii, jj]
                if not np.ma.is_masked(a):
                    found = (float(a) / 100.0, float(pha[ii, jj]) % 360.0)
                    break
            if found:
                break
        if found:
            break
    ds.close()
    return found


def main():
    cm = {}
    for xt, (a, g_loc) in MEASURED.items():
        g_grw = (g_loc - SPEED[xt] * TZ_H) % 360.0
        cm[xt] = (a, g_grw, 'meas')
    for fn, xt in FES_ADD.items():
        a, g = fes_point(fn)
        cm[xt] = (a, g, 'fes')
        print(f'# FES {xt}: {a:.3f} m @ {g:.1f} grw', file=sys.stderr)

    # 19-Jahres-Rekonstruktion (stuendlich) fuer Z0~LAT, ueber utide
    import utide
    from utide._ut_constants import ut_constants
    from generate_germany_harmonics_175 import find_xtide_match
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    # utide-Namen zu unseren XTide-Namen finden
    u2x = {}
    for i, u in enumerate(unames):
        xt, _ = find_xtide_match(u, float(table.freq[i]) * 360.0)
        if xt in cm and xt not in u2x.values():
            u2x[u] = xt
    missing = [x for x in cm if x not in u2x.values()]
    if missing:
        print(f'# WARNUNG: kein utide-Match fuer {missing}', file=sys.stderr)
    names = list(u2x.keys())
    from datetime import timedelta
    t0 = datetime(2015, 1, 1)
    tsolve = np.array([t0 + timedelta(hours=h) for h in range(24 * 400)])
    coef = utide.solve(tsolve, np.zeros(len(tsolve)), lat=LAT, nodal=True,
                       trend=False, method='ols', conf_int='none',
                       verbose=False, constit=names)
    for i, u in enumerate(coef['name']):
        xt = u2x[u.strip()]
        coef['A'][i] = cm[xt][0]
        coef['g'][i] = cm[xt][1]
    coef['mean'] = 0.0
    coef['slope'] = 0.0
    t0 = datetime(2008, 1, 1)
    t = np.array([t0 + timedelta(hours=h) for h in range(19 * 8766)])
    rec = utide.reconstruct(t, coef, verbose=False)
    z0 = -float(np.min(rec['h']))
    print(f'# 19y-Rekonstruktion: min={-z0:.3f} max={np.max(rec["h"]):.3f} -> Z0={z0:.3f}',
          file=sys.stderr)

    L = [
        "#", f"# {NAME}", "# BEGIN HOT COMMENTS", "# country: India",
        "# state: Maharashtra",
        "# source: Hybrid: 21d gauge harmonic analysis (JETIR 2018) + FES2022b",
        "# note: Measured M2/S2/O1/MSF/M3/SK3/M4/MS4/M6 from 21-day Valeport gauge",
        "# note: record Feb 15-Mar 13 2015 (Manikandan & Venkatachalapathy, JETIR",
        "# note: 5(10) 2018, IST phases verified vs FES within 4 deg for M2/S2).",
        "# note: K1/N2/K2/P1/Q1/NU2/MU2/L2/T2/2N2 supplemented from FES2022b",
        "# note: (21d record cannot resolve them; measured K1 was P1-contaminated).",
        "# note: Z0 from 19y reconstruction minimum (CD~LAT). No SA/SSA.",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (approx., CD~LAT from constituents)",
        "# confidence: 4",
        "# !units: meters",
        f"# !longitude: {LON:.4f}", f"# !latitude: {LAT:.4f}",
        NAME, '+00:00 :Asia/Kolkata', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
