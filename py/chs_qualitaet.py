#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Datensaetze gegen die Vorhersagen des CHS (Kanada).

Wie dhn_qualitaet fuer Brasilien und bom_qualitaet fuer Australien, nur
ohne Papier: die CHS-Schnittstelle liefert Hoch- und Niedrigwasser schon
in UTC und mit Position. Ein gefundener Zeitversatz gehoert deshalb dem
Datensatz, nicht der Zonenwahl.

Kanada ist der groesste Posten im Bestand -- gut 2300 Saetze -- und
stellt zugleich ein Drittel der offenen Nachbarschaftsfaelle des
health_check. Fast alle davon sind Altbestand (die XTide-Datenbank von
2004, NOAA AMTT) neben neueren, aus CHS gefitteten Saetzen; welcher der
bessere ist, liess sich bisher nicht entscheiden.

Ein Vorbehalt gehoert dazu: die neueren Saetze sind aus eben diesen
CHS-Vorhersagen gefittet. Dass sie hier gut abschneiden, ist deshalb
teilweise zirkulaer und kein Beleg ihrer Guete. Was die Messung wirklich
zeigt, ist die andere Haelfte -- wie weit der Altbestand von der
amtlichen Vorhersage abweicht -- und genau darum geht es beim
Aufraeumen. Wo zwei Saetze konkurrieren, die beide nicht aus CHS
stammen, ist der Vergleich unverzerrt.

Usage: python3 py/chs_qualitaet.py [--km 3] [--max N] > <ausgabe.csv>
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT                    # noqa: E402
from bom_qualitaet import vergleich, EREIGNIS                      # noqa: E402
from dhn_qualitaet import art_bestimmen                            # noqa: E402
import chs_referenz as C                                           # noqa: E402

TCD = '/usr/share/xtide'


def xtide(tcd, name, von, bis):
    out = subprocess.run(['tide', '-l', name, '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c', '-z'],
                         env=dict(os.environ, HFILE_PATH=os.path.join(TCD, tcd)),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    ev = []
    for z in out.split('\n'):
        m = EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        ev.append((dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return ev


def main(argv):
    umkreis = 3.0
    if '--km' in argv:
        umkreis = float(argv[argv.index('--km') + 1])
    grenze = int(argv[argv.index('--max') + 1]) if '--max' in argv else None

    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    liste = [s for s in C.stationen()
             if os.path.exists(C._datei(s['code']))]
    if grenze:
        liste = liste[:grenze]
    print(f'{len(liste)} CHS-Stationen mit Vorhersage, Umkreis {umkreis:.0f} km',
          file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m',
                'n', 'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m'])
    for i, s in enumerate(liste, 1):
        roh = C.vorhersage(s)
        if len(roh) < 40:
            continue
        ref = art_bestimmen(roh)
        if len(ref) < 40:
            continue
        hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
        von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
        ziel = {'lat': s['latitude'], 'lon': s['longitude']}
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
            w.writerow([s['officialName'], f"{s['latitude']:.4f}",
                        f"{s['longitude']:.4f}", 2026, x['name'],
                        os.path.basename(x['file']), round(d * 1000), g['n'],
                        round(g['rms'], 4), round(g['max'], 3),
                        round(g['zeit_med'], 1), round(g['hoehe_off'], 3),
                        round(hub, 3)])
            sys.stdout.flush()
        if i % 100 == 0:
            print(f'  {i}/{len(liste)}', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
