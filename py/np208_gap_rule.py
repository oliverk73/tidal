#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3-km-Regel fuer neue ATT-Stationen (Oliver, 2026-07-02):
Bauen, wenn im Umkreis von RULE_KM nichts existiert ODER nur schlechte
Qualitaet (FES-2022, classic-1997). FES-2022 im Umkreis wird geloescht,
classic-1997 bleibt daneben bestehen.

Koordinatenbasiert gegen static/js/leaflet_markers_data.json.
Import: decide(lat, lon) -> (build: bool, fes_hits: list, reason: str)
CLI:    python3 py/np208_gap_rule.py <part2_json...>  -> Report pro Hafen
"""
import json, math, sys

RULE_KM = 3.0
MARKERS = '/home/oliver/static/js/leaflet_markers_data.json'
BAD = {'Harmonics FES2022', 'Harmonics 1997'}   # schlechte Qualitaet
FES = 'Harmonics FES2022'

def _load():
    d = json.load(open(MARKERS))
    gname = [g['name'] for g in d['groups']]
    # Stroemungsstationen zaehlen nicht als Tiden-Abdeckung
    st = [(s[1], s[2], gname[s[4]], s[0]) for s in d['stations']
          if 'Current' not in gname[s[4]]]
    return st

_ST = None

def _hav(la1, lo1, la2, lo2):
    r = math.radians
    a = (math.sin(r(la2-la1)/2)**2 +
         math.cos(r(la1))*math.cos(r(la2))*math.sin(r(lo2-lo1)/2)**2)
    return 12742.0*math.asin(math.sqrt(a))

def decide(lat, lon):
    """(build, fes_hits, reason); fes_hits = [(name, dist_km), ...]"""
    global _ST
    if _ST is None:
        _ST = _load()
    hits = [(g, n, _hav(lat, lon, a, b)) for a, b, g, n in _ST
            if abs(a-lat) < 0.06 and _hav(lat, lon, a, b) <= RULE_KM]
    good = [(g, n, d) for g, n, d in hits if g not in BAD]
    fes = [(n, round(d, 2)) for g, n, d in hits if g == FES]
    if good:
        g, n, d = min(good, key=lambda x: x[2])
        return False, fes, f'skip: {g} "{n}" {d:.2f}km'
    if hits:
        g, n, d = min(hits, key=lambda x: x[2])
        return True, fes, f'build: nur {g} "{n}" {d:.2f}km'
    return True, fes, 'build: Luecke (nichts <3km)'

def main():
    import glob
    files = sys.argv[1:]
    nb = ns = 0
    fes_del = []
    for f in files:
        for p in json.load(open(f, encoding='utf-8')):
            b, fes, why = decide(p['lat'], p['lon'])
            tag = 'BUILD' if b else 'skip '
            if b: nb += 1
            else: ns += 1
            if b and fes: fes_del += [x[0] for x in fes]
            print(f'{tag} {p["att"]:>7} {p["name"][:38]:38s} {why}')
    print(f'\n=== BUILD {nb} | skip {ns} ===')
    if fes_del:
        print('FES-2022 zu loeschen:')
        for n in sorted(set(fes_del)): print(f'  - {n}')

if __name__ == '__main__':
    main()
