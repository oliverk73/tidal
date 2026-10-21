#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meldet Saetze, deren Region (Bundesstaat/Provinz) im Namen nicht zur Position passt (Oliver 21.10.2026).

Anlass: "Clump, South Australia" lag in Queensland. Wie py/land_gegen_position.py, eine Ebene tiefer:
Region = vorletztes Namensglied (US-Namen: letztes, der Staat). Gemeldet wird nur, wenn die Region
im Namen als Natural-Earth-admin-1 desselben Landes erkannt wird UND deutlich weiter weg ist als die
naechste Region dieses Landes (mehr als ABSTAND_KM). Unbekannte Regionsnamen (andere Schreibung,
Gattungswoerter) werden nicht gemeldet, nur gezaehlt.

Aufruf: venv/bin/python py/region_gegen_position.py   -> harmonics/help/region_gegen_position.csv
"""
from __future__ import annotations

import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import region_felder_fuellen as RF                                   # noqa: E402
from health_check import load_records                                # noqa: E402

AUS = os.path.join(RF.HELP, 'region_gegen_position.csv')
ABSTAND_KM = 25.0
SUCH_KM = 400.0
# Bestandsschreibung -> Natural Earth (nur wo NE anders heisst)
ALIAS = {'yamalo-nenets': 'yamal-nenets'}
GATTUNG = (' autonomous okrug', ' oblast', ' krai', ' kray', ' republic', ' province', ' prefecture', ' region',
           ' state', ' territory', ' governorate', ' county', ' department', ' district')


def glieder(name):
    t = [s.strip() for s in name.replace(' Current', '').split(',') if s.strip()]
    if len(t) >= 2 and RF._flach(t[-1]) in RF.US_STAATEN:
        return t[-1], 'United States'
    if len(t) >= 3:
        return t[-2], t[-1]
    return None, None


def _kern(s):
    s = RF._flach(s)
    for g in GATTUNG:
        if s.endswith(g):
            s = s[:-len(g)]
    return ALIAS.get(s, s)


def gleich(a, b):
    return _kern(a) == _kern(b)


def main(argv):
    polys = RF.polygone()
    pro_land = collections.defaultdict(list)
    for p in polys:
        pro_land[RF._flach(RF.LAND_ALIAS.get(p[0], p[0]))].append(p)
    zeilen, unbekannt = [], collections.Counter()
    for r in load_records():
        if r['lat'] is None:
            continue
        reg, land = glieder(r['name'])
        if not reg:
            continue
        fl = RF._flach(RF.BESTAND_ALIAS.get(RF._flach(land), land))
        P = pro_land.get(fl)
        if not P:
            continue
        eigen = [p for p in P if gleich(reg, p[1])]
        if not eigen:
            unbekannt[(land, reg)] += 1
            continue
        drin = RF.welches(r['lon'], r['lat'], P)
        naechst = drin or RF.naechstes(r['lon'], r['lat'], P, SUCH_KM)
        if not naechst or gleich(reg, naechst[1]):
            continue
        e = RF.naechstes(r['lon'], r['lat'], eigen, 5000.0)
        if e and e[3] <= naechst[3] + ABSTAND_KM:
            continue
        zeilen.append(dict(name=r['name'], datei=r['file'], lat=f"{r['lat']:.4f}", lon=f"{r['lon']:.4f}",
                           region_im_namen=reg, km_dorthin='' if not e else f'{e[3]:.0f}',
                           liegt_in=naechst[1], km=f'{naechst[3]:.1f}'))
    zeilen.sort(key=lambda z: (z['liegt_in'], z['name']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]) if zeilen else ['name'])
        w.writeheader()
        w.writerows(zeilen)
    for z in zeilen:
        print('%-60s %-28s -> %-24s (%s km / %s km)  %s' % (z['name'][:60], z['region_im_namen'][:28], z['liegt_in'][:24],
                                                           z['km'], z['km_dorthin'], z['datei'].split('/')[-1][:30]))
    print(len(zeilen), 'Saetze ->', AUS)
    print('unbekannte Regionsnamen (nicht geprueft):', sum(unbekannt.values()), 'Saetze,',
          len(unbekannt), 'Namen; haeufigste:', unbekannt.most_common(12))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
