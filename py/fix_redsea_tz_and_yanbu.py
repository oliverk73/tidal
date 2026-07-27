#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zwei Korrekturen in harmonics_att_np203_secondary.txt (2026-07-27).

1. ANZEIGE-ZEITZONEN am Roten Meer / Arabischen Golf.
   Der NP203-Part-II-Transfer erbt Meridian UND Anzeige-Zeitzone vom Bezugshafen.
   Der Meridian muss geerbt werden -- die Phasen stehen in dessen Zone --, die
   Anzeige-Zeitzone nicht. Dadurch zeigen z.B. saudische Stationen ägyptische Zeit
   (im Winter eine Stunde zu früh). Geändert wird ausschliesslich der :TZ-Teil,
   der Meridian bleibt stehen; die Rechenwerte sind nicht betroffen.

2. MADINAT YANBU AS SINAIYAH (ATT 4131a).
   Die visuelle Transkription page_228.json hat die Höhendifferenzen der falschen
   Zeile übernommen: -1.2/-1.0/-/- mit ML 0.5. Der Scan (S.228, 400 dpi, am
   2026-07-27 nachgelesen) zeigt -1.2/-0.9/-0.3/0.0 mit ML 0.56 und -0440/-0440.
   Konstituenten und Z0 werden mit derselben Transfer-Engine neu gerechnet;
   Name und die von Oliver korrigierten Koordinaten bleiben unangetastet.

Aufruf: python3 py/fix_redsea_tz_and_yanbu.py            # dry-run
        python3 py/fix_redsea_tz_and_yanbu.py --write
