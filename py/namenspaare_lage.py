#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entscheidet [B]-Faelle des health_check ueber die Landmaske.

Der health_check meldet unter [B] Saetze, die denselben Namen tragen,
dieselbe Kurve haben und trotzdem weit auseinander stehen. Wo die
Kurven auf null bis zwei Prozent uebereinstimmen, ist es derselbe
Pegel -- dann muss eine der beiden Positionen falsch sein, und die
Frage ist nur, welche.

Oft entscheidet das die Landmaske: ein Pegel liegt nicht 25 Kilometer
im Landesinneren. Dieses Werkzeug misst fuer beide Positionen den
Abstand zum Wasser und den zum naechsten anderen Pegel und stellt sie
nebeneinander.

Der Anlass war, dass 1304 Eintraege aus lage_ausreisser zu viele sind,
um sie von Hand durchzusehen. Die [B]-Liste ist mit fuenfzehn Faellen
kurz genug -- und sie enthaelt die groben Fehler, waehrend die lange
Liste von Rundungen beherrscht wird: von neunzehn Korrekturen in den
ersten vierzig Eintraegen betrafen siebzehn weniger als zwei Kilometer.

Usage: python3 py/namenspaare_lage.py [--km 25]
"""
from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, curve_diff               # noqa: E402
from lage_ausreisser import ozean_abstand                           # noqa: E402


def main(argv):
    weit = float(argv[argv.index('--km') + 1]) if '--km' in argv else 25.0
    recs = [r for r in load_records() if r['lat'] is not None]
    nach = collections.defaultdict(list)
    for r in recs:
        nach[r['name']].append(r)
    paare = []
    for name, g in nach.items():
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                d = km(g[i], g[j])
                if d < weit:
                    continue
                _, rel = curve_diff(g[i], g[j])
                paare.append((d, rel, g[i], g[j]))
    paare.sort(key=lambda x: (x[1], -x[0]))
    print(f'{len(paare)} Namenspaare weiter als {weit:.0f} km auseinander\n')
    print(f'{"Abstand":>8} {"Kurve":>6}  {"A: Wasser":>9} {"Pegel":>7}  '
          f'{"B: Wasser":>9} {"Pegel":>7}  Name')
    for d, rel, a, b in paare:
        oa, ob = ozean_abstand(a['lat'], a['lon']), ozean_abstand(b['lat'], b['lon'])

        def nachbar(x):
            w = sorted(km(x, y) for y in recs if km(x, y) > 0.3)
            return w[0] if w else float('inf')

        urteil = ''
        if rel < 0.05:
            if oa >= 5 and ob < 5:
                urteil = '  -> A liegt im Landesinneren'
            elif ob >= 5 and oa < 5:
                urteil = '  -> B liegt im Landesinneren'
        print(f'{d:7.0f}km {rel*100:5.0f}%  {oa:7.0f}km {nachbar(a):6.1f}km  '
              f'{ob:7.0f}km {nachbar(b):6.1f}km  {a["name"][:34]}{urteil}')
        if urteil:
            print(f'{"":26}A {a["lat"]:8.4f} {a["lon"]:10.4f} [{os.path.basename(a["file"])[:24]}]')
            print(f'{"":26}B {b["lat"]:8.4f} {b["lon"]:10.4f} [{os.path.basename(b["file"])[:24]}]')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
