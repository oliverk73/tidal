#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phu Quy (Insel vor Phan Thiet) aus NCHMF-Bulletin-HW/LW fitten.

Quelle: NCHMF-10-Tage-Bulletins (Wayback 2021-12..2022, parse_nchmf_bulletins.py),
je Tag 1 Hmax + 1 Hmin (Ortszeit UTC+7, cm ueber Kartennull — Datum gegen
Qui-Nhon-UHSLC validiert, +12cm wie ICOE). Ganztaegig dominiertes Regime
(K1/O1 >> M2) -> 1 HW + 1 NW pro Tag ist dort fast der volle Zyklus.
Cosinus-Interpolation + UTide (CONSTIT_67), Greenwich-Phasen, +00:00.

Usage: python3 py/fit_phuquy_nchmf.py [json] > block.txt
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/py')
sys.path.insert(0, '/home/oliver/batch')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67

JSON = Path(sys.argv[1] if len(sys.argv) > 1 else
            '/home/oliver/water_levels/VN_nchmf/ph_qu.json')
NAME = 'Phu Quy, Vietnam'
LAT, LON = 10.5333, 108.9333  # VHO-Stationsverzeichnis ID27 (10deg32'N 108deg56'E)


def main():
    d = json.loads(JSON.read_text())
    ev = []
    for day, rec in d.items():
        for typ in ('HW', 'LW'):
            if typ in rec:
                t, cm = rec[typ]
                dt = datetime.fromisoformat(f'{day}T{t}') - timedelta(hours=7)
                ev.append((dt, float(cm) / 100.0))
    ev.sort(key=lambda x: x[0])
    hw_lw = [ev[0]] + [b for a, b in zip(ev, ev[1:]) if b[0] > a[0]]
    print(f'# {len(hw_lw)} HW/LW-Events {hw_lw[0][0]:%Y-%m-%d}..{hw_lw[-1][0]:%Y-%m-%d}',
          file=sys.stderr)
    # Wayback-Luecken: nur innerhalb zusammenhaengender Segmente interpolieren,
    # sonst Riesenboegen ueber Wochenluecken (Z0/SA-Leakage)
    segs = [[hw_lw[0]]]
    for e in hw_lw[1:]:
        if (e[0] - segs[-1][-1][0]).total_seconds() > 30 * 3600:
            segs.append([e])
        else:
            segs[-1].append(e)
    dts, lv = [], []
    for s in segs:
        if len(s) < 8:
            continue
        t, v = cosine_interpolate(s)
        if t is not None:
            dts += list(t)
            lv += list(v)
    dts, lv = np.array(dts), np.array(lv)
    print(f'# {len(segs)} Segmente -> {len(lv)} Interp-Punkte', file=sys.stderr)
    # Reduzierter Satz: 67er-Satz aliast auf lueckigen ~6-Monats-HW/LW-Daten
    # massiv (K1>1m); aufloesbar sind nur die Hauptkonstituenten
    constit = ['K1', 'O1', 'P1', 'Q1', 'M2', 'S2', 'N2', 'K2']
    coef = utide.solve(dts, lv, lat=LAT, nodal=True, trend=False, method='ols',
                       conf_int='none', verbose=False, constit=constit)
    rec = utide.reconstruct(dts, coef, verbose=False)
    resid = lv - rec['h']
    r2 = 1 - float(np.sum(resid ** 2)) / float(np.sum((lv - lv.mean()) ** 2))
    rms = float(np.sqrt(np.mean(resid ** 2)))

    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u not in unames:
            continue
        xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
        if xt:
            cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(coef['mean'])
    m2, k1, o1 = (cm.get(c, (0, 0)) for c in ('M2', 'K1', 'O1'))
    print(f'# r2={r2:.4f} rms={rms:.4f} Z0={z0:.2f} M2={m2[0]:.2f}@{m2[1]:.0f} '
          f'K1={k1[0]:.2f}@{k1[1]:.0f} O1={o1[0]:.2f}@{o1[1]:.0f}', file=sys.stderr)

    n_ana = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        "#", f"# {NAME}", "# BEGIN HOT COMMENTS", "# country: Vietnam",
        "# source: NCHMF 10-day tide bulletins (Hmax/Hmin, via Wayback) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (Kartennull der amtlichen Tidetafel)",
        "# datum_note: gegen Qui Nhon UHSLC/ICOE validiert (+12cm vs UHSLC-Z0)",
        "# confidence: 5",
        f"# utide: pts={len(hw_lw)} hwlw period={hw_lw[0][0]:%Y-%m-%d}..{hw_lw[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={n_ana}",
        "# !units: meters",
        f"# !longitude: {LON:.4f}", f"# !latitude: {LAT:.4f}",
        NAME, '+00:00 :Asia/Ho_Chi_Minh', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    print('\n'.join(L))


if __name__ == '__main__':
    main()