"""
from __future__ import annotations
import importlib.util
import os
import re
import sys

TXT = '/home/oliver/weather/harmonics/att/harmonics_att_np203_secondary.txt'

# Land -> tzdata-Name. Nur die Länder, die am Roten Meer / Arabischen Golf
# tatsächlich betroffen sind; bewusst keine Weltkarte.
TZ = {
    'Saudi Arabia': 'Asia/Riyadh',
    'Eritrea':      'Africa/Asmara',
    'Sudan':        'Africa/Khartoum',
    'Yemen':        'Asia/Aden',
    'Israel':       'Asia/Jerusalem',
    'Jordan':       'Asia/Amman',
    'Egypt':        'Africa/Cairo',
}
MER = re.compile(r'^([+-]\d\d:\d\d) :(\S+)\s*$')

# ATT 4131a, aus dem Scan nachgelesen
YANBU = dict(att='4131a', name='Madinat Yanbu as Sinaiyah', region='Saudi Arabia',
             std='Suez', t=(-440, -440), h=(-1.2, -0.9, -0.3, 0.0), ml=0.56)


def load_engine():
    os.environ['HOME'] = '/home/oliver/weather'      # ~/harmonics == weather/harmonics
    spec = importlib.util.spec_from_file_location(
        'B', '/home/oliver/weather/py/build_np203_secondary.py')
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    return B


def block_bounds(L, i):
    """Grenzen des Stationsblocks, dessen Namenszeile bei i steht."""
    start = max(k for k in range(i) if L[k] == '# BEGIN HOT COMMENTS')
    end = i + 1
    while end < len(L) and not L[end].startswith('#'):
        end += 1
    return start, end


def fix_timezones(L):
    changed = []
    for i, l in enumerate(L):
        m = MER.match(l)
        if not m:
            continue
        name = L[i - 1].strip()
        land = name.rsplit(', ', 1)[-1] if ', ' in name else ''
        soll = TZ.get(land)
        if not soll or m.group(2) == soll:
            continue
        lat = float(L[i - 2].split(': ')[1]) if 'latitude' in L[i - 2] else None
        if lat is None or not 12 < lat < 32:      # Rotes Meer / Arabischer Golf
            continue
        L[i] = f'{m.group(1)} :{soll}'
        changed.append((name, m.group(2), soll))
    return changed


def rebuild_yanbu(L, B):
    i = next(k for k, l in enumerate(L) if l.startswith('Madinat Yanbu'))
    start, end = block_bounds(L, i)
    alt_name, alt_mer = L[i], L[i + 1]
    lat = float(next(x for x in L[start:i] if x.startswith('# !latitude:')).split(': ')[1])
    lon = float(next(x for x in L[start:i] if x.startswith('# !longitude:')).split(': ')[1])

    s = dict(YANBU, lat=lat, lon=lon)
    refname, rr = B.find(s['std'])
    tr = B.transfer(s, rr)
    tr['refname'] = refname
    blk, _name, conf = B.block(s, tr)

    # Koordinaten und Namenszeile aus dem Bestand uebernehmen -- die hat Oliver
    # korrigiert, die Engine wuerde die ATT-Rohwerte und den Namen ohne "(Yanbu)"
    # schreiben. Die Anzeige-Zeitzone raeumt anschliessend fix_timezones auf.
    for k, x in enumerate(blk):
        if x.startswith('# !latitude:'):
            blk[k] = f'# !latitude: {lat:.4f}'
        elif x.startswith('# !longitude:'):
            blk[k] = f'# !longitude: {lon:.4f}'
        elif x.startswith('# date_imported:'):
            blk[k] = '# date_imported: 20260727'
        elif x.startswith('# note:'):
            blk[k] = x.replace('Zeit-/Hoehendiff. aus ATT Vol.3 (2015).',
                               'Zeit-/Hoehendiff. aus ATT Vol.3 (2015), '
                               'Scan S.228 am 20260727 nachgelesen.')
        elif x == _name:
            blk[k] = alt_name
    assert alt_mer.startswith(blk[blk.index(alt_name) + 1][:6]), 'Meridian weicht ab'

    # ATT gibt Spring- und Nipphub hier gleich gross an (beide 0.3 m bei 0.1-m-
    # Aufloesung) -- S2 ist damit nicht aufloesbar und faellt auf 0. FES2022b
    # sieht an derselben Stelle S2/M2 = 0.29. Und die *-Anmerkung S.238 warnt,
    # dass der Windstau groesser ist als der gesamte astronomische Hub.
    j = blk.index('# confidence: %d' % conf)
    blk[j:j] = [
        '# note: ATT-Aufloesung 0.1 m: Spring- = Nipphub -> S2 nicht bestimmbar (=0).',
        '# note: ATT S.238 (*): NW-Sturm senkt den Pegel ~1 Tag spaeter um ca. 0.6 m,',
        '# note: danach deutlicher Anstieg. Meteo-Anteil > astronomischer Hub (0.3 m).',
    ]
    return start, end, blk, tr, conf


def main():
    write = '--write' in sys.argv
    L = open(TXT, encoding='iso-8859-1').read().split('\n')
    B = load_engine()

    start, end, blk, tr, conf = rebuild_yanbu(L, B)
    alt = {m.group(1): (float(m.group(2)), float(m.group(3)))
           for m in (re.match(r'^([A-Z0-9]+)\s+([\d.]+)\s+([\d.]+)$', x) for x in L[start:end])
           if m}
    neu = {m.group(1): (float(m.group(2)), float(m.group(3)))
           for m in (re.match(r'^([A-Z0-9]+)\s+([\d.]+)\s+([\d.]+)$', x) for x in blk) if m}
    print('Madinat Yanbu as Sinaiyah (ATT 4131a) neu gerechnet:')
    print(f"  fS={tr['fS']:.2f} fN={tr['fN']:.2f} dt={tr['dt']*60:+.0f}min  confidence {conf}")
    for c in ('M2', 'S2', 'N2', 'K1', 'O1'):
        if c in alt and c in neu:
            print(f"  {c:3s} {alt[c][0]:.4f}@{alt[c][1]:6.2f}  ->  {neu[c][0]:.4f}@{neu[c][1]:6.2f}")
    zl = re.compile(r'^[\d.]+ meters$')
    z_alt = next(x for x in L[start:end] if zl.match(x))
    z_neu = next(x for x in blk if zl.match(x))
    print(f"  Z0  {z_alt}  ->  {z_neu}")

    L[start:end] = blk
    ch = fix_timezones(L)
    print(f'\n{len(ch)} Anzeige-Zeitzonen korrigiert:')
    for n, a, b in ch:
        print(f'  {n:48s} :{a:14s} -> :{b}')

    if write:
        open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(L))
        n = sum(1 for l in L if l.startswith('# !latitude:'))
        print(f'\nGeschrieben. Stationen: {n}')
    else:
        print('\n(Dry-run. --write zum Schreiben.)')


if __name__ == '__main__':
    main()
