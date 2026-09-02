#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Datensaetze gegen die Tafeln des chilenischen SHOA.

Wie shn_qualitaet fuer Argentinien, nur mit weniger Massstab: von den
40 Orten, die der SHOA veroeffentlicht, liegen 20 vor -- die uebrigen
sind nicht abrufbar (siehe shoa_referenz). Acht der 20 sind
Antarktisstationen, fuer die es sonst kaum eine Pruefmoeglichkeit gibt.

Verglichen wird der ganze gespeicherte Zeitraum (Mai bis Juli 2026), da
er ohnehin vorliegt; drei Monate tragen den Vergleich sicherer als
einer.

Usage: python3 py/shoa_qualitaet.py [--km 3] > harmonics/help/shoa_qualitaet.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                          # noqa: E402
from bom_qualitaet import vergleich                                # noqa: E402
from chs_qualitaet import xtide, TCD                               # noqa: E402
import shoa_referenz as H                                          # noqa: E402


def main(argv):
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else 3.0
    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    liste = H.stationen()
    print(f'{len(liste)} SHOA-Orte, Umkreis {umkreis:.0f} km', file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m',
                'n', 'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m'])
    for s in liste:
        ref = H.vorhersage(s)
        if len(ref) < 40:
            print(f'  {s["name"][:40]}: nur {len(ref)} Ereignisse', file=sys.stderr)
            continue
        hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
        von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        ziel = {'lat': s['lat'], 'lon': s['lon']}
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
            w.writerow([s['name'], f"{s['lat']:.4f}", f"{s['lon']:.4f}", 2026,
                        x['name'], os.path.basename(x['file']), round(d * 1000),
                        g['n'], round(g['rms'], 4), round(g['max'], 3),
                        round(g['zeit_med'], 1), round(g['hoehe_off'], 3),
                        round(hub, 3)])
            sys.stdout.flush()
        print(f'  {s["name"][:44]}', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
