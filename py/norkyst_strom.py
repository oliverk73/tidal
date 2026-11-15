#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NorKyst800 (met.no ROMS, 800 m, stuendlich 02/2017-10/2025) als Strom-Lueckenquelle fuer Norwegen (15.11.2026).

Daten: thredds.met.no/thredds/dodsC/fou-hi/norkyst800m-1h/NorKyst-800m_ZDEPTHS_his.an.YYYYMMDD00.nc (Tagesdateien,
24 h, NLOD/CC BY 4.0). ubar/vbar = tiefengemittelt, GITTERbezogen -> mit angle drehen:
    ost = ubar*cos(a) - vbar*sin(a),  nord = ubar*sin(a) + vbar*cos(a);  zeta = Wasserstand.
Gitter (lat/lon/h/angle; mask = zeta- ODER ubar-Maske, ubar ist strenger!) einmal geladen: quellen/tidal_streams/Norway_NorKyst800/gitter.npz.
Server bittet: keine parallelen Sitzungen -> streng nacheinander, ~1 s je Variable/Punkt/Tag.

  laden PUNKTDATEI VON BIS   Punktdatei: name;lat;lon je Zeile -> punkte/<slug>.csv (zeit,u,v,zeta; fortsetzbar)
  pruefen PUNKTDATEI         Modell gegen die gleichnamigen Saetze (Strom: Hauptachse, Wasserstand: zeta),
                             Kurvenfehler ueber M2 S2 N2 K1 O1 wie fes2014_strom.kurve, dazu Zeitversatz/Faktor M2
