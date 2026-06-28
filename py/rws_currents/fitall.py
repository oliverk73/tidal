#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fittet die 3 reparierten Bestandsstationen + alle GAP_*.csv mit fit2.fit().
Schreibt results.json (kein Harmonics-Write) + Tabelle."""
import json, glob, os, sys
sys.path.insert(0, '/home/oliver/py/rws_currents')
from fit2 import fit

CD = '/home/oliver/currents/Netherlands'
meta = json.load(open(f'{CD}/_stations.json'))

# extra Meta fuer 2026-Neustationen ohne _stations.json-Eintrag
EXTRA = {
 'dantziggat.pietscheveplaat.zuid': {'name': 'Dantziggat', 'lat': 53.380, 'lon': 5.795},
 'holwerd.vaargeul': {'name': 'Holwerd Vaargeul', 'lat': 53.398, 'lon': 5.882},
}

REPAIR = ['eemshaven.waddenzee', 'ijgeul.1', 'ijmuiden.stroommeetpaal.backup']

jobs = []
for c in REPAIR:
    jobs.append((c, f'{CD}/{c}.csv', 'repair'))
for p in sorted(glob.glob(f'{CD}/GAP_*.csv')):
    c = os.path.basename(p)[4:-4]
    jobs.append((c, p, 'gap'))

results = []
for code, path, kind in jobs:
    m = meta.get(code) or EXTRA.get(code) or {'name': code, 'lat': 52.0, 'lon': 4.0}
    try:
        r = fit(path, m['lat'], m['name'], code)
    except Exception as e:
        r = {'code': code, 'name': m['name'], 'error': repr(e)[:80]}
    r['kind'] = kind
    r['lon'] = m['lon']
    results.append(r)
    if 'error' in r:
        print(f"{kind:6s} {code:38s} FEHLER: {r['error']}", flush=True)
    else:
        conf = 8 if r['r2'] >= 0.7 else (5 if r['r2'] >= 0.4 else 0)
        print(f"{kind:6s} {r['name']:30s} R²={r['r2']:.3f} M2={r['m2']:.3f}kn "
              f"axis={r['axis']:.0f}° n={r['n']} [{r['t0']}..{r['t1']}] -> conf {conf or 'DROP'}", flush=True)

# cm dict ist nicht JSON-serialisierbar pur? ist dict[str]->tuple -> ok als list
for r in results:
    if 'cm' in r:
        r['cm'] = {k: list(v) for k, v in r['cm'].items()}
json.dump(results, open('/home/oliver/py/rws_currents/results.json', 'w'))
print('FITALL FERTIG', flush=True)
