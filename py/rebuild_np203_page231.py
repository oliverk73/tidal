#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut alle Stationen der ATT-NP203-Seite 231 (VAE, Katar, Bahrain) aus dem
Scan neu auf.

Hintergrund: page_231.json stammt aus einer visuellen Transkription, die auf
dieser Seite in 29 von 41 Zeilen falsch ist -- Koordinaten, Hoehendifferenzen
und Mittelwasser. Drei Zeilen fehlten ganz. Die Tabelle BOOK unten ist am
20260728 direkt aus dem Scan gelesen
(tide_tables/att/np203_2015_secondary_ports_p222-238.pdf, Seite 231).

Namens- und Laenderzeilen aus dem Bestand bleiben erhalten -- die hat Oliver
kuratiert. Neu gerechnet werden Position, Z0 und die Konstituenten.

Aufruf: python3 py/rebuild_np203_page231.py            # dry-run
        python3 py/rebuild_np203_page231.py --write
"""
from __future__ import annotations
import importlib.util
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'
JSON = '/home/oliver/weather/harmonics/help/np203_part2_json/page_231.json'
HARM = '/home/oliver/weather/harmonics'
D = None                      # Dreieck im Buch = keine Angabe

# att, Name laut Buch, lat_d, lat_m, lon_d, lon_m, tHW, tLW, (MHHW,MLHW,MHLW,MLLW), ML
BOOK = [
    ('4223a', "Ghasha Light Buoy",          24, 26, 52, 34, D, D, (-0.2, D, D, +0.2), 1.00),
    ('4224',  "Jazirat Arzanah",            24, 47, 52, 34, D, D, (-0.3, D, D, +0.3), 1.05),
    ('4228',  "Jazirat Shuwayhat",          24,  6, 52, 27, D, D, (-0.3, D, D, -0.1), 1.07),
    ('4229',  "Jazirat Dalma",              24, 28, 52, 19, D, D, (-0.2, D, D,  0.0), 1.18),
    ('4230',  "Jazair al Yasat",            24, 10, 52,  0, D, D, (-0.2, D, D, -0.2), 1.00),
    ('4231',  "Umm al Hatab",               24, 13, 51, 52, D, D, (0.0, -0.1, +0.1, -0.1), 1.20),
    ('4232',  "Jazair Ghaghah",             24, 24, 51, 33, 138, 137, (+0.2, +0.1, +0.2, 0.0), 1.35),
    ('4233',  "Jazirat Shara'iwah",         25,  2, 52, 14, D, D, (-0.4, D, D, -0.2), 1.01),
    ('4234',  "Jazirat Halul",              25, 40, 52, 25, -76, -77, (-0.6, -0.2, 0.0, -0.2), 0.95),
    ('4235',  "Ras Abu Qumayyis",           24, 34, 51, 30, 63, 60, (+0.2, 0.0, 0.0, +0.1), 1.30),
    ('4235a', "Khawr al Udayd",             24, 42, 51, 27, 60, 50, (+0.1, 0.0, +0.1, 0.0), 1.30),
    ('4237',  "Mesaieed (Musay'id)",        24, 54, 51, 33, 50, 40, (0.0, 0.0, +0.2, 0.0), 1.28),
    ('4238',  "Al Wakrah",                  25, 10, 51, 37, -3, 15, (-0.4, -0.3, -0.2, -0.2), 0.90),
    ('4239a', "Al Jazirah al Aliyah",       25, 24, 51, 34, D, D, (-0.4, -0.3, -0.3, -0.3), 0.90),
    ('4240',  "Sumaysimah",                 25, 34, 51, 30, D, D, (-0.4, -0.2, -0.4, -0.3), 0.90),
    ('4241',  "Khawr Shaqiq",               25, 41, 51, 31, D, D, (-0.4, -0.3, -0.3, -0.3), 0.90),
    ('4243',  "Jabal al Fuwayrit",          26,  3, 51, 22, D, D, (-0.4, 0.0, -0.5, -0.2), 0.90),
    ('4244',  "Ar Ru'ays",                  26, 10, 51, 11, -11, -6, (-0.7, -0.5, -0.3, -0.3), 1.20),
    ('4245',  "Fasht al Dibal",             26, 17, 50, 59, -12, -9, (-0.4, -0.3, -0.1, -0.1), 1.26),
    ('4246',  "Ras ' Ushayriq",             25, 59, 51,  0, 22, 22, (-1.1, -0.8, -0.5, -0.3), 0.82),
    ('4247',  "Nagiyah",                    25, 41, 50, 54, D, D, (-1.8, -1.4, -0.7, -0.4), 0.30),
    ('4247b', "Zikrit",                     25, 28, 50, 51, D, D, (-1.9, -1.4, -0.7, -0.5), 0.34),
    ('4247c', "Dukhan",                     25, 26, 50, 45, D, D, (-1.8, -1.4, -0.7, -0.4), 0.30),
    ('4247d', "Umm Bab",                    25, 13, 50, 46, D, D, (-1.7, -1.3, -0.8, -0.5), 0.30),
    ('4247e', "Al Khraij",                  25,  0, 50, 48, D, D, (-1.6, -1.3, -0.6, -0.4), 0.40),
    ('4247f', "Ghar al Buraid",             24, 48, 50, 52, D, D, (-1.7, -1.3, -0.8, -0.4), 0.40),
    ('4248',  "Hawar Island (North East)",  25, 44, 50, 48, D, D, (-1.8, -1.5, -0.8, -0.4), 0.34),
    ('4249',  "Az Zallaq",                  26,  3, 50, 29, D, D, (-2.1, -1.7, -0.9, -0.6), 0.15),
    ('4249a', "Mutarid",                    25, 47, 50, 43, D, D, (-2.0, -1.5, -0.8, -0.4), 0.30),
    ('4250',  "Ras al Jamal",               25, 51, 50, 37, D, D, (-1.9, -1.4, -0.7, -0.4), 0.36),
    ('4250a', "Bahrain Yacht Club (Sitrah)", 26, 7, 50, 38, D, D, (-1.6, -1.3, -0.6, -0.4), 0.50),
    ('4250b', "Umm Jalid",                  26,  2, 50, 43, D, D, (-1.8, -1.4, -0.7, -0.4), 0.40),
    ('4250c', "Umais",                      25, 59, 50, 53, D, D, (-1.5, -1.2, -0.7, -0.5), 0.50),
    ('4250d', "Ne Fasht al Adhm",           26,  5, 50, 53, 5, 3, (-0.3, -0.2, -0.1, -0.1), 1.34),
    ('4250e', "Bahrain Approach Buoy",      26, 22, 50, 47, -17, -13, (-0.3, -0.2, -0.2, -0.2), 1.25),
    ('4250f', "Khalifa Bin Salman Port",    26, 11, 50, 43, -1, -6, (-0.1, 0.0, 0.0, 0.0), 1.45),
    ('4251',  "Sitrah (Bapco Causeway)",    26, 10, 50, 40, 5, 5, (-0.1, 0.0, 0.0, 0.0), 1.44),
    ('4253',  "Mina al Manama",             26, 14, 50, 34, -6, 8, (0.0, 0.0, +0.1, +0.2), 1.55),
    ('4253a', "Khawr Fasht",                26, 20, 50, 26, 6, 15, (-0.2, -0.1, 0.0, 0.0), 1.39),
    ('4253b', "Al Budayyi",                 26, 13, 50, 26, 25, 35, (-0.9, -0.7, -0.3, -0.1), 1.00),
    ('4253c', "Al Jasser Island",           26, 11, 50, 20, 25, 20, (-1.3, -1.1, -0.5, -0.3), 0.63),
]
# Bezugshafen je att -- aus der Blockgliederung der Seite
STD = {}
for a in ('4223a', '4224'):
    STD[a] = 'Jebel Ali'
for a in ('4228', '4229', '4230', '4231', '4232', '4233', '4234', '4235', '4235a', '4237', '4238'):
    STD[a] = 'Mesaieed'
for a in ('4239a', '4240', '4241'):
    STD[a] = 'Doha'
STD['4243'] = 'Ras Laffan'
for a, *_ in BOOK:
    STD.setdefault(a, 'Mina Salman')
REGION = {'4223a': 'United Arab Emirates', '4224': 'United Arab Emirates',
          '4228': 'United Arab Emirates', '4229': 'United Arab Emirates',
          '4230': 'United Arab Emirates', '4231': 'United Arab Emirates',
          '4232': 'United Arab Emirates'}
NOTE = '# note: Seite 231 am 20260728 aus dem Scan neu gelesen (Position, Differenzen, ML).'


def load_engine():
    os.environ['HOME'] = '/home/oliver/weather'
    spec = importlib.util.spec_from_file_location(
        'B', '/home/oliver/weather/py/build_np203_secondary.py')
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    return B


def index(L):
    """att -> (start, name_idx, end, name, country)"""
    out = {}
    att = None
    for i, l in enumerate(L):
        if l.startswith('# att_number:'):
            att = l.split(': ')[1].strip()
        elif re.match(r'^[+-]\d\d:\d\d :', l) and att:
            s = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
            e = i
            while e < len(L) and not L[e].startswith('#'):
                e += 1
            country = next((x.split(': ')[1] for x in L[s:i] if x.startswith('# country:')), '')
            out[att] = (s, i - 1, e, L[i - 1].strip(), country)
            att = None
    return out


def km(a, b, c, d):
    return math.hypot((d - b) * math.cos(math.radians(a)) * 111.32, (c - a) * 110.57)


def akey(a):
    m = re.match(r'^(\d+)([a-z]*)$', a)
    return (int(m.group(1)), m.group(2))


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    B = load_engine()
    idx = index(L)

    plan = []
    for att, bname, lad, lam, lod, lom, tH, tL, h, ml in BOOK:
        lat, lon = lad + lam / 60, lod + lom / 60
        s = dict(att=att, name=bname, region=REGION.get(att, 'Qatar' if att < '4248' else 'Bahrain'),
                 std=STD[att], lat=lat, lon=lon, t=(tH, tL), h=h, ml=ml)
        refname, rr = B.find(s['std'])
        if rr is None:
            print(f'{att}: Bezugshafen {s["std"]} nicht gefunden'); continue
        tr = B.transfer(s, rr)
        if tr is None:
            print(f'{att} {bname}: keine Differenzen -> uebersprungen'); continue
        tr['refname'] = refname
        blk, gen_name, conf = B.block(s, tr)
        old = idx.get(att)
        if old:                                   # Name und Land aus dem Bestand
            _, _, _, name, country = old
            for k, x in enumerate(blk):
                if x == gen_name:
                    blk[k] = name
                elif x.startswith('# country:') and country:
                    blk[k] = f'# country: {country}'
            d = km(lat, lon, float(next(x for x in L[old[0]:old[1]] if x.startswith('# !latitude:')).split(': ')[1]),
                   float(next(x for x in L[old[0]:old[1]] if x.startswith('# !longitude:')).split(': ')[1]))
        else:
            name, d = gen_name, None
        j = blk.index('# date_imported: 20260618')
        blk[j] = '# date_imported: 20260728'
        blk[j:j] = [NOTE]
        plan.append((att, name, blk, tr, conf, d, old is None, bname))

    print(f'{"att":6s} {"Station":34s} {"fS":>5s} {"fN":>5s} {"dt":>6s} {"conf":>4s} {"Verschiebung":>13s}')
    for att, name, blk, tr, conf, d, neu, bname in sorted(plan, key=lambda x: akey(x[0])):
        v = 'NEU' if neu else (f'{d:.1f} km' if d and d > 0.3 else '-')
        print(f'{att:6s} {name[:34]:34s} {tr["fS"]:5.2f} {tr["fN"]:5.2f} {tr["dt"]*60:+6.0f} {conf:4d} {v:>13s}')

    if not write:
        print('\n(Dry-run. --write zum Schreiben.)')
        return

    shutil.copy(TXT, f'{HARM}/backup/harmonics_att_np203_secondary_pre_p231_{datetime.now():%Y%m%d}.txt')
    # bestehende Bloecke ersetzen (von hinten, damit die Indizes halten)
    for att, name, blk, *_ in sorted(plan, key=lambda x: -idx[x[0]][0] if x[0] in idx else 1):
        if att in idx:
            s, _, e, _, _ = index(L)[att]
            L[s:e] = blk
    # fehlende einfuegen: vor dem naechstgroesseren att auf dieser Seite
    cur = index(L)
    for att, name, blk, *_ in sorted(plan, key=lambda x: akey(x[0])):
        if att in cur:
            continue
        later = [a for a in cur if akey(a) > akey(att) and a in STD]
        anchor = min(later, key=akey) if later else None
        pos = cur[anchor][0] if anchor else len(L)
        L[pos:pos] = blk
        cur = index(L)
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
    os.chmod(TXT, 0o600)

    js = {e['att']: e for e in json.load(open(JSON, encoding='utf-8'))}
    for att, bname, lad, lam, lod, lom, tH, tL, h, ml in BOOK:
        e = js.setdefault(att, {'att': att, 'name': bname, 'region': '', 'std': STD[att], 'flags': ''})
        e.update(name=bname, lat=round(lad + lam / 60, 4), lon=round(lod + lom / 60, 4),
                 tHW=tH, tLW=tL, dMHWS=h[0], dMHWN=h[1], dMLWN=h[2], dMLWS=h[3], ml=ml,
                 source='scan 20260728')
    json.dump([js[a] for a in sorted(js, key=akey)], open(JSON, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'\nGeschrieben. Stationen: {sum(1 for l in L if l.startswith("# !latitude:"))}')


if __name__ == '__main__':
    main()
