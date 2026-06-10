#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""UTide-Fit fuer Magadan (Ochotskisches Meer) aus Kolymskoe-UGMS-Tidenkalendern.

Quelle: rybalka-magadan.ru (abgetippte UGMS-Tabellen, Bucht Gertnera,
Apr 2025 - Mai 2026, Magadan-Zeit UTC+11) -> py/parse_rybalka_magadan.py.
Korrekturtabelle der Quelle: Basis Nagaeva = 0 min, Gertnera = -11 min
=> Nagaeva-Block per Phasenshift g += speed * (11/60) aus dem Gertnera-Fit.

Schreibt 2 neue Stationen in harmonics_utide_tidetables.txt (UTide TC):
  - Magadan (Bukhta Nagaeva), Russia   [Stadt/Hafen Magadan]
  - Bukhta Gertnera (Magadan), Russia  [Basisstation der Tabellen]

Aufruf:  python3 py/fit_magadan_rybalka.py [--write]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67

EVENTS = Path('/home/oliver/water_levels/RU_magadan/gertnera_events_utc.json')
HARM = Path('/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt')
SOURCE = 'Kolymskoe UGMS tide tables (via rybalka-magadan.ru) with UTide'
MERIDIAN = '+00:00 :Asia/Magadan'
SPEED = dict(CONSTITUENTS_175)

# Lage: Gertnera oestlich, Nagaeva (Stadt/Hafen Magadan) westlich der
# Staritskiy-Halbinsel; Tabellen-Poprawka Nagaeva = Gertnera + 11 min.
STATIONS = [
    ('Magadan (Bukhta Nagaeva), Russia', 59.5530, 150.7600, +11.0),
    ('Bukhta Gertnera (Magadan), Russia', 59.5830, 150.8830, 0.0),
]


def load_events():
    evs = json.loads(EVENTS.read_text())
    return [(datetime.strptime(e['t'], '%Y-%m-%d %H:%M'), e['h']) for e in evs]


def fit(hw_lw, lat):
    dts, levels = cosine_interpolate(hw_lw)
    coef = utide.solve(dts, levels, lat=lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)
    rec = utide.reconstruct(dts, coef, verbose=False)
    resid = levels - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((levels - np.mean(levels)) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))
    return coef, r2, rms, len(dts), dts[0], dts[-1]


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


def build_block(name, lat, lon, z0, cm, shift_min, r2, rms, n_hwlw, npts, t0, t1):
    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Russia",
        f"# source: {SOURCE}",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: Chart Datum (Russia, nul' glubin ~ LAT)",
        "# confidence: 6",
        "# coordinates: approximate",
    ]
    if shift_min:
        L.append(f"# offset_note: Phasen = Gertnera-Fit + speed*{shift_min:.0f}min (Poprawka-Tabelle der Quelle, Basis Nagaeva)")
    L += [
        f"# utide: pts={npts} hwlw={n_hwlw} period={t0:%Y-%m-%d}..{t1:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, MERIDIAN, f"{z0:.4f} meters",
    ]
    for cn, sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            amp, pha = cm[cn]
            pha = (pha + sp * shift_min / 60.0) % 360.0
            L.append(f"{cn:15s} {amp:.4f}  {pha:.2f}")
        else:
            L.append("x 0 0")
    return L


def main():
    write = '--write' in sys.argv
    hw_lw = load_events()
    print(f'{len(hw_lw)} HW/LW-Events {hw_lw[0][0]:%Y-%m-%d}..{hw_lw[-1][0]:%Y-%m-%d}')
    coef, r2, rms, npts, t0, t1 = fit(list(hw_lw), STATIONS[1][1])
    cm = map_const(coef)
    z0 = float(coef['mean'])
    m2 = cm.get('M2', (0, 0))
    k1 = cm.get('K1', (0, 0))
    print(f'R2={r2:.4f} RMS={rms:.3f}m Z0={z0:.2f}m M2={m2[0]:.3f}m@{m2[1]:.1f} K1={k1[0]:.3f}m@{k1[1]:.1f}')

    lines = HARM.read_text(encoding='iso-8859-1').split('\n')
    for name, lat, lon, shift in STATIONS:
        if any(l == name for l in lines):
            raise SystemExit(f'Station existiert schon: {name}')
        blk = build_block(name, lat, lon, z0, cm, shift, r2, rms, len(hw_lw), npts, t0, t1)
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        lines = lines[:end] + blk + lines[end:]
        print(f'NEU: {name}')

    if write:
        HARM.write_text('\n'.join(lines) + '\n', encoding='iso-8859-1')
        print(f'Geschrieben: {HARM}')
    else:
        print('(Dry-run — --write zum Schreiben.)')


if __name__ == '__main__':
    main()
