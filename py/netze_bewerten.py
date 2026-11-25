#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geladene Netz-Reihen (py/netze_laden.py) fuer die Revierauswahl bewerten (25.11.2026).

Je Station: Stunden 9-19 Uhr Sonnenzeit in Mai-Sep je Jahr, Mittel, Stunden >= 12 kn, naechster OSM-Spot.
    venv/bin/python py/netze_bewerten.py smhi,dwd_synop,rws  -> harmonics/help/netze_kandidaten.csv
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, 'quellen', 'thermik')
AUS = os.path.join(ROOT, 'harmonics', 'help', 'netze_kandidaten.csv')


def main(argv):
    netze = argv[0].split(',')
    kat = pd.read_csv(os.path.join(Q, 'spotsuche', 'stationen_alle.csv'), dtype={'id': str})
    e = json.load(open(os.path.join(Q, 'spotsuche', 'osm_spots.json')))['elements']
    sla = np.array([x.get('lat') or x.get('center', {}).get('lat') for x in e], float)
    slo = np.array([x.get('lon') or x.get('center', {}).get('lon') for x in e], float)
    snam = [(x.get('tags') or {}).get('name') or '' for x in e]
    z = []
    for _, s in kat[kat['netz'].isin(netze)].iterrows():
        p = os.path.join(Q, s['netz'], '%s.csv' % s['id'])
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        if not len(d):
            continue
        t = pd.to_datetime(d['t'].str.rstrip('Z'))
        h = d.set_index(t)['kn'].resample('1h').mean().dropna()
        sonne = (h.index + pd.to_timedelta(s['lon'] / 15, 'h')).hour
        tag = h[(sonne >= 9) & (sonne <= 18)]
        if not len(tag):
            continue
        k = 12742 * np.arcsin(np.sqrt(np.sin(np.radians(sla - s['lat']) / 2) ** 2 + np.cos(np.radians(s['lat'])) *
                                      np.cos(np.radians(sla)) * np.sin(np.radians(slo - s['lon']) / 2) ** 2))
        i = int(np.nanargmin(k))
        jahre = tag.groupby(tag.index.year)
        z.append(dict(netz=s['netz'], id=s['id'], name=s['name'], lat=s['lat'], lon=s['lon'],
                      jahre=' '.join(str(j) for j, g in jahre if len(g) > 500),
                      stunden_2026=int((tag.index.year == 2026).sum()), mittel_kn=round(tag.mean(), 1),
                      h12_je_jahr=int(round((tag >= 12).sum() / max(1, jahre.ngroups))),
                      h15_je_jahr=int(round((tag >= 15).sum() / max(1, jahre.ngroups))),
                      spot_km=round(float(k[i]), 1), spot=snam[i]))
    b = pd.DataFrame(z).sort_values('h12_je_jahr', ascending=False)
    b.to_csv(AUS, index=False)
    print(b.to_string(index=False, max_colwidth=28))
    print('->', os.path.relpath(AUS, ROOT), len(b))


if __name__ == '__main__':
    main(sys.argv[1:])
