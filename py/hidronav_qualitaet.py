#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Datensaetze gegen die Tafeln der peruanischen HIDRONAV.

Wie shn_qualitaet fuer Argentinien und shoa_qualitaet fuer Chile.
Massstab sind 25 Haefen mit je zwei Monaten (Juni und Juli 2026); der
ebenfalls vorliegende Juni 2024 bleibt aussen vor, damit der Vergleich
einen zusammenhaengenden Zeitraum sieht.

Peru ist die letzte grosse Luecke an der Westkueste Suedamerikas: im
Kasten stehen rund 50 Saetze, fast alle aus harmonics_noaa_amtt und der
1997er Datenbank, und bisher gab es nichts, woran sie zu pruefen waren.

Usage: python3 py/hidronav_qualitaet.py [--km 3] > harmonics/help/hidronav_qualitaet.csv
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
import hidronav_referenz as P                                      # noqa: E402


def main(argv):
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else 3.0
    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    liste = P.stationen()
    print(f'{len(liste)} HIDRONAV-Haefen, Umkreis {umkreis:.0f} km', file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m',
                'n', 'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m'])
    for s in liste:
        ref = P.vorhersage(s)
        if len(ref) < 40:
            print(f'  {s["code"]}: nur {len(ref)} Ereignisse', file=sys.stderr)
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
        print(f'  {s["code"]}', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
