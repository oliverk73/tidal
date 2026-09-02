#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Datensaetze gegen die Gezeitentafeln des argentinischen SHN.

Wie chs_qualitaet fuer Kanada und dhn_qualitaet fuer Brasilien. Der
Massstab sind die 66 Stationen des Servicio de Hidrografia Naval, deren
Reihen fuer 2024 und 2025 vorliegen -- 38 als Hoch- und Niedrigwasser,
28 als Stundenwerte, aus denen shn_referenz die Scheitel rechnet.

Im Kasten Argentinien stehen 443 Saetze, 145 davon aus harmonics_noaa_amtt
und 81 aus der Admiralty-Tafel NP207. Welcher von zwei Nachbarn der
bessere ist, liess sich hier bisher nicht entscheiden.

Der Vorbehalt aus Kanada gilt auch hier: wo ein Satz aus eben diesen
SHN-Daten gefittet wurde, ist ein gutes Ergebnis zum Teil zirkulaer. Was
die Messung unverzerrt zeigt, ist der Abstand des Altbestands zur
amtlichen Vorhersage -- und darum geht es beim Aufraeumen.

Gerechnet wird durchweg in UTC. Ein gefundener Zeitversatz gehoert
deshalb dem Datensatz und nicht der Zonenwahl.

Usage: python3 py/shn_qualitaet.py [--km 3] > harmonics/help/shn_qualitaet.csv
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
import shn_referenz as S                                           # noqa: E402


def main(argv):
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else 3.0
    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    liste = S.stationen()
    print(f'{len(liste)} SHN-Stationen, Umkreis {umkreis:.0f} km, '
          f'Vergleichsmonat {S.VON:%Y-%m}', file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m',
                'n', 'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m', 'art'])
    for i, s in enumerate(liste, 1):
        ref = S.vorhersage(s)
        if len(ref) < 40:
            print(f'  {s["code"]}: nur {len(ref)} Ereignisse, uebersprungen',
                  file=sys.stderr)
            continue
        hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
        von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        art = 'stuendlich' if S.stuendlich(s) else 'HW/NW'
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
            w.writerow([s['name'], f"{s['lat']:.4f}", f"{s['lon']:.4f}",
                        S.VON.year, x['name'], os.path.basename(x['file']),
                        round(d * 1000), g['n'], round(g['rms'], 4),
                        round(g['max'], 3), round(g['zeit_med'], 1),
                        round(g['hoehe_off'], 3), round(hub, 3), art])
            sys.stdout.flush()
        print(f'  {i}/{len(liste)}  {s["code"]}', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
