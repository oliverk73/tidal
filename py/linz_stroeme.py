#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LINZ Neuseeland: Stroemungsvorhersagen Te Aumiti / French Pass und Tory Channel (Oliver 25.10.2026).

Quelle: https://www.linz.govt.nz/products-services/tides-and-tidal-streams/tidal-stream-predictions
CSV je Jahr (2025-2029, Stand 2026update) mit den Zeiten, zu denen der Strom in eine Richtung
einsetzt (= Kenterzeiten), Ortszeit Pacific/Auckland inkl. Sommerzeit. Staerken stehen nicht in den
CSVs. Sie kommen aus den LINZ-Seiten (French Pass 5-7 kn, Tory Channel 5 kn) und werden je
Halbtide mit dem Tidenhub am Bezugshafen der LINZ-Diagramme skaliert (Nelson bzw. Picton, aus
unserem Bestand per tide). Zwischen zwei Kenterzeiten: Sinusbogen, alle 20 min ein Wert.
Flutrichtung aus den Spring-Diagrammen: French Pass SW, Tory Channel W (in den Sund).

Ablage: tide_tables/newzealand/linz_stroeme/
Usage: venv/bin/python py/linz_stroeme.py [--bloecke]
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
from shn_corrientes import KONST                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'tide_tables/newzealand/linz_stroeme')
HILFE = os.path.join(ROOT, 'harmonics/help')
NZ = ZoneInfo('Pacific/Auckland')

# Position = Engstelle mit den staerksten Pfeilen in den LINZ-Diagrammen.
ORTE = {
    'TeAumiti-FrenchPass': dict(
        name='Te Aumiti / French Pass, Nelson, New Zealand', lat=-40.9244, lon=173.8341,
        bezug='Nelson, New Zealand', spring_kn=6.0, flut='SW', flut_grad=220.0),
    'ToryChannel-KuraTeAuEntrance': dict(
        name='Kura Te Au / Tory Channel (Entrance), Marlborough, New Zealand', lat=-41.2093, lon=174.3167,
        bezug='Picton, New Zealand', spring_kn=5.0, flut='W', flut_grad=285.0),
}


def kenter(code):
    """[(UTC-Zeit, Richtung des einsetzenden Stroms)] aus allen Jahres-CSVs."""
    ev = set()
    for pfad in sorted(glob.glob(os.path.join(QUELLE, code + '_*.csv'))):
        for z in csv.reader(open(pfad, encoding='utf-8-sig')):
            if len(z) < 6 or not z[0].isdigit() or not z[3].isdigit():
                continue
            tag, mon, jahr = int(z[0]), int(z[2]), int(z[3])
            for k in range(4, len(z) - 1, 2):
                if not z[k]:
                    continue
                hh, mm = map(int, z[k].split(':'))
                lokal = dt.datetime(jahr, mon, tag, hh, mm, tzinfo=NZ)
                ev.add((lokal.astimezone(dt.timezone.utc).replace(tzinfo=None), z[k + 1]))
    return sorted(ev)


def hub(bezug, von, bis):
    """Tidenhub am Bezugshafen: Zeitpunkte (Mitte HW/NW-Paar) und Hub in m."""
    out = subprocess.run(['tide', '-l', bezug, '-b', von.strftime('%Y-%m-%d %H:%M'),
                          '-e', bis.strftime('%Y-%m-%d %H:%M'), '-m', 'p', '-f', 'c', '-z'],
                         capture_output=True, encoding='utf-8', errors='replace').stdout
    sch = []
    for z in out.split('\n'):
        f = z.split(',')
        if len(f) >= 5 and f[4] in ('High Tide', 'Low Tide'):
            t = dt.datetime.strptime(f[1] + ' ' + f[2].replace(' UTC', ''), '%Y-%m-%d %I:%M %p')
            sch.append((t, float(f[3].split()[0])))
    t = [a[0] + (b[0] - a[0]) / 2 for a, b in zip(sch, sch[1:])]
    h = [abs(b[1] - a[1]) for a, b in zip(sch, sch[1:])]
    return np.array(t, dtype='datetime64[s]'), np.array(h)


