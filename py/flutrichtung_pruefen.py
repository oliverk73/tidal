#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeigt XTides "Flood" bei unseren Stroemungssaetzen in Flutrichtung? (Oliver 25.10.2026)

cmems_stroemung_nachholen.analyse legt die Hauptachse immer in 0-180 Grad. Positiv (XTide "Flood")
ist damit die Richtung, die zufaellig in diese Haelfte faellt -- bei Luis Correia war es die Ebbe.

Probe: Phasenabstand d = G(Strom, Hauptkonstituente) - G(Wasserstand FES2022 am selben Ort). Der
Flutstrom hat sein Maximum zwischen Niedrigwasser-Mitte und kurz nach Hochwasser (stehende Welle:
~ -90 Grad, fortschreitende: ~0 Grad). Geeicht an den Saetzen mit sicherer Flutrichtung (NOAA/CHS).
Hauptkonstituente: M2, bei Tagestiden (K1+O1 > M2+S2) K1.

Unklar -> TPXO10 (18.11.2026): Laufrichtung der Tidewelle = Richtung zunehmender Phase (Ebenen-Fit ueber 9x9
Zellen). Liegt die Flutrichtung (Achse) darin, ist der Satz richtig, sonst drehen. Nur bei Gradient >= 0.5 Grad/km und
|cos(Achse - Laufrichtung)| >= 0.3. Geeicht an den NOAA-Saetzen im unklaren Fenster: 154/154 richtig.

Usage: venv/bin/python py/flutrichtung_pruefen.py [--eichen] [--schreiben]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import os
import sys

import math
import re

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, ROOT, active_files                         # noqa: E402
import xtide_modell as X                                           # noqa: E402
import tpxo as TP                                                  # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR                      # noqa: E402

SPEED = {'M2': 28.9841042, 'K1': 15.0410686, 'S2': 30.0, 'O1': 13.9430356}
ZWEITE = {'M2': 'S2', 'K1': 'O1'}
GEPRUEFT = ('harmonics_utide_current_observations.txt', 'harmonics_utide_current_tables.txt',
            'harmonics_utide_australia_oceancurrent.txt',
            # ATT Part IIIa: Dir(+) ist nur die positive Richtung, N/E-Saetze haben eine
            # willkuerliche Achse -> gleiche Probe (seit 7.11.2026)
            'harmonics_att_np203_currents.txt', 'harmonics_att_np204_currents.txt',
            'harmonics_att_np208_currents.txt')
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


GRAD_MIN, COS_MIN = 0.5, 0.3
# Nach Nachbarvergleich bewusst nicht drehen (18.11.2026), Urteil 'behalten'
BEHALTEN = {
    'Bird Island (35 km SSE, Algoa Bay), South Africa Current',            # 0.01 kn, Nachbarn gleich
    'Horse Sand Fort Lighthouse (2 km NNE), England, United Kingdom Current',  # Solent-Doppeltide, wie Spitbank
    'Epson Shoal (7 km ENE), England, United Kingdom Current',              # wie Tater Du (1 km)
}


def achse(r):
    """Flutrichtung des Satzes (flood_dir / max_direction / Hauptachse) aus den Hot Comments."""
    L = open(os.path.join(ROOT, r['file']), encoding='iso-8859-1').read().split('\n')
    i = L.index(r['name'])
    a = i
    while a > 0 and L[a - 1].startswith('#'):    # nur der Kommentarkopf direkt ueber dem Satz
        a -= 1
    blk = '\n'.join(L[a:i])
    m = re.search(r'# (?:flood_dir|max_direction): (\d+)', blk)
    if m:
        return float(m.group(1))
    m = re.search(r'# (?:major_axis_deg_true|Major axis): ([-\d.]+)', blk)
    return float(m.group(1)) if m else None


