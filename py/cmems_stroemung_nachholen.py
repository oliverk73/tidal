#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CMEMS-Stroemungsverankerungen nachholen, die wir noch nicht nutzen (Oliver 19.10.2026).

Quelle: lokaler Katalog water_levels/CMEMS_currents_idx/.../index_history.txt (globales
In-situ-Produkt). Kandidaten: feste Plattform (Messgebiet < 3 km), mindestens 6 Monate,
Stroemung gemessen (EWCT/NSCT oder HCSP/HCDT), cmems_code noch nicht im Bestand und keine
vorhandene Stroemungsstation naeher als 1 km.

Download direkt per HTTPS vom Marine Data Store (ohne Anmeldung) nach
water_levels/CMEMS_currents_neu/. Analyse wie batch/batch_utide_eu_currents.py:
Stundenmittel, Hauptachse, UTide auf der Projektion in Knoten. Als Position gilt der Median
der gemessenen Positionen -- nicht die Ecke des Messgebiets (Fehler der ersten Uebernahme).

Schreibt (aendert den Bestand nicht):
  harmonics/help/cmems_stroemung_neu_<datum>.txt   Bloecke, Name = Plattformcode
  harmonics/help/cmems_stroemung_neu_<datum>.csv   Kennzahlen je Plattform
