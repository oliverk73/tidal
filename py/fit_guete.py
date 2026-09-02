#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht Saetze, deren eigene Kopfzeile einen gescheiterten Fit meldet.

Viele uTide-Saetze protokollieren im Kopf, wie gut der Ausgleich war:

    # R^2 = 0.4310, RMS error = 1.4945 m

Diese Zahl wurde beim Einspielen offenbar nie gelesen. Puerto Penasco
stand mit R^2 = 0.46 und 1.28 m im Bestand; gegen die CICESE-Tafel
gemessen lag der Satz 52 Zentimeter daneben, seine M2-Phase 195 Grad --
also fast eine halbe Tide, Hoch- und Niedrigwasser praktisch vertauscht.
Alle sechs CICESE-Saetze waren so.

Was "schlecht" heisst, haengt davon ab, wogegen gefittet wurde, und das
ist der Kern dieser Pruefung:

Gegen eine amtliche TAFEL gefittet, muss R^2 bei eins liegen. Solche
Tafeln sind selbst aus Konstituenten gerechnet und enthalten nichts als
Gezeiten -- man rechnet nur zurueck, was ein anderer vorwaerts gerechnet
hat. Alles unter 0.99 ist dort erklaerungsbeduerftig, unter 0.90 ist der
Ausgleich gescheitert.

Gegen echte MESSUNGEN gefittet, ist ein niedriges R^2 dagegen normal: im
Pegelstand steckt auch Wind, Luftdruck und Abfluss. In Cartagena oder
Bocas del Toro ist der Tidenhub klein und das Wetter gross. Erst unter
0.50 lohnt das Hinsehen, und auch dann ist es kein Urteil.

R^2 ist ausserdem einheitenlos und sagt nichts ueber den absoluten
Fehler. Es ist ein Verdachtsmoment, kein Befund -- entschieden wird
gegen eine Tafel, in Prozent des Tidenhubs.

Zeilen, die auf "(galt bis ...)" enden, beschreiben einen Fit, der
inzwischen ersetzt wurde, und werden uebergangen.

Usage: python3 py/fit_guete.py [--tafel 0.99] [--messung 0.50] [--alle]
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import active_files, ROOT, MERIDIAN              # noqa: E402

WERT = re.compile(r'#\s*R\^2 = ([\d.]+), RMS error = ([\d.]+) m')
VERALTET = re.compile(r'galt bis \d{8}')
# Woran erkennt man einen Fit gegen eine gerechnete Tafel? An seiner
# Quellenangabe. Alles andere gilt als Messung -- im Zweifel milder.
TAFEL = ('tide table', 'tide tables', 'tide predictions', 'tidetimes',
         'HW/LW pred', 'Tide Table', 'tide-table')


def saetze(pfad):
    l = open(pfad, encoding='iso-8859-1', errors='replace').read().split('\n')
    r2 = rms = quelle = None
    for k, z in enumerate(l):
        m = WERT.match(z.strip())
        if m and not VERALTET.search(z):
            r2, rms = float(m.group(1)), float(m.group(2))
        if z.startswith('# source:'):
            quelle = z[9:].strip()
        if (z and not z.startswith('#') and k + 1 < len(l)
                and MERIDIAN.match(l[k + 1])):
            if r2 is not None:
                yield r2, rms, z.strip(), quelle or ''
            r2 = rms = quelle = None


def main(argv):
    g = lambda n, v: (float(argv[argv.index(n) + 1]) if n in argv else v)
    s_tafel, s_messung = g('--tafel', 0.99), g('--messung', 0.50)
    alle = '--alle' in argv
    ges = auff = 0
    for rel in active_files():
        treffer = []
        for r2, rms, name, quelle in saetze(os.path.join(ROOT, rel)):
            ges += 1
            ist_tafel = any(t.lower() in quelle.lower() for t in TAFEL)
            grenze = s_tafel if ist_tafel else s_messung
            if r2 < grenze:
                treffer.append((r2, rms, name, quelle, 'Tafel' if ist_tafel else 'Messung'))
        if not treffer:
            continue
        auff += len(treffer)
        print(f'\n{os.path.basename(rel)}: {len(treffer)} auffaellig')
        for r2, rms, name, quelle, art in sorted(treffer)[:None if alle else 15]:
            print(f'   R2={r2:.3f} RMS={rms:6.3f} m  {art:7} {name[:40]:40} '
                  f'{quelle[:38]}')
        if not alle and len(treffer) > 15:
            print(f'   ... und {len(treffer) - 15} weitere (--alle)')
    print(f'\n{ges} Saetze mit protokolliertem R^2, {auff} auffaellig '
          f'(Tafel unter {s_tafel}, Messung unter {s_messung})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
