#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst den Bestand an den amtlichen Konstanten der IH-Tabela de Marés.

harmonics/help/ih_konstanten.csv (py/ih_konstanten_tafel.py) haelt M2, S2,
K1 und O1 fuer 23 Haupthaefen der PALOP-Laender, dazu die Lage des Pegels
aus dem Tafelkopf. Hier wird jeder Satz im Umkreis dagegen gerechnet.

Zwei Dinge muessen dabei stimmen, sonst misst man Unsinn:

  Zone     Die Buchphasen stehen in der ORTSZEIT des Hafens (Angola UT+1,
           Mosambik UT+2, Kap Verde UT-1). Verglichen wird deshalb kappa
           auf demselben Meridian, nicht die Greenwich-Phase.
  Ort      Der Buchname ist nicht immer der Ort, den er nennt: "QUELIMANE"
           gehoert zum Pegel an der Muendung, nicht zur Stadt 25 km
           flussaufwaerts. Der Abstand steht deshalb in jeder Zeile, und
           weiter entfernte Saetze sind kein Fehler, sondern ein anderer Ort.

Ergebnis: harmonics/help/ih_konstanten_probe.csv, eine Zeile je Satz und Hafen.

Usage: python3 py/ih_konstanten_probe.py [--km 8]
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                         # noqa: E402
import xtide_modell as X                                            # noqa: E402
from health_check import ROOT, km, load_records                     # noqa: E402

QUELLE = os.path.join(ROOT, 'harmonics/help/ih_konstanten.csv')
AUS = os.path.join(ROOT, 'harmonics/help/ih_konstanten_probe.csv')
KONST = ('M2', 'S2', 'K1', 'O1')
UMKREIS = 8.0


def main(argv):
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else UMKREIS
    haefen = [z for z in csv.DictReader(open(QUELLE, encoding='utf-8')) if z['lat']]
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    kopf = {}
    zeilen = []
    for h in haefen:
        hl, ho = float(h['lat']), float(h['lon'])
        zone = float(h['zone_h'])
        nah = sorted(((km({'lat': hl, 'lon': ho}, r), r) for r in recs), key=lambda p: p[0])
        for d, r in nah:
            if d > umkreis:
                break
            pfad = os.path.join(ROOT, r['file'])
            if pfad not in kopf:
                kopf[pfad] = X.kopf_lesen(pfad)[1]
            sp = kopf[pfad]
            try:
                _z0, w, _e, mer = X.satz_lesen(pfad, r['name'])
            except KeyError:
                continue
            z = dict(hafen=h['hafen'], land=h['land'], km=round(d, 2), satz=r['name'],
                     datei=os.path.basename(r['file']), klasse=P.klasse(r) or 'Uebertragung/Modell')
            for c in KONST:
                bh, bg = float(h[f'{c}_H']), float(h[f'{c}_G'])
                if c not in w or bh <= 0:
                    z[f'{c}_verh'] = z[f'{c}_min'] = ''
                    continue
                # Satz-kappa auf die Buchzone bringen
                kappa = w[c][1] + (zone - mer) * sp[c]
                dg = (kappa - bg + 180) % 360 - 180
                z[f'{c}_verh'] = round(w[c][0] / bh, 3)
                z[f'{c}_min'] = round(dg / sp[c] * 60)
            zeilen.append(z)
    felder = (['hafen', 'land', 'km', 'satz', 'datei', 'klasse']
              + [f'{c}_{x}' for c in KONST for x in ('verh', 'min')])
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w_ = csv.DictWriter(fh, fieldnames=felder)
        w_.writeheader()
        w_.writerows(zeilen)

    print(f'{len(zeilen)} Vergleiche an {len(haefen)} Haefen (Umkreis {umkreis:.0f} km)\n')
    print(f'{"Hafen":22} {"km":>5} {"Satz":36} {"Klasse":8} {"M2":>12} {"S2":>12}')
    for z in zeilen:
        m2 = f"{z['M2_verh']:.2f}/{z['M2_min']:+.0f}min" if z['M2_verh'] != '' else '--'
        s2 = f"{z['S2_verh']:.2f}/{z['S2_min']:+.0f}min" if z['S2_verh'] != '' else '--'
        warn = ' <<<' if z['M2_verh'] != '' and (abs(z['M2_verh'] - 1) > 0.05
                                                 or abs(z['M2_min']) > 15) else ''
        print(f"{z['hafen'][:22]:22} {z['km']:5.1f} {z['satz'][:36]:36} {z['klasse'][:8]:8} "
              f"{m2:>12} {s2:>12}{warn}")
    print('\n->', os.path.relpath(AUS, ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
