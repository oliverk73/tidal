#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet die aus CICESE gefitteten Saetze neu.

Alle sechs Saetze, die harmonics_utide_tidetables aus CICESE-Tafeln
bezieht, tragen in ihrer eigenen Kopfzeile ein gescheitertes Ergebnis:
R^2 zwischen 0.43 und 0.68, RMS bis 1.49 m. Bei einem Fit gegen eine
gerechnete Tafel muss R^2 bei eins liegen -- die Tafel enthaelt ja
nichts als Gezeiten. Ein siebter, Puerto Penasco, stand mit R^2 = 0.46
und 1.28 m im Bestand und war gegen die Tafel um 52 cm daneben; er ist
bereits geloescht.

Warum der Ausgleich damals scheiterte, laesst sich nicht mehr
feststellen. Nachvollziehbar ist nur, dass er nie geprueft wurde: die
Kopfzeile sagt es deutlich, und der Satz wurde trotzdem eingespielt.

Zugeordnet wird ueber den Namen, nicht ueber den Abstand: der Satz
"La Crucecita (Huatulco)" steht 30 km von der Position, die das CICESE
fuer Huatulco angibt. Welche der beiden stimmt, ist eine eigene Frage --
fuer die Rechnung zaehlt, aus welcher Tafel der Satz stammt.

Gefittet wird gegen das ganze Jahr 2026, gemessen gegen den Juli.
Uebernommen wird nur, was deutlich besser ist.

Usage: python3 py/cicese_neufit.py [--schreiben]
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import MERIDIAN, ROOT                            # noqa: E402
from dhn_neufit import fitte, block_bauen                          # noqa: E402
from bom_qualitaet import vergleich, EREIGNIS                      # noqa: E402
import cicese_referenz as C                                        # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
ARBEIT = '/tmp/cicese_neufit'
BESSER = 0.7

# Satzname im Bestand -> CICESE-Ordner.
ZUORDNUNG = {
    'Guerrero Negro, Baja California Sur, Mexico': 'grn',
    'Golfo de Santa Clara, Sonora, Mexico': 'gsc',
    'La Crucecita (Huatulco), Oaxaca, Mexico': 'hua',
    'Puerto Refugio (Isla Ángel de la Guarda), Baja California, Mexico': 'rfg',
    'El Sauzal, Baja California, Mexico': 'szl',
    'Isla Tiburón, Sonora, Mexico': 'tib',
}


def bloecke(zeilen):
    aus = {}
    for k, z in enumerate(zeilen):
        if not (z and not z.startswith('#') and k + 1 < len(zeilen)
                and MERIDIAN.match(zeilen[k + 1])):
            continue
        a = k
        while a > 0 and (zeilen[a - 1].startswith('#') or not zeilen[a - 1].strip()):
            a -= 1
        e = k + 3
        while e < len(zeilen) and zeilen[e].strip() and not zeilen[e].startswith('#'):
            e += 1
        aus.setdefault(z.strip(), (a, k, e))
    return aus


def messe(block, ref):
    import build_noaa_cptt as b
    os.makedirs(ARBEIT, exist_ok=True)
    bl = list(block)
    for j, z in enumerate(bl):
        if MERIDIAN.match(z) and j > 0:
            bl[j - 1] = 'PROBE'
            break
    txt, tcd = os.path.join(ARBEIT, 'p.txt'), os.path.join(ARBEIT, 'p.tcd')
    with open(txt, 'w', encoding='iso-8859-1', errors='replace') as fh:
        fh.write('\n'.join(list(b.HEADER) + bl) + '\n')
    if os.path.exists(tcd):
        os.remove(tcd)
    if subprocess.run(['build_tide_db', tcd, txt], capture_output=True).returncode:
        return None
    von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    out = subprocess.run(['tide', '-l', 'PROBE', '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c', '-z'],
                         env=dict(os.environ, HFILE_PATH=tcd),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    y = []
    for z in out.split('\n'):
        m = EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        y.append((dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return vergleich(ref, y) if y else None


def main(argv):
    schreiben = '--schreiben' in argv
    zeilen = open(TXT, encoding='iso-8859-1').read().split('\n')
    bl = bloecke(zeilen)
    st = {s['code']: s for s in C.stationen()}
    gebaut, unveraendert = [], []
    for name, code in sorted(ZUORDNUNG.items()):
        if name not in bl or code not in st:
            print(f'  fehlt: {name[:44]}')
            continue
        a, k, e = bl[name]
        s = st[code]
        jahr = C.jahresreihe(s)
        ref = C.vorhersage(s)
        if len(jahr) < 700 or len(ref) < 40:
            print(f'  zu wenig Daten: {name[:44]}')
            continue
        hub = max(h for _z, h, _x in ref) - min(h for _z, h, _x in ref)
        alt = messe(zeilen[a:e], ref)
        con, z0 = fitte(jahr, 0.0, s['lat'])
        neu = block_bauen(zeilen[a:e], con, z0, s['tafel'], C.JAHR)
        g = messe(neu, ref)
        if not g:
            print(f'  nicht messbar: {name[:44]}')
            continue
        va = alt['rms'] / hub * 100 if alt else float('nan')
        vn = g['rms'] / hub * 100
        if alt and g['rms'] < alt['rms'] * BESSER:
            gebaut.append((name, a, e, neu, va, vn, alt['rms'], g['rms'], hub))
        else:
            unveraendert.append((name, va, vn))
    for n, _a, _e, _b, va, vn, ra, rn, hub in sorted(gebaut, key=lambda x: -x[4]):
        print(f'  {va:6.2f} % ({ra*100:6.1f} cm) -> {vn:5.2f} % ({rn*100:5.1f} cm)  '
              f'bei {hub:4.2f} m Hub   {n[:40]}')
    for n, va, vn in unveraendert:
        print(f'  unveraendert: {va:6.2f} % -> {vn:6.2f} %   {n[:40]}')
    if not gebaut or not schreiben:
        if gebaut:
            print('\n(--schreiben, um sie zu uebernehmen)')
        return 0
    for n, a, e, neu, *_ in sorted(gebaut, key=lambda q: -q[1]):
        zeilen[a:e] = neu
    shutil.copy2(TXT, os.path.join(
        BACKUP, os.path.basename(TXT) + f'.vor_cicese_{dt.datetime.now():%Y%m%d_%H%M}'))
    tmp = TXT + '.neu'
    with open(tmp, 'w', encoding='iso-8859-1') as fh:
        fh.write('\n'.join(zeilen))
    os.replace(tmp, TXT)
    print(f'\n{len(gebaut)} Saetze neu gerechnet: {TXT}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
