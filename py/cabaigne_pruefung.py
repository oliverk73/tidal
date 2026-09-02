#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gegenprobe der tunesischen Saetze gegen ÇaBaigne.net.

Bewusst KEINE Qualitaetsmessung wie bom_/dhn_/chs_qualitaet, und darum
auch nicht so benannt: die Quelle nennt kein Amt, erklaert ihre Daten
selbst fuer nicht navigationstauglich und trifft nicht ueberall (siehe
cabaigne_referenz). Fuer Tunesien steht mit der Admiralty NP208 eine
hydrographische Quelle daneben, die hoeher wiegt.

Was dieses Werkzeug leistet: es zeigt, wo eine zweite, unabhaengige
Rechnung unseren Saetzen widerspricht. Wo beide uebereinstimmen, ist das
eine Bestaetigung; wo sie auseinandergehen, ist ein Blick angezeigt --
und dann braucht es einen dritten Zeugen, nicht diese Seite.

Deshalb schreibt es auch keine Loeschliste.

Usage: python3 py/cabaigne_pruefung.py
"""
from __future__ import annotations

import datetime as dt
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from bom_qualitaet import vergleich                                # noqa: E402
from chs_qualitaet import xtide, TCD                               # noqa: E402
import cabaigne_referenz as C                                      # noqa: E402

# Ort auf der Seite -> Satzname im Bestand, der die Position liefert.
# Nur eindeutige Zuordnungen; geraten wird nichts.
#   Carthage, Guellala, Hammamet, Kelibia, Nabeul, Sousse, Tabarka haben
#   keinen Satz im Bestand -- dort ist nichts zu pruefen.
#   Kerkennah bleibt aussen vor: dort stehen drei Saetze (Cercina, El
#   Abassia, Borj el Hsar) weit auseinander, und welchen die Seite
#   meint, sagt sie nicht.
ORTE = {
    'Ajim': 'Houmt Ajim (Djerba), Tunisia',
    'Bizerte': 'Bizerte, Tunisia',
    'Boughrara': 'Boughrara, Tunisia',
    'Gabès': 'Gabès, Tunisia',
    'Houmt Souk': 'Houmt Souk (Djerba), Tunisia',
    'Mahdia': 'Mahdia, Tunisia',
    'Monastir': 'Monastir, Tunisia',
    'Sfax': 'Sfax, Tunisia',
    'Tunis': 'La Goulette (Halq-al-Wadi), Tunisia',
}


def main(argv):
    recs = [x for x in load_records()
            if x['lat'] is not None and not x['current']]
    nach_name = {}
    for r in recs:
        nach_name.setdefault(r['name'], r)
    print(f'{"Ort":13} {"Satz":30} {"Datei":26} {"Hub Seite":>9} {"Hub Satz":>8} '
          f'{"RMS":>7} {"Versatz":>8}')
    for s in C.stationen():
        name = ORTE.get(s['code'])
        if not name or name not in nach_name:
            continue
        ref = C.vorhersage(s)
        if len(ref) < 40:
            continue
        hoch = [h for _z, h, a in ref if a == 'High']
        tief = [h for _z, h, a in ref if a == 'Low']
        hub_seite = statistics.mean(hoch) - statistics.mean(tief)
        von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        ziel = nach_name[name]
        for x in sorted(recs, key=lambda q: km(ziel, q)):
            if km(ziel, x) > 3:
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
            h2 = [h for _z, h, a in y if a.startswith('High')]
            t2 = [h for _z, h, a in y if a.startswith('Low')]
            hub_satz = (statistics.mean(h2) - statistics.mean(t2)) if h2 and t2 else 0
            print(f'  {s["code"][:12]:13} {x["name"][:30]:30} '
                  f'{os.path.basename(x["file"])[:26]:26} {hub_seite:8.3f}m '
                  f'{hub_satz:7.3f}m {g["rms"]*100:6.1f}cm {g["versatz_min"]:+7.0f}')
    print('\nDie Seite entscheidet nichts. Wo sie abweicht, braucht es einen')
    print('dritten Zeugen -- fuer Tunesien zuerst die Admiralty NP208.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
