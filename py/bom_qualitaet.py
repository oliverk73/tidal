#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Datensaetze gegen die gedruckten BOM-Tafeln (Hoch-/Niedrigwasser).

Die Tafeln drucken Ortszeit ohne Zonenangabe. Statt die Zone zu raten wird
der Zeitversatz aus dem Vergleich selbst geschaetzt: passt er auf volle
Stunden, ist es eine Zonendifferenz und kein Fehler des Datensatzes.
Gemeldet werden Hoehen-RMS (nach Abzug des konstanten Pegelversatzes),
mittlerer Zeitfehler und die Zahl der verglichenen Ereignisse.

Usage: python3 py/bom_qualitaet.py [--monat JULY] [--km 5] [--max N]
"""
from __future__ import annotations

import calendar
import collections
import csv
import datetime as dt
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from bom_referenz import lies, MONATE                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS = os.path.join(ROOT, 'tide_tables/australia')
TCD = '/usr/share/xtide'
EREIGNIS = re.compile(r'^(.*),(\d{4}-\d\d-\d\d),(\d+):(\d\d) ([AP])M[^,]*,'
                      r'(-?[\d.]+) m,(High|Low) Tide$')


def xtide(tcd, name, von, bis):
    env = dict(os.environ, HFILE_PATH=os.path.join(TCD, tcd))
    out = subprocess.run(['tide', '-l', name, '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c'],
                         env=env, capture_output=True, text=True).stdout
    ev = []
    for z in out.split('\n'):
        m = EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        d = dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4)))
        ev.append((d, float(m.group(6)), m.group(7)))
    return ev


def vergleich(ref, y):
    """ref/y: Listen (zeitpunkt, hoehe, art). -> Kennzahlen oder None."""
    if len(ref) < 40 or len(y) < 40:
        return None
    paare = []
    for zr, hr, ar in ref:
        nah = [(abs((zy - zr).total_seconds()), zy, hy)
               for zy, hy, ay in y if ay == ar and abs((zy - zr).days) <= 1]
        if nah:
            paare.append((min(nah), zr, hr))
    if len(paare) < 40:
        return None
    dz = [p[0][0] * (1 if p[0][1] > p[1] else -1) / 60.0 for p in paare]
    versatz = statistics.median(dz)
    # Zeitversatz herausrechnen, dann erneut zuordnen
    y2 = [(zy - dt.timedelta(minutes=versatz), hy, ay) for zy, hy, ay in y]
    treffer = []
    for zr, hr, ar in ref:
        nah = [(abs((zy - zr).total_seconds()) / 60.0, hy)
               for zy, hy, ay in y2 if ay == ar and abs((zy - zr).total_seconds()) < 5400]
        if nah:
            treffer.append((min(nah), hr))
    if len(treffer) < 40:
        return None
    dh_roh = [t[1] - t[0][1] for t in treffer]
    off = statistics.mean(dh_roh)
    dh = [q - off for q in dh_roh]
    dt_min = [t[0][0] for t in treffer]
    return dict(n=len(treffer), versatz_min=versatz, hoehe_off=off,
                rms=(sum(q * q for q in dh) / len(dh)) ** 0.5,
                max=max(abs(q) for q in dh),
                zeit_med=statistics.median(dt_min))


def main():
    monat = 'JULY'
    if '--monat' in sys.argv:
        monat = sys.argv[sys.argv.index('--monat') + 1].upper()
    umkreis = 5.0
    if '--km' in sys.argv:
        umkreis = float(sys.argv[sys.argv.index('--km') + 1])
    grenze = None
    if '--max' in sys.argv:
        grenze = int(sys.argv[sys.argv.index('--max') + 1])

    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    dateien = collections.OrderedDict()
    for f in sorted(os.listdir(PDFS)):
        if f.startswith('IDO59001') and f.endswith('.pdf'):
            dateien.setdefault(re.sub(r'_20\d\d_', '_', f), []).append(f)
    schluessel = list(dateien)
    if grenze:
        schluessel = schluessel[:grenze]
    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m',
                'n', 'rms_m', 'max_m', 'zeit_min', 'zonenversatz_min'])
    for s in schluessel:
        f = sorted(dateien[s])[-1]           # neueste Ausgabe
        k = lies(os.path.join(PDFS, f))
        if not k or not k.get('tage'):
            continue
        i = MONATE.index(monat) + 1
        tage = {t: v for (m, t), v in k['tage'].items() if m == monat}
        if len(tage) != calendar.monthrange(k['jahr'], i)[1]:
            continue
        # Erst alle Ereignisse des Monats in Zeitfolge, dann Hoch/Niedrig
        # ueber die Nachbarn bestimmen. Tageweise zu entscheiden geht schief,
        # weil ein Tag drei oder vier Ereignisse haben kann und das erste
        # keinen Vorgaenger im selben Tag hat.
        roh = sorted((dt.datetime(k['jahr'], i, t, hh, mm), h)
                     for t, ev in tage.items() for hh, mm, h in ev)
        ref = []
        for j, (z, h) in enumerate(roh):
            vor = roh[j - 1][1] if j else None
            nach = roh[j + 1][1] if j + 1 < len(roh) else None
            nachbarn = [q for q in (vor, nach) if q is not None]
            ref.append((z, h, 'High' if h > max(nachbarn) else
                        'Low' if h < min(nachbarn) else
                        ('High' if h > statistics.mean(nachbarn) else 'Low')))
        ziel = {'lat': k['lat'], 'lon': k['lon']}
        von = f'{k["jahr"]}-{i:02d}-01 00:00'
        bis = f'{k["jahr"]}-{i:02d}-{calendar.monthrange(k["jahr"], i)[1]} 23:59'
        for x in sorted(recs, key=lambda x: km(ziel, x)):
            d = km(ziel, x)
            if d > umkreis:
                break
            tcd = os.path.basename(x['file'])[:-4] + '.tcd'
            if not os.path.exists(os.path.join(TCD, tcd)):
                continue
            g = vergleich(ref, xtide(tcd, x['name'], von, bis))
            if g:
                w.writerow([k['name'], f'{k["lat"]:.4f}', f'{k["lon"]:.4f}', k['jahr'],
                            x['name'], os.path.basename(x['file']), f'{d*1000:.0f}',
                            g['n'], f'{g["rms"]:.4f}', f'{g["max"]:.3f}',
                            f'{g["zeit_med"]:.1f}', f'{g["versatz_min"]:.0f}'])
            sys.stdout.flush()


if __name__ == '__main__':
    main()
