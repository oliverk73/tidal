#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Englische Gattungswoerter in russischen Stationsnamen durch die russische Form ersetzen.

Oliver 15.10.2026: "die englischen Woerter wie Bay, Cape, Island durch die russischen, aber
lateinischen Namen ersetzen (Bukhta, Mys, Ostrov)". Wort-fuer-Wort geht nicht: Bay ist je nach Ort
Bukhta, Guba oder Zaliv, und der Eigenname aendert sich mit ("Cape Chesmenski" -> "Mys Chesmenskiy",
"Solovets Roads" -> "Solovetskiy Reyd"). Deshalb wird nur uebernommen, was GeoNames (BGN-Umschrift,
wie Google Maps) in der Naehe mit passendem Objekttyp und aehnlichem Eigennamen fuehrt. Kein Treffer
-> Name bleibt und wird gelistet. Nur ISO-8859-1-Zeichen.

Usage: venv/bin/python py/russland_namen_russisch.py [--schreiben]
"""
import collections
import difflib
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import active_files                             # noqa: E402
from sicher_schreiben import schreiben                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GN = os.path.join(ROOT, 'tide_tables/catalogues/geonames/umfeld.tsv')
MERIDIAN = re.compile(r'^[+-]?\d{1,2}:\d{2}\b')
# englisches Gattungswort -> passende GeoNames-Codes
TYP = {
    'bay': {'BAY', 'BAYS', 'COVE', 'INLT', 'GULF', 'LGN', 'FJD', 'HBR'}, 'bight': {'BAY', 'COVE', 'BGHT'},
    'gulf': {'GULF', 'BAY'}, 'inlet': {'INLT', 'BAY', 'COVE'}, 'lagoon': {'LGN', 'BAY'}, 'harbour': {'HBR', 'BAY', 'PRT'},
    'harbor': {'HBR', 'BAY', 'PRT'}, 'cape': {'CAPE', 'PT'}, 'point': {'CAPE', 'PT'}, 'head': {'CAPE', 'PT'},
    'island': {'ISL'}, 'islet': {'ISL', 'RK'}, 'islands': {'ISLS'}, 'strait': {'STRT', 'CHN'},
    'spit': {'SPIT', 'PT', 'CAPE'}, 'peninsula': {'PEN'}, 'bank': {'BNK', 'SHOL', 'BNKR'},
    'road': {'RD', 'ANCH'}, 'roads': {'RD', 'ANCH'}, 'anchorage': {'ANCH', 'RD'}, 'sand': {'BAR', 'SHOL', 'BNK', 'SAND'},
}
RU_GATTUNG = r'\b(mys|ostrov|ostrova|ostrovok|bukhta|guba|zaliv|proliv|reka|kosa|poluostrov|banka|reyd|laguna|' \
             r'gavan|o|zal|b)\b'      # Bol'shoy/Malyy/Yuzhnyy zaehlen mit (Kildin ist nicht Malyy Kil'din)


def norm(s):
    s = s.lower().replace("'", '').replace('ʹ', '')
    s = re.sub(r'(iy|yy|yi|ii|y|i|aya|oye|iye|ye|ie|ski|skiy|skaya|sky|nyy|nyi|ny|ni)\b', '', s)
    return re.sub(r'[^a-z]', '', s.replace('kh', 'h').replace('yu', 'u').replace('ya', 'a').replace('ye', 'e'))


def latin1(s):
    s = s.replace('ë', 'e').replace('Ë', 'E')          # Chërnyy -> Chernyy, wie Google Maps
    s = s.replace('ʹ', "'").replace('ʼ', "'").replace('’', "'")
    try:
        s.encode('iso-8859-1')
        return s
    except UnicodeEncodeError:
        return None


def geonames():
    out = collections.defaultdict(list)
    for z in open(GN, encoding='utf-8'):
        p = z.rstrip('\n').split('\t')
        if len(p) < 9 or p[8] != 'RU':
            continue
        lat, lon = float(p[4]), float(p[5])
        out[(round(lat), round(lon))].append((p[1], p[2], lat, lon, p[7]))
    return out


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0])))


WEIT = {'island', 'islands', 'peninsula', 'gulf', 'strait', 'lagoon'}     # GeoNames-Punkt in der Mitte
FLUSS = re.compile(r'^(.*?) River( (entrance|mouth))?$')


def vorschlag(G, basis, lat, lon, radius=None, mind=0.8):
    f = FLUSS.match(basis)
    if f:
        # "Kovda River entrance" -> "Reka Kovda" wie in NP202, wenn GeoNames den Fluss in der Naehe kennt
        ne, best = norm(f.group(1)), None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for name, asc, la, lo, code in G.get((round(lat) + dy, round(lon) + dx), ()):
                    d = km((lat, lon), (la, lo))
                    if code != 'STM' or d > (radius or 40):
                        continue
                    kern = re.sub(r'^Reka ', '', latin1(name) or asc)
                    sm = difflib.SequenceMatcher(None, ne, norm(kern)).ratio()
                    if sm >= 0.85 and (best is None or (sm, -d) > (best[0], -best[2])):
                        best = (sm, 'Reka ' + kern, d, code)
        return (best, '') if best else (None, 'kein GeoNames-Treffer')
    w = basis.split()
    gatt = [x for x in w if x.lower().rstrip('.') in TYP]
    if not gatt:
        return None, 'kein englisches Gattungswort'
    g = gatt[-1].lower()
    eigen = ' '.join(x for x in w if x.lower() != g)
    if not eigen:
        return None, 'nur Gattungswort'
    ne = norm(eigen)
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for name, asc, la, lo, code in G.get((round(lat) + dy, round(lon) + dx), ()):
                if code not in TYP[g]:
                    continue
                d = km((lat, lon), (la, lo))
                if d > (radius or (60 if g in WEIT else 20)):
                    continue
                ng = norm(re.sub(RU_GATTUNG, ' ', name.lower()))
                s = difflib.SequenceMatcher(None, ne, ng).ratio()
                if s >= mind and (best is None or (s, -d) > (best[0], -best[2])):
                    best = (s, latin1(name) or asc, d, code)
    if not best:
        return None, 'kein GeoNames-Treffer'
    return best, ''


def main(argv):
    G = geonames()
    plan, ohne = {}, []
    saetze = []
    for f in active_files():
        L = open(os.path.join(ROOT, f), encoding='iso-8859-1').read().split('\n')
        for i, l in enumerate(L[:-1]):
            if l.endswith(', Russia') and not l.startswith('#') and MERIDIAN.match(L[i + 1]):
                j, lat, lon = i - 1, None, None
                while L[j].startswith('#') and L[j] != '#':
                    if L[j].startswith('# !latitude:'):
                        lat = float(L[j].split(':')[1])
                    elif L[j].startswith('# !longitude:'):
                        lon = float(L[j].split(':')[1])
                    j -= 1
                saetze.append((f, i, l, lat, lon))
    for f, i, l, lat, lon in saetze:
        teile = l.split(', ')
        m = re.match(r'^(.*?)( \(.*\))?$', teile[0])
        basis, klammer = m.group(1), m.group(2) or ''
        b, grund = vorschlag(G, basis, lat, lon)
        # Klammerkontext ("Kotel'nyy Island", "Kresta Bay") ebenso, Radius weiter
        if klammer:
            kt = []
            for t in klammer[2:-1].split(', '):
                kb, _ = vorschlag(G, t, lat, lon, radius=80, mind=0.9)
                kt.append(kb[1] if kb else t)
            klammer = ' (%s)' % ', '.join(kt)
        if b or klammer != (m.group(2) or ''):
            neu = ', '.join([(b[1] if b else basis) + klammer] + teile[1:])
            if neu != l:
                plan[(f, i)] = (l, neu, b or (0, '', 0, 'Klammer'))
        elif grund != 'kein englisches Gattungswort':
            ohne.append((l, grund, os.path.basename(f)))
    for (f, i), (a, n, b) in sorted(plan.items(), key=lambda x: x[1][0]):
        print('%-55s -> %-55s %.2f %4.1f km %s' % (a[:55], n[:55], b[0], b[2], b[3]))
    print('\nOHNE TREFFER:')
    for a, g, f in sorted(ohne):
        print('  %-60s %s [%s]' % (a, g, f))
    print('\n%d umbenennen, %d ohne Treffer, %d Saetze gesamt' % (len(plan), len(ohne), len(saetze)))
    if '--schreiben' in argv:
        for f in sorted({k[0] for k in plan}):
            L = open(os.path.join(ROOT, f), encoding='iso-8859-1').read().split('\n')
            for (ff, i), (a, n, b) in plan.items():
                if ff == f:
                    assert L[i] == a
                    L[i] = n
            schreiben(os.path.join(ROOT, f), '\n'.join(L))


if __name__ == '__main__':
    main(sys.argv[1:])
