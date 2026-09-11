#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meldet Saetze, deren Land im Namen nicht zur Position passt.

Erste Fassung als einmalige Rechnung am 07.09.2026 (Commit 5584e33),
als Werkzeug am 11.09.2026 -- die Liste war da schon zu 64 von 158 Zeilen
veraltet, weil Saetze inzwischen umbenannt oder geloescht waren.

Verglichen wird mit Natural Earth admin-1 (harmonics/help/ne_admin1_welt.json,
siehe py/region_felder_fuellen.py): Liegt der Satz in einem Polygon oder
nahe an einem Ufer, und ist das im Namen genannte Land DEUTLICH weiter weg
(mehr als ABSTAND_KM), wird er gemeldet. Nur "liegt nicht im genannten
Polygon" reicht nicht -- fast jeder Pegel steht im Wasser, und dann faellt
Macuro (Venezuela, als Trinidad benannt) durch.

Entscheidungen aus einer vorhandenen Liste (Spalte "entscheidung") bleiben
erhalten.

Aufruf: python3 py/land_gegen_position.py      -> harmonics/help/land_gegen_position2.csv
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as RF                                   # noqa: E402
from health_check import load_records                                # noqa: E402

AUS = os.path.join(RF.HELP, 'land_gegen_position2.csv')
ABSTAND_KM = 15.0
SUCH_KM = 60.0


# Natural Earth fuehrt diese Gebiete als eigenes admin; der Bestand nennt sie
# mit ihrem eigenen Namen ("Ponce, Puerto Rico") oder dem Mutterstaat
# ("Unnamed Cay, Queensland, Australia"). Beides ist richtig.
GEBIET = {'coral sea islands': 'australia', 'heard island and mcdonald islands': 'australia',
          'ashmore and cartier islands': 'australia', 'norfolk island': 'australia',
          'puerto rico': 'united states', 'guam': 'united states',
          'northern mariana islands': 'united states', 'american samoa': 'united states',
          'united states virgin islands': 'united states', 'us virgin islands': 'united states',
          'united states minor outlying islands': 'united states', 'usa': 'united states'}


def passt(admin, land):
    if RF._passt(admin, land):
        return True
    a, l = RF._flach(admin), RF._flach(land)
    return a == l or GEBIET.get(a) == l or GEBIET.get(l) == a or \
        (GEBIET.get(a) and GEBIET.get(a) == GEBIET.get(l))


def land_im_namen(name):
    teile = [t.strip() for t in name.replace(' Current', '').split(',') if t.strip()]
    return teile[-1] if len(teile) >= 2 else None


def main(argv):
    polys = RF.polygone()
    bekannt = {RF._flach(RF.LAND_ALIAS.get(a, a)) for a, _n, _t, _p in polys}
    alt = {}
    if os.path.exists(AUS):
        for r in csv.DictReader(open(AUS, encoding='utf-8')):
            if (r.get('entscheidung') or '').strip():
                alt[(r['datei'], r['name'])] = r['entscheidung']
    zeilen = []
    for r in load_records():
        if r['lat'] is None:
            continue
        land = land_im_namen(r['name'])
        if not land:
            continue
        fl = RF._flach(RF.BESTAND_ALIAS.get(RF._flach(land), land))
        if fl not in bekannt and fl not in RF.US_STAATEN and fl not in GEBIET:
            continue                          # Name ohne erkennbares Land
        drin = RF.welches(r['lon'], r['lat'], polys)
        naechst = drin or RF.naechstes(r['lon'], r['lat'], polys, SUCH_KM)
        if not naechst or passt(naechst[0], land):
            continue
        d_any = naechst[3]
        zu = [p for p in polys if passt(p[0], land)]
        eigen = RF.naechstes(r['lon'], r['lat'], zu, d_any + ABSTAND_KM)
        if eigen:
            continue                          # genanntes Land ist nicht deutlich weiter weg
        eigen = RF.naechstes(r['lon'], r['lat'], zu, 3000.0)
        zeilen.append(dict(
            name=r['name'], datei=r['file'], lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}",
            land_im_namen=land, km_zum_genannten='' if not eigen else f'{eigen[3]:.1f}',
            liegt_in=RF.LAND_ALIAS.get(naechst[0], naechst[0]), km_dorthin=f'{d_any:.1f}',
            region=naechst[1], entscheidung=alt.get((r['file'], r['name']), '')))
    zeilen.sort(key=lambda z: (z['liegt_in'], z['name']))
    with open(AUS + '.neu', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'datei', 'lat', 'lon', 'land_im_namen',
                                           'km_zum_genannten', 'liegt_in', 'km_dorthin',
                                           'region', 'entscheidung'])
        w.writeheader()
        w.writerows(zeilen)
    if '--probe' in argv:
        print(f'{len(zeilen)} Saetze (Probe, nicht geschrieben) -> {AUS}.neu')
    else:
        os.replace(AUS + '.neu', AUS)
        print(f'{len(zeilen)} Saetze -> {AUS}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