def reihe(o, ev):
    th, h = hub(o['bezug'], ev[0][0] - dt.timedelta(days=1), ev[-1][0] + dt.timedelta(days=1))
    h_spring = np.percentile(h, 90)
    zeiten, werte = [], []
    for (t0, r0), (t1, _r1) in zip(ev, ev[1:]):
        dauer = (t1 - t0).total_seconds()
        if dauer > 9 * 3600:                    # Luecke (Jahreswechsel o. ae.)
            continue
        mitte = np.datetime64(t0 + (t1 - t0) / 2, 's')
        k = int(np.argmin(np.abs(th - mitte)))
        a = o['spring_kn'] * h[k] / h_spring
        vz = 1.0 if r0 == o['flut'] else -1.0
        for s in np.arange(0, dauer, 1200):
            zeiten.append(t0 + dt.timedelta(seconds=float(s)))
            werte.append(vz * a * math.sin(math.pi * s / dauer))
    w = np.array(werte) / C.MS_KN
    rad = math.radians(o['flut_grad'])
    return pd.DataFrame({'u': w * math.sin(rad), 'v': w * math.cos(rad)}, index=pd.to_datetime(zeiten))


def main():
    erg = []
    for code, o in ORTE.items():
        ev = kenter(code)
        df = reihe(o, ev)
        df = df[~df.index.duplicated()]
        r = C.analyse(df, o['lat'], KONST)
        if abs((r['achse'] - o['flut_grad'] + 180) % 360 - 180) > 90:
            # Achse liegt immer in 0-180 Grad; positiv soll der Flutstrom sein.
            r['achse'] = (r['achse'] + 180) % 360
            r['mean'] = -r['mean']
            r['konst'] = {k: (a, (g + 180) % 360) for k, (a, g) in r['konst'].items()}
        print('%-30s %d Kenter %s..%s  Achse %5.1f  R2 %.3f  M2 %.2f S2 %.2f K1 %.2f  M2-Phase %.1f' % (
            code, len(ev), ev[0][0].date(), ev[-1][0].date(), r['achse'], r['r2'], r['m2'], r['s2'],
            r['k1'], r['konst']['M2'][1]))
        erg.append((code, o, ev, r))
    return erg


def block(code, o, ev, r):
    from cmems_stroemung_nachholen import CONSTITUENTS_175, utide
    L = ['# Harmonic constants derived from the LINZ (Toitu Te Whenua Land Information New Zealand) tidal',
         '# stream predictions %s..%s: times of commencement of flood/ebb (%d slacks), local time' % (
             ev[0][0].date(), ev[-1][0].date(), len(ev)),
         '# Pacific/Auckland. Rates are not tabulated: spring rate %.1f kn (LINZ notes), scaled by the' % o['spring_kn'],
         '# tidal range at %s, sine-shaped between slacks' % o['bezug'].split(',')[0],
         '# (UTide v%s, principal-axis projection, %d fixed constituents)' % (utide.__version__, len(KONST)),
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true (flood %s)' % (r['achse'], o['flut']), '#',
         '# BEGIN HOT COMMENTS', '# country: New Zealand',
         '# source: LINZ tidal stream predictions (slack times), UTide analysis',
         '# station_id_context: LINZ-STREAM-%s' % code,
         '# institution: Toitu Te Whenua Land Information New Zealand', '# datum: n/a',
         '# station_type: current', '# major_axis_deg_true: %.1f' % r['achse'], '# confidence: 4',
         '# !units: knots', '# !longitude: %.4f' % o['lon'], '# !latitude: %.4f' % o['lat'],
         '%s Current' % o['name'], '+00:00 :UTC', '%.4f knots' % r['mean']]
    for c, _sp in CONSTITUENTS_175:
        a = r['konst'].get(c)
        L.append('%-15s %.4f  %.2f' % (c, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


if __name__ == '__main__':
    erg = main()
    if '--bloecke' in sys.argv:
        out = os.path.join(HILFE, 'linz_stroeme_%s.txt' % dt.date.today().strftime('%Y%m%d'))
        with open(out, 'w', encoding='iso-8859-1') as f:
            f.write('\n'.join(block(*e) for e in erg) + '\n')
        print('->', out)
