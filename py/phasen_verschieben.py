#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reinen Zeitversatz eines Satzes exakt beheben: jede Phase g -> g - speed * dt (dt in Stunden, > 0 = Satz war zu
spaet), dazu die Nebenachse in harmonics/ellipsen/eigen.json; Notiz in den Satzkopf (13.11.2026).
Kein Neufit (der scheiterte an kurzen BODC-Reihen mit gekoppelten Tiden/anderen Einheiten).

Usage: venv/bin/python py/phasen_verschieben.py <datei.txt> "<Satzname>" <minuten> "<Begruendung>" [--schreiben]
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xtide_modell as X                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EIGEN = os.path.join(ROOT, 'harmonics/ellipsen/eigen.json')


def main(argv):
    schreiben = '--schreiben' in argv
    a = [x for x in argv if x != '--schreiben']
    pfad, name, minuten, grund = a[0], a[1], float(a[2]), a[3]
    pfad = pfad if os.path.isabs(pfad) else os.path.join(ROOT, pfad)
    _n, speeds, _arg, _fak = X.kopf_lesen(pfad)
    L = open(pfad, encoding='iso-8859-1').read().split('\n')
    i = L.index(name)
    j, n = i + 3, 0
    while j < len(L) and L[j].strip() and not L[j].startswith('#'):
        f = L[j].split()
        if f[0] != 'x' and f[0] in speeds:
            L[j] = '%-15s %.4f  %.2f' % (f[0], float(f[1]), (float(f[2]) - speeds[f[0]] * minuten / 60.0) % 360)
            n += 1
        j += 1
    L.insert(i, '# note: %s Phasen um %.0f min %s gelegt (g - speed*dt, py/phasen_verschieben.py): %s' % (
        dt.date.today().strftime('%Y%m%d'), abs(minuten), 'frueher' if minuten > 0 else 'spaeter', grund))
    print('%s: %d Tiden um %+.0f min' % (name, n, -minuten))
    if not schreiben:
        return
    from sicher_schreiben import schreiben as sw
    sw(pfad, '\n'.join(L))
    if os.path.exists(EIGEN):
        d = json.load(open(EIGEN))
        e = d.get(os.path.basename(pfad), {}).get(name)
        if e:
            e['neben'] = {k: [v[0], round((v[1] - speeds[k] * minuten / 60.0) % 360, 2)] for k, v in e['neben'].items() if k in speeds}
            json.dump(d, open(EIGEN, 'w'), ensure_ascii=False, indent=1, sort_keys=True)
            print('  Nebenachse ebenso')


if __name__ == '__main__':
    main(sys.argv[1:])
