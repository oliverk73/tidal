#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stromsaetze nach markanten Punkten VOR ORT benennen (Oliver 14.11.2026).

Anlass: "Pedder Bay (4 km SSE)" lag genau auf Race Rocks, "Gordon Head (12 km ENE)" 200 m vor Lime Kiln Point
(San Juan Island) -- Bezug auf ferne Orte statt aussagekraeftiger Namen direkt vor Ort.
Quelle: GeoNames (offline, englische Namen, Provinz): currents/strom_landmarken_geonames.json (Leuchttuerme LTHSE,
Kaps/Spitzen CAPE/PT, Felsen/Riffe RK/RKS/RF/SHOL, Inseln ISL/ISLET/ISLS, Halbinsel PEN; Gewaesser STRT/CHN/INLT/SD/
HBR/BAY/NRWS/PASS/FJD). Overpass war fuer BC zu langsam (4 Saetze in 30 min) und lieferte Inuktitut-Namen.
Name: Landmarke bis 1 km (Vorrang Leuchtturm > Kap/Spitze > Felsen > Inselchen > Insel) -> "Landmarke (Kontext)";
1-2,5 km -> "Landmarke (x km RICHTUNG, Kontext)". Kontext: Insel bis 6 km (Kap, Spitze, Leuchtturm, Felsen) sonst
Gewaesser bis 5 km; ohne Landmarke, aber Gewaesser bis 4 km -> "Gewaesser (Landmarke bis 5 km)"; sonst bleibt der Name.
Nur Saetze aus der Liste --namen (automatisch erzeugte Namen; Olivers Namen bleiben).

