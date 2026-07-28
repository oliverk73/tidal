#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ergaenzt die beiden fehlenden Stationen der katarischen Westkueste
(ATT NP203 Part II) in harmonics_att_np203_secondary.txt.

Warum sie fehlen -- zwei verschiedene Ursachen:

  4247a  Nagiyah     Die Zeile steht in keiner Transkription. Zwischen 4247
                     Jazirat Hawar und 4247b Zikrit klafft in page_231.json
                     genau ein Loch; beim Abschreiben uebersprungen.

  4247e  Al Khraij   In page_231.json als "Ar Akhaj" erfasst, mit den Flags
                     "illegible; coords-illegible" und ohne Koordinaten. Ohne
                     Position baut der Generator keinen Block -- die Station
                     wurde verworfen.

Die Nachbarn 4247b..4247f beziehen sich auf Mina Salman. Das ist hier als
Vorgabe eingetragen; falls das Buch etwas anderes nennt, in STATIONS aendern.

VOR DEM LAUF AUSFUELLEN: Ohne die Werte aus dem Scan bricht das Skript ab.
Gebraucht werden je Station Koordinaten, Zeitdifferenzen (HW/LW, Minuten),
die vier Hoehendifferenzen (MHWS, MHWN, MLWN, MLWS) und ML.

Aufruf: python3 py/add_qatar_west.py            # dry-run
        python3 py/add_qatar_west.py --write
"""
from __future__ import annotations
import importlib.util
import os
import sys

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'

# ---------------------------------------------------------------- ausfuellen
# lat/lon dezimal, t=(tHW, tLW) in Minuten, h=(dMHWS, dMHWN, dMLWN, dMLWS),
# ml = Mittelwasser ueber Kartennull. None ist erlaubt, wo das Buch nichts
# angibt -- ausser bei lat/lon/ml und mindestens einem Wert aus t oder h[0].
STATIONS = [
    # Scan (Oliver, 20260728): "4247 Nagiyah 25 41 50 54 p p -1.8 -1.4 -0.7 -0.4 0.3 x"
    # Zeitdifferenzen stehen als "p" -- das Buch gibt keine an, dt bleibt 0.
    dict(att='4247', name='Nagiyah', region='Qatar', std='Mina Salman',
         lat=25 + 41 / 60, lon=50 + 54 / 60, t=(None, None),
         h=(-1.8, -1.4, -0.7, -0.4), ml=0.30, before='Zekreet, Qatar'),
    # Scan (Oliver, 20260728): "4247e Al Khraij 25 00 50 48 p p -1.6 -1.3 -0.6 -0.4 0.4 x"
    dict(att='4247e', name='Al Khraij', region='Qatar', std='Mina Salman',
         lat=25 + 0 / 60, lon=50 + 48 / 60, t=(None, None),
         h=(-1.6, -1.3, -0.6, -0.4), ml=0.40, before='Ghar al Buraid, Qatar'),
]
NOTE = ('# note: 20260728 nachgetragen, Werte aus ATT Vol.3 (2015) Scan. '
        'Die Transkription page_231.json hatte die Zeile %s.')
WHY = {'4247': 'gar nicht erfasst',
       '4247e': 'als "Ar Akhaj" ohne lesbare Koordinaten erfasst'}
# ---------------------------------------------------------------------------


def load_engine():
    os.environ['HOME'] = '/home/oliver/weather'      # ~/harmonics == weather/harmonics
    spec = importlib.util.spec_from_file_location(
        'B', '/home/oliver/weather/py/build_np203_secondary.py')
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    return B


def check(s):
    miss = [k for k in ('lat', 'lon', 'ml') if s[k] is None]
    if all(x is None for x in s['t']) and s['h'][0] is None:
        miss.append('t oder h[0]')
    return miss


def main():
    write = '--write' in sys.argv
    todo = [(s['name'], check(s)) for s in STATIONS if check(s)]
    if todo:
        print('Fehlende Werte aus dem Scan:\n')
        for n, m in todo:
            print(f'  {n:12s} {", ".join(m)}')
        sys.exit('\nSTATIONS oben ausfuellen, dann erneut starten.')

    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    B = load_engine()
    for s in STATIONS:
        name_line = f"{s['name']}, {s['region']}"
        if name_line in L:
            sys.exit(f'{name_line} steht bereits in der Datei.')
        refname, rr = B.find(s['std'])
        if rr is None:
            sys.exit(f'Bezugshafen nicht gefunden: {s["std"]}')
        tr = B.transfer(s, rr)
        if tr is None:
            sys.exit(f'{s["name"]}: Differenzen reichen fuer keinen Transfer.')
        tr['refname'] = refname
        blk, name, conf = B.block(s, tr)
        j = blk.index('# date_imported: 20260618')
        blk[j] = '# date_imported: 20260728'
        blk[j:j] = [NOTE % WHY[s['att']]]
        i = L.index(s['before'])
        start = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
        L[start:start] = blk
        print(f'{name} (att {s["att"]}) aus {refname}: '
              f'fS={tr["fS"]:.2f} fN={tr["fN"]:.2f} dt={tr["dt"]*60:+.0f}min, conf {conf}')

    if write:
        open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
        os.chmod(TXT, 0o600)
        print(f'\nGeschrieben. Stationen: {sum(1 for l in L if l.startswith("# !latitude:"))}')
    else:
        print('\n(Dry-run. --write zum Schreiben.)')


if __name__ == '__main__':
    main()
