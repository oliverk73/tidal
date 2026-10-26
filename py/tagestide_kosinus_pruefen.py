#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tafelfits bei Tagestide: hat die Kosinus-Zwischenkurve M2 verschluckt? (Oliver 26.10.2026)

Bei SEMAR (Mexiko) verloren UTide-Fits auf Kosinusboegen zwischen gedruckten
Hoch- und Niedrigwassern bei Formzahl > 3 die halbe M2 (47-66 % von FES, 8-25
Grad spaet); py/semar_scheitelfit.py hat sie repariert. Hier wird der ganze
Bestand nach demselben Muster abgesucht: Saetze, deren Kopf eine HW/NW-Tafel
als Quelle nennt, mit ueberwiegender Tagestide, verglichen mit
  - FES2022 an der Position (nur offene Kueste aussagekraeftig) und
  - dem naechsten Satz, der NICHT aus einer HW/NW-Tafel stammt (<= 60 km).

Usage: venv/bin/python py/tagestide_kosinus_pruefen.py [--formzahl 2] [--csv]
       --csv schreibt harmonics/help/tagestide_kosinus.csv
"""
import csv
import math
import os
import re
import sys

import netCDF4 as nc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import FES_DIR, sample                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOPF = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
# Woran ein Satz aus einer HW/NW-Tafel zu erkennen ist (Kopfkommentar)
TAFEL = re.compile(r'HW/LW|HW/NW|cosine-interpolated|high/low water|Tabla de Mareas|'
                   r'tide tables? ×|predictions with UTide|Lageberichte|HW/LW-Tafel', re.I)
# Bereits per Scheitelfit repariert
REPARIERT = re.compile(r'Scheitelfit|scheitelfit\.py|peak fit', re.I)


def koepfe():
    """-> {(datei, name): Kommentarblock als Text}"""
    out = {}
    for f in sorted({r['file'] for r in H.load_records()}):
        L = open(f, encoding='iso-8859-1').read().split('\n')
        for i, l in enumerate(L):
            if i + 1 < len(L) and re.match(r'^[+-]\d\d:\d\d', L[i + 1]) and not l.startswith('#'):
                j = i
                while j > 0 and L[j - 1].startswith('#'):
                    j -= 1
                out[(f, l)] = '\n'.join(L[j:i])
    return out


def main(argv):
    grenze = float(argv[argv.index('--formzahl') + 1]) if '--formzahl' in argv else 2.0
    kopf = X.kopf_lesen(KOPF)
    speeds = kopf[1]
    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    K = koepfe()
    fes = {k: nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in ('M2', 'K1')}

    def konst(r):
        z0, w, e, m = X.satz_lesen(r['file'], r['name'])
        f = 0.3048 if e.startswith('f') else 1.0
        return {k: (a * f, X.greenwich(kp, speeds[k], m) % 360) for k, (a, kp) in w.items() if k in speeds}

    def ist_tafel(r):
        t = K.get((r['file'], r['name']), '')
        return bool(TAFEL.search(t)), bool(REPARIERT.search(t))

    unabh = []
    for r in recs:
        tf, _ = ist_tafel(r)
        if not tf:
            unabh.append(r)
    zeilen = []
    for r in recs:
        tf, rep = ist_tafel(r)
        if not tf:
            continue
        try:
            w = konst(r)
        except (KeyError, IndexError, ValueError):
            continue
        a = lambda k: w.get(k, (0.0, 0.0))[0]
        if a('M2') + a('S2') <= 0:
            continue
        fz = (a('K1') + a('O1')) / (a('M2') + a('S2'))
        if fz < grenze:
            continue
        fa, fg = sample(fes['M2'], r['lat'], r['lon'])
        nb = None
        for q in unabh:
            d = H.km(r, q)
            if d <= 60 and (nb is None or d < nb[0]):
                nb = (d, q)
        nbw = None
        if nb:
            try:
                nbw = konst(nb[1])
            except (KeyError, IndexError, ValueError):
                nb = None
        dphi = lambda g1, g2: (g1 - g2 + 180) % 360 - 180
        z = dict(datei=os.path.basename(r['file']), name=r['name'], lat=r['lat'], lon=r['lon'],
                 formzahl=round(fz, 1), m2=round(a('M2'), 3), m2_phase=round(w.get('M2', (0, 0))[1]),
                 repariert='ja' if rep else '',
                 fes_verh=round(a('M2') / fa, 2) if fa else '', fes_dg=round(dphi(w['M2'][1], fg)) if fa and 'M2' in w else '',
                 nachbar=nb[1]['name'] if nb else '', nachbar_km=round(nb[0], 1) if nb else '',
                 nb_verh=round(a('M2') / nbw['M2'][0], 2) if nb and 'M2' in nbw and nbw['M2'][0] else '',
                 nb_dg=round(dphi(w['M2'][1], nbw['M2'][1])) if nb and 'M2' in nbw and 'M2' in w else '')
        zeilen.append(z)
    zeilen.sort(key=lambda z: (z['repariert'], z['datei'], z['nb_verh'] if z['nb_verh'] != '' else (z['fes_verh'] or 9)))
    print('%d Tafelsaetze mit Formzahl >= %.1f' % (len(zeilen), grenze))
    print('%-44s %-28s %5s %6s %10s %12s  %s' % ('Satz', 'Datei', 'F', 'M2', 'FES', 'Nachbar', ''))
    for z in zeilen:
        print('%-44s %-28s %5.1f %6.3f %10s %12s  %s%s' % (
            z['name'][:44], z['datei'][:28], z['formzahl'], z['m2'],
            '%s/%s' % (z['fes_verh'], z['fes_dg']) if z['fes_verh'] != '' else '-',
            '%s/%s' % (z['nb_verh'], z['nb_dg']) if z['nb_verh'] != '' else '-',
            ('%s (%.0f km)' % (z['nachbar'][:30], z['nachbar_km'])) if z['nachbar'] else '',
            '  [repariert]' if z['repariert'] else ''))
    if '--csv' in argv and zeilen:
        pfad = os.path.join(ROOT, 'harmonics/help/tagestide_kosinus.csv')
        with open(pfad, 'w', newline='', encoding='utf-8') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
            wr.writeheader()
            wr.writerows(zeilen)
        print('->', os.path.relpath(pfad, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
