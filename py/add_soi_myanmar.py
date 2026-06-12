#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8 Myanmar-Stationen aus den Survey-of-India-Monatstafeln als NEUE Eintraege
in harmonics_utide_tidetables.txt (bestehende 1997er/NMDIS/obs-Stationen
bleiben unangetastet — bewusste Duplikate, vgl. NMDIS-intl-Session).

TZ-Konvention der PDFs: 'TIME ZONE -0630' = UTC+6:30 (invertiert, wie Indien).
Validierung: OOS Juli 2026 + FES2022-M2-Phasencheck (Zeitzonen-Beweis).

Usage: python3 py/add_soi_myanmar.py [--write]
"""
from __future__ import annotations
import contextlib
import io
import os
import sys
import tempfile
from datetime import datetime

import numpy as np

sys.path.insert(0, '/home/oliver/py')
from fit_soi_tide_pdf import collect_events
from refit_soi_stations import fit_events, oos_july
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

HFILE = '/home/oliver/harmonics/utide/harmonics_utide_tidetables.txt'
FES_DIR = '/home/oliver/tide_models/fes2022b/ocean_tide_extrapolated'

# alias, neuer Name, lat, lon (PDF-Kopf)
STATIONS = [
    ('AKYAB', 'Akyab (Sittwe), Myanmar', 20.1333, 92.9000),
    ('AMHERST', 'Amherst (Kyaikkami), Myanmar', 16.0833, 97.5667),
    ('BASSEIN', 'Pathein (Bassein River), Myanmar', 16.7833, 94.7833),
    ('DIAMOND ISLAND', 'Diamond Island (Bassein River), Myanmar', 15.8667, 94.2833),
    ('ELEPHANT POINT', 'Elephant Point (Yangon River), Myanmar', 16.5000, 96.3000),
    ('MERGUI', 'Mergui (Myeik), Myanmar', 12.4333, 98.6000),
    ('MOULMEIN', 'Moulmein (Mawlamyine), Myanmar', 16.4833, 97.6167),
    ('YANGON', 'Yangon, Myanmar', 16.7667, 96.1667),
]


def fes_m2(lat, lon):
    import netCDF4
    ds = netCDF4.Dataset(f'{FES_DIR}/m2_fes2022.nc')
    lats = ds['lat'][:]
    lons = ds['lon'][:]
    li = int(np.abs(lats - lat).argmin())
    lo = int(np.abs(lons - (lon % 360)).argmin())
    amp, ph = ds['amplitude'][li, lo], ds['phase'][li, lo]
    if np.ma.is_masked(amp):
        for d in range(1, 10):
            sa = ds['amplitude'][li - d:li + d + 1, lo - d:lo + d + 1]
            sp = ds['phase'][li - d:li + d + 1, lo - d:lo + d + 1]
            if not np.ma.getmaskarray(sa).all():
                amp, ph = sa.compressed()[0], sp.compressed()[0]
                break
    ds.close()
    return float(amp) / 100.0, float(ph) % 360


def make_block(name, lat, lon, coef, r2, rms, events, conf):
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    cm = {}
    for i, u in enumerate(coef['name']):
        u = u.strip()
        if u in unames:
            xt, _ = find_xtide_match(u, table.freq[unames.index(u)] * 360.0)
            if xt:
                cm[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360.0)
    z0 = float(coef['mean'])
    L = [
        "#", f"# {name}", "# BEGIN HOT COMMENTS", "# country: Myanmar",
        "# source: Survey of India monthly tide tables (surveyofindia.gov.in) with UTide",
        f"# date_imported: {datetime.now():%Y%m%d}",
        "# datum: chart datum (per Survey of India tide tables)",
        f"# confidence: {conf}",
        f"# utide: pts={len(events)} hwlw period={events[0][0]:%Y-%m-%d}..{events[-1][0]:%Y-%m-%d} r2={r2:.4f} rms={rms:.4f}m const={sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)}",
        "# !units: meters", f"# !longitude: {lon:.4f}", f"# !latitude: {lat:.4f}",
        name, '+00:00 :Asia/Yangon', f"{z0:.4f} meters",
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f"{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}")
        else:
            L.append("x 0 0")
    return '\n'.join(L), cm


def main():
    write = '--write' in sys.argv
    text = open(HFILE, encoding='iso-8859-1').read()
    n_before = text.count('# !units:')
    blocks = []
    for alias, name, lat, lon in STATIONS:
        assert ('\n' + name + '\n') not in text, f'Name existiert schon: {name}'
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            events = collect_events(alias)
        warn = [l for l in buf.getvalue().splitlines() if 'WARNUNG' in l or 'FEHLER' in l]
        if len(events) < 1000:
            print(f'!! {name}: nur {len(events)} Events - UEBERSPRUNGEN')
            continue
        coef, r2, rms = fit_events(events, lat)
        oos = oos_july(events, lat)
        conf = 7 if (r2 > 0.97 and oos and abs(oos[0]) < 10 and oos[1] < 15) else 6
        blk, cm = make_block(name, lat, lon, coef, r2, rms, events, conf)
        famp, fph = fes_m2(lat, lon)
        m2 = cm.get('M2', (0, 0))
        dphi = (m2[1] - fph + 180) % 360 - 180
        o = f'dt={oos[0]:+.1f}±{oos[1]:.1f}min dh={oos[2]:+.3f}±{oos[3]:.3f}m n={oos[4]}/{oos[5]}' if oos else 'OOS n/a'
        print(f'{name[:40]:42s} ev={len(events):4d} r2={r2:.4f} rms={rms:.3f} conf={conf} {o}')
        print(f'    M2 {m2[0]:.3f}m@{m2[1]:.1f}  FES {famp:.3f}m@{fph:.1f}  dPhi={dphi:+.1f}'
              + (f'  {len(warn)} Warnungen' if warn else ''))
        for w in warn[:3]:
            print('    ', w)
        blocks.append(blk)
    if write and blocks:
        out = text if text.endswith('\n') else text + '\n'
        out += '\n'.join(blocks) + '\n'
        n_after = out.count('# !units:')
        print(f'Stationen vorher={n_before} nachher={n_after}')
        assert n_after == n_before + len(blocks)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(HFILE))
        with os.fdopen(fd, 'w', encoding='iso-8859-1') as f:
            f.write(out)
        os.replace(tmp, HFILE)
        print('geschrieben:', HFILE)


if __name__ == '__main__':
    main()