Usage: venv/bin/python py/strom_namen_vorort.py --namen LISTE [--schreiben]   -> harmonics/help/strom_namen_vorort.csv
"""
import csv
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIEL = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_current_observations.txt')
LM = os.path.join(ROOT, 'currents/strom_landmarken_geonames.json')
RICHTUNG = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
PUNKT = {'LTHSE': 0, 'CAPE': 1, 'PT': 1, 'PTS': 1, 'PEN': 2, 'RKS': 3, 'RK': 3, 'RF': 3, 'SHOL': 4, 'ISLET': 5, 'ISLS': 6, 'ISL': 7}
WASSER = {'STRT', 'CHN', 'CHNM', 'INLT', 'SD', 'HBR', 'BAY', 'NRWS', 'PASS', 'FJD'}
GEN = {'island', 'islands', 'islet', 'rock', 'rocks', 'point', 'head', 'cape', 'great', 'little', 'north', 'south', 'east',
       'west', 'the', 'of', 'light', 'lighthouse'}


def km(a, b, c, d):
    return 111.2 * math.hypot(a - c, (b - d) * math.cos(math.radians(a)))


def richtung(la, lo, rla, rlo):
    az = math.degrees(math.atan2((lo - rlo) * math.cos(math.radians(la)), la - rla)) % 360
    return RICHTUNG[int((az + 11.25) % 360 // 22.5)]


def worte(t):
    return {x.lower() for x in re.findall(r'\w+', t)} - GEN


def vorschlag(la, lo, L):
    nah = sorted((km(la, lo, a, b), n, c, a, b, t) for n, a, b, c, t in L if abs(a - la) < 0.2 and abs(b - lo) < 0.4)
    lm = [x for x in nah if x[2] in PUNKT and x[0] <= 2.5 and not (x[2] == 'ISL' and x[0] > 1.0)]
    n1 = sorted([x for x in lm if x[0] <= 1.0], key=lambda x: (PUNKT[x[2]], x[0]))
    if n1:
        lm = n1 + [x for x in lm if x not in n1]

    def kurz(x):
        """Leuchtturm -> gleichnamige Spitze/Kap bis 0,5 km ('Lime Kiln' -> 'Lime Kiln Point'), sonst ohne 'Lighthouse'."""
        n = x[1]
        if x[2] == 'LTHSE':
            sp = [y for y in nah if y[2] in ('CAPE', 'PT') and km(x[3], x[4], y[3], y[4]) <= 0.5 and worte(y[1]) & worte(n)]
            n = sp[0][1] if sp else re.sub(r'\s+(Lighthouse|Light Station|Light)$', '', n)
        return n
    # 1. enge Passage bis 2 km: 'Hawkins Narrows (Davenport Point)' -- ausser ein Leuchtturm steht bis 1 km (Race Rocks)
    eng = [x for x in nah if x[2] in ('NRWS', 'PASS', 'CHN', 'CHNM', 'STRT') and x[0] <= 2.0]
    if lm and lm[0][2] == 'LTHSE' and lm[0][0] <= 1.0:
        eng = []
    if eng:
        ref = [x for x in lm if not (worte(x[1]) & worte(eng[0][1]))]
        if not ref and eng[0][2] == 'STRT':                         # breite Strasse ohne Bezugspunkt sagt nichts
            eng = []
    if eng:
        return '%s%s, %s Current' % (eng[0][1], (' (%s)' % kurz(ref[0])) if ref else '', eng[0][5])
    # 2. Landmarke bis 2,5 km
    if lm:
        x = lm[0]
        d, _n, c, a, b, tail = x
        n = kurz(x)
        ctx = [] if d <= 1.0 else ['%d km %s' % (max(1, round(d)), richtung(la, lo, a, b))]
        insel = [y for y in nah if y[2] == 'ISL' and 'Island' in y[1] and km(a, b, y[3], y[4]) <= 10 and not (worte(y[1]) & worte(n))]
        insel.sort(key=lambda y: km(a, b, y[3], y[4]))
        ww = [y for y in nah if y[2] in WASSER and y[0] <= 5 and not (worte(y[1]) & worte(n))]
        # Inselkontext aus GeoNames unzuverlaessig (Inselmittelpunkte: 'Lime Kiln Point (Low Island)') -> nur Gewaesser
        if ww:
            ctx.append(ww[0][1])
        return '%s%s, %s Current' % (n, (' (%s)' % ', '.join(ctx)) if ctx else '', tail)
    # 3. benanntes Gewaesser bis 4 km: 'Juan de Fuca Strait (Sheringham Point 11 km SSW)'
    ww = [x for x in nah if x[2] in WASSER and x[0] <= 4]
    if ww:
        ref = [x for x in nah if x[2] in ('LTHSE', 'CAPE', 'PT', 'PTS', 'RKS') and x[0] <= 15]
        r = ('%s %d km %s' % (kurz(ref[0]), max(1, round(ref[0][0])), richtung(la, lo, ref[0][3], ref[0][4]))) if ref else ''
        if r:
            return '%s (%s), %s Current' % (ww[0][1], r, ww[0][5])
    return None


HAND = {'Pedder Bay (4 km SSE), British Columbia, Canada Current': 'Race Rocks, British Columbia, Canada Current',
        'Gordon Head (12 km ENE), British Columbia, Canada Current': 'Lime Kiln Point (San Juan Island), Washington Current'}


def main(argv):
    namen = [l.strip() for l in open(argv[argv.index('--namen') + 1], encoding='utf-8') if l.strip()]
    T = open(ZIEL, encoding='iso-8859-1').read()
    alle = set(re.findall(r'^([^#\n].* Current)$', T, re.M))
    zeilen = []
    L = json.load(open(LM, encoding='utf-8'))
    for alt in namen:
        i = T.find('\n' + alt + '\n')
        if i < 0:
            print('nicht gefunden:', alt)
            continue
        kopf = T[T.rfind('\n#\n', 0, i):i]
        la = float(re.search(r'!latitude: (\S+)', kopf).group(1))
        lo = float(re.search(r'!longitude: (\S+)', kopf).group(1))
        if alt in HAND:                                                # Olivers Namen (14.11.)
            zeilen.append(dict(alt=alt, neu=HAND[alt], lat=0, lon=0))
            alle.add(HAND[alt])
            print('%-62s -> %s (Oliver)' % (alt[:62], HAND[alt]))
            continue
        m = re.search(r'\((\d+) km ', alt)
        neu = vorschlag(la, lo, L) if m and int(m.group(1)) >= 3 else None   # nur echte Fernbezuege (>= 3 km)
        if neu and neu != alt:
            if neu in alle:
                neu = neu.replace(' Current', ' (IOS) Current' if '# ios_file' in kopf else ' (NCEI) Current')
            alle.add(neu)
        zeilen.append(dict(alt=alt, neu=neu if neu and neu != alt else '', lat=la, lon=lo))
        print('%-62s -> %s' % (alt[:62], neu or '(bleibt)'), flush=True)
    with open(os.path.join(ROOT, 'harmonics/help/strom_namen_vorort.csv'), 'w', newline='', encoding='utf-8') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        wr.writeheader()
        wr.writerows(zeilen)


if __name__ == '__main__':
    main(sys.argv[1:])
