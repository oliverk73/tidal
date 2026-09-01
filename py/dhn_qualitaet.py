#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Datensaetze gegen die gedruckten DHN-Tafeln (Brasilien).

Die Tafeln der brasilianischen Marine drucken Hoch- und Niedrigwasser in
Ortszeit und nennen ihre Zeitzone im Kopf. Damit laesst sich in UTC
vergleichen, und der gefundene Zeitversatz ist ein echter Fehler des
Datensatzes -- nicht, wie bei den australischen Tafeln, moeglicherweise
nur eine ungenannte Zone.

Gemeldet werden Hoehen-RMS nach Abzug des konstanten Pegelversatzes (die
Bezugsniveaus sind verschieden), der mittlere Zeitfehler und die Zahl der
verglichenen Ereignisse.

Usage: python3 py/dhn_qualitaet.py [--km 5] [--max N] [--jahr]
       --km    Umkreis um die Tafel
       --max   nur die ersten N Tafeln (zum Ausprobieren)
       --jahr  ganzes Jahr statt eines Monats
"""
from __future__ import annotations

import csv
import collections
import datetime as dt
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                    # noqa: E402
from bom_qualitaet import vergleich, EREIGNIS                      # noqa: E402
import dhn_referenz as D                                           # noqa: E402

TCD = '/usr/share/xtide'
HELP = os.path.join(ROOT, 'harmonics/help')


def art_bestimmen(ev):
    """(zeit, hoehe) -> (zeit, hoehe, 'High'|'Low') aus den Nachbarn.

    Tageweise zu entscheiden geht schief, weil ein Tag drei oder vier
    Ereignisse haben kann und das erste keinen Vorgaenger im selben Tag
    hat. Darum ueber die ganze Reihe.
    """
    aus = []
    for i, (z, h) in enumerate(ev):
        nb = [q for q in (ev[i - 1][1] if i else None,
                          ev[i + 1][1] if i + 1 < len(ev) else None)
              if q is not None]
        if not nb:
            continue
        aus.append((z, h, 'High' if h > max(nb) else 'Low' if h < min(nb)
                    else ('High' if h > statistics.mean(nb) else 'Low')))
    return aus


def xtide(tcd, name, von, bis):
    """Vorhersage in UTC. Die Tafelzeiten werden ebenfalls nach UTC
    gerechnet, damit ein gefundener Versatz wirklich dem Datensatz
    gehoert und nicht der Zonenwahl."""
    out = subprocess.run(['tide', '-l', name, '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c', '-z'],
                         env=dict(os.environ, HFILE_PATH=os.path.join(TCD, tcd)),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    ev = []
    for z in out.split('\n'):
        m = EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        ev.append((dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return ev


def tafeln():
    """Je Station die neueste Tafel, Kopf schon gelesen."""
    beste = {}
    for fn in sorted(os.listdir(D.PDFS)):
        if not fn.lower().endswith('.pdf'):
            continue
        try:
            k = D.kopf(os.path.join(D.PDFS, fn))
        except Exception:
            continue
        if not k or k.get('jahr') is None or k.get('fuso') is None:
            continue
        s = round(k['lat'], 3), round(k['lon'], 3)
        if s not in beste or k['jahr'] > beste[s][1]['jahr']:
            beste[s] = (fn, k)
    return [(fn, k) for fn, k in beste.values()]


def main(argv):
    umkreis = 5.0
    if '--km' in argv:
        umkreis = float(argv[argv.index('--km') + 1])
    grenze = int(argv[argv.index('--max') + 1]) if '--max' in argv else None
    ganzes_jahr = '--jahr' in argv

    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    liste = tafeln()
    if grenze:
        liste = liste[:grenze]
    print(f'{len(liste)} Tafeln, Umkreis {umkreis:.0f} km, '
          f'{"ganzes Jahr" if ganzes_jahr else "Juli"}\n', file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m',
                'n', 'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m'])
    for fn, k in liste:
        try:
            _k, roh = D.lies(os.path.join(D.PDFS, fn))
        except Exception as e:
            print(f'  {fn}: {type(e).__name__}', file=sys.stderr)
            continue
        if not roh:
            continue
        if not ganzes_jahr:
            roh = [(z, h) for z, h in roh if z.month == 7]
        ev = art_bestimmen(roh)
        # Ortszeit -> UTC. Fuso ist der Zonen-Offset, also abziehen.
        vers = dt.timedelta(hours=k['fuso'])
        ref = [(z - vers, h, a) for z, h, a in ev]
        if len(ref) < 40:
            continue
        # Tidenhub des Vergleichszeitraums: erst er macht einen RMS
        # zwischen Orten vergleichbar -- 5 cm sind an einem Ort mit 40 cm
        # Hub viel und an einem mit 5 m nichts.
        hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
        von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        ziel = {'lat': k['lat'], 'lon': k['lon']}
        for x in sorted(recs, key=lambda q: km(ziel, q)):
            d = km(ziel, x)
            if d > umkreis:
                break
            tcd = os.path.basename(x['file'])[:-4] + '.tcd'
            if not os.path.exists(os.path.join(TCD, tcd)):
                continue
            y = xtide(tcd, x['name'], von, bis)
            if not y:
                continue
            g = vergleich(ref, y)
            if not g:
                continue
            w.writerow([k['name'], f'{k["lat"]:.4f}', f'{k["lon"]:.4f}',
                        k['jahr'], x['name'], os.path.basename(x['file']),
                        round(d * 1000), g['n'], round(g['rms'], 4),
                        round(g['max'], 3), round(g['zeit_med'], 1),
                        round(g['hoehe_off'], 3), round(hub, 3)])
            sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
