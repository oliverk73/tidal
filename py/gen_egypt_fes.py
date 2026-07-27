#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FES2022b-Modellstationen fuer die aegyptische Rote-Meer-Kueste (Safaga,
Soma Bay).  Dort gibt es weder Pegel (IOC/PSMSL/UHSLC kennen fuer Aegypten nur
Alexandria und Port Said) noch einen ATT-Sekundaerhafen; die naechsten Eintraege
der Sammlung -- Hurghada und Al Qusayr -- sind NP203-Transfers aus Suez ueber
gut 9 Stunden und tragen deshalb Confidence 3.

Aufbau wie gen_fes_gaps.py: Z0 = |min| einer 19y-utide-Rekonstruktion (CD~LAT),
Greenwich-Phasen direkt aus FES, Ausgabe -> harmonics_fes2022.txt.

Aufruf: python3 py/gen_egypt_fes.py            # dry-run
        python3 py/gen_egypt_fes.py --write    # an harmonics_fes2022.txt anfuegen
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta

import netCDF4 as nc
import numpy as np

sys.path.insert(0, '/home/oliver/weather/py')
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match

FES_DIR = '/home/oliver/weather/tide_models/fes2022b/ocean_tide_extrapolated'
TXT = '/home/oliver/weather/harmonics/utide/harmonics_fes2022.txt'

# name, lat, lon, tz, country, water_body
# Positionen im Wasser gewaehlt und gegen GEBCO geprueft:
#   Safaga   26.7420/33.9450  -6 m  (Hafenbecken Bur Safajah)
#   Soma Bay 26.8420/33.9880 -11 m  (Bucht suedwestlich Ra's Abu Suma,
#                                    vor den Hotelstraenden)
STATIONS = [
    ('Safaga (Bur Safajah), Egypt',    26.7420, 33.9450, 'Africa/Cairo', 'Egypt', 'Red Sea'),
    ('Soma Bay (Ra\'s Abu Suma), Egypt', 26.8420, 33.9880, 'Africa/Cairo', 'Egypt', 'Red Sea'),
]

NOTE = [
    '# note: MODEL-DERIVED (not observations). Kein Pegel und kein ATT-Sekundaerhafen',
    '# note: vorhanden; FES-Feld hier ueber 120 km praktisch konstant (M2 +-1%).',
    '# note: Z0 from 19y reconstruction minimum (CD~LAT).',
]


def stem(name):
    return 'lambda2' if name == 'LDA2' else name.lower()


def sample(ds, lat, lon):
    lons = ds.variables['lon'][:]
    lats = ds.variables['lat'][:]
    j = int(np.argmin(np.abs(lons - lon % 360)))
    k = int(np.argmin(np.abs(lats - lat)))
    amp = ds.variables['amplitude']
    ph = ds.variables['phase']
    a = amp[k, j]
    if np.ma.is_masked(a):
        for r in range(1, 15):
            sa = amp[max(0, k - r):k + r + 1, max(0, j - r):j + r + 1]
            sp = ph[max(0, k - r):k + r + 1, max(0, j - r):j + r + 1]
            m = np.ma.getmaskarray(sa)
            if not np.all(m):
                aa = sa[~m]; pp = sp[~m]
                x = np.mean(aa * np.cos(np.radians(pp)))
                y = np.mean(aa * np.sin(np.radians(pp)))
                return float(aa.mean()) / 100.0, float(np.degrees(np.arctan2(y, x)) % 360)
        return None
    return float(a) / 100.0, float(ph[k, j]) % 360.0


def sample_all():
    out = [dict() for _ in STATIONS]
    for cn, _sp in CONSTITUENTS_175:
        try:
            ds = nc.Dataset(f'{FES_DIR}/{stem(cn)}_fes2022.nc')
        except (FileNotFoundError, OSError):
            continue
        for i, (_, la, lo, *_rest) in enumerate(STATIONS):
            v = sample(ds, la, lo)
            if v and v[0] > 0:
                out[i][cn] = v
        ds.close()
    return out


def z0_lat(cm, lat):
    """Z0 = |min| einer 19y-Rekonstruktion (CD~LAT) via utide."""
    import utide
    from utide._ut_constants import ut_constants
    table = ut_constants['const']
    unames = [n.strip() for n in table.name]
    u2x = {}
    for i, u in enumerate(unames):
        xt, _ = find_xtide_match(u, float(table.freq[i]) * 360.0)
        if xt in cm and xt not in u2x.values():
            u2x[u] = xt
    names = list(u2x.keys())
    t0 = datetime(2015, 1, 1)
    tsolve = np.array([t0 + timedelta(hours=h) for h in range(24 * 60)])
    coef = utide.solve(tsolve, np.zeros(len(tsolve)), lat=lat, nodal=True,
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
    return -float(np.min(rec['h']))


def build_block(name, lat, lon, tz, country, wb, cm, z0):
    n = sum(1 for cn, _ in CONSTITUENTS_175 if cn in cm)
    L = [
        '#', f'# {name}', '# BEGIN HOT COMMENTS', f'# country: {country}',
        f'# water_body: {wb}',
        '# source: FES2022b global ocean tide model (extrapolated), sampled at port location',
        *NOTE,
        f'# date_imported: {datetime.now():%Y%m%d}',
        '# datum: Chart Datum (approx., CD~LAT from constituents)',
        '# confidence: 5',
        f'# fes: const={n} M2={cm.get("M2",(0,0))[0]:.3f}@{cm.get("M2",(0,0))[1]:.0f}',
        '# !units: meters', f'# !longitude: {lon:.6f}', f'# !latitude: {lat:.6f}',
        name, f'+00:00 :{tz}', f'{z0:.4f} meters',
    ]
    for cn, _sp in CONSTITUENTS_175:
        if cn in cm and cm[cn][0] >= 0.00005:
            L.append(f'{cn:15s} {cm[cn][0]:.4f}  {cm[cn][1]:.2f}')
        else:
            L.append('x 0 0')
    return L


def main():
    write = '--write' in sys.argv
    data = sample_all()
    blocks = []
    for i, (name, lat, lon, tz, country, wb) in enumerate(STATIONS):
        cm = data[i]
        if 'M2' not in cm:
            print(f'{name}: KEIN M2 (Land/maskiert) -> uebersprungen'); continue
        z0 = z0_lat(cm, lat)
        m2, s2 = cm['M2'], cm.get('S2', (0, 0))
        k1, o1 = cm.get('K1', (0, 0)), cm.get('O1', (0, 0))
        f = (k1[0] + o1[0]) / (m2[0] + s2[0])
        print(f'{name}: {len(cm)} Konst., M2={m2[0]:.4f}@{m2[1]:.1f}, '
              f'Springhub={2*(m2[0]+s2[0]):.3f} m, F={f:.3f}, Z0={z0:.3f}')
        blocks.append((name, build_block(name, lat, lon, tz, country, wb, cm, z0)))
    if write and blocks:
        lines = open(TXT, encoding='iso-8859-1').read().split('\n')
        existing = set(lines)
        end = len(lines)
        while end > 0 and lines[end - 1].strip() == '':
            end -= 1
        add = []
        for name, blk in blocks:
            if name in existing:
                print(f'  SKIP (existiert): {name}'); continue
            add += blk
        lines = lines[:end] + add + lines[end:]
        open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(lines))
        n = sum(1 for l in lines if l.startswith('# !latitude:'))
        print(f'\nGeschrieben. !latitude jetzt {n}')
    else:
        print('\n(Dry-run. --write zum Anfuegen.)')


if __name__ == '__main__':
    main()
