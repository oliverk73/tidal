#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""UTide-Fit fuer Qinhuangdao aus offiziellen NMDIS-Stundenwerten.

Quelle: mds.nmdis.org.cn (NMDIS, Herausgeber der chinesischen Tidetafeln),
stuendliche Tidenhoehen (cm ueber Tidenull = theoretisch niedrigste Tide,
benchmark "91cm unter Mittelwasser"), Beijing-Zeit UTC+8
-> py/download_nmdis_tides.py T020 2024-07-01 2026-06-30.

Qinhuangdao liegt nahe der M2-Amphidromie des Bohai: ueberwiegend
ganztaegige Gezeit (K1/O1 dominieren, M2 klein).

Schreibt 1 neue Station in harmonics_utide_tidetables.txt (UTide TC).
Aufruf:  python3 py/fit_qinhuangdao_nmdis.py [--write]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import CONSTIT_67

DATA = Path('/home/oliver/water_levels/CN_nmdis/T020_2024-07-01_2026-06-30.json')
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
SOURCE = 'NMDIS hourly tide predictions (mds.nmdis.org.cn, sitecode T020) with UTide'
NAME = 'Qinhuangdao, Hebei, China'
LAT, LON = 39.9167, 119.6167   # API: 39 54'N 119 36'E
MERIDIAN = '+00:00 :Asia/Shanghai'
UTC_OFF = timedelta(hours=8)


def load_series():
    d = json.loads(DATA.read_text())
    t, v = [], []
    for day, rec in sorted(d.items()):
        if not rec:
            continue
        base = datetime.fromisoformat(day)
        for h, cm in enumerate(rec['hourly_cm']):
            if cm is None:
                continue
            t.append(base + timedelta(hours=h) - UTC_OFF)
            v.append(float(cm) / 100.0)
    return np.array(t), np.array(v)


def map_const(coef):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    out = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        speed = table.freq[unames.index(u)] * 360.0
        xt, _ = find_xtide_match(u, speed)
        if xt:
            out[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    return out


def build_block(z0, cm, r2, rms, npts, t0, t1):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {NAME}", "# BEGIN HOT COMMENTS", "# country: China",
        f"# source: {SOURCE}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (China, theoretical lowest tide, 91cm below MSL)",
        "# confidence: 7",
        f"# utide: pts={npts} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {LON:.4f}", f"# !latitude: {LAT:.4f}",
        NAME, MERIDIAN, f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return L


def main():
    write = '--write' in sys.argv
    t, v = load_series()
    print(f'{len(t)} Stundenwerte {t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d}, '
          f'min={v.min():.2f} max={v.max():.2f} mean={v.mean():.3f} m')
    coef = utide.solve(t, v, lat=LAT, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=CONSTIT_67)
    rec = utide.reconstruct(t, coef, verbose=False)
    resid = v - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((v - v.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    cm = map_const(coef)
    z0 = float(coef['mean'])
    for c in ['M2', 'S2', 'K1', 'O1', 'P1', 'Q1']:
        a, g = cm.get(c, (0, 0))
        print(f'  {c}: {a:.3f} m @ {g:.1f}')
    print(f'R2={r2:.4f} RMS={rms:.3f}m Z0={z0:.3f}m (erwartet ~0.91)')

    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    if any(l == NAME for l in lines):
        raise SystemExit(f'Station existiert schon: {NAME}')
    blk = build_block(z0, cm, r2, rms, len(t), t[0], t[-1])
    end = len(lines)
    while end > 0 and lines[end - 1].strip() == '':
        end -= 1
    lines = lines[:end] + blk + lines[end:]
    if write:
        HARM.write_text('\n'.join(lines) + '\n', encoding='iso-8859-1')
        print(f'Geschrieben: {HARM}')
    else:
        print('(Dry-run — --write zum Schreiben.)')


if __name__ == '__main__':
    main()
