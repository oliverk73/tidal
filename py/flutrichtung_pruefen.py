#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeigt XTides "Flood" bei unseren Stroemungssaetzen in Flutrichtung? (Oliver 25.10.2026)

cmems_stroemung_nachholen.analyse legt die Hauptachse immer in 0-180 Grad. Positiv (XTide "Flood")
ist damit die Richtung, die zufaellig in diese Haelfte faellt -- bei Luis Correia war es die Ebbe.

Probe: Phasenabstand d = G(Strom, Hauptkonstituente) - G(Wasserstand FES2022 am selben Ort). Der
Flutstrom hat sein Maximum zwischen Niedrigwasser-Mitte und kurz nach Hochwasser (stehende Welle:
~ -90 Grad, fortschreitende: ~0 Grad). Geeicht an den Saetzen mit sicherer Flutrichtung (NOAA/CHS).
Hauptkonstituente: M2, bei Tagestiden (K1+O1 > M2+S2) K1.

Usage: venv/bin/python py/flutrichtung_pruefen.py [--eichen] [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT                         # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR                      # noqa: E402

SPEED = {'M2': 28.9841042, 'K1': 15.0410686, 'S2': 30.0, 'O1': 13.9430356}
ZWEITE = {'M2': 'S2', 'K1': 'O1'}
GEPRUEFT = ('harmonics_utide_current_observations.txt', 'harmonics_utide_current_tables.txt',
            'harmonics_utide_australia_oceancurrent.txt')
EICHUNG = ('harmonics-dwf-20251228-free.txt', 'harmonics_noaa_currents.txt')
HILFE = os.path.join(ROOT, 'harmonics/help')
BIS_KM = 15.0


def wrap(x):
    return (x + 180.0) % 360.0 - 180.0


def urteil(d, d2):
    """richtig / drehen / unklar -- beide Konstituenten muessen im selben Fenster liegen."""
    def zone(x):
        if x is None:
            return None
        if -120 <= x <= 0:
            return 'richtig'
        if x >= 60:
            return 'drehen'
        return 'unklar'
    a, b = zone(d), zone(d2)
    return a if a != 'unklar' and (b is None or b == a) else 'unklar'


def km(a, b, c, d):
    p = np.pi / 180
    x = np.sin(a * p) * np.sin(c * p) + np.cos(a * p) * np.cos(c * p) * np.cos((b - d) * p)
    return 6371.0 * np.arccos(np.clip(x, -1, 1))


def pegel_phase(r, k, pegel):
    """Greenwich-Phase von k am naechsten Gezeitenpegel bis BIS_KM -> (G, Name, km) oder None.
    In engen Buchten trifft FES den Wasserstand schlecht (Pembina Terminal: FES +112, Messung +40 Grad)."""
    lat, lon, recs = pegel
    e = km(r['lat'], r['lon'], lat, lon)
    for i in np.argsort(e)[:5]:
        if e[i] > BIS_KM:
            return None
        p = recs[i]
        try:
            _z, w, _e, mer = X.satz_lesen(p['file'], p['name'])
        except KeyError:
            continue
        if k in w and w[k][0] > 0:
            return X.greenwich(w[k][1], SPEED[k], mer) % 360, p['name'], float(e[i])
    return None


def abstand(r, fes, pegel=None):
    """-> (d in Grad, Konstituente, Strom-Amplitude, d2, Bezug) oder None."""
    try:
        z0, w, _e, mer = X.satz_lesen(r['file'], r['name'])
    except KeyError:
        return None
    m2, s2 = w.get('M2', (0, 0))[0], w.get('S2', (0, 0))[0]
    k1, o1 = w.get('K1', (0, 0))[0], w.get('O1', (0, 0))[0]
    k = 'K1' if k1 + o1 > m2 + s2 else 'M2'
    if k not in w or w[k][0] <= 0:
        return None
    gs = X.greenwich(w[k][1], SPEED[k], mer) % 360
    bezug = 'FES2022'
    pp = pegel_phase(r, k, pegel) if pegel else None
    if pp:
        gt, bezug = pp[0], '%s (%.1f km)' % (pp[1], pp[2])
    else:
        amp, gt = sample(fes[k], r['lat'], r['lon'])
    if gt is None:
        return None
    # Zweite Konstituente desselben Bandes als Gegenprobe (S2 zu M2, O1 zu K1)
    k2 = ZWEITE[k]
    d2 = None
    if k2 in w and w[k2][0] > 0:
        pp2 = pegel_phase(r, k2, pegel) if pp else None
        gt2 = pp2[0] if pp2 else sample(fes[k2], r['lat'], r['lon'])[1]
        if gt2 is not None:
            d2 = wrap(X.greenwich(w[k2][1], SPEED[k2], mer) % 360 - gt2)
    return wrap(gs - gt), k, w[k][0], d2, bezug


def main(argv):
    fes = {k: nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in SPEED}
    alle = [r for r in load_records() if r['lat'] is not None]
    R = [r for r in alle if r['current']]
    T = [r for r in alle if not r['current']]
    pegel = (np.array([r['lat'] for r in T]), np.array([r['lon'] for r in T]), T)
    dateien = EICHUNG if '--eichen' in argv else GEPRUEFT
    zeilen = []
    for r in R:
        f = os.path.basename(r['file'])
        if f not in dateien:
            continue
        a = abstand(r, fes, pegel)
        if a is None:
            continue
        zeilen.append(dict(datei=f, name=r['name'], lat=r['lat'], lon=r['lon'], konst=a[1],
                           amp=round(a[2], 3), d=round(a[0], 1),
                           d2='' if a[3] is None else round(a[3], 1), urteil=urteil(a[0], a[3]), bezug=a[4]))
    d = np.array([z['d'] for z in zeilen])
    print(len(zeilen), 'Saetze', collections.Counter(z['urteil'] for z in zeilen))
    h, kanten = np.histogram(d, bins=12, range=(-180, 180))
    for n, k0 in zip(h, kanten):
        print('  %+5.0f..%+5.0f  %4d %s' % (k0, k0 + 30, n, '#' * (n // 5)))
    if '--eichen' in argv:
        return zeilen
    heute = dt.date.today().strftime('%Y%m%d')
    out = os.path.join(HILFE, 'flutrichtung_%s.csv' % heute)
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)
    print('->', out)
    return zeilen


def drehen(zeilen):
    """Saetze mit Urteil 'drehen': Phasen +180, Z0 negiert, Achse +180, Notiz."""
    import re
    pro = collections.defaultdict(set)
    for z in zeilen:
        if z['urteil'] == 'drehen':
            pro[z['datei']].add(z['name'])
    for f, namen in sorted(pro.items()):
        pfad = os.path.join(ROOT, 'harmonics/utide', f)
        L = open(pfad, encoding='iso-8859-1').read().split('\n')
        n = 0
        for i in reversed([k for k, l in enumerate(L) if l in namen]):
            a = i
            while a > 0 and L[a - 1].startswith('#'):
                a -= 1
            # Kommentarkopf vor BEGIN HOT COMMENTS gehoert mit zum Satz
            while a > 0 and (L[a - 1].startswith('#') or not L[a - 1].strip()) and 'End congen' not in L[a - 1]:
                a -= 1
            for k in range(a, i):
                m = re.match(r'(# Major axis: |# major_axis_deg_true: )([-\d.]+)(.*)', L[k])
                if m:
                    L[k] = '%s%.1f%s' % (m.group(1), (float(m.group(2)) + 180) % 360, m.group(3))
            z0 = L[i + 2].split()
            L[i + 2] = '%.4f %s' % (-float(z0[0]), ' '.join(z0[1:]))
            k = i + 3
            while k < len(L) and L[k].strip() and not L[k].startswith('#'):
                f3 = L[k].split()
                if f3[0] != 'x':
                    L[k] = '%-15s %s  %.2f' % (f3[0], f3[1], (float(f3[2]) + 180) % 360)
                k += 1
            L.insert(i, '# note: 20261025 Vorzeichen gedreht, damit XTide-Flood der Flutstrom ist '
                        '(Phase gegen den Wasserstand, py/flutrichtung_pruefen.py)')
            n += 1
        open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(L))
        print('  %-45s %d Saetze gedreht' % (f, n))


if __name__ == '__main__':
    z = main(sys.argv)
    if '--schreiben' in sys.argv:
        drehen(z)
