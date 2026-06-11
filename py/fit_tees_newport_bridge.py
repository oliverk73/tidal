#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""Tees (Newport) Bridge aus tidetimes.co.uk-HW/LW fitten (Nachzuegler).

Die Station fehlte im 604er-Batch: names_match() in find_missing_tidetimes.py
matchte den Klammerinhalt "Newport" faelschlich auf "Newport (River Usk),
Wales" (300 km entfernt). Fit wie refit_tidetimes_bst.py: Rohzeiten als
FESTES UTC+1 (tidetimes publiziert ganzjaehrig BST), Cosinus-Interpolation,
UTide mit CONSTIT_67. Gibt den fertigen Harmonics-Block auf stdout aus.

Usage: python3 py/fit_tees_newport_bridge.py [JSON [Location]]
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import utide

sys.path.insert(0, '/home/oliver/batch')
sys.path.insert(0, '/home/oliver/py')
from batch_utide_uk_tidetimes import cosine_interpolate, CONSTIT_67
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

JSON_PATH = Path(sys.argv[1] if len(sys.argv) > 1 else
                 '/home/oliver/water_levels/UK_tidetimes/Tees_(Newport)_Bridge.json')
LOCATION = sys.argv[2] if len(sys.argv) > 2 else \
    'Tees (Newport) Bridge, England, United Kingdom'


def main():
    data = json.loads(JSON_PATH.read_text())
    entries = []
    for e in data['entries']:
        try:
            dt = datetime.strptime(f"{e['date']} {e['time']}", '%Y-%m-%d %H:%M')
            entries.append((dt - timedelta(hours=1), e['height_m']))  # festes UTC+1
        except (ValueError, TypeError):
            continue
    entries.sort(key=lambda x: x[0])
    hw_lw = [entries[0]]
    for e in entries[1:]:
        if e[0] > hw_lw[-1][0]:
            hw_lw.append(e)

    # Seitengrenzen-Duplikate: dasselbe Event erscheint auf der Folgeseite
    # nochmal, um 27-100 min verschoben (eigene Tagesseite stimmt mit UKHO/
    # EasyTide ueberein) -> bei gleichem Typ <3.5h Abstand zweites verwerfen
    typed = []
    for e in data['entries']:
        try:
            dt = datetime.strptime(f"{e['date']} {e['time']}", '%Y-%m-%d %H:%M')
        except (ValueError, TypeError):
            continue
        typed.append((dt - timedelta(hours=1), e['type'], e['height_m']))
    typed.sort(key=lambda x: x[0])
    clean = []
    for ev in typed:
        if clean and ev[1] == clean[-1][1] \
           and (ev[0] - clean[-1][0]).total_seconds() < 3.5 * 3600:
            continue
        clean.append(ev)
    n_dup = len(typed) - len(clean)
    if n_dup:
        print(f'# {n_dup} Seitengrenzen-Duplikate entfernt', file=sys.stderr)
    hw_lw = [(t, h) for t, _typ, h in clean]

    lat, lon = float(data['lat']), float(data['lon'])
    dts, levels = cosine_interpolate(hw_lw)
    coef = utide.solve(dts, levels, lat=lat, nodal=True, trend=False,
                       method='ols', conf_int='none', verbose=False,
                       constit=CONSTIT_67)

    from utide._ut_constants import ut_constants
    ct = ut_constants['const']
    allnames = [x.strip() for x in ct.name]
    res = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        if uname not in allnames:
            continue
        speed = ct.freq[allnames.index(uname)] * 360.0
        xn, _ = find_xtide_match(uname, speed)
        if xn:
            res[xn] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)

    rec = utide.reconstruct(dts, coef, verbose=False)
    resid = levels - rec['h']
    ss_tot = float(np.sum((levels - np.mean(levels)) ** 2))
    r2 = 1 - float(np.sum(resid ** 2)) / ss_tot
    rms = float(np.sqrt(np.mean(resid ** 2)))
    print(f"# Fit: R2={r2:.4f} RMS={rms:.4f}m M2={res.get('M2', (0,))[0]:.3f}m "
          f"const={len(res)}", file=sys.stderr)

    lines = []
    lines.append('# Harmonic constants derived from tidetimes.co.uk HW/LW predictions')
    lines.append(f'# using UTide (v{utide.__version__}) with cosine-interpolated HW/LW data')
    lines.append(f'# {len(hw_lw)} HW/LW points -> {len(dts)} interpolated points')
    lines.append(f"# from {dts[0].strftime('%Y-%m-%d')} to {dts[-1].strftime('%Y-%m-%d')}")
    lines.append(f'# R^2 = {r2:.4f}, RMS error = {rms:.4f} m')
    lines.append(f'# Constituents analyzed: {len(res)}')
    lines.append('#')
    lines.append(f'# {LOCATION}')
    lines.append('# BEGIN HOT COMMENTS')
    lines.append('# country: United Kingdom')
    lines.append('# source: Derived from tidetimes.co.uk HW/LW predictions with UTide')
    lines.append(f"# date_imported: {datetime.now().strftime('%Y%m%d')}")
    lines.append('# datum: approximate chart datum')
    lines.append('# confidence: 7')
    lines.append('# bst_fix: 20260611 Erstfit bereits mit Rohzeiten als festem UTC+1'
                 ' (tidetimes publiziert ganzjaehrig BST)')
    lines.append('# !units: meters')
    lines.append(f'# !longitude: {lon:.6f}')
    lines.append(f'# !latitude: {lat:.6f}')
    lines.append(LOCATION)
    lines.append('+00:00 :Europe/London')
    lines.append(f"{float(coef['mean']):.4f} meters")
    for cname, _speed in CONSTITUENTS_175:
        if cname in res and res[cname][0] >= 0.00005:
            amp, pha = res[cname]
            lines.append(f'{cname:15s} {amp:.4f}  {pha:.2f}')
        else:
            lines.append('x 0 0')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