"""
import csv
import datetime as dt
import os
import re
import sys
import time

import netCDF4 as nc
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'quellen/tidal_streams/Norway_NorKyst800')
URL = 'https://thredds.met.no/thredds/dodsC/fou-hi/norkyst800m-1h/NorKyst-800m_ZDEPTHS_his.an.%s00.nc'


def slug(n):
    return re.sub(r'[^A-Za-z0-9]+', '_', n.split(',')[0]).strip('_')


def zelle(la, lo, g=None):
    """Naechste Wasserzelle -> (j, i, km, tiefe)."""
    g = g if g is not None else np.load(os.path.join(D, 'gitter.npz'))
    d2 = (g['lat'] - la) ** 2 + ((g['lon'] - lo) * np.cos(np.radians(la))) ** 2
    d2 = np.where(g['mask'], np.inf, d2)
    j, i = np.unravel_index(np.argmin(d2), d2.shape)
    return int(j), int(i), 111.2 * float(np.sqrt(d2[j, i])), float(g['h'][j, i])


def laden(argv):
    pdatei, von, bis = argv[0], dt.date.fromisoformat(argv[1]), dt.date.fromisoformat(argv[2])
    g = np.load(os.path.join(D, 'gitter.npz'))
    punkte = []
    for z in open(pdatei, encoding='utf-8'):
        if z.strip() and not z.startswith('#'):
            n, la, lo = z.strip().split(';')
            j, i, km, h = zelle(float(la), float(lo), g)
            punkte.append((n, j, i, float(np.cos(g['angle'][j, i])), float(np.sin(g['angle'][j, i]))))
            print('%-45s Zelle %d,%d  %.2f km  %.0f m' % (n, j, i, km, h), flush=True)
    os.makedirs(os.path.join(D, 'punkte'), exist_ok=True)
    tag = von
    while tag <= bis:
        ds = None
        for n, j, i, ca, sa in punkte:
            p = os.path.join(D, 'punkte', slug(n) + '.csv')
            schon = set()
            if os.path.exists(p):
                schon = {z[:10] for z in open(p)}
            if tag.isoformat() in schon:
                continue
            for versuch in range(4):
                try:
                    if ds is None:
                        ds = nc.Dataset(URL % tag.strftime('%Y%m%d'))
                    t = ds['time'][:]
                    u = np.ma.filled(ds['ubar'][:, j, i].astype(float), np.nan)
                    v = np.ma.filled(ds['vbar'][:, j, i].astype(float), np.nan)
                    z = np.ma.filled(ds['zeta'][:, j, i].astype(float), np.nan)
                    break
                except Exception as e:                   # noqa: BLE001
                    ds = None
                    if 'file not found' in str(e):       # Tagesdatei fehlt im Archiv -> ganzen Tag ueberspringen
                        break
                    print('  Fehler %s %s: %s' % (tag, n, str(e)[:200]), flush=True)
                    time.sleep(20 * (versuch + 1))
            else:
                continue
            if ds is None:
                print('  %s fehlt im Archiv' % tag, flush=True)
                break
            neu = not os.path.exists(p)
            with open(p, 'a', newline='') as fh:
                wr = csv.writer(fh)
                if neu:
                    wr.writerow(['zeit', 'u', 'v', 'zeta'])
                for tt, uu, vv, zz in zip(t, u, v, z):
                    zeit = dt.datetime.fromtimestamp(float(tt), dt.UTC).strftime('%Y-%m-%d %H:%M')
                    wr.writerow([zeit, '%.4f' % (uu * ca - vv * sa), '%.4f' % (uu * sa + vv * ca), '%.3f' % zz])
        if ds is not None:
            ds.close()
        if tag.day == 1:
            print(tag, flush=True)
        tag += dt.timedelta(days=1)


FREI = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4', '2N2', 'MU2', 'NU2', 'L2', 'M6', 'MK3', 'M3']


def harmon(df, spalte, kopf):
    """Kleinste Quadrate -> {k: A*e^{-ig}} (Greenwich, Einheit der Spalte)."""
    import xtide_modell as X
    _n, sp, arg, fak = kopf
    x = df[spalte].values
    ok = np.isfinite(x)
    t = df.index.values.astype('datetime64[s]').astype(np.int64).astype(float)[ok]
    ks = [k for k in FREI if k in sp]
    Cm, Sm, _ = X.matrix(t, ks, sp, arg, fak)
    M = np.hstack([np.ones((len(t), 1)), np.column_stack([c for j in range(len(ks)) for c in (Cm[:, j], Sm[:, j])])])
    b, *_ = np.linalg.lstsq(M, x[ok], rcond=None)
    return {k: complex(b[1 + 2 * j], -b[2 + 2 * j]) for j, k in enumerate(ks)}     # A cos(E-g): a=A cos g, b=A sin g


def reihe(name):
    import pandas as pd
    p = os.path.join(D, 'punkte', slug(name) + '.csv')
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    return df[~df.index.duplicated()].sort_index()


def pruefen(argv):
    import cmath
    import math
    import health_check as H
    import xtide_modell as X
    import fes2014_strom as F
    kopf = X.kopf_lesen(os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt'))
    sp = kopf[1]
    R = {r['name']: r for r in H.load_records() if r['lat'] is not None}
    for z in open(argv[0], encoding='utf-8'):
        if not z.strip() or z.startswith('#'):
            continue
        n = z.split(';')[0]
        r = R.get(n)
        if r is None:
            print('%-40s kein Satz' % n)
            continue
        df = reihe(n)
        tage = (df.index[-1] - df.index[0]).days
        _z0, w, _e, mer = X.satz_lesen(os.path.join(ROOT, r['file']), n)
        s = {k: cmath.rect(w[k][0], -math.radians(X.greenwich(w[k][1], sp[k], mer))) for k in F.KS if k in w and w[k][0] > 0}
        if r['current']:
            txt = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
            i = txt.index(n)
            ax = float(re.findall(r'major_axis_deg_true: ([\d.]+)', '\n'.join(txt[max(0, i - 40):i]))[-1])
            hu, hv = harmon(df, 'u', kopf), harmon(df, 'v', kopf)
            m = {k: F.proj((hu[k], hv[k]), ax) for k in s}
        else:
            hz = harmon(df, 'zeta', kopf)
            m = {k: hz[k] for k in s}
        f, vz = F.kurve(m, s)
        dphi = math.degrees(cmath.phase((vz * s['M2']) / m['M2']))
        print('%-45s %3d Tage  Kurve %5.1f %%  M2 x%.2f  %+4.0f min  (%s)' % (n[:45], tage, f, abs(m['M2']) / abs(s['M2']),
              dphi / sp['M2'] * 60, 'Strom' if r['current'] else 'Pegel'))


if __name__ == '__main__':
    if sys.argv[1:2] == ['pruefen']:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        pruefen(sys.argv[2:])
        sys.exit()
    if sys.argv[1:2] == ['laden']:
        laden(sys.argv[2:])
    else:
        print(__doc__)