def laufrichtung(k, lat, lon, s=4):
    """TPXO10: (Richtung zunehmender Phase, Grad/km) per Ebenen-Fit, oder None."""
    f = TP.feld('10', k.lower())
    z = TP.naechste_wasserzelle('10', lat, lon, 30)
    if f is None or z is None or z[2] > 10:
        return None
    i, j, _dk = z
    if i - s < 0 or i + s >= TP.NY:
        return None
    ii = np.arange(i - s, i + s + 1)
    jj = np.arange(j - s, j + s + 1) % TP.NX
    blk = np.asarray(f[ii[0]:ii[-1] + 1][:, jj])
    h = blk[..., 0] - 1j * blk[..., 1]
    ok = np.abs(h) > 0
    if ok.sum() < 8 or h[s, s] == 0:
        return None
    ph = np.degrees(np.angle(h / h[s, s]))
    Y, Xg = np.meshgrid((ii - i) / 30 * 111.2, ((jj - j + TP.NX // 2) % TP.NX - TP.NX // 2) / 30 * 111.2
                        * math.cos(math.radians(lat)), indexing='ij')
    A = np.c_[Xg[ok], Y[ok], np.ones(ok.sum())]
    (gx, gy, _), *_ = np.linalg.lstsq(A, ph[ok], rcond=None)
    return math.degrees(math.atan2(gx, gy)) % 360, math.hypot(gx, gy)


def tpxo_urteil(r, k):
    """-> ('richtig'|'drehen'|None, Laufrichtung, Gradient, cos)."""
    ax, lr = achse(r), laufrichtung(k, r['lat'], r['lon'])
    if ax is None or lr is None:
        return None, None, None, None
    c = math.cos(math.radians(ax - lr[0]))
    if lr[1] < GRAD_MIN or abs(c) < COS_MIN:
        return None, round(lr[0]), round(lr[1], 2), round(c, 2)
    return ('richtig' if c > 0 else 'drehen'), round(lr[0]), round(lr[1], 2), round(c, 2)


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
        u = urteil(a[0], a[3])
        tu = lr = gr = cs = None
        if r['name'] in BEHALTEN:
            u = 'behalten'
        if u == 'unklar':
            tu, lr, gr, cs = tpxo_urteil(r, a[1])
            if tu:
                u = tu
        zeilen.append(dict(datei=f, name=r['name'], lat=r['lat'], lon=r['lon'], konst=a[1],
                           amp=round(a[2], 3), d=round(a[0], 1),
                           d2='' if a[3] is None else round(a[3], 1), urteil=u, bezug=a[4],
                           tpxo='' if tu is None else tu, laufrichtung='' if lr is None else lr,
                           grad='' if gr is None else gr, cos='' if cs is None else cs))
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
        pfad = next(os.path.join(ROOT, p) for p in active_files() if os.path.basename(p) == f)
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
                fe = re.match(r'# (flood_dir|ebb_dir): (\d+)\s*$', L[k])
                if fe:   # Flut- und Ebbrichtung tauschen
                    L[k] = '# %s: %03d' % (fe.group(1), (int(fe.group(2)) + 180) % 360)
                    continue
                m = re.match(r'(# Major axis: |# major_axis_deg_true: )([-\d.]+)(.*)', L[k])
                if m:
                    L[k] = '%s%.1f%s' % (m.group(1), (float(m.group(2)) + 180) % 360, m.group(3))
            z0 = L[i + 2].split()
            L[i + 2] = '%.4f %s' % (-float(z0[0]), ' '.join(z0[1:]))
            k = i + 3
            while k < len(L) and L[k].strip() and not L[k].startswith('#'):
                f3 = L[k].split()
                if f3[1] != 'x':
                    L[k] = '%-15s %s  %.2f' % (f3[0], f3[1], (float(f3[2]) + 180) % 360)
                k += 1
            L.insert(i, '# note: ' + dt.date.today().strftime('%Y%m%d') + ' Vorzeichen gedreht, damit XTide-Flood der Flutstrom ist '
                        '(Phase gegen den Wasserstand, py/flutrichtung_pruefen.py)')
            n += 1
        open(pfad, 'w', encoding='iso-8859-1').write('\n'.join(L))
        print('  %-45s %d Saetze gedreht' % (f, n))


if __name__ == '__main__':
    z = main(sys.argv)
    if '--schreiben' in sys.argv:
        drehen(z)