Usage: venv/bin/python py/cmems_stroemung_nachholen.py [--nur-liste]
"""
import csv
import math
import os
import re
import sys
import urllib.request
from datetime import date, datetime

import numpy as np
import pandas as pd
import utide
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as hc                                           # noqa: E402
from generate_germany_harmonics_175 import CONSTITUENTS_175, find_xtide_match   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, 'water_levels/CMEMS_currents_idx/glo/INSITU_GLO_PHYBGCWAV_DISCRETE_MYNRT_013_030/'
                         'cmems_obs-ins_glo_phybgcwav_mynrt_na_irr_202311/index_history.txt')
BASIS = 'https://s3.waw3-1.cloudferro.com/mdl-native-01/native/'
ROH = os.path.join(ROOT, 'water_levels/CMEMS_currents_neu')
BESTAND = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
MS_KN = 1.94384449
MIN_STUNDEN = 4380
# Offener Ozean (TAO/TRITON/RAMA, Papa) und Schwarzes Meer: kaum Gezeitenstrom, grosse Dateien
OHNE = re.compile(r'^(T\d+[NS]\d+[EW]|5[23]0\d\d|140\d+|1400049|14048|2300019|23011|48400|EUXRo.*|CG)$')
KONST = ['K1', 'O1', 'P1', 'Q1', 'J1', 'OO1', '2Q1', 'RHO1', 'NO1', 'CHI1', 'PI1', 'PHI1', 'PSI1', 'SIG1',
         'THE1', 'SO1', 'M2', 'S2', 'N2', 'K2', 'L2', '2N2', 'R2', 'T2', 'LDA2', 'MU2', 'NU2', 'EPS2', 'ETA2',
         'MF', 'MSF', 'MM', 'SA', 'SSA', 'MSM', 'M3', 'MK3', 'MO3', 'SK3', 'SO3', 'M4', 'MN4', 'MS4', 'MK4',
         'S4', 'SN4', 'M6', '2MS6', '2MN6', 'M8', '2SM2', 'MKS2', 'SKM2', 'NO3', 'N4', '3MS4', '2MK5',
         '2SK5', '2MK6', 'MSK6']


def kandidaten():
    genutzt = set(re.findall(r'cmems_code: (\S+)', open(BESTAND, encoding='iso-8859-1').read()))
    strom = [r for r in hc.load_records() if r['current'] and r['lat'] is not None]
    out = {}
    for l in open(IDX, encoding='latin-1'):
        if l.startswith('#'):
            continue
        p = l.rstrip('\n').split(',')
        if len(p) < 12 or '/MO/' not in p[1]:
            continue
        par = set(p[11].split())
        if not ({'EWCT', 'NSCT'} <= par or {'HCSP', 'HCDT'} <= par):
            continue
        try:
            la0, la1, lo0, lo1 = map(float, p[2:6])
            t0 = datetime.fromisoformat(p[6].replace('Z', '+00:00'))
            t1 = datetime.fromisoformat(p[7].replace('Z', '+00:00'))
        except ValueError:
            continue
        if 111 * math.hypot(la1 - la0, (lo1 - lo0) * math.cos(math.radians(la0))) >= 3:
            continue
        if (t1 - t0).days < 183:
            continue
        code = re.search(r'_MO_(.+)\.nc$', p[1]).group(1)
        if code in genutzt or OHNE.match(code):
            continue
        la, lo = (la0 + la1) / 2, (lo0 + lo1) / 2
        nah = [r for r in strom if abs(r['lat'] - la) < 0.02 and hc.km(dict(lat=la, lon=lo), r) < 1]
        if nah:
            continue
        out[code] = dict(code=code, datei=p[1], lat=la, lon=lo, start=p[6][:10], ende=p[7][:10], inst=p[8])
    return list(out.values())


def laden(k):
    os.makedirs(ROH, exist_ok=True)
    ziel = os.path.join(ROH, os.path.basename(k['datei']))
    if not os.path.exists(ziel):
        urllib.request.urlretrieve(BASIS + k['datei'], ziel + '.part')
        os.rename(ziel + '.part', ziel)
    return ziel


def gut(qc):
    return np.isin(np.asarray(qc), [1, 2]) if qc is not None else True


def reihe(pfad):
    """-> (DataFrame u,v in m/s stuendlich, lat, lon, tiefe) oder None."""
    ds = xr.open_dataset(pfad, decode_times=True)
    if 'EWCT' in ds and 'NSCT' in ds:
        u, v = ds['EWCT'].values, ds['NSCT'].values
        ok = gut(ds['EWCT_QC'].values if 'EWCT_QC' in ds else None) & gut(ds['NSCT_QC'].values if 'NSCT_QC' in ds else None)
    else:
        s, d = ds['HCSP'].values, ds['HCDT'].values
        u, v = s * np.sin(np.radians(d)), s * np.cos(np.radians(d))
        ok = gut(ds['HCSP_QC'].values if 'HCSP_QC' in ds else None) & gut(ds['HCDT_QC'].values if 'HCDT_QC' in ds else None)
    u = np.where(ok, u, np.nan)
    v = np.where(ok, v, np.nan)
    if u.ndim == 1:
        u, v = u[:, None], v[:, None]
    deph = ds['DEPH'].values if 'DEPH' in ds else np.zeros_like(u)
    if deph.ndim == 1:
        deph = np.broadcast_to(deph[:, None] if deph.shape[0] == u.shape[0] else deph[None, :], u.shape)
    n = np.isfinite(u).sum(axis=0)
    if n.max() < MIN_STUNDEN:
        return None
    # flachste Ebene mit mindestens 80 % der besten Abdeckung
    kand = [j for j in range(u.shape[1]) if n[j] >= 0.8 * n.max()]
    tiefen = [np.nanmedian(np.where(np.isfinite(u[:, j]), deph[:, j], np.nan)) for j in kand]
    j = kand[int(np.nanargmin(np.abs(tiefen)))] if any(np.isfinite(tiefen)) else kand[0]
    t = pd.to_datetime(ds['TIME'].values)
    df = pd.DataFrame({'u': u[:, j], 'v': v[:, j]}, index=t).dropna()
    df = df[(df['u'].abs() < 5) & (df['v'].abs() < 5)]
    df = df.resample('1h').mean().dropna()
    lat = float(np.nanmedian(ds['LATITUDE'].values))
    lon = float(np.nanmedian(ds['LONGITUDE'].values))
    tiefe = float(np.nanmedian(deph[:, j])) if np.isfinite(deph[:, j]).any() else float('nan')
    return df, lat, lon, tiefe


def analyse(df, lat, konst=None):
    """konst=None: feste Liste KONST; 'auto': UTide waehlt nach Rayleigh (kurze Reihen)."""
    u, v = df['u'].values, df['v'].values
    cov = np.cov(np.vstack([u, v]))
    w, V = np.linalg.eigh(cov)
    a = V[:, np.argmax(w)]
    achse = float(np.degrees(np.arctan2(a[0], a[1])) % 180)
    s = (u * np.sin(np.radians(achse)) + v * np.cos(np.radians(achse))) * MS_KN
    zeiten = df.index.to_pydatetime()
    coef = utide.solve(zeiten, s, lat=lat, nodal=True, trend=False, method='ols', conf_int='none',
                       verbose=False, constit=konst or KONST)
    from utide._ut_constants import ut_constants
    tab = ut_constants['const']
    namen = [x.strip() for x in tab.name]
    mapped = {}
    for i, un in enumerate(coef['name']):
        un = un.strip()
        if un not in namen:
            continue
        xt, _ = find_xtide_match(un, tab.freq[namen.index(un)] * 360)
        if xt:
            mapped[xt] = (float(coef['A'][i]), float(coef['g'][i]) % 360)
    rec = utide.reconstruct(zeiten, coef, verbose=False)['h']
    res = s - rec
    r2 = 1 - np.sum(res ** 2) / np.sum((s - s.mean()) ** 2)
    return dict(achse=achse, mean=float(coef['mean']), konst=mapped, r2=float(r2),
                rms=float(np.sqrt(np.mean(res ** 2))), n=len(s), t0=df.index[0], t1=df.index[-1],
                m2=mapped.get('M2', (0, 0))[0], k1=mapped.get('K1', (0, 0))[0], s2=mapped.get('S2', (0, 0))[0],
                smax=float(np.percentile(np.abs(s), 95)))


def block(k, r, lat, lon, tiefe):
    L = ['# Harmonic constants derived from CMEMS in-situ',
         '# (UTide v%s, principal-axis projection)' % utide.__version__,
         '# %d hourly samples, depth %.0f m' % (r['n'], tiefe if math.isfinite(tiefe) else -1),
         '# from %s to %s' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d')),
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS',
         '# source: CMEMS in-situ, UTide analysis',
         '# station_id_context: CMEMS-%s' % k['code'],
         '# institution: %s' % k['inst'][:60],
         '# datum: n/a', '# station_type: current',
         '# major_axis_deg_true: %.1f' % r['achse'],
         '# confidence: %d' % (8 if r['r2'] > 0.7 else 5),
         '# cmems_code: %s' % k['code'],
         '# utide: period=%s..%s const=%d' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d'), len(r['konst'])),
         '# !units: knots', '# !longitude: %.4f' % lon, '# !latitude: %.4f' % lat,
         '%s Current' % k['code'], '+00:00 :UTC', '%.4f knots' % r['mean']]
    for name, _sp in CONSTITUENTS_175:
        a = r['konst'].get(name)
        L.append('%-15s %.4f  %.2f' % (name, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def main(argv):
    K = kandidaten()
    print(len(K), 'Kandidaten')
    if '--nur-liste' in argv:
        for k in K:
            print('%-28s %8.3f %9.3f %s..%s %s' % (k['code'], k['lat'], k['lon'], k['start'], k['ende'], k['inst'][:30]))
        return
    tag = date.today().strftime('%Y%m%d')
    bloecke, zeilen = [], []
    for k in K:
        try:
            x = reihe(laden(k))
            if x is None:
                print('  zu kurz:', k['code'])
                continue
            df, lat, lon, tiefe = x
            if len(df) < MIN_STUNDEN:
                print('  zu kurz:', k['code'])
                continue
            r = analyse(df, lat)
        except Exception as e:                                       # noqa: BLE001
            print('  Fehler:', k['code'], str(e)[:80])
            continue
        bloecke.append(block(k, r, lat, lon, tiefe))
        zeilen.append(dict(code=k['code'], inst=k['inst'][:40], lat=round(lat, 4), lon=round(lon, 4),
                           tiefe=round(tiefe, 1) if math.isfinite(tiefe) else '', stunden=r['n'],
                           von=r['t0'].date(), bis=r['t1'].date(), r2=round(r['r2'], 3), m2_kn=round(r['m2'], 3),
                           s2_kn=round(r['s2'], 3), k1_kn=round(r['k1'], 3), v95_kn=round(r['smax'], 2),
                           achse=round(r['achse'])))
        print('  %-26s R2 %.2f M2 %.2f kn  %s' % (k['code'], r['r2'], r['m2'], k['inst'][:30]), flush=True)
    with open(os.path.join(ROOT, 'harmonics/help/cmems_stroemung_neu_%s.txt' % tag), 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(bloecke) + '\n')
    with open(os.path.join(ROOT, 'harmonics/help/cmems_stroemung_neu_%s.csv' % tag), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    print(len(zeilen), 'Saetze gefittet')


if __name__ == '__main__':
    main(sys.argv[1:])
